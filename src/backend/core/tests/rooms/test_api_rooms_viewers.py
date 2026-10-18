"""
Test rooms API endpoints in the Meet core app: joining as a viewer.
"""

# pylint: disable=redefined-outer-name,unused-argument

import random
from unittest import mock

from django.conf import settings

import jwt
import pytest
from rest_framework.test import APIClient

from ...factories import RoomFactory, UserFactory
from ...models import RoomAccessLevel
from ...services.seats import SeatService

pytestmark = pytest.mark.django_db


@pytest.fixture
def viewers_enabled(settings):
    """Enable viewers, without any LiveKit room to reconcile the seats with."""
    settings.VIEWERS_ENABLED = True
    with mock.patch.object(SeatService, "_list_participants", return_value=None):
        yield


def decode_token(token: str) -> dict:
    """Decode a LiveKit JWT access token for inspection."""
    return jwt.decode(
        token, settings.LIVEKIT_CONFIGURATION["api_secret"], algorithms=["HS256"]
    )


def request_entry(client, room, tab=None):
    """Ask to join a room and return the LiveKit configuration given."""
    data = {"username": "someone", **({"tab": tab} if tab else {})}
    response = client.post(f"/api/v1.0/rooms/{room.id}/request-entry/", data)
    assert response.status_code == 200
    return response.json()["livekit"]


def test_api_rooms_viewers_retrieve_disabled(settings):
    """Without viewers, reading a room still gives a token."""
    settings.VIEWERS_ENABLED = False
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)

    response = APIClient().get(f"/api/v1.0/rooms/{room.id}/")

    assert response.status_code == 200
    assert "role" not in response.json()["livekit"]


def test_api_rooms_viewers_retrieve_anonymous(viewers_enabled):
    """Reading a room gives no token: seats are given through request-entry."""
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)

    response = APIClient().get(f"/api/v1.0/rooms/{room.id}/")

    assert response.status_code == 200
    content = response.json()
    assert "livekit" not in content
    assert "pin_code" in content


@pytest.mark.parametrize("role", ["administrator", "owner"])
def test_api_rooms_viewers_retrieve_privileged(viewers_enabled, role):
    """Owners and administrators read a room with a participant token."""
    user = UserFactory()
    room = RoomFactory(users=[(user, role)], configuration={"viewers_threshold": 1})
    SeatService().allocate(room.id, "someone", 1)
    client = APIClient()
    client.force_login(user)

    response = client.get(f"/api/v1.0/rooms/{room.id}/")

    livekit = response.json()["livekit"]
    assert livekit["role"] == "participant"
    claims = decode_token(livekit["token"])
    assert claims["attributes"]["viewer"] == "false"
    assert claims["video"]["canPublish"] is True


def test_api_rooms_viewers_request_entry_beyond_threshold(viewers_enabled):
    """Beyond the threshold, people join as viewers who cannot publish."""
    room = RoomFactory(
        access_level=RoomAccessLevel.PUBLIC, configuration={"viewers_threshold": 1}
    )
    first, second = APIClient(), APIClient()

    livekit = request_entry(first, room)
    assert livekit["role"] == "participant"
    assert decode_token(livekit["token"])["video"]["canPublish"] is True

    livekit = request_entry(second, room)
    assert livekit["role"] == "viewer"
    claims = decode_token(livekit["token"])
    assert claims["attributes"]["viewer"] == "true"
    assert claims["video"].get("canPublish", False) is False

    # Asking again keeps the seat, thanks to the lobby cookie.
    assert request_entry(first, room)["role"] == "participant"
    assert request_entry(second, room)["role"] == "viewer"


def test_api_rooms_viewers_request_entry_authenticated(viewers_enabled):
    """The seat of an authenticated user is held by their identity."""
    user = UserFactory()
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    client = APIClient()
    client.force_login(user)

    assert request_entry(client, room)["role"] == "participant"
    assert SeatService().has_seat(room.id, str(user.sub))


