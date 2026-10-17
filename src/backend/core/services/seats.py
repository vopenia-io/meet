"""Seats of the people who can speak in a room.

Beyond a number of seats, people joining a room become viewers: they see and
hear the room but cannot publish. The seats of a room live in Redis:

- a sorted set maps each seat holder's LiveKit identity to the time its seat
  expires: a seat is pending until its holder joins, active (+inf) while they
  are connected, and kept for a grace period once they disconnect;
- a hash keeps, per identity, the participant sid and whether the holder is
  authenticated or a phone caller.

Every operation is a Lua script, so concurrent arrivals cannot take more seats
than the room has.
"""

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Iterable, Optional
from uuid import UUID

from django.conf import settings
from django.core.cache import cache

import aiohttp
from asgiref.sync import async_to_sync
from livekit.api import (  # pylint: disable=E0611
    ListParticipantsRequest,
    TwirpError,
)
from livekit.protocol.models import ParticipantInfo

from core import models, utils

logger = logging.getLogger(__name__)

# Seats keys outlive any meeting; they are deleted when the room finishes.
SEATS_KEY_TIMEOUT = 24 * 3600
# Seconds the number of seats taken is cached for the people about to join.
SEATS_TAKEN_CACHE_TIMEOUT = 5

_PURGE = """
local function purge(seats, info, now)
  local expired = redis.call('ZRANGEBYSCORE', seats, '-inf', now)
  if #expired > 0 then
    redis.call('ZREM', seats, unpack(expired))
    redis.call('HDEL', info, unpack(expired))
  end
end
local function touch(seats, info, ttl)
  redis.call('EXPIRE', seats, ttl)
  redis.call('EXPIRE', info, ttl)
end
"""

# KEYS: seats, info. ARGV: identity, now, pending_until, threshold, ttl, info.
# Returns 1 when the identity holds a seat, 0 when the room is full.
_ALLOCATE = (
    _PURGE
    + """
purge(KEYS[1], KEYS[2], ARGV[2])
local score = redis.call('ZSCORE', KEYS[1], ARGV[1])
if score then
  if score ~= 'inf' and tonumber(score) < tonumber(ARGV[3]) then
    redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
  end
  return 1
end
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[4]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
redis.call('HSET', KEYS[2], ARGV[1], ARGV[6])
touch(KEYS[1], KEYS[2], ARGV[5])
return 1
"""
)

# KEYS: seats, info. ARGV: identity, now, info, force, ttl.
# Marks the seat of a connected participant as active. Without force, only an
# identity already holding a seat is activated. Returns 1 when activated.
_ACTIVATE = (
    _PURGE
    + """
purge(KEYS[1], KEYS[2], ARGV[2])
if ARGV[4] ~= '1' and not redis.call('ZSCORE', KEYS[1], ARGV[1]) then
  return 0
end
redis.call('ZADD', KEYS[1], '+inf', ARGV[1])
redis.call('HSET', KEYS[2], ARGV[1], ARGV[3])
touch(KEYS[1], KEYS[2], ARGV[5])
return 1
"""
)

# KEYS: seats, info. ARGV: identity, sid, grace_until.
# Starts the grace period of an active seat, unless the event comes from
# another session of the same identity. A phone caller's seat is freed.
_RELEASE = """
local raw = redis.call('HGET', KEYS[2], ARGV[1])
if not raw then
  return 0
end
local info = cjson.decode(raw)
if ARGV[2] ~= '' and type(info.sid) == 'string' and info.sid ~= ARGV[2] then
  return 0
end
if info.sip then
  redis.call('ZREM', KEYS[1], ARGV[1])
  redis.call('HDEL', KEYS[2], ARGV[1])
  return 1
end
if redis.call('ZSCORE', KEYS[1], ARGV[1]) ~= 'inf' then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
return 1
"""

# KEYS: seats, info. ARGV: identity, only_pending.
_REMOVE = """
local score = redis.call('ZSCORE', KEYS[1], ARGV[1])
if not score or (ARGV[2] == '1' and score == 'inf') then
  return 0
end
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('HDEL', KEYS[2], ARGV[1])
return 1
"""

