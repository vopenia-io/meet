"""
Test the seats service.
"""

# pylint: disable=redefined-outer-name,protected-access

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser

import aiohttp
import pytest
from freezegun import freeze_time
from livekit.api import TwirpError
from livekit.protocol.models import ParticipantInfo

from core.factories import RoomFactory, UserFactory
from core.services.seats import (
    JoinRole,
    SeatService,
    get_threshold,
    is_viewers_enabled,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def seats():
    """Return a SeatService instance."""
    return SeatService()


@pytest.fixture
def room_id():
    """Return a fresh room id: tests share the Redis instance."""
    return uuid4()


def participant(identity, kind=ParticipantInfo.Kind.STANDARD, **attributes):
    """Build a LiveKit participant."""
    return ParticipantInfo(
        identity=identity, sid=f"PA_{identity}", kind=kind, attributes=attributes
    )


def test_seats_allocate_up_to_threshold(seats, room_id):
    """Seats are given until the threshold is reached."""
    assert seats.allocate(room_id, "a", 2)
    assert seats.allocate(room_id, "b", 2)
    assert not seats.allocate(room_id, "c", 2)


def test_seats_allocate_is_idempotent(seats, room_id):
    """An identity asking again keeps its seat and takes no other one."""
    assert seats.allocate(room_id, "a", 2)
    assert seats.allocate(room_id, "a", 2)
    assert seats.allocate(room_id, "b", 2)
    assert not seats.allocate(room_id, "c", 2)


def test_seats_allocate_concurrently(seats, room_id):
    """Concurrent arrivals never take more seats than the threshold."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(
            executor.map(
                lambda identity: seats.allocate(room_id, identity, 5),
                [f"identity-{i}" for i in range(40)],
            )
        )

    assert results.count(True) == 5


def test_seats_pending_seat_expires(seats, room_id, settings):
    """A seat whose holder never joins is freed after the pending timeout."""
    settings.VIEWERS_PENDING_SEAT_TIMEOUT = 120

    with freeze_time("2026-10-17 10:00:00") as frozen:
        assert seats.allocate(room_id, "a", 1)
        assert not seats.allocate(room_id, "b", 1)

        frozen.tick(121)

        assert not seats.has_seat(room_id, "a")
        assert seats.allocate(room_id, "b", 1)


def test_seats_active_seat_does_not_expire(seats, room_id):
    """Once its holder joined, a seat is kept as long as they are connected."""
    with freeze_time("2026-10-17 10:00:00") as frozen:
        assert seats.allocate(room_id, "a", 1)
        assert seats.activate(room_id, "a", {"sid": "PA_a", "auth": False})

        frozen.tick(3600)

        assert seats.has_seat(room_id, "a")
        assert not seats.allocate(room_id, "b", 1)


def test_seats_activate_without_seat(seats, room_id):
    """Without force, joining does not create a seat."""
    assert not seats.activate(room_id, "a", {"sid": "PA_a"})
    assert not seats.has_seat(room_id, "a")


def test_seats_activate_with_force_beyond_threshold(seats, room_id):
    """Forced seats (owners, phone callers) are counted beyond the threshold."""
    assert seats.allocate(room_id, "a", 1)
    assert seats.activate(room_id, "owner", {"sid": "PA_owner"}, force=True)

    assert seats.has_seat(room_id, "owner")
    assert not seats.allocate(room_id, "b", 2)


def test_seats_release_keeps_seat_for_grace_period(seats, room_id, settings):
    """A disconnected participant gets their seat back within the grace period."""
    settings.VIEWERS_RECONNECT_GRACE_PERIOD = 120

    with freeze_time("2026-10-17 10:00:00") as frozen:
        seats.allocate(room_id, "a", 1)
        seats.activate(room_id, "a", {"sid": "PA_a"})

        assert seats.release(room_id, "a", "PA_a")
        frozen.tick(60)

        assert not seats.allocate(room_id, "b", 1)
        assert seats.allocate(room_id, "a", 1)


def test_seats_release_frees_seat_after_grace_period(seats, room_id, settings):
    """After the grace period, the seat goes to the next arrival."""
    settings.VIEWERS_RECONNECT_GRACE_PERIOD = 120

    with freeze_time("2026-10-17 10:00:00") as frozen:
        seats.allocate(room_id, "a", 1)
        seats.activate(room_id, "a", {"sid": "PA_a"})
        seats.release(room_id, "a", "PA_a")

        frozen.tick(121)

        assert seats.allocate(room_id, "b", 1)
        assert not seats.has_seat(room_id, "a")


def test_seats_release_ignores_another_session(seats, room_id):
    """A late participant_left of a previous session keeps the seat active."""
    seats.allocate(room_id, "a", 1)
    seats.activate(room_id, "a", {"sid": "PA_new"})

    assert not seats.release(room_id, "a", "PA_old")

    with freeze_time() as frozen:
        frozen.tick(3600)
        assert seats.has_seat(room_id, "a")


def test_seats_release_phone_caller(seats, room_id):
    """A phone caller hanging up frees their seat right away."""
    seats.activate(room_id, "sip_1", {"sid": "PA_sip", "sip": True}, force=True)

    assert seats.release(room_id, "sip_1", "PA_sip")
    assert not seats.has_seat(room_id, "sip_1")


def test_seats_remove_only_pending(seats, room_id):
    """An aborted connection frees a pending seat but not an active one."""
    seats.allocate(room_id, "pending", 5)
    seats.allocate(room_id, "active", 5)
    seats.activate(room_id, "active", {"sid": "PA_active"})

    assert seats.remove(room_id, "pending", only_pending=True)
    assert not seats.remove(room_id, "active", only_pending=True)
    assert seats.has_seat(room_id, "active")

    assert seats.remove(room_id, "active")
    assert not seats.has_seat(room_id, "active")


def test_seats_reconcile(seats, room_id, settings):
    """Seats follow the participants LiveKit reports."""
    settings.VIEWERS_RECONNECT_GRACE_PERIOD = 120

    with freeze_time("2026-10-17 10:00:00") as frozen:
        seats.allocate(room_id, "gone", 10)
        seats.activate(room_id, "gone", {"sid": "PA_gone"})
        seats.allocate(room_id, "here", 10)
        seats.activate(room_id, "here", {"sid": "PA_here"})

        seats.reconcile(
            room_id,
            [
                participant("here", viewer="false"),
                participant("unknown", viewer="false", is_authenticated="true"),
                participant("viewer", viewer="true"),
                participant("egress", kind=ParticipantInfo.Kind.EGRESS),
                participant("agent", kind=ParticipantInfo.Kind.AGENT),
            ],
        )

        assert seats.has_seat(room_id, "gone")
        assert seats.has_seat(room_id, "here")
        assert seats.has_seat(room_id, "unknown")
        assert not seats.has_seat(room_id, "viewer")
        assert not seats.has_seat(room_id, "egress")
        assert not seats.has_seat(room_id, "agent")

        frozen.tick(121)

        assert not seats.has_seat(room_id, "gone")
        assert seats.has_seat(room_id, "here")
        assert seats.has_seat(room_id, "unknown")


def test_seats_reconcile_if_due_is_throttled(seats, room_id, settings):
    """LiveKit is asked at most once per interval."""
    settings.VIEWERS_RECONCILE_INTERVAL = 15

    with mock.patch.object(
        SeatService, "_list_participants", return_value=[]
    ) as list_participants:
        assert seats.reconcile_if_due(room_id)
        assert not seats.reconcile_if_due(room_id)

    list_participants.assert_called_once_with(str(room_id))


@pytest.mark.parametrize(
    "error",
    [
        TwirpError(code="internal", msg="boom", status=500),
        aiohttp.ServerDisconnectedError(),
        asyncio.TimeoutError(),
    ],
)
def test_seats_reconcile_if_due_livekit_unreachable(seats, room_id, error):
    """Failing to reach LiveKit leaves the seats as they are."""
    with mock.patch.object(SeatService, "_list_participants", side_effect=error):
        assert not seats.reconcile_if_due(room_id)


def test_seats_reconcile_if_due_room_not_started(seats, room_id):
    """Nothing to reconcile when the LiveKit room does not exist."""
    with mock.patch.object(SeatService, "_list_participants", return_value=None):
        assert not seats.reconcile_if_due(room_id)


def test_seats_clear(seats, room_id):
    """Clearing a room drops all its seats."""
    seats.allocate(room_id, "a", 5)
    seats.activate(room_id, "b", {"sid": "PA_b"}, force=True)

    seats.clear(room_id)

    assert not seats.has_seat(room_id, "a")
    assert not seats.has_seat(room_id, "b")


@pytest.mark.parametrize("role", ["owner", "administrator"])
def test_seats_assign_role_privileged(seats, role):
    """Owners and administrators always join as participants."""
    room = RoomFactory(configuration={"viewers_threshold": 1})
    seats.allocate(room.id, "someone", 1)

    assert (
        seats.assign_role(room, "owner-identity", UserFactory(), role)
        == JoinRole.PARTICIPANT
    )
    # Their seat is only counted once they join.
    assert not seats.has_seat(room.id, "owner-identity")


def test_seats_assign_role_viewer_when_full(seats):
    """Beyond the threshold, people join as viewers."""
    room = RoomFactory(configuration={"viewers_threshold": 1})

    with mock.patch.object(SeatService, "reconcile_if_due", return_value=False):
        assert seats.assign_role(room, "a", AnonymousUser()) == JoinRole.PARTICIPANT
        assert seats.assign_role(room, "b", AnonymousUser()) == JoinRole.VIEWER
        assert seats.assign_role(room, "a", AnonymousUser()) == JoinRole.PARTICIPANT


def test_seats_assign_role_after_reconciliation(seats):
    """A seat held by someone gone is given once LiveKit confirms they left."""
    room = RoomFactory(configuration={"viewers_threshold": 1})
    seats.allocate(room.id, "gone", 1)
    seats.activate(room.id, "gone", {"sid": "PA_gone"})

    def reconcile(room_id):
        seats.remove(room_id, "gone")
        return True

    with mock.patch.object(SeatService, "reconcile_if_due", side_effect=reconcile):
        assert seats.assign_role(room, "b", AnonymousUser()) == JoinRole.PARTICIPANT


def test_seats_get_threshold(settings):
    """The room threshold overrides the instance default."""
    settings.VIEWERS_DEFAULT_THRESHOLD = 50

    assert get_threshold(RoomFactory(configuration={})) == 50
    assert get_threshold(RoomFactory(configuration={"viewers_threshold": 3})) == 3


def test_seats_is_viewers_enabled(settings):
    """Viewers are only enabled on registered rooms of an enabled instance."""
    room = RoomFactory()

    settings.VIEWERS_ENABLED = False
    assert not is_viewers_enabled(room)

    settings.VIEWERS_ENABLED = True
    assert is_viewers_enabled(room)
    assert not is_viewers_enabled(None)


def test_seats_demote(seats, room_id):
    """Going back to viewers frees the seat."""
    seats.activate(room_id, "a", {"sid": "PA_a", "auth": False}, force=True)

    assert seats.demote(room_id, "a") == 1
    assert not seats.has_seat(room_id, "a")
    assert seats.demote(room_id, "a") == 0


def test_seats_demote_last_authenticated(seats, room_id):
    """The last authenticated participant connected keeps their seat."""
    seats.activate(room_id, "auth", {"sid": "PA_1", "auth": True}, force=True)
    seats.activate(room_id, "anon", {"sid": "PA_2", "auth": False}, force=True)

    assert seats.demote(room_id, "auth") == -1
    assert seats.has_seat(room_id, "auth")
    assert seats.demote(room_id, "auth", check_last=False) == 1


def test_seats_demote_authenticated_with_another_one(seats, room_id):
    """An authenticated participant can leave when another one stays."""
    seats.activate(room_id, "auth-1", {"sid": "PA_1", "auth": True}, force=True)
    seats.activate(room_id, "auth-2", {"sid": "PA_2", "auth": True}, force=True)

    assert seats.demote(room_id, "auth-1") == 1


def test_seats_demote_authenticated_with_another_one_disconnected(seats, room_id):
    """A disconnected authenticated participant cannot let viewers speak."""
    seats.activate(room_id, "auth-1", {"sid": "PA_1", "auth": True}, force=True)
    seats.activate(room_id, "auth-2", {"sid": "PA_2", "auth": True}, force=True)
    seats.release(room_id, "auth-2", "PA_2")

    assert seats.demote(room_id, "auth-1") == -1


def test_seats_take_seat(seats, room_id):
    """An authenticated viewer takes the seat of an unauthenticated participant."""
    seats.activate(room_id, "anon", {"sid": "PA_anon", "auth": False}, force=True)

    assert seats.take_seat(room_id, "viewer", "anon", {"sid": "PA_v", "auth": True})
    assert seats.has_seat(room_id, "viewer")
    assert not seats.has_seat(room_id, "anon")
    assert seats.get_info(room_id, "viewer") == {"sid": "PA_v", "auth": True}


def test_seats_take_seat_with_authenticated_participant(seats, room_id):
    """No seat is taken while an authenticated participant is connected."""
    seats.activate(room_id, "auth", {"sid": "PA_1", "auth": True}, force=True)
    seats.activate(room_id, "anon", {"sid": "PA_2", "auth": False}, force=True)

    assert seats.take_seat(room_id, "viewer", "anon", {"auth": True}) == -1
    assert seats.has_seat(room_id, "anon")


@pytest.mark.parametrize("info", [{"auth": True}, {"auth": False, "sip": True}])
def test_seats_take_seat_invalid_target(seats, room_id, info):
    """The seat of an authenticated participant or a phone caller is not taken."""
    seats.allocate(room_id, "target", 5, **info)

    assert seats.take_seat(room_id, "viewer", "target", {"auth": True}) == -3


def test_seats_take_seat_target_without_seat(seats, room_id):
    """Only a seat that exists can be taken."""
    assert seats.take_seat(room_id, "viewer", "nobody", {"auth": True}) == -2
