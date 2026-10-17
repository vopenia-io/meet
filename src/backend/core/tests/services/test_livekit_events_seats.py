"""
Test the seats kept up to date by LiveKit webhooks.
"""

# pylint: disable=redefined-outer-name,protected-access,no-name-in-module,unused-argument

from unittest import mock
from uuid import uuid4

import pytest
from freezegun import freeze_time
from livekit.protocol.models import DisconnectReason, ParticipantInfo
from livekit.protocol.models import Room as LiveKitRoom
from livekit.protocol.webhook import WebhookEvent

from core.factories import RoomFactory
from core.services.livekit_events import LiveKitEventsService
from core.services.participants_management import ParticipantsManagement
from core.services.seats import SeatService

pytestmark = pytest.mark.django_db


@pytest.fixture
def service(settings):
    """Initialize LiveKitEventsService with viewers enabled."""
    settings.VIEWERS_ENABLED = True
    settings.VIEWERS_RECONNECT_GRACE_PERIOD = 120
    return LiveKitEventsService()


@pytest.fixture
def seats():
    """Return a SeatService instance."""
    return SeatService()


def event(name, room_name, identity="someone", **participant):
    """Build a webhook event about a participant."""
    participant.setdefault("sid", f"PA_{identity}")
    return WebhookEvent(
        event=name,
        room=LiveKitRoom(name=str(room_name)),
        participant=ParticipantInfo(identity=identity, **participant),
    )


def test_joined_activates_pending_seat(service, seats):
    """A participant joining with a pending seat keeps it while connected."""
    room_id = uuid4()
    seats.allocate(room_id, "someone", 5)

    with freeze_time() as frozen:
        service._handle_participant_joined(
            event("participant_joined", room_id, attributes={"viewer": "false"})
        )
        frozen.tick(3600)

        assert seats.has_seat(room_id, "someone")


def test_joined_viewer_takes_no_seat(service, seats):
    """A viewer joining takes no seat."""
    room_id = uuid4()

    service._handle_participant_joined(
        event("participant_joined", room_id, attributes={"viewer": "true"})
    )

    assert not seats.has_seat(room_id, "someone")


def test_joined_participant_without_seat_is_counted(service, seats):
    """Owners, administrators and older tokens are counted beyond the threshold."""
    room_id = uuid4()
    seats.allocate(room_id, "first", 1)

    service._handle_participant_joined(
        event("participant_joined", room_id, "owner", attributes={"viewer": "false"})
    )

    assert seats.has_seat(room_id, "owner")
    assert not seats.allocate(room_id, "late", 2)


def test_joined_phone_caller_is_counted(service, seats):
    """Phone callers are accepted beyond the threshold and take a seat."""
    room_id = uuid4()
    seats.allocate(room_id, "first", 1)

    service._handle_participant_joined(
        event("participant_joined", room_id, "sip_1", kind=ParticipantInfo.Kind.SIP)
    )

    assert seats.has_seat(room_id, "sip_1")


@pytest.mark.parametrize(
    "kind", [ParticipantInfo.Kind.EGRESS, ParticipantInfo.Kind.AGENT]
)
def test_joined_egress_and_agents_take_no_seat(service, seats, kind):
    """Recorders and agents never take a seat."""
    room_id = uuid4()

    service._handle_participant_joined(
        event("participant_joined", room_id, "bot", kind=kind)
    )

    assert not seats.has_seat(room_id, "bot")


@mock.patch.object(ParticipantsManagement, "update")
def test_joined_with_viewer_token_while_holding_seat(mock_update, service, seats):
    """A promoted participant rejoining with an old viewer token gets their rights."""
    room = RoomFactory(configuration={"can_publish_sources": ["microphone"]})
    seats.activate(room.id, "someone", {"sid": "PA_old"}, force=True)

    service._handle_participant_joined(
        event("participant_joined", room.id, attributes={"viewer": "true"})
    )

    mock_update.assert_called_once_with(
        room_name=str(room.id),
        identity="someone",
        attributes={"viewer": "false"},
        permission={
            "can_subscribe": True,
            "can_publish": True,
            "can_publish_data": True,
            "can_publish_sources": ["MICROPHONE"],
        },
    )


