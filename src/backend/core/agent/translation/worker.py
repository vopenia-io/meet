import asyncio
import json
from celery.utils.log import get_logger
from typing import AsyncIterable
import uuid
from livekit.agents import WorkerOptions, WorkerPermissions, cli, worker
import threading, time, signal
from celery import bootsteps
from django.core.cache import cache
from django.conf import settings
from core import utils
from livekit.agents import JobContext
from livekit import rtc
from livekit.plugins import gladia
from core.services.translation import TranslationMeta
from livekit.agents.stt import SpeechEventType, SpeechEvent
from core.agent.agent import AbstractAgent, AgentInfo

from .agent import entrypoint

logger = get_logger(__name__)


class TranslationAgent(AbstractAgent):
    @staticmethod
    def info():
        return AgentInfo(
            name=settings.TRANSLATION_AGENT_NAME, enabled=settings.TRANSLATION_ENABLED
        )

    @property
    def options(self) -> WorkerOptions:
        return WorkerOptions(
            agent_name=settings.TRANSLATION_AGENT_NAME,
            ws_url=settings.LIVEKIT_CONFIGURATION["url"],
            api_key=settings.LIVEKIT_CONFIGURATION["api_key"],
            api_secret=settings.LIVEKIT_CONFIGURATION["api_secret"],
            permissions=WorkerPermissions(
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                # when set to true, the agent won't be visible to others in the room.
                # when hidden, it will also not be able to publish tracks to the room as it won't be visible.
                hidden=True,
            ),
            entrypoint_fnc=entrypoint,
        )