# KEYS: seats, info. ARGV: now, grace_until, present, ttl.
# Aligns the seats with the participants LiveKit reports: an active seat whose
# holder is gone starts its grace period, a present publisher gets a seat.
_RECONCILE = (
    _PURGE
    + """
purge(KEYS[1], KEYS[2], ARGV[1])
local present = cjson.decode(ARGV[3])
local by_identity = {}
for _, participant in ipairs(present) do
  by_identity[participant.identity] = participant
end
for _, member in ipairs(redis.call('ZRANGEBYSCORE', KEYS[1], '+inf', '+inf')) do
  if not by_identity[member] then
    redis.call('ZADD', KEYS[1], ARGV[2], member)
  end
end
for _, participant in ipairs(present) do
  if participant.publisher then
    redis.call('ZADD', KEYS[1], '+inf', participant.identity)
    redis.call('HSET', KEYS[2], participant.identity, cjson.encode(participant.info))
  end
end
touch(KEYS[1], KEYS[2], ARGV[4])
return 1
"""
)


class JoinRole(str, Enum):
    """Role given to a person joining a room."""

    PARTICIPANT = "participant"
    VIEWER = "viewer"


def is_viewers_enabled(room) -> bool:
    """Whether people joining the room can become viewers."""
    return settings.VIEWERS_ENABLED and isinstance(room, models.Room)


def get_threshold(room) -> int:
    """Number of people who can speak in the room."""
    configuration = room.configuration or {}
    return configuration.get("viewers_threshold") or settings.VIEWERS_DEFAULT_THRESHOLD


def is_publisher(participant) -> bool:
    """Whether a LiveKit participant should hold a seat.

    Egress and agents never do; viewers are flagged by their token attribute.
    """
    if participant.kind in (ParticipantInfo.Kind.EGRESS, ParticipantInfo.Kind.AGENT):
        return False
    return participant.attributes.get("viewer") != "true"


def seat_info(participant) -> dict:
    """Information kept about the holder of a seat."""
    info = {
        "auth": participant.attributes.get("is_authenticated") == "true",
        "sip": participant.kind == ParticipantInfo.Kind.SIP,
    }
    if participant.sid:
        info["sid"] = participant.sid
    return info


def livekit_permission(room, viewer: bool) -> dict:
    """LiveKit permission of a participant or a viewer of the room.

    UpdateParticipant replaces the whole permission, so every field is given.
    """
    sources = []
    if not viewer:
        sources = (room.configuration or {}).get("can_publish_sources")
        if sources is None:
            sources = settings.LIVEKIT_DEFAULT_SOURCES

    return {
        "can_subscribe": True,
        "can_publish": bool(sources),
        "can_publish_data": True,
        "can_publish_sources": [source.upper() for source in sources],
    }


