"""Turn viewers into participants and participants back into viewers."""

# pylint: disable=no-name-in-module

import logging

from livekit.protocol.models import ParticipantInfo

from core import models

from .participants_management import (
    ParticipantsManagement,
    ParticipantsManagementException,
)
from .seats import SeatService, is_publisher, livekit_permission, seat_info

logger = logging.getLogger(__name__)


class ViewersError(Exception):
    """A role change that cannot be made."""

    status_code = 409


class NotAViewerError(ViewersError):
    """Only a viewer can be promoted, or take a seat."""


class NotAParticipantError(ViewersError):
    """Only a participant holding a seat can go back to viewers."""


class LastAuthenticatedParticipantError(ViewersError):
    """Someone authenticated must stay able to let viewers speak."""


class NoSourceAllowedError(ViewersError):
    """A promoted viewer could publish nothing in this room."""


class SeatTakenByAuthenticatedError(ViewersError):
    """A seat can only be taken while no authenticated participant is there."""


class InvalidTargetError(ViewersError):
    """The participant cannot change role this way."""

    status_code = 400


class ForbiddenTargetError(ViewersError):
    """Only owners and administrators can send them back to viewers."""

    status_code = 403


def is_privileged(participant: ParticipantInfo) -> bool:
    """Whether a participant owns or administrates the room."""
    return participant.attributes.get("room_role") in (
        models.RoleChoices.OWNER,
        models.RoleChoices.ADMIN,
    )


class ViewersService:
    """Change the role of the participants of a room with viewers.

    Seats are changed first, then the LiveKit permission and the "viewer"
    attribute; when LiveKit fails, the seats are put back.
    """

    def __init__(self):
        self.seats = SeatService()
        self.participants = ParticipantsManagement()

    def _set_role(self, room, identity: str, viewer: bool) -> None:
        attributes = {"viewer": "true" if viewer else "false"}
        if not viewer:
            # Their hand was raised to speak: they now can.
            attributes["handRaisedAt"] = ""

        self.participants.update(
            room_name=str(room.pk),
            identity=identity,
            attributes=attributes,
            permission=livekit_permission(room, viewer=viewer),
        )

    def promote(self, room, identity: str) -> None:
        """Let a viewer speak, even beyond the threshold."""
        participant = self.participants.get(room_name=str(room.pk), identity=identity)

        if participant.kind == ParticipantInfo.Kind.SIP or is_publisher(participant):
            raise NotAViewerError("Only a viewer can be promoted.")
        if not livekit_permission(room, viewer=False)["can_publish"]:
            raise NoSourceAllowedError("Participants cannot publish in this room.")

        self.seats.activate(room.pk, identity, seat_info(participant), force=True)
        try:
            self._set_role(room, identity, viewer=False)
        except ParticipantsManagementException:
            self.seats.remove(room.pk, identity)
            raise

    def demote(self, room, identity: str, by_privileged: bool) -> None:
        """Send a participant back to viewers."""
        participant = self.participants.get(room_name=str(room.pk), identity=identity)

        if participant.kind == ParticipantInfo.Kind.SIP:
            raise InvalidTargetError("Phone callers always remain participants.")
        if is_privileged(participant) and not by_privileged:
            raise ForbiddenTargetError(
                "Only owners and administrators can do this to them."
            )

        info = self.seats.get_info(room.pk, identity) or seat_info(participant)
        result = self.seats.demote(room.pk, identity)
        if result == -1:
            raise LastAuthenticatedParticipantError(
                "The last authenticated participant cannot become a viewer."
            )
        if result == 0:
            raise NotAParticipantError("This participant is already a viewer.")

        try:
            self._set_role(room, identity, viewer=True)
        except ParticipantsManagementException:
            self.seats.activate(room.pk, identity, info, force=True)
            raise

    def take_seat(self, room, identity: str, target: str) -> None:
        """Let an authenticated viewer take the seat of an unauthenticated one.

        Only allowed while no authenticated participant is connected, so that
        viewers can always be let in.
        """
        caller = self.participants.get(room_name=str(room.pk), identity=identity)
        if is_publisher(caller):
            raise NotAViewerError("Only a viewer can take a seat.")

        target_info = self.seats.get_info(room.pk, target)
        result = self.seats.take_seat(room.pk, identity, target, seat_info(caller))
        if result == -1:
            raise SeatTakenByAuthenticatedError(
                "An authenticated participant can let you speak."
            )
        if result == -2:
            raise NotAParticipantError("This participant is already a viewer.")
        if result == -3:
            raise InvalidTargetError("Only an unauthenticated participant's seat.")

        try:
            self._set_role(room, target, viewer=True)
            self._set_role(room, identity, viewer=False)
        except ParticipantsManagementException:
            self.seats.remove(room.pk, identity)
            self.seats.activate(room.pk, target, target_info or {}, force=True)
            raise