def test_joined_ignored_when_disabled(service, seats, settings):
    """Seats are not counted when viewers are disabled."""
    settings.VIEWERS_ENABLED = False
    room_id = uuid4()

    service._handle_participant_joined(
        event("participant_joined", room_id, "sip_1", kind=ParticipantInfo.Kind.SIP)
    )

    assert not seats.has_seat(room_id, "sip_1")


def test_joined_ignored_for_unregistered_room(service):
    """Unregistered rooms, named after their slug, have no seats."""
    service._handle_participant_joined(
        event("participant_joined", "my-room", "sip_1", kind=ParticipantInfo.Kind.SIP)
    )


def test_left_keeps_seat_for_grace_period(service, seats):
    """A participant who left gets their seat back within the grace period."""
    room_id = uuid4()

    with freeze_time() as frozen:
        seats.activate(room_id, "someone", {"sid": "PA_someone"}, force=True)
        service._handle_participant_left(
            event(
                "participant_left",
                room_id,
                disconnect_reason=DisconnectReason.SIGNAL_CLOSE,
            )
        )

        frozen.tick(60)
        assert seats.has_seat(room_id, "someone")

        frozen.tick(61)
        assert not seats.has_seat(room_id, "someone")


def test_left_removed_participant_loses_seat(service, seats):
    """A participant removed from the room loses their seat at once."""
    room_id = uuid4()
    seats.activate(room_id, "someone", {"sid": "PA_someone"}, force=True)

    service._handle_participant_left(
        event(
            "participant_left",
            room_id,
            disconnect_reason=DisconnectReason.PARTICIPANT_REMOVED,
        )
    )

    assert not seats.has_seat(room_id, "someone")


def test_left_duplicate_identity_keeps_seat(service, seats):
    """Leaving because the identity joined again elsewhere keeps the seat active."""
    room_id = uuid4()
    seats.activate(room_id, "someone", {"sid": "PA_someone"}, force=True)

    with freeze_time() as frozen:
        service._handle_participant_left(
            event(
                "participant_left",
                room_id,
                disconnect_reason=DisconnectReason.DUPLICATE_IDENTITY,
            )
        )
        frozen.tick(3600)

        assert seats.has_seat(room_id, "someone")


def test_left_previous_session_keeps_seat(service, seats):
    """A late event about a previous session keeps the new session's seat."""
    room_id = uuid4()
    seats.activate(room_id, "someone", {"sid": "PA_new"}, force=True)

    with freeze_time() as frozen:
        service._handle_participant_left(
            event("participant_left", room_id, sid="PA_old")
        )
        frozen.tick(3600)

        assert seats.has_seat(room_id, "someone")


def test_connection_aborted_frees_pending_seat(service, seats):
    """A participant who could not connect frees their pending seat."""
    room_id = uuid4()
    seats.allocate(room_id, "someone", 5)

    service._handle_participant_connection_aborted(
        event("participant_connection_aborted", room_id)
    )

    assert not seats.has_seat(room_id, "someone")


@mock.patch("core.services.livekit_events.LobbyService.clear_room_cache")
def test_room_finished_clears_seats(mock_clear_lobby, service, seats, settings):
    """Seats are dropped when the room finishes."""
    settings.ROOM_TELEPHONY_ENABLED = False
    settings.ROOMKIT_ENABLED = False
    room_id = uuid4()
    seats.activate(room_id, "someone", {"sid": "PA_someone"}, force=True)

    service._handle_room_finished(
        WebhookEvent(event="room_finished", room=LiveKitRoom(name=str(room_id)))
    )

    assert not seats.has_seat(room_id, "someone")
