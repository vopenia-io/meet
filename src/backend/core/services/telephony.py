"""Telephony service for managing SIP dispatch rules for room access."""

from logging import getLogger

from asgiref.sync import async_to_sync
from livekit.api import TwirpError
from django.conf import settings
from livekit.protocol.agent_dispatch import RoomAgentDispatch
from livekit.protocol.room import RoomConfiguration
from livekit.protocol.sip import (
    CreateSIPDispatchRuleRequest,
    DeleteSIPDispatchRuleRequest,
    ListSIPDispatchRuleRequest,
    SIPDispatchRule,
    SIPDispatchRuleCallee,
    SIPDispatchRuleDirect,
)

from core import utils

logger = getLogger(__name__)


class TelephonyException(Exception):
    """Exception raised when telephony operations fail."""


class TelephonyService:
    """Service for managing participant access through the telephony system (SIP)."""

    def _rule_name(self, room_id):
        """Generate the rule name for a room based on its ID."""
        return f"SIP_{str(room_id)}"

    @async_to_sync
    async def create_dispatch_rule(self, room):
        """Create a SIP inbound dispatch rule for direct room routing.

        Configures telephony to route incoming SIP calls directly to the specified room
        using the room's ID and PIN code for authentication.
        """

        direct_rule = SIPDispatchRule(
            dispatch_rule_direct=SIPDispatchRuleDirect(
                room_name=str(room.pk), pin=str(room.pin_code)
            )
        )

        request = CreateSIPDispatchRuleRequest(
            rule=direct_rule, name=self._rule_name(room.pk)
        )

        lkapi = utils.create_livekit_client()

        try:
            await lkapi.sip.create_sip_dispatch_rule(create=request)
        except TwirpError as e:
            logger.exception(
                "Unexpected error creating dispatch rule for room %s", room.id
            )
            raise TelephonyException("Could not create dispatch rule") from e

        finally:
            await lkapi.aclose()

    async def _list_dispatch_rules_ids(self, room_id):
        """List SIP dispatch rule IDs for a specific room.

        Fetches all existing SIP dispatch rules and filters them by room name
        since LiveKit API doesn't support server-side filtering by 'room_name'.
        This approach is acceptable for moderate scale but may need refactoring
        for high-volume scenarios.

        Note:
            Feature request for server-side filtering: livekit/sip#405
        """

        lkapi = utils.create_livekit_client()

        try:
            existing_rules = await lkapi.sip.list_sip_dispatch_rule(
                list=ListSIPDispatchRuleRequest()
            )
        except TwirpError as e:
            logger.exception("Failed to list dispatch rules for room %s", room_id)
            raise TelephonyException("Could not list dispatch rules") from e
        finally:
            await lkapi.aclose()

        if not existing_rules or not existing_rules.items:
            return []

        rule_name = self._rule_name(room_id)

        return [
            existing_rule.sip_dispatch_rule_id
            for existing_rule in existing_rules.items
            if existing_rule.name == rule_name
        ]

    @async_to_sync
    async def delete_dispatch_rule(self, room_id):
        """Delete all SIP inbound dispatch rules associated with a specific room."""

        rules_ids = await self._list_dispatch_rules_ids(room_id)

        if not rules_ids:
            logger.info("No dispatch rules found for room %s", room_id)
            return False

        if len(rules_ids) > 1:
            logger.error("Multiple dispatch rules found for room %s", room_id)

        lkapi = utils.create_livekit_client()
        try:
            for rule_id in rules_ids:
                await lkapi.sip.delete_sip_dispatch_rule(
                    delete=DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
                )

            return True

        except TwirpError as e:
            logger.exception("Failed to delete dispatch rules for room %s", room_id)
            raise TelephonyException("Could not delete dispatch rules") from e

        finally:
            await lkapi.aclose()

    def _lobby_rule_name(self, phone_number: str) -> str:
        """Generate the rule name for a lobby phone number."""
        # Remove + and any non-alphanumeric chars for the rule name
        clean_number = phone_number.lstrip("+").replace("-", "")
        return f"SIP_lobby_{clean_number}"

    @async_to_sync
    async def create_lobby_dispatch_rules(self):
        """Create SIP dispatch rules for lobby routing.

        This creates dispatch rules for phone numbers designated for the lobby pattern.
        Calls to these numbers are routed to transient lobby rooms with a unique suffix.
        """
        if not settings.PHONE_SYSTEM_ENABLED:
            logger.info("Phone system not enabled, skipping lobby dispatch rule creation")
            return

        lobby_numbers = settings.PHONE_SYSTEM_LOBBY_PHONE_NUMBERS
        if not lobby_numbers:
            logger.warning("No lobby phone numbers configured")
            return

        lkapi = utils.create_livekit_client()

        try:
            for phone_number in lobby_numbers:
                # Create a callee-based dispatch rule that routes to unique lobby rooms
                # Using SIPDispatchRuleCallee with randomize=True creates unique rooms
                # per call without requiring a PIN (unlike SIPDispatchRuleIndividual)
                callee_rule = SIPDispatchRule(
                    dispatch_rule_callee=SIPDispatchRuleCallee(
                        room_prefix=settings.PHONE_SYSTEM_LOBBY_ROOM_PREFIX,
                        pin="",  # No PIN required
                        randomize=True,  # Unique room per call
                    )
                )

                # Configure the room to dispatch the lobby-bot agent
                # The lobby-bot agent joins the room and subscribes to the SIP
                # participant's audio track, which triggers livekit-sip to
                # answer the call (send SIP 200 OK)
                lobby_bot_agent_name = settings.PHONE_SYSTEM_LOBBY_BOT_AGENT_NAME
                room_config = RoomConfiguration(
                    agents=[
                        RoomAgentDispatch(agent_name=lobby_bot_agent_name),
                    ]
                )

                request = CreateSIPDispatchRuleRequest(
                    rule=callee_rule,
                    name=self._lobby_rule_name(phone_number),
                    inbound_numbers=[phone_number],
                    room_config=room_config,
                )

                try:
                    await lkapi.sip.create_sip_dispatch_rule(create=request)
                    logger.info(
                        "Created lobby dispatch rule for %s",
                        phone_number,
                    )
                except TwirpError as e:
                    # Check if rule already exists (don't fail for duplicate)
                    if "already exists" in str(e).lower():
                        logger.info(
                            "Lobby dispatch rule already exists for %s",
                            phone_number,
                        )
                    else:
                        logger.exception(
                            "Failed to create lobby dispatch rule for %s",
                            phone_number,
                        )
                        raise TelephonyException(
                            f"Could not create lobby dispatch rule for {phone_number}"
                        ) from e

        finally:
            await lkapi.aclose()

    @async_to_sync
    async def delete_lobby_dispatch_rules(self):
        """Delete all lobby dispatch rules."""
        if not settings.PHONE_SYSTEM_ENABLED:
            return

        lobby_numbers = settings.PHONE_SYSTEM_LOBBY_PHONE_NUMBERS
        if not lobby_numbers:
            return

        lkapi = utils.create_livekit_client()

        try:
            # List all rules
            existing_rules = await lkapi.sip.list_sip_dispatch_rule(
                list=ListSIPDispatchRuleRequest()
            )

            if not existing_rules or not existing_rules.items:
                return

            # Find lobby rules
            lobby_rule_names = {
                self._lobby_rule_name(num) for num in lobby_numbers
            }

            for rule in existing_rules.items:
                if rule.name in lobby_rule_names:
                    await lkapi.sip.delete_sip_dispatch_rule(
                        delete=DeleteSIPDispatchRuleRequest(
                            sip_dispatch_rule_id=rule.sip_dispatch_rule_id
                        )
                    )
                    logger.info("Deleted lobby dispatch rule: %s", rule.name)

        except TwirpError as e:
            logger.exception("Failed to delete lobby dispatch rules")
            raise TelephonyException("Could not delete lobby dispatch rules") from e

        finally:
            await lkapi.aclose()
