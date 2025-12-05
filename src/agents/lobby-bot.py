"""Lobby Bot Agent - Manages SIP calls in lobby rooms.

This agent joins SIP lobby rooms (rooms with prefix "sip-lobby-") and waits
for the user to accept the call before answering. This keeps the phone
ringing until the user accepts.

How it works:
1. SIP call arrives → livekit-sip creates lobby room (phone rings)
2. Agent joins the lobby room but does NOT publish audio track yet
3. Backend sends push notification to user
4. User accepts → backend sets room metadata to {"status": "accepted"}
5. Agent sees metadata change → publishes audio track
6. livekit-sip subscribes to track → answers the call (phone stops ringing)
7. Backend transfers call to meeting room

The agent stays connected until:
- The call is transferred (participant leaves the lobby)
- The caller hangs up (room is closed)
- A timeout is reached (no answer within RINGING_TIMEOUT)
"""

import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobRequest,
    WorkerOptions,
    WorkerPermissions,
    cli,
)

load_dotenv()

logger = logging.getLogger("lobby-bot")

# Agent configuration
LOBBY_BOT_AGENT_NAME = os.getenv("LOBBY_BOT_AGENT_NAME", "lobby-bot")
LOBBY_ROOM_PREFIX = os.getenv("LOBBY_ROOM_PREFIX", "sip-lobby-")
# How long to wait for user to accept before hanging up (seconds)
RINGING_TIMEOUT = int(os.getenv("LOBBY_RINGING_TIMEOUT", "60"))


def is_lobby_room(room_name: str) -> bool:
    """Check if a room is a SIP lobby room."""
    return room_name.startswith(LOBBY_ROOM_PREFIX)


async def entrypoint(ctx: JobContext):
    """Join the lobby room and wait for user to accept before answering.

    The bot waits for room metadata to be set to {"status": "accepted"}
    before publishing an audio track. Publishing the track triggers
    livekit-sip to answer the call.
    """
    logger.info(f"Lobby bot joining room: {ctx.room.name}")

    # Create an audio source (48kHz, mono - standard for voice)
    audio_source = rtc.AudioSource(sample_rate=48000, num_channels=1)

    # Create a local audio track from the source - but don't publish yet
    track = rtc.LocalAudioTrack.create_audio_track("lobby-audio", audio_source)

    # Track state
    call_accepted = asyncio.Event()
    track_published = False

    async def publish_track_and_answer():
        """Publish audio track to trigger livekit-sip to answer the call."""
        nonlocal track_published
        if track_published:
            return

        track_published = True
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        publication = await ctx.room.local_participant.publish_track(track, options)

        logger.info(
            f"Published audio track in {ctx.room.name} - call will be answered, "
            f"track_sid={publication.sid}"
        )

    @ctx.room.on("room_metadata_changed")
    def on_metadata_changed(old_metadata: str, new_metadata: str):
        """Watch for room metadata changes to detect user acceptance."""
        logger.info(f"Room metadata changed in {ctx.room.name}: old={old_metadata!r}, new={new_metadata!r}")
        metadata = new_metadata  # Use the NEW metadata value

        if not metadata:
            return

        try:
            data = json.loads(metadata)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in room metadata: {metadata}")
            return

        if data.get("status") == "accepted":
            logger.info(f"Call accepted in {ctx.room.name}!")
            call_accepted.set()
            # Schedule track publishing (can't await in sync callback)
            asyncio.create_task(publish_track_and_answer())

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        """Log when we subscribe to a track."""
        logger.info(
            f"Subscribed to track in {ctx.room.name}: "
            f"kind={track.kind}, sid={track.sid}, participant={participant.identity}"
        )

        # Check if this is a SIP participant
        sip_call_id = participant.attributes.get("sip.callID", "")
        if sip_call_id:
            logger.info(
                f"SIP participant track: call_id={sip_call_id}, "
                f"caller={participant.attributes.get('sip.phoneNumber', 'unknown')}"
            )

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        """Log when a participant leaves - usually means call ended or transferred."""
        logger.info(f"Participant left {ctx.room.name}: {participant.identity}")

    # Connect to the room with audio subscription enabled
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    logger.info(
        f"Lobby bot connected to {ctx.room.name}, "
        f"participants: {len(ctx.room.remote_participants)}, "
        f"waiting for user to accept (timeout: {RINGING_TIMEOUT}s)"
    )

    # Check if call was already accepted (metadata set before we connected)
    if ctx.room.metadata:
        logger.info(f"Initial room metadata: {ctx.room.metadata}")
        try:
            data = json.loads(ctx.room.metadata)
            if data.get("status") == "accepted":
                logger.info("Call was already accepted, publishing track immediately")
                await publish_track_and_answer()
        except json.JSONDecodeError:
            pass

    # Log existing participants
    for participant in ctx.room.remote_participants.values():
        sip_call_id = participant.attributes.get("sip.callID", "")
        logger.info(
            f"Existing participant: {participant.identity}, "
            f"sip_call_id={sip_call_id or 'not SIP'}"
        )

    # Wait for call to be accepted or timeout
    try:
        await asyncio.wait_for(call_accepted.wait(), timeout=RINGING_TIMEOUT)
        logger.info(f"Call accepted in {ctx.room.name}, waiting for transfer...")
    except asyncio.TimeoutError:
        logger.warning(
            f"Ringing timeout ({RINGING_TIMEOUT}s) reached in {ctx.room.name}, "
            "call was not accepted"
        )
        # The call will be hung up when the agent disconnects
        return

    # Keep the agent running until the room is closed or call is transferred
    # LiveKit agents framework handles the lifecycle automatically


async def handle_lobby_bot_job_request(job_req: JobRequest) -> None:
    """Accept job requests only for lobby rooms."""
    room_name = job_req.room.name

    # Only accept jobs for lobby rooms
    if not is_lobby_room(room_name):
        logger.debug(f"Ignoring non-lobby room: {room_name}")
        await job_req.reject()
        return

    # Generate unique identity for this bot instance
    bot_identity = f"{LOBBY_BOT_AGENT_NAME}-{room_name}"

    logger.info(f"Accepting lobby bot job for room: {room_name}")
    await job_req.accept(identity=bot_identity)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            request_fnc=handle_lobby_bot_job_request,
            agent_name=LOBBY_BOT_AGENT_NAME,
            # NOT hidden - livekit-sip needs to see this participant to trigger subscribed.Break()
            # Hidden participants don't trigger OnParticipantConnected or OnTrackPublished callbacks
            permissions=WorkerPermissions(hidden=False),
        )
    )
