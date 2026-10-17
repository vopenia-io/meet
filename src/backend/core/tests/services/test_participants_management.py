"""
Test participants management service.
"""

# pylint: disable=redefined-outer-name

import json
from unittest import mock

import pytest

from core.services.participants_management import ParticipantsManagement


@pytest.fixture
def mock_livekit_client():
    """Mock LiveKit API client."""
    with mock.patch("core.utils.create_livekit_client") as mock_create:
        mock_client = mock.AsyncMock()
        mock_create.return_value = mock_client
        yield mock_client


def test_update_without_metadata_keeps_participant_metadata(mock_livekit_client):
    """Updating attributes only must not send any metadata to LiveKit."""
    ParticipantsManagement().update(
        room_name="room", identity="identity", attributes={"handRaisedAt": ""}
    )

    (request,), _ = mock_livekit_client.room.update_participant.call_args
    assert request.metadata == ""
    assert request.attributes == {"handRaisedAt": ""}


def test_update_with_metadata_sends_it_serialized(mock_livekit_client):
    """Metadata passed explicitly is sent as JSON."""
    ParticipantsManagement().update(
        room_name="room", identity="identity", metadata={"role": "presenter"}
    )

    (request,), _ = mock_livekit_client.room.update_participant.call_args
    assert json.loads(request.metadata) == {"role": "presenter"}