@pytest.mark.parametrize("role", ["administrator", "owner"])
def test_api_rooms_viewers_request_entry_privileged(viewers_enabled, role):
    """Owners and administrators join as participants even beyond the threshold."""
    user = UserFactory()
    room = RoomFactory(
        access_level=random.choice(list(RoomAccessLevel)),
        users=[(user, role)],
        configuration={"viewers_threshold": 1},
    )
    SeatService().allocate(room.id, "someone", 1)
    client = APIClient()
    client.force_login(user)

    assert request_entry(client, room)["role"] == "participant"


def test_api_rooms_viewers_request_entry_disabled(settings):
    """Without viewers, the configuration given is unchanged."""
    settings.VIEWERS_ENABLED = False
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)

    assert "role" not in request_entry(APIClient(), room)


def test_api_rooms_viewers_seats_disabled(settings):
    """A room without viewers is never full."""
    settings.VIEWERS_ENABLED = False
    room = RoomFactory()

    response = APIClient().get(f"/api/v1.0/rooms/{room.id}/seats/")

    assert response.status_code == 200
    assert response.json() == {"full": False, "threshold": 50}


def test_api_rooms_viewers_seats(viewers_enabled):
    """Anyone about to join can tell whether they would be a viewer."""
    room = RoomFactory(configuration={"viewers_threshold": 2})
    SeatService().allocate(room.id, "a", 2)
    SeatService().allocate(room.id, "b", 2)

    response = APIClient().get(f"/api/v1.0/rooms/{room.slug}/seats/")

    assert response.status_code == 200
    assert response.json() == {"full": True, "threshold": 2}


def test_api_rooms_viewers_seats_not_full(viewers_enabled):
    """A room with seats left is not full."""
    room = RoomFactory(configuration={"viewers_threshold": 2})
    SeatService().allocate(room.id, "a", 2)

    response = APIClient().get(f"/api/v1.0/rooms/{room.id}/seats/")

    assert response.json() == {"full": False, "threshold": 2}


def test_api_rooms_viewers_seats_follow_arrivals(viewers_enabled):
    """The join screen tells at once when the last seat is taken or freed."""
    room = RoomFactory(configuration={"viewers_threshold": 2})
    client = APIClient()
    SeatService().allocate(room.id, "a", 2)

    assert client.get(f"/api/v1.0/rooms/{room.id}/seats/").json()["full"] is False

    SeatService().allocate(room.id, "b", 2)

    assert client.get(f"/api/v1.0/rooms/{room.id}/seats/").json()["full"] is True

    SeatService().remove(room.id, "b")

    assert client.get(f"/api/v1.0/rooms/{room.id}/seats/").json()["full"] is False


@pytest.mark.parametrize("role", ["administrator", "owner"])
def test_api_rooms_viewers_seats_privileged(viewers_enabled, role):
    """Owners and administrators never join as viewers."""
    user = UserFactory()
    room = RoomFactory(users=[(user, role)], configuration={"viewers_threshold": 1})
    SeatService().allocate(room.id, "a", 1)
    client = APIClient()
    client.force_login(user)

    response = client.get(f"/api/v1.0/rooms/{room.id}/seats/")

    assert response.json() == {"full": False, "threshold": 1}


def test_api_rooms_viewers_request_entry_tabs(viewers_enabled):
    """Each tab of a browser joins as its own participant, and keeps its seat."""
    room = RoomFactory(
        access_level=RoomAccessLevel.PUBLIC, configuration={"viewers_threshold": 1}
    )
    browser = APIClient()

    first = request_entry(browser, room, tab="tab-1")
    second = request_entry(browser, room, tab="tab-2")

    first_identity = decode_token(first["token"])["sub"]
    second_identity = decode_token(second["token"])["sub"]
    assert first_identity != second_identity
    assert first["role"] == "participant"
    assert second["role"] == "viewer"

    # Reloading the first tab gets its seat back.
    again = request_entry(browser, room, tab="tab-1")
    assert decode_token(again["token"])["sub"] == first_identity
    assert again["role"] == "participant"


def test_api_rooms_viewers_request_entry_tabs_of_other_browsers(viewers_enabled):
    """The same tab id in another browser is another participant."""
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)

    first = request_entry(APIClient(), room, tab="tab-1")
    second = request_entry(APIClient(), room, tab="tab-1")

    assert decode_token(first["token"])["sub"] != decode_token(second["token"])["sub"]
