"""Calls to Ilimo's CallService, the part of its API LiveKit does not have.

The LiveKit SDK does not know these calls: the request is a Twirp call over
HTTP, its protobuf message written by hand (three string fields).
"""

from logging import getLogger

from django.conf import settings

import aiohttp
from livekit.api import AccessToken, VideoGrants

logger = getLogger(__name__)

MOVE_PARTICIPANT_PATH = "/twirp/ilimo.callservice.CallService/MoveParticipant"


class MoveError(Exception):
    """Moving a participant to another node failed."""


class MoveUnavailable(MoveError):
    """The SFU cannot move this participant: no other node, or not Ilimo."""


class MoveParticipantNotFound(MoveError):
    """The participant is not in the room."""


def _varint(value: int) -> bytes:
    """Encode a non-negative integer as a protobuf varint."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _string_field(number: int, text: str) -> bytes:
    """Encode a string field; an empty one is left out, as protobuf does."""
    if not text:
        return b""
    data = text.encode("utf-8")
    return _varint((number << 3) | 2) + _varint(len(data)) + data


def encode_move_request(room: str, identity: str, region: str) -> bytes:
    """Encode `MoveParticipantRequest{room = 1, identity = 2, region = 4}`.

    `node` (3) is left empty: Ilimo chooses the node.
    """
    return (
        _string_field(1, room) + _string_field(2, identity) + _string_field(4, region)
    )


def decode_move_response(payload: bytes) -> dict:
    """Decode `MoveParticipantResponse{node = 1, region = 2}`."""
    fields = {1: "", 2: ""}
    position = 0

    def varint():
        nonlocal position
        value = shift = 0
        while True:
            if position >= len(payload):
                raise ValueError("truncated protobuf message")
            byte = payload[position]
            position += 1
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7

    while position < len(payload):
        key = varint()
        number, wire_type = key >> 3, key & 0x07
        if wire_type == 2:
            length = varint()
            data = payload[position : position + length]
            if len(data) != length:
                raise ValueError("truncated protobuf message")
            position += length
            if number in fields:
                fields[number] = data.decode("utf-8")
        elif wire_type == 0:
            varint()
        else:
            raise ValueError(f"unexpected protobuf wire type {wire_type}")
    return {"node": fields[1], "region": fields[2]}


async def move_participant(room_name: str, identity: str, region: str = "") -> dict:
    """Ask Ilimo to move a participant to another node; return node and region.

    Ilimo chooses the node: the least loaded one of `region`, or of the region
    the participant is hosted in when `region` is empty, unknown or full.
    """
    configuration = settings.LIVEKIT_CONFIGURATION
    token = (
        AccessToken(configuration["api_key"], configuration["api_secret"])
        .with_identity("meet-backend")
        .with_grants(VideoGrants(room_admin=True, room=room_name))
        .to_jwt()
    )
    connector = None if settings.LIVEKIT_VERIFY_SSL else aiohttp.TCPConnector(ssl=False)
    timeout = aiohttp.ClientTimeout(total=settings.LIVEKIT_API_TIMEOUT_SECONDS)
    url = configuration["url"].rstrip("/") + MOVE_PARTICIPANT_PATH

    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.post(
                url,
                data=encode_move_request(room_name, identity, region),
                headers={
                    "Content-Type": "application/protobuf",
                    "Authorization": f"Bearer {token}",
                },
            ) as response:
                body = await response.read()
                status = response.status
    except (aiohttp.ClientError, TimeoutError) as e:
        raise MoveError("the SFU did not answer") from e

    if status == 200:
        try:
            return decode_move_response(body)
        except (ValueError, UnicodeDecodeError) as e:
            raise MoveError("the SFU answered something else than a move") from e

    message = body[:200].decode("utf-8", errors="replace")
    if status == 404 and "participant not found" in message:
        raise MoveParticipantNotFound(message)
    if status == 404:
        # No other node to move to, or an SFU without this call (LiveKit).
        raise MoveUnavailable(message)
    logger.error("MoveParticipant failed with status %s: %s", status, message)
    raise MoveError(f"the SFU refused the move ({status})")
