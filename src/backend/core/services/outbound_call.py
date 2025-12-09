"""Service for initiating outbound SIP calls."""

from logging import getLogger

from asgiref.sync import async_to_sync
from django.conf import settings
from livekit.api import TwirpError
from livekit.protocol.sip import CreateSIPParticipantRequest

from core import utils

logger = getLogger(__name__)


class OutboundCallException(Exception):
    """Exception raised when outbound call operations fail."""


class OutboundCallService:
    """Service for initiating outbound SIP calls to phone numbers."""

    @async_to_sync
    async def initiate_call(
        self,
        phone_number: str,
        room_name: str,
        participant_identity: str,
        participant_name: str = None,
    ) -> dict:
        """
        Initiate an outbound SIP call to a phone number.

        Args:
            phone_number: E.164 formatted phone number to dial
            room_name: LiveKit room to connect the call to
            participant_identity: Identity for the SIP participant
            participant_name: Display name for the participant

        Returns:
            dict with sip_call_id and participant info
        """
        if not settings.OUTBOUND_CALL_ENABLED:
            raise OutboundCallException("Outbound calls are not enabled")

        if not settings.OUTBOUND_SIP_TRUNK_ID:
            raise OutboundCallException("Outbound SIP trunk ID is not configured")

        lkapi = utils.create_livekit_client()

        try:
            request = CreateSIPParticipantRequest(
                sip_trunk_id=settings.OUTBOUND_SIP_TRUNK_ID,
                sip_call_to=phone_number,
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name=participant_name or phone_number,
                play_dialtone=True,
            )

            logger.info(
                "Initiating outbound call to %s in room %s",
                phone_number,
                room_name,
            )

            response = await lkapi.sip.create_sip_participant(request)

            logger.info(
                "Outbound call initiated: sip_call_id=%s, participant_id=%s",
                response.sip_call_id,
                response.participant_id,
            )

            return {
                "sip_call_id": response.sip_call_id,
                "participant_id": response.participant_id,
                "participant_identity": response.participant_identity,
            }

        except TwirpError as e:
            logger.exception("Failed to initiate outbound call to %s", phone_number)
            raise OutboundCallException(f"Failed to initiate call: {e}") from e

        finally:
            await lkapi.aclose()
