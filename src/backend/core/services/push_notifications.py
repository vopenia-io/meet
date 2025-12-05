"""Push notification service for incoming calls."""

from logging import getLogger
from typing import TYPE_CHECKING

from django.conf import settings

from core import models

if TYPE_CHECKING:
    from .phone_system import PendingCall

logger = getLogger(__name__)


class PushNotificationService:
    """Service for sending push notifications."""

    def send_incoming_call_notification(
        self,
        user: models.User,
        pending_call: "PendingCall",
    ) -> bool:
        """Send push notification for incoming call.

        Returns True if at least one notification was sent successfully.
        """
        # Lazy import to avoid circular dependencies and allow graceful degradation
        try:
            from push_notifications.models import APNSDevice, WebPushDevice
        except ImportError:
            logger.warning(
                "push_notifications not installed, skipping notification for call %s",
                pending_call.call_id,
            )
            return False

        payload = {
            "type": "incoming_call",
            "call_id": pending_call.call_id,
            "caller_number": pending_call.caller_number,
            "callee_number": pending_call.callee_number,
            "lobby_room_name": pending_call.lobby_room_name,
            "sip_participant_identity": pending_call.sip_participant_identity,
            "room_id": pending_call.meeting_room_id,
            "room_slug": pending_call.meeting_room_slug,
        }

        # Human-readable message
        caller_display = self._format_phone_number(pending_call.caller_number)
        message = f"Incoming call from {caller_display}"

        success = False

        # Send to APNS devices (iOS)
        apns_devices = APNSDevice.objects.filter(user=user, active=True)
        if apns_devices.exists():
            try:
                apns_devices.send_message(
                    message=message,
                    extra=payload,
                    sound="default",
                    category="INCOMING_CALL",
                )
                success = True
                logger.info(
                    "Sent APNS notification to user %s for call %s",
                    user.id,
                    pending_call.call_id,
                )
            except Exception as e:
                logger.exception("Failed to send APNS notification: %s", e)

        # Send to Web Push devices
        web_devices = WebPushDevice.objects.filter(user=user, active=True)
        if web_devices.exists():
            try:
                web_devices.send_message(
                    message=message,
                    extra=payload,
                    tag="incoming-call",
                )
                success = True
                logger.info(
                    "Sent WebPush notification to user %s for call %s",
                    user.id,
                    pending_call.call_id,
                )
            except Exception as e:
                logger.exception("Failed to send WebPush notification: %s", e)

        if not success:
            logger.warning(
                "No active devices found for user %s, call %s",
                user.id,
                pending_call.call_id,
            )

        return success

    def send_call_cancelled_notification(
        self,
        user: models.User,
        call_id: str,
    ) -> None:
        """Notify user that incoming call was cancelled/hung up."""
        try:
            from push_notifications.models import APNSDevice, WebPushDevice
        except ImportError:
            logger.warning(
                "push_notifications not installed, skipping cancellation for call %s",
                call_id,
            )
            return

        payload = {
            "type": "call_cancelled",
            "call_id": call_id,
        }

        # Silent notification to dismiss incoming call UI
        apns_devices = APNSDevice.objects.filter(user=user, active=True)
        if apns_devices.exists():
            try:
                apns_devices.send_message(
                    message=None,
                    extra=payload,
                    content_available=True,  # Silent push
                )
                logger.info(
                    "Sent APNS cancellation to user %s for call %s",
                    user.id,
                    call_id,
                )
            except Exception as e:
                logger.exception("Failed to send APNS cancellation: %s", e)

        web_devices = WebPushDevice.objects.filter(user=user, active=True)
        if web_devices.exists():
            try:
                web_devices.send_message(
                    message="Call ended",
                    extra=payload,
                    tag="incoming-call",
                )
                logger.info(
                    "Sent WebPush cancellation to user %s for call %s",
                    user.id,
                    call_id,
                )
            except Exception as e:
                logger.exception("Failed to send WebPush cancellation: %s", e)

    def _format_phone_number(self, number: str) -> str:
        """Format phone number for display.

        Basic formatting - can be enhanced with phonenumbers library.
        """
        if not number:
            return "Unknown"

        # US format
        if number.startswith("+1") and len(number) == 12:
            return f"({number[2:5]}) {number[5:8]}-{number[8:]}"

        # French format
        if number.startswith("+33") and len(number) == 12:
            # +33612345678 -> +33 6 12 34 56 78
            digits = number[3:]
            return f"+33 {digits[0]} {digits[1:3]} {digits[3:5]} {digits[5:7]} {digits[7:]}"

        return number