class SeatService:
    """Allocate and track the seats of the people who can speak in a room."""

    @staticmethod
    def _redis():
        """Raw redis-py client, scripts are not exposed by the Django cache API."""
        return cache.client.get_client(write=True)

    @staticmethod
    def _keys(room_id: UUID | str) -> list[str]:
        prefix = settings.VIEWERS_KEY_PREFIX
        return [
            cache.client.make_key(f"{prefix}_{room_id!s}"),
            cache.client.make_key(f"{prefix}-info_{room_id!s}"),
        ]

    @staticmethod
    def _reconcile_key(room_id: UUID | str) -> str:
        return f"{settings.VIEWERS_KEY_PREFIX}-reconcile_{room_id!s}"

    def _run(self, script: str, room_id: UUID | str, *args) -> int:
        client = self._redis()
        return client.register_script(script)(keys=self._keys(room_id), args=args)

    def allocate(self, room_id: UUID | str, identity: str, threshold: int, **info):
        """Give a seat to an identity if the room has one left.

        Idempotent: an identity holding a seat keeps it, and a seat in its
        grace period is pending again. Returns True when the identity holds a
        seat.
        """
        now = time.time()
        return bool(
            self._run(
                _ALLOCATE,
                room_id,
                identity,
                now,
                now + settings.VIEWERS_PENDING_SEAT_TIMEOUT,
                threshold,
                SEATS_KEY_TIMEOUT,
                json.dumps(info),
            )
        )

    def activate(
        self, room_id: UUID | str, identity: str, info: dict, force: bool = False
    ) -> bool:
        """Mark the seat of a connected participant as active.

        With force, a seat is created even beyond the threshold.
        """
        return bool(
            self._run(
                _ACTIVATE,
                room_id,
                identity,
                time.time(),
                json.dumps(info),
                "1" if force else "0",
                SEATS_KEY_TIMEOUT,
            )
        )

    def release(self, room_id: UUID | str, identity: str, sid: str = "") -> bool:
        """Keep the seat of a disconnected participant for the grace period."""
        return bool(
            self._run(
                _RELEASE,
                room_id,
                identity,
                sid or "",
                time.time() + settings.VIEWERS_RECONNECT_GRACE_PERIOD,
            )
        )

    def remove(
        self, room_id: UUID | str, identity: str, only_pending: bool = False
    ) -> bool:
        """Free a seat right away, or only if its holder has not joined yet."""
        return bool(self._run(_REMOVE, room_id, identity, "1" if only_pending else "0"))

    def has_seat(self, room_id: UUID | str, identity: str) -> bool:
        """Whether an identity holds a seat, pending, active or kept."""
        score = self._redis().zscore(self._keys(room_id)[0], identity)
        return score is not None and score > time.time()

    def is_full(self, room) -> bool:
        """Whether a person joining the room now would be a viewer.

        Polled by everyone waiting to join, so the count is cached briefly.
        """
        if not is_viewers_enabled(room):
            return False

        taken = cache.get_or_set(
            f"{settings.VIEWERS_KEY_PREFIX}-taken_{room.id!s}",
            lambda: self._redis().zcount(self._keys(room.id)[0], time.time(), "+inf"),
            timeout=SEATS_TAKEN_CACHE_TIMEOUT,
        )
        return taken >= get_threshold(room)

    def clear(self, room_id: UUID | str) -> None:
        """Drop every seat of a room."""
        self._redis().delete(*self._keys(room_id))

    def reconcile(self, room_id: UUID | str, participants: Iterable) -> None:
        """Align the seats with the participants of the LiveKit room."""
        now = time.time()
        present = [
            {
                "identity": participant.identity,
                "publisher": is_publisher(participant),
                "info": seat_info(participant),
            }
            for participant in participants
        ]
        self._run(
            _RECONCILE,
            room_id,
            now,
            now + settings.VIEWERS_RECONNECT_GRACE_PERIOD,
            json.dumps(present),
            SEATS_KEY_TIMEOUT,
        )

    def reconcile_if_due(self, room_id: UUID | str) -> bool:
        """Reconcile the seats with LiveKit, at most once per interval.

        Webhooks can be lost: without this, a participant who left without a
        participant_left event would keep a seat forever. Returns True when the
        seats were reconciled.
        """
        if not cache.add(
            self._reconcile_key(room_id), 1, timeout=settings.VIEWERS_RECONCILE_INTERVAL
        ):
            return False

        try:
            participants = self._list_participants(str(room_id))
        except (TwirpError, aiohttp.ClientError, asyncio.TimeoutError):
            # Joining must not fail because LiveKit cannot be reached.
            logger.exception("Could not list the participants of room %s", room_id)
            return False

        if participants is None:
            return False

        self.reconcile(room_id, participants)
        return True

    @staticmethod
    @async_to_sync
    async def _list_participants(room_name: str) -> Optional[list]:
        """Participants of a LiveKit room, or None if the room does not exist."""
        lkapi = utils.create_livekit_client()
        try:
            response = await lkapi.room.list_participants(
                ListParticipantsRequest(room=room_name)
            )
        except TwirpError as e:
            if e.code == "not_found":
                return None
            raise
        finally:
            await lkapi.aclose()
        return list(response.participants)

    def assign_role(
        self, room, identity: str, user, role: Optional[str] = None
    ) -> JoinRole:
        """Decide whether a person joining the room can speak.

        Owners and administrators always can: their seat is counted when they
        join, even beyond the threshold.
        """
        if models.RoleChoices.check_owner_role(
            role
        ) or models.RoleChoices.check_administrator_role(role):
            return JoinRole.PARTICIPANT

        threshold = get_threshold(room)
        info = {"auth": bool(user.is_authenticated), "sip": False}

        if self.allocate(room.id, identity, threshold, **info):
            return JoinRole.PARTICIPANT

        # The room looks full: make sure no seat is held by someone gone.
        if self.reconcile_if_due(room.id) and self.allocate(
            room.id, identity, threshold, **info
        ):
            return JoinRole.PARTICIPANT

        return JoinRole.VIEWER
