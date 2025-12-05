"""LiveKit Events Service"""

# pylint: disable=no-member

import re
import uuid
from enum import Enum
from logging import getLogger

from django.conf import settings

from livekit import api

from core import models
from core.recording.services.recording_events import (
    RecordingEventsError,
    RecordingEventsService,
)

from .lobby import LobbyService
from .phone_system import PhoneSystemService, PendingCallStatus
from .push_notifications import PushNotificationService
from .telephony import TelephonyException, TelephonyService

logger = getLogger(__name__)


class LiveKitWebhookError(Exception):
    """Base exception for LiveKit webhook processing errors."""

    status_code = 500


class AuthenticationError(LiveKitWebhookError):
    """Authentication failed."""

    status_code = 401


class InvalidPayloadError(LiveKitWebhookError):
    """Invalid webhook payload."""

    status_code = 400


class UnsupportedEventTypeError(LiveKitWebhookError):
    """Unsupported event type."""

    status_code = 422


class ActionFailedError(LiveKitWebhookError):
    """Webhook action fails to process or complete."""

    status_code = 500


class LiveKitWebhookEventType(Enum):
    """LiveKit webhook event types."""

    # Room events
    ROOM_STARTED = "room_started"
    ROOM_FINISHED = "room_finished"

    # Participant events
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"

    # Track events
    TRACK_PUBLISHED = "track_published"
    TRACK_UNPUBLISHED = "track_unpublished"

    # Egress events
    EGRESS_STARTED = "egress_started"
    EGRESS_UPDATED = "egress_updated"
    EGRESS_ENDED = "egress_ended"

    # Ingress events
    INGRESS_STARTED = "ingress_started"
    INGRESS_ENDED = "ingress_ended"


