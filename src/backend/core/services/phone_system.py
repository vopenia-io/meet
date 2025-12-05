"""Phone system service for managing inbound SIP calls via lobby pattern."""

import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from logging import getLogger
from typing import Optional

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from livekit.api import LiveKitAPI, RoomParticipantIdentity, TwirpError
from livekit.protocol.sip import TransferSIPParticipantRequest

from core import models

logger = getLogger(__name__)


def normalize_phone_number(number: str, default_country_code: str = "+33") -> str:
    """
    Normalize a phone number to E.164 format.

    Handles various formats:
    - 0535005942 -> +33535005942 (French national)
    - +33535005942 -> +33535005942 (already E.164)
    - 33535005942 -> +33535005942 (missing +)
    """
    if not number:
        return number

    # Remove any spaces or dashes
    number = number.replace(" ", "").replace("-", "")

    # Already in E.164 format
    if number.startswith("+"):
        return number

    # French national format (starts with 0)
    if number.startswith("0") and len(number) == 10:
        return default_country_code + number[1:]

    # Number without + but with country code
    if number.startswith("33") and len(number) >= 11:
        return "+" + number

    # Default: add country code
    return default_country_code + number


class PendingCallStatus(Enum):
    """Status of a pending call."""

    RINGING = "ringing"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    TRANSFERRED = "transferred"


