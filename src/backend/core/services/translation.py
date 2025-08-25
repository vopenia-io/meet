"""Translation service"""

import asyncio
import json
from logging import getLogger

from asgiref.sync import async_to_sync
from livekit.api import TwirpError
from livekit.protocol.sip import (
    CreateSIPDispatchRuleRequest,
    DeleteSIPDispatchRuleRequest,
    ListSIPDispatchRuleRequest,
    SIPDispatchRule,
    SIPDispatchRuleDirect,
)
from livekit.api import (
    CreateAgentDispatchRequest,
    AgentDispatch,
    LiveKitAPI,
)
from dataclasses import dataclass, asdict, field

from core import utils
from django.conf import settings

logger = getLogger(__name__)

class TranslationException(Exception):
    """Exception raised when translation operations fail."""


@dataclass
class TranslationMeta:
    lang: set[str]

    def to_dict(self):
        return {"lang": list(self.lang)}

    @classmethod
    def from_dict(cls, data: dict) -> "TranslationMeta":
        return cls(lang=set(data.get("lang", [])))

@dataclass
class Translation:
    meta: TranslationMeta
    roomID: str
    id: str

    def to_dict(self):
        return {"meta": self.meta.to_dict(), "roomID": self.roomID, "id": self.id}

    @classmethod
    def from_dict(cls, data: dict) -> "Translation":
        return cls(
            meta=TranslationMeta.from_dict(data["meta"]),
            roomID=data["roomID"],
            id=data["id"],
        )


class TranslationService:
    """Service for managing the translation system."""

    async def _stop_agent(
        self, lkapi: LiveKitAPI, room, dispatch: AgentDispatch
    ) -> None:
        """Stop the translation agent for a specific room."""
        await lkapi.agent_dispatch.delete_dispatch(dispatch.id, str(room.id))
        while await lkapi.agent_dispatch.get_dispatch(dispatch.id, str(room.id)) != None:
            await asyncio.sleep(0.1)

    async def _get_translation_agent_dispatch(
        self, lkapi: LiveKitAPI, room
    ) -> AgentDispatch | None:
        """List SIP dispatch rule IDs for a specific room.

        Fetches all existing SIP dispatch rules and filters them by room name
        since LiveKit API doesn't support server-side filtering by 'room_name'.
        This approach is acceptable for moderate scale but may need refactoring
        for high-volume scenarios.

        Note:
            Feature request for server-side filtering: livekit/sip#405
        """

        try:
            agents = await lkapi.agent_dispatch.list_dispatch(str(room.id))
        except TwirpError as e:
            logger.exception("Failed to list dispatch rules for room %s", room.id)
            raise TranslationException("Could not list dispatch") from e

        agents = [
            agent for agent in agents if agent.agent_name == settings.TRANSLATION_AGENT_NAME
        ]

        if not agents or len(agents) == 0:
            return None

        if len(agents) > 1:
            logger.warning("Multiple dispatch agents found for room %s", room.id)

        return agents[0]

    @async_to_sync
    async def start_translation(self, room, meta: TranslationMeta) -> Translation:
        request = CreateAgentDispatchRequest(
            agent_name=settings.TRANSLATION_AGENT_NAME,
            room=str(room.id),
            metadata=json.dumps(meta.to_dict()),
        )

        lkapi = utils.create_livekit_client()

        try:
            agent = await self._get_translation_agent_dispatch(lkapi, room)
            if agent:
                m: TranslationMeta = json.loads(agent.metadata)
                if m and m == meta:
                    logger.info(
                        "Translation agent already running for room %s", room.id
                    )
                    return Translation(meta=m, roomID=str(room.id), id=agent.id)
                else:
                    await self._stop_agent(lkapi, room, agent)
            agent = await lkapi.agent_dispatch.create_dispatch(request)
            return Translation(meta=meta, roomID=str(room.id), id=agent.id)
        except TwirpError as e:
            logger.exception("Unexpected error creating dispatch for room %s", room.id)
            raise TranslationException("Could not create dispatch") from e
        finally:
            await lkapi.aclose()

    @async_to_sync
    async def stop_translation(self, room):
        """
        Delete all SIP inbound dispatch rules associated with a specific room.
        """

        lkapi = utils.create_livekit_client()

        try:
            agent = await self._get_translation_agent_dispatch(lkapi, room)
            if not agent:
                logger.info("No translation agent found for room %s", room.id)
                return False

            await self._stop_agent(lkapi, room, agent)
            logger.info("Translation agent stopped for room %s", room.id)
            return True
        except TwirpError as e:
            logger.exception("Failed to delete dispatch for room %s", room.id)
            raise TranslationException("Could not delete dispatch") from e

        finally:
            await lkapi.aclose()

    @async_to_sync
    async def fetch_translation(self, room) -> Translation | None:
        """Fetch the current translation for a specific room."""
        lkapi = utils.create_livekit_client()

        try:
            agent = await self._get_translation_agent_dispatch(lkapi, room)
            if not agent:
                logger.info("No translation agent found for room %s", room.id)
                return None

            metadata = TranslationMeta.from_dict(json.loads(agent.metadata))
            return Translation(meta=metadata, roomID=str(room.id), id=agent.id)
        except TwirpError as e:
            logger.exception("Failed to fetch dispatch for room %s", room.id)
            raise TranslationException("Could not fetch dispatch") from e
        finally:
            await lkapi.aclose()