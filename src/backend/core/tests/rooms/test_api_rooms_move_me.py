"""
Test rooms API endpoints: a participant asking to be moved to another SFU node.
"""

# pylint: disable=redefined-outer-name,unused-argument

from unittest import mock

from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import utils
from core.factories import RoomFactory, UserFactory
from core.services import ilimo_callservice

pytestmark = pytest.mark.django_db


@pytest.fixture
def room():
    """Create a room."""
    return RoomFactory()


@pytest.fixture
def token(room):
    """Generate a real LiveKit JWT for a user in the room."""
    return utils.generate_token(room=str(room.id), user=UserFactory())


@pytest.fixture
def mock_move():
    """Mock the call to Ilimo's CallService."""
    with mock.patch(
        "core.services.ilimo_callservice.move_participant", new_callable=mock.AsyncMock
    ) as mock_move:
        mock_move.return_value = {"node": "node-b", "region": "de"}
        yield mock_move


def _post(room, token, data=None):
    client = APIClient()
    url = reverse("rooms-move-me", kwargs={"pk": room.id})
    return client.post(
        url, data or {}, format="json", HTTP_AUTHORIZATION=f"X-LiveKit-Token {token}"
    )


def test_move_me_disabled_by_default(mock_move, room, token):
    """The command does not exist unless it is enabled."""
    response = _post(room, token, {"region": "de"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    mock_move.assert_not_called()


def test_move_me_to_a_region(mock_move, room, token, settings):
    """A participant asks for a region: the SFU is asked, its choice returned."""
    settings.ROOM_MOVE_ME_ENABLED = True

    response = _post(room, token, {"region": "de"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "success", "node": "node-b", "region": "de"}
    mock_move.assert_called_once()
    assert mock_move.call_args.kwargs["room_name"] == str(room.id)
    assert mock_move.call_args.kwargs["region"] == "de"
    assert mock_move.call_args.kwargs["identity"]


def test_move_me_without_a_region(mock_move, room, token, settings):
    """Without a region, the SFU keeps the participant in its own."""
    settings.ROOM_MOVE_ME_ENABLED = True

    response = _post(room, token)

    assert response.status_code == status.HTTP_200_OK
    assert mock_move.call_args.kwargs["region"] == ""


def test_move_me_rejects_a_malformed_region(mock_move, room, token, settings):
    """A region is a short name, nothing else."""
    settings.ROOM_MOVE_ME_ENABLED = True

    response = _post(room, token, {"region": "de; drop"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    mock_move.assert_not_called()


def test_move_me_without_another_node(mock_move, room, token, settings):
    """No other node, or an SFU that cannot move: a conflict, not a failure."""
    settings.ROOM_MOVE_ME_ENABLED = True
    mock_move.side_effect = ilimo_callservice.MoveUnavailable("no other node")

    response = _post(room, token)

    assert response.status_code == status.HTTP_409_CONFLICT


def test_move_me_participant_not_found(mock_move, room, token, settings):
    """A participant the SFU does not know."""
    settings.ROOM_MOVE_ME_ENABLED = True
    mock_move.side_effect = ilimo_callservice.MoveParticipantNotFound("not found")

    response = _post(room, token)

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_move_me_sfu_failure(mock_move, room, token, settings):
    """The SFU does not answer."""
    settings.ROOM_MOVE_ME_ENABLED = True
    mock_move.side_effect = ilimo_callservice.MoveError("no answer")

    response = _post(room, token)

    assert response.status_code == status.HTTP_502_BAD_GATEWAY


def test_move_me_without_a_token(mock_move, room, settings):
    """Only a participant of the room, by its LiveKit token."""
    settings.ROOM_MOVE_ME_ENABLED = True
    client = APIClient()
    url = reverse("rooms-move-me", kwargs={"pk": room.id})

    response = client.post(url, {}, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    mock_move.assert_not_called()


def test_encode_move_request():
    """The request is `MoveParticipantRequest{room = 1, identity = 2, region = 4}`."""
    assert (
        ilimo_callservice.encode_move_request("room-1", "alice", "de")
        == b"\x0a\x06room-1\x12\x05alice\x22\x02de"
    )
    assert ilimo_callservice.encode_move_request("r", "a", "") == b"\x0a\x01r\x12\x01a"


def test_decode_move_response():
    """The answer is `MoveParticipantResponse{node = 1, region = 2}`."""
    assert ilimo_callservice.decode_move_response(b"\x0a\x06node-b\x12\x03gra") == {
        "node": "node-b",
        "region": "gra",
    }
    with pytest.raises(ValueError):
        ilimo_callservice.decode_move_response(b"\x0a\x06nod")