class LiveKitEventsService:
    """Service for processing and handling LiveKit webhook events and notifications."""

    def __init__(self):
        """Initialize with required services."""

        token_verifier = api.TokenVerifier(
            settings.LIVEKIT_CONFIGURATION["api_key"],
            settings.LIVEKIT_CONFIGURATION["api_secret"],
        )
        self.webhook_receiver = api.WebhookReceiver(token_verifier)
        self.lobby_service = LobbyService()
        self.telephony_service = TelephonyService()
        self.recording_events = RecordingEventsService()
        self.phone_system = PhoneSystemService()
        self.push_service = PushNotificationService()

        self._filter_regex = None
        if settings.LIVEKIT_WEBHOOK_EVENTS_FILTER_REGEX:
            try:
                self._filter_regex = re.compile(
                    settings.LIVEKIT_WEBHOOK_EVENTS_FILTER_REGEX
                )
            except re.error:
                logger.exception(
                    "Invalid LIVEKIT_WEBHOOK_EVENTS_FILTER_REGEX. Webhook filtering disabled."
                )

    def receive(self, request):
        """Process webhook and route to appropriate handler."""

        auth_token = request.headers.get("Authorization")
        if not auth_token:
            raise AuthenticationError("Authorization header missing")

        try:
            data = self.webhook_receiver.receive(
                request.body.decode("utf-8"), auth_token
            )
        except Exception as e:
            raise InvalidPayloadError("Invalid webhook payload") from e

        if self._filter_regex and not self._filter_regex.search(data.room.name):
            logger.info("Filtered webhook event for room '%s'", data.room.name)
            return

        try:
            webhook_type = LiveKitWebhookEventType(data.event)
        except ValueError as e:
            raise UnsupportedEventTypeError(
                f"Unknown webhook type: {data.event}"
            ) from e

        handler_name = f"_handle_{webhook_type.value}"
        handler = getattr(self, handler_name, None)

        if not handler or not callable(handler):
            return

        # pylint: disable=not-callable
        handler(data)

    def _handle_egress_ended(self, data):
        """Handle 'egress_ended' event."""

        try:
            recording = models.Recording.objects.get(
                worker_id=data.egress_info.egress_id
            )
        except models.Recording.DoesNotExist as err:
            raise ActionFailedError(
                f"Recording with worker ID {data.egress_info.egress_id} does not exist"
            ) from err

        if (
            data.egress_info.status == api.EgressStatus.EGRESS_LIMIT_REACHED
            and recording.status == models.RecordingStatusChoices.ACTIVE
        ):
            try:
                self.recording_events.handle_limit_reached(recording)
            except RecordingEventsError as e:
                raise ActionFailedError(
                    f"Failed to process limit reached event for recording {recording}"
                ) from e

    def _handle_room_started(self, data):
        """Handle 'room_started' event."""

        try:
            room_id = uuid.UUID(data.room.name)
        except ValueError:
            # Non-UUID rooms (like sip-lobby-*) are not managed rooms, skip them
            logger.debug(
                "Ignoring room_started: room name '%s' is not a valid UUID format.",
                data.room.name,
            )
            return

        try:
            room = models.Room.objects.get(id=room_id)
        except models.Room.DoesNotExist as err:
            raise ActionFailedError(f"Room with ID {room_id} does not exist") from err

        if settings.ROOM_TELEPHONY_ENABLED:
            try:
                self.telephony_service.create_dispatch_rule(room)
            except TelephonyException as e:
                raise ActionFailedError(
                    f"Failed to create telephony dispatch rule for room {room_id}"
                ) from e

    def _handle_room_finished(self, data):
        """Handle 'room_finished' event."""

        try:
            room_id = uuid.UUID(data.room.name)
        except ValueError:
            # Non-UUID rooms (like sip-lobby-*) are not managed rooms, skip them
            logger.debug(
                "Ignoring room_finished: room name '%s' is not a valid UUID format.",
                data.room.name,
            )
            return

        if settings.ROOM_TELEPHONY_ENABLED:
            try:
                self.telephony_service.delete_dispatch_rule(room_id)
            except TelephonyException as e:
                raise ActionFailedError(
                    f"Failed to delete telephony dispatch rule for room {room_id}"
                ) from e

        try:
            self.lobby_service.clear_room_cache(room_id)
        except Exception as e:
            raise ActionFailedError(
                f"Failed to clear room cache for room {room_id}"
            ) from e

    def _handle_participant_joined(self, data):
        """Handle 'participant_joined' event - detect SIP lobby calls."""
        print(f"[PHONE_SYSTEM] _handle_participant_joined called, PHONE_SYSTEM_ENABLED={settings.PHONE_SYSTEM_ENABLED}")
        if not settings.PHONE_SYSTEM_ENABLED:
            return

        room_name = data.room.name
        participant = data.participant
        print(f"[PHONE_SYSTEM] room_name={room_name}, participant={participant.identity}")

        # Check if this is a lobby room
        if not self.phone_system.is_lobby_room(room_name):
            print(f"[PHONE_SYSTEM] Not a lobby room, skipping")
            return

        print(f"[PHONE_SYSTEM] This is a lobby room!")
        # Check if this is a SIP participant by looking at attributes
        attributes = dict(participant.attributes) if participant.attributes else {}
        print(f"[PHONE_SYSTEM] participant.attributes={attributes}")

        # SIP participants have sip.callID in their attributes
        if "sip.callID" not in attributes:
            logger.debug(
                "Non-SIP participant joined lobby room %s: %s",
                room_name,
                participant.identity,
            )
            return

        # Extract SIP call info from participant attributes
        sip_call_id = attributes.get("sip.callID", "")
        caller_number = attributes.get("sip.phoneNumber", "")
        callee_number = attributes.get("sip.trunkPhoneNumber", "")

        # If callee_number not in attributes, try extracting from trunk info
        if not callee_number:
            callee_number = attributes.get("sip.to.user", "")

        logger.info(
            "SIP participant joined lobby: room=%s, identity=%s, caller=%s, callee=%s",
            room_name,
            participant.identity,
            caller_number,
            callee_number,
        )

        # Look up target user by the called phone number
        target_user = self.phone_system.lookup_user_by_callee_number(callee_number)

        if not target_user:
            logger.warning(
                "No user found for callee number %s, hanging up call in room %s",
                callee_number,
                room_name,
            )
            self.phone_system.hangup_participant(room_name, participant.identity)
            return

        # Pre-create meeting room immediately so we can include it in the push notification
        # This allows the client to navigate directly without waiting for accept_call response
        from core.utils import generate_room_slug

        slug = generate_room_slug()
        meeting_room = models.Room.objects.create(
            name=slug,
            access_level=models.RoomAccessLevel.RESTRICTED,
        )
        models.ResourceAccess.objects.create(
            resource=meeting_room,
            user=target_user,
            role=models.RoleChoices.OWNER,
        )
        logger.info(
            "Pre-created meeting room %s (slug=%s) for incoming call from %s",
            meeting_room.id,
            meeting_room.slug,
            caller_number,
        )

        # Create pending call record with room info
        pending_call = self.phone_system.create_pending_call(
            lobby_room_name=room_name,
            sip_participant_identity=participant.identity,
            sip_call_id=sip_call_id,
            caller_number=caller_number,
            callee_number=callee_number,
            target_user=target_user,
            meeting_room_id=str(meeting_room.id),
            meeting_room_slug=meeting_room.slug,
        )

        # Send push notification to the target user (now includes room info)
        self.push_service.send_incoming_call_notification(
            user=target_user,
            pending_call=pending_call,
        )

        # Note: The lobby-bot LiveKit agent (src/agents/lobby-bot.py) will
        # automatically join this room and subscribe to the SIP participant's
        # audio track, which triggers livekit-sip to answer the call (200 OK).
        # This is configured via the dispatch rule's agent configuration.

    def _handle_participant_left(self, data):
        """Handle 'participant_left' event - detect caller hangup in lobby."""
        if not settings.PHONE_SYSTEM_ENABLED:
            return

        room_name = data.room.name

        # Only handle lobby rooms
        if not self.phone_system.is_lobby_room(room_name):
            return

        # Check if there's a pending call for this lobby
        pending_call = self.phone_system.get_pending_call_by_lobby(room_name)

        if not pending_call:
            logger.debug("No pending call found for lobby room %s", room_name)
            return

        # If call is still ringing, the caller hung up before answer
        if pending_call.status == PendingCallStatus.RINGING.value:
            logger.info(
                "Caller hung up before answer in lobby %s, call_id=%s",
                room_name,
                pending_call.call_id,
            )

            # Update call status
            self.phone_system.update_call_status(
                pending_call.call_id, PendingCallStatus.EXPIRED
            )

            # Send cancellation notification to user
            try:
                target_user = models.User.objects.get(id=pending_call.target_user_id)
                self.push_service.send_call_cancelled_notification(
                    user=target_user,
                    call_id=pending_call.call_id,
                )
            except models.User.DoesNotExist:
                logger.warning(
                    "User %s not found for call cancellation notification",
                    pending_call.target_user_id,
                )

            # Clean up orphan pre-created room (was never used)
            if pending_call.meeting_room_id:
                try:
                    orphan_room = models.Room.objects.get(id=pending_call.meeting_room_id)
                    orphan_room.delete()
                    logger.info(
                        "Cleaned up unused room %s for cancelled call %s",
                        pending_call.meeting_room_id,
                        pending_call.call_id,
                    )
                except models.Room.DoesNotExist:
                    pass

            # Clean up pending call record
            self.phone_system.clear_pending_call(pending_call.call_id)