@dataclass
class PendingCall:
    """Represents a pending inbound call waiting for user acceptance."""

    call_id: str  # Unique ID for this pending call
    lobby_room_name: str  # LiveKit room name for the lobby
    sip_participant_identity: str  # SIP participant identity in LiveKit
    sip_call_id: str  # SIP call ID from LiveKit attributes
    caller_number: str  # Caller's phone number (E.164)
    callee_number: str  # Called phone number (E.164)
    target_user_id: str  # UUID of target user
    status: str  # PendingCallStatus value
    created_at: float  # Unix timestamp
    meeting_room_id: str  # Pre-created room ID (created on call arrival)
    meeting_room_slug: str  # Room slug for push notification / navigation

    def to_dict(self) -> dict:
        """Convert to dictionary for cache storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PendingCall":
        """Create from dictionary."""
        return cls(**data)


class PhoneSystemError(Exception):
    """Base exception for phone system errors."""


class UserNotFoundError(PhoneSystemError):
    """Target user for phone number not found."""


class CallNotFoundError(PhoneSystemError):
    """Pending call not found."""


class TransferError(PhoneSystemError):
    """Failed to transfer SIP participant."""


def _create_livekit_client() -> LiveKitAPI:
    """Create a LiveKit API client."""
    from core import utils

    return utils.create_livekit_client()


class PhoneSystemService:
    """Service for managing the phone lobby system."""

    CACHE_KEY_PREFIX = "phone_system_call"

    def _get_cache_key(self, call_id: str) -> str:
        """Get cache key for a pending call."""
        return f"{self.CACHE_KEY_PREFIX}_{call_id}"

    def _get_user_calls_key(self, user_id: str) -> str:
        """Get cache key for user's pending calls list."""
        return f"{self.CACHE_KEY_PREFIX}_user_{user_id}"

    def _get_lobby_call_key(self, lobby_room_name: str) -> str:
        """Get cache key for mapping lobby room to call ID."""
        return f"{self.CACHE_KEY_PREFIX}_lobby_{lobby_room_name}"

    def is_lobby_room(self, room_name: str) -> bool:
        """Check if a room name is a lobby room."""
        return room_name.startswith(settings.PHONE_SYSTEM_LOBBY_ROOM_PREFIX)

    def lookup_user_by_callee_number(self, callee_number: str) -> Optional[models.User]:
        """Find user associated with the called phone number.

        Normalizes the phone number to E.164 format before lookup to handle
        various input formats (e.g., 0535005942 -> +33535005942).
        """
        # Normalize the phone number to E.164 format
        normalized_number = normalize_phone_number(callee_number)

        logger.debug(
            "Looking up user by phone number: input=%s, normalized=%s",
            callee_number,
            normalized_number,
        )

        try:
            phone_number = models.PhoneNumber.objects.select_related("user").get(
                phone_number=normalized_number, is_active=True
            )
            return phone_number.user
        except models.PhoneNumber.DoesNotExist:
            logger.debug(
                "No PhoneNumber found for normalized number: %s", normalized_number
            )
            return None

    def create_pending_call(
        self,
        lobby_room_name: str,
        sip_participant_identity: str,
        sip_call_id: str,
        caller_number: str,
        callee_number: str,
        target_user: models.User,
        meeting_room_id: str,
        meeting_room_slug: str,
    ) -> PendingCall:
        """Create a new pending call record."""
        call_id = str(uuid.uuid4())
        pending_call = PendingCall(
            call_id=call_id,
            lobby_room_name=lobby_room_name,
            sip_participant_identity=sip_participant_identity,
            sip_call_id=sip_call_id,
            caller_number=caller_number,
            callee_number=callee_number,
            target_user_id=str(target_user.id),
            status=PendingCallStatus.RINGING.value,
            created_at=time.time(),
            meeting_room_id=meeting_room_id,
            meeting_room_slug=meeting_room_slug,
        )

        timeout = settings.PHONE_SYSTEM_PENDING_CALL_TIMEOUT

        # Store the pending call
        cache.set(
            self._get_cache_key(call_id),
            pending_call.to_dict(),
            timeout=timeout,
        )

        # Index by user for quick lookup
        user_calls_key = self._get_user_calls_key(str(target_user.id))
        user_calls = cache.get(user_calls_key, [])
        user_calls.append(call_id)
        cache.set(user_calls_key, user_calls, timeout=timeout)

        # Index by lobby room for lookup when caller hangs up
        cache.set(
            self._get_lobby_call_key(lobby_room_name),
            call_id,
            timeout=timeout,
        )

        logger.info(
            "Created pending call %s: %s -> %s (user: %s)",
            call_id,
            caller_number,
            callee_number,
            target_user.id,
        )

        return pending_call

    def get_pending_call(self, call_id: str) -> Optional[PendingCall]:
        """Retrieve a pending call by ID."""
        data = cache.get(self._get_cache_key(call_id))
        if not data:
            return None
        return PendingCall.from_dict(data)

    def get_pending_call_by_lobby(self, lobby_room_name: str) -> Optional[PendingCall]:
        """Retrieve a pending call by lobby room name."""
        call_id = cache.get(self._get_lobby_call_key(lobby_room_name))
        if not call_id:
            return None
        return self.get_pending_call(call_id)

    def get_user_pending_calls(self, user_id: str) -> list[PendingCall]:
        """Get all pending calls for a user."""
        user_calls_key = self._get_user_calls_key(user_id)
        call_ids = cache.get(user_calls_key, [])

        calls = []
        for call_id in call_ids:
            call = self.get_pending_call(call_id)
            if call and call.status == PendingCallStatus.RINGING.value:
                calls.append(call)

        return calls

    def update_call_status(
        self, call_id: str, status: PendingCallStatus, **extra_fields
    ) -> Optional[PendingCall]:
        """Update the status of a pending call."""
        call = self.get_pending_call(call_id)
        if not call:
            return None

        call.status = status.value
        for key, value in extra_fields.items():
            if hasattr(call, key):
                setattr(call, key, value)

        cache.set(
            self._get_cache_key(call_id),
            call.to_dict(),
            timeout=settings.PHONE_SYSTEM_PENDING_CALL_TIMEOUT,
        )

        logger.info("Updated call %s status to %s", call_id, status.value)
        return call

    def clear_pending_call(self, call_id: str) -> None:
        """Remove a pending call from cache."""
        call = self.get_pending_call(call_id)
        if call:
            cache.delete(self._get_lobby_call_key(call.lobby_room_name))
        cache.delete(self._get_cache_key(call_id))
        logger.info("Cleared pending call %s", call_id)

    @async_to_sync
    async def signal_call_accepted(self, lobby_room_name: str, call_id: str) -> None:
        """Signal the lobby-bot that the call has been accepted.

        This sets the room metadata to {"status": "accepted"}, which the lobby-bot
        watches for. When it sees this, it publishes its audio track, which triggers
        livekit-sip to answer the call.
        """
        import json

        from livekit.protocol.room import UpdateRoomMetadataRequest

        lkapi = _create_livekit_client()

        try:
            metadata = json.dumps({"status": "accepted", "call_id": call_id})
            await lkapi.room.update_room_metadata(
                UpdateRoomMetadataRequest(room=lobby_room_name, metadata=metadata)
            )
            logger.info(
                "Signaled call acceptance for room %s, call_id=%s",
                lobby_room_name,
                call_id,
            )
        finally:
            await lkapi.aclose()

    @async_to_sync
    async def transfer_to_room(self, call: PendingCall, target_room_name: str) -> bool:
        """Transfer SIP participant from lobby to target room."""
        lkapi = _create_livekit_client()

        try:
            transfer_request = TransferSIPParticipantRequest(
                room_name=call.lobby_room_name,
                participant_identity=call.sip_participant_identity,
                transfer_to=target_room_name,
            )

            await lkapi.sip.transfer_sip_participant(transfer_request)

            logger.info(
                "Transferred SIP participant %s from %s to %s",
                call.sip_participant_identity,
                call.lobby_room_name,
                target_room_name,
            )
            return True

        except TwirpError as e:
            logger.exception(
                "Failed to transfer SIP participant %s from %s to %s: %s",
                call.sip_participant_identity,
                call.lobby_room_name,
                target_room_name,
                e,
            )
            raise TransferError(f"Transfer failed: {e}") from e
        finally:
            await lkapi.aclose()

    @async_to_sync
    async def hangup_participant(
        self, room_name: str, participant_identity: str
    ) -> bool:
        """Remove/hangup a SIP participant."""
        lkapi = _create_livekit_client()

        try:
            await lkapi.room.remove_participant(
                RoomParticipantIdentity(room=room_name, identity=participant_identity)
            )
            logger.info(
                "Hung up participant %s in room %s",
                participant_identity,
                room_name,
            )
            return True
        except TwirpError as e:
            logger.exception(
                "Failed to hangup participant %s in room %s: %s",
                participant_identity,
                room_name,
                e,
            )
            return False
        finally:
            await lkapi.aclose()
