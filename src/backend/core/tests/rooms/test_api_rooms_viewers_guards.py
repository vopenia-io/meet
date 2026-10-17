"""
Test rooms API endpoints in the Meet core app: what viewers cannot do.
"""

# pylint: disable=redefined-outer-name,unused-argument

from unittest import mock
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser

import pytest
from rest_framework.test import APIClient

from ... import utils
from ...factories import RoomFactory, UserFactory
from ...models import RoomAccessLevel
from ...services.seats import SeatService
from ...services.subtitle import SubtitleService

pytestmark = pytest.mark.django_db


@pytest.fixture
def viewers_enabled(settings):
    """Enable viewers."""
    settings.VIEWERS_ENABLED = True


@pytest.fixture
def mock_livekit_client():
    """Mock LiveKit API client."""
    with mock.patch("core.utils.create_livekit_client") as mock_create:
        mock_client = mock.AsyncMock()
        mock_create.return_value = mock_client
        yield mock_client


def client_with_token(room, user=None, identity=None):
    """API client authenticated with a LiveKit token for the room."""
    token = utils.generate_token(
        room=str(room.id), user=user or AnonymousUser(), participant_id=identity
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def mute(client, room):
    """Ask to mute someone in the room."""
    return client.post(
        f"/api/v1.0/rooms/{room.id}/mute-participant/",
        {"participant_identity": str(uuid4()), "track_sid": "TR_mic"},
        format="json",
    )


def test_api_rooms_viewers_mute_refused_to_viewers(
    viewers_enabled, mock_livekit_client
):
    """A viewer cannot mute the people who can speak."""
    room = RoomFactory()

    response = mute(client_with_token(room, identity="viewer"), room)

    assert response.status_code == 403
    mock_livekit_client.room.mute_published_track.assert_not_called()


def test_api_rooms_viewers_mute_by_seat_holder(viewers_enabled, mock_livekit_client):
    """A participant holding a seat can mute, as before."""
    room = RoomFactory()
    SeatService().activate(room.id, "speaker", {"sid": "PA_speaker"}, force=True)

    response = mute(client_with_token(room, identity="speaker"), room)

    assert response.status_code == 200
    mock_livekit_client.room.mute_published_track.assert_called_once()


def test_api_rooms_viewers_mute_without_viewers(settings, mock_livekit_client):
    """Rooms without viewers are unchanged."""
    settings.VIEWERS_ENABLED = False
    room = RoomFactory()

    response = mute(client_with_token(room, identity="anyone"), room)

    assert response.status_code == 200


@mock.patch.object(SubtitleService, "start_subtitle")
def test_api_rooms_viewers_subtitles_refused_to_viewers(
    mock_start, viewers_enabled, settings
):
    """A viewer cannot start the subtitles."""
    settings.ROOM_SUBTITLE_ENABLED = True
    room = RoomFactory()

    response = client_with_token(room, identity="viewer").post(
        f"/api/v1.0/rooms/{room.id}/start-subtitle/"
    )

    assert response.status_code == 403
    mock_start.assert_not_called()


@mock.patch.object(SubtitleService, "start_subtitle")
def test_api_rooms_viewers_subtitles_by_seat_holder(
    mock_start, viewers_enabled, settings
):
    """A participant holding a seat can start the subtitles."""
    settings.ROOM_SUBTITLE_ENABLED = True
    room = RoomFactory()
    SeatService().activate(room.id, "speaker", {"sid": "PA_speaker"}, force=True)

    response = client_with_token(room, identity="speaker").post(
        f"/api/v1.0/rooms/{room.id}/start-subtitle/"
    )

    assert response.status_code == 200
    mock_start.assert_called_once()


@mock.patch.object(SubtitleService, "start_subtitle")
def test_api_rooms_viewers_subtitles_by_owner(mock_start, viewers_enabled, settings):
    """Owners can start the subtitles, their seat is not needed."""
    settings.ROOM_SUBTITLE_ENABLED = True
    user = UserFactory()
    room = RoomFactory(users=[(user, "owner")])

    response = client_with_token(room, user=user).post(
        f"/api/v1.0/rooms/{room.id}/start-subtitle/"
    )

    assert response.status_code == 200


def update_participant(room, identity, **payload):
    """Update a participant as the owner of the room."""
    owner = UserFactory()
    room.accesses.create(user=owner, role="owner")
    client = APIClient()
    client.force_login(owner)
    return client.post(
        f"/api/v1.0/rooms/{room.id}/update-participant/",
        {"participant_identity": identity, **payload},
        format="json",
    )


def test_api_rooms_viewers_update_cannot_promote_viewer(
    viewers_enabled, mock_livekit_client
):
    """Granting publish rights to the room keeps viewers as viewers."""
    room = RoomFactory()
    identity = str(uuid4())

    response = update_participant(
        room,
        identity,
        permission={"can_publish": True, "can_publish_sources": ["camera"]},
        attributes={"viewer": "false", "handRaisedAt": ""},
    )

    assert response.status_code == 200
    (request,), _ = mock_livekit_client.room.update_participant.call_args
    assert request.permission.can_publish is False
    assert not request.permission.can_publish_sources
    assert request.permission.can_subscribe is True
    assert request.attributes == {"viewer": "true", "handRaisedAt": ""}


def test_api_rooms_viewers_update_seat_holder(viewers_enabled, mock_livekit_client):
    """Seat holders get the permission asked for."""
    room = RoomFactory()
    identity = str(uuid4())
    SeatService().activate(room.id, identity, {"sid": "PA_x"}, force=True)

    response = update_participant(
        room,
        identity,
        permission={"can_publish": True, "can_publish_sources": ["camera"]},
        attributes={"viewer": "true"},
    )

    assert response.status_code == 200
    (request,), _ = mock_livekit_client.room.update_participant.call_args
    assert request.permission.can_publish is True
    assert request.attributes == {"viewer": "false"}


@mock.patch(
    "core.services.participants_management.ParticipantsManagement.check_if_in_meeting_cached",
    return_value=True,
)
def test_api_rooms_viewers_lobby_refused_to_viewers(mock_present, viewers_enabled):
    """In a trusted room, a viewer cannot let people in."""
    user = UserFactory()
    room = RoomFactory(access_level=RoomAccessLevel.TRUSTED)
    client = APIClient()
    client.force_login(user)

    response = client.get(f"/api/v1.0/rooms/{room.id}/waiting-participants/")
    assert response.status_code == 403

    SeatService().activate(room.id, str(user.sub), {"sid": "PA_x"}, force=True)

    response = client.get(f"/api/v1.0/rooms/{room.id}/waiting-participants/")
    assert response.status_code == 200
