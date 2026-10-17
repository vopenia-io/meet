"""
Test rooms API endpoints in the Meet core app: letting viewers speak.
"""

# pylint: disable=redefined-outer-name,unused-argument,no-name-in-module

from unittest import mock

from django.contrib.auth.models import AnonymousUser

import pytest
from livekit.api import TwirpError
from livekit.protocol.models import ParticipantInfo
from rest_framework.test import APIClient

from ... import utils
from ...factories import RoomFactory, UserFactory
from ...services.seats import SeatService

pytestmark = pytest.mark.django_db


@pytest.fixture
def viewers_enabled(settings):
    """Enable viewers."""
    settings.VIEWERS_ENABLED = True


@pytest.fixture
def livekit_participants():
    """Participants LiveKit knows, by identity; LiveKit calls are mocked."""
    participants = {}

    async def get_participant(request):
        try:
            return participants[request.identity]
        except KeyError as e:
            raise TwirpError(code="not_found", msg="not found", status=404) from e

    with mock.patch("core.utils.create_livekit_client") as mock_create:
        client = mock.AsyncMock()
        client.room.get_participant.side_effect = get_participant
        mock_create.return_value = client
        participants["client"] = client
        yield participants


def join(participants, room, identity, viewer, authenticated=False, **kwargs):
    """Make someone a participant of the LiveKit room, holding a seat or not."""
    participants[identity] = ParticipantInfo(
        identity=identity,
        sid=f"PA_{identity}",
        attributes={
            "viewer": "true" if viewer else "false",
            "is_authenticated": "true" if authenticated else "false",
            **kwargs.pop("attributes", {}),
        },
        **kwargs,
    )
    if not viewer:
        SeatService().activate(
            room.id,
            identity,
            {"sid": f"PA_{identity}", "auth": authenticated},
            force=True,
        )


def logged_in(user):
    """API client with a session for the user."""
    client = APIClient()
    client.force_login(user)
    return client


def with_token(room, identity):
    """API client with an anonymous LiveKit token for the room."""
    token = utils.generate_token(
        room=str(room.id), user=AnonymousUser(), participant_id=identity
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def post(client, room, action, identity):
    """Call a role change endpoint."""
    return client.post(
        f"/api/v1.0/rooms/{room.id}/{action}/",
        {"participant_identity": identity},
        format="json",
    )


def last_update(participants):
    """The last UpdateParticipant request sent to LiveKit."""
    (request,), _ = participants["client"].room.update_participant.call_args
    return request


# promote-viewer


def test_promote_viewer(viewers_enabled, livekit_participants):
    """An authenticated participant lets a viewer speak, even beyond the threshold."""
    user = UserFactory()
    room = RoomFactory(configuration={"viewers_threshold": 1})
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(livekit_participants, room, "viewer", viewer=True)

    response = post(logged_in(user), room, "promote-viewer", "viewer")

    assert response.status_code == 200
    assert SeatService().has_seat(room.id, "viewer")
    request = last_update(livekit_participants)
    assert request.identity == "viewer"
    assert request.permission.can_publish is True
    assert request.permission.can_subscribe is True
    assert request.permission.can_publish_data is True
    assert dict(request.attributes) == {"viewer": "false", "handRaisedAt": ""}


def test_promote_viewer_by_viewer(viewers_enabled, livekit_participants):
    """An authenticated viewer cannot let another viewer speak."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=True, authenticated=True)
    join(livekit_participants, room, "viewer", viewer=True)

    response = post(logged_in(user), room, "promote-viewer", "viewer")

    assert response.status_code == 403
    livekit_participants["client"].room.update_participant.assert_not_called()


def test_promote_viewer_anonymous(viewers_enabled, livekit_participants):
    """Unauthenticated participants cannot let viewers speak."""
    room = RoomFactory()
    join(livekit_participants, room, "anon", viewer=False)
    join(livekit_participants, room, "viewer", viewer=True)

    response = post(with_token(room, "anon"), room, "promote-viewer", "viewer")

    assert response.status_code in (401, 403)


def test_promote_viewer_by_owner(viewers_enabled, livekit_participants):
    """Owners can let viewers speak."""
    user = UserFactory()
    room = RoomFactory(users=[(user, "owner")])
    join(livekit_participants, room, "viewer", viewer=True)

    assert post(logged_in(user), room, "promote-viewer", "viewer").status_code == 200


def test_promote_participant(viewers_enabled, livekit_participants):
    """Only viewers can be promoted."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(livekit_participants, room, "speaker", viewer=False)

    response = post(logged_in(user), room, "promote-viewer", "speaker")

    assert response.status_code == 409


def test_promote_viewer_without_sources(viewers_enabled, livekit_participants):
    """No viewer is promoted in a room where nobody can publish."""
    user = UserFactory()
    room = RoomFactory(configuration={"can_publish_sources": []})
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(livekit_participants, room, "viewer", viewer=True)

    response = post(logged_in(user), room, "promote-viewer", "viewer")

    assert response.status_code == 409
    assert not SeatService().has_seat(room.id, "viewer")


def test_promote_unknown_participant(viewers_enabled, livekit_participants):
    """A participant gone in the meantime is not found."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)

    assert post(logged_in(user), room, "promote-viewer", "gone").status_code == 404


def test_promote_viewer_livekit_failure(viewers_enabled, livekit_participants):
    """The seat given is taken back when LiveKit fails."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(livekit_participants, room, "viewer", viewer=True)
    livekit_participants["client"].room.update_participant.side_effect = TwirpError(
        code="internal", msg="boom", status=500
    )

    response = post(logged_in(user), room, "promote-viewer", "viewer")

    assert response.status_code == 500
    assert not SeatService().has_seat(room.id, "viewer")


def test_promote_viewer_disabled(settings, livekit_participants):
    """Rooms without viewers have nobody to promote."""
    settings.VIEWERS_ENABLED = False
    user = UserFactory()
    room = RoomFactory(users=[(user, "owner")])

    assert post(logged_in(user), room, "promote-viewer", "viewer").status_code == 404


# demote-participant


def test_demote_self(viewers_enabled, livekit_participants):
    """Anyone can go back to viewers, with their LiveKit token."""
    room = RoomFactory()
    join(livekit_participants, room, "anon", viewer=False)

    response = post(with_token(room, "anon"), room, "demote-participant", "anon")

    assert response.status_code == 200
    assert not SeatService().has_seat(room.id, "anon")
    request = last_update(livekit_participants)
    assert request.permission.can_publish is False
    assert request.permission.can_subscribe is True
    assert dict(request.attributes) == {"viewer": "true"}


def test_demote_other_by_anonymous(viewers_enabled, livekit_participants):
    """Unauthenticated participants can only change their own role."""
    room = RoomFactory()
    join(livekit_participants, room, "anon", viewer=False)
    join(livekit_participants, room, "other", viewer=False)

    response = post(with_token(room, "anon"), room, "demote-participant", "other")

    assert response.status_code == 403
    assert SeatService().has_seat(room.id, "other")


def test_demote_other_by_authenticated(viewers_enabled, livekit_participants):
    """An authenticated participant can send someone back to viewers."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(livekit_participants, room, "other", viewer=False)

    response = post(logged_in(user), room, "demote-participant", "other")

    assert response.status_code == 200
    assert not SeatService().has_seat(room.id, "other")


def test_demote_last_authenticated(viewers_enabled, livekit_participants):
    """The last authenticated participant cannot go back to viewers."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(livekit_participants, room, "anon", viewer=False)

    response = post(logged_in(user), room, "demote-participant", str(user.sub))

    assert response.status_code == 409
    assert SeatService().has_seat(room.id, str(user.sub))


def test_demote_owner_by_participant(viewers_enabled, livekit_participants):
    """Only owners and administrators send an owner back to viewers."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(
        livekit_participants,
        room,
        "owner",
        viewer=False,
        authenticated=True,
        attributes={"room_role": "owner"},
    )

    response = post(logged_in(user), room, "demote-participant", "owner")

    assert response.status_code == 403


def test_demote_phone_caller(viewers_enabled, livekit_participants):
    """Phone callers always remain participants."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(livekit_participants, room, "sip", viewer=False, kind=ParticipantInfo.Kind.SIP)

    assert post(logged_in(user), room, "demote-participant", "sip").status_code == 400


def test_demote_viewer(viewers_enabled, livekit_participants):
    """A viewer is already a viewer."""
    room = RoomFactory()
    join(livekit_participants, room, "viewer", viewer=True)

    response = post(with_token(room, "viewer"), room, "demote-participant", "viewer")

    assert response.status_code == 409


def test_demote_token_for_another_room(viewers_enabled, livekit_participants):
    """A LiveKit token only works in its own room."""
    room = RoomFactory()
    other_room = RoomFactory()
    join(livekit_participants, room, "anon", viewer=False)

    response = post(with_token(other_room, "anon"), room, "demote-participant", "anon")

    assert response.status_code == 403


# take-seat


def test_take_seat(viewers_enabled, livekit_participants):
    """With no authenticated participant, an authenticated viewer takes a seat."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=True, authenticated=True)
    join(livekit_participants, room, "anon", viewer=False)

    response = post(logged_in(user), room, "take-seat", "anon")

    assert response.status_code == 200
    assert SeatService().has_seat(room.id, str(user.sub))
    assert not SeatService().has_seat(room.id, "anon")
    updates = [
        (request.identity, request.attributes["viewer"])
        for (request,), _ in livekit_participants[
            "client"
        ].room.update_participant.call_args_list
    ]
    assert updates == [("anon", "true"), (str(user.sub), "false")]


def test_take_seat_with_authenticated_participant(
    viewers_enabled, livekit_participants
):
    """No seat is taken while an authenticated participant can let viewers in."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=True, authenticated=True)
    join(livekit_participants, room, "auth", viewer=False, authenticated=True)
    join(livekit_participants, room, "anon", viewer=False)

    response = post(logged_in(user), room, "take-seat", "anon")

    assert response.status_code == 409
    assert SeatService().has_seat(room.id, "anon")


def test_take_seat_by_participant(viewers_enabled, livekit_participants):
    """A participant already holds a seat."""
    user = UserFactory()
    room = RoomFactory()
    join(livekit_participants, room, str(user.sub), viewer=False, authenticated=True)
    join(livekit_participants, room, "anon", viewer=False)

    assert post(logged_in(user), room, "take-seat", "anon").status_code == 409


def test_take_seat_anonymous(viewers_enabled, livekit_participants):
    """Unauthenticated viewers cannot take a seat."""
    room = RoomFactory()
    join(livekit_participants, room, "viewer", viewer=True)
    join(livekit_participants, room, "anon", viewer=False)

    response = post(with_token(room, "viewer"), room, "take-seat", "anon")

    assert response.status_code in (401, 403)
