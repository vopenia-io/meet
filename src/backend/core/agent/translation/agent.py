import asyncio
import json
import uuid

from livekit import agents, rtc
from livekit.agents import WorkerOptions, WorkerPermissions, cli

from livekit.agents.stt import SpeechEventType, SpeechEvent
from typing import AsyncIterable
from livekit.plugins import gladia
from pydantic import BaseModel

from core.services.translation import TranslationMeta


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    
    room = ctx.room

    print(f"Connected to room: {room.name} as agent: {room.local_participant.identity}")
    
    metadata = json.loads(ctx.job.metadata) if ctx.job.metadata else {}
    meta = TranslationMeta.from_dict(metadata)
    print("metadata:", meta)

    langs: set[str] = meta.lang
    if not langs or len(langs) == 0:
        langs = {"en"}
    if isinstance(langs, str):
        langs = {langs} # pyright: ignore[reportUnhashable]
    if isinstance(langs, list):
        langs = set(langs)
    if not isinstance(langs, set):
        raise ValueError("Languages must be a set")
    if not all(isinstance(lang, str) for lang in langs):
        raise ValueError("All languages must be strings")

    stt_impl = gladia.STT(
      languages=None,
      translation_enabled=True,
      interim_results=False,
      translation_target_languages=list(langs),
      energy_filter=False
    )


    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.RemoteTrack, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        print(f"Subscribed to track: {track.name}")
        if (room.local_participant.identity != participant.identity):
          asyncio.create_task(process_track(track, participant))

    async def process_track(track: rtc.RemoteTrack, participant: rtc.RemoteParticipant):
        stt_stream = stt_impl.stream()
        audio_stream = rtc.AudioStream(track)

        async with asyncio.TaskGroup() as tg:
            # Create task for processing STT stream
            stt_task = tg.create_task(process_stt_stream(stt_stream, participant, track))

            # Process audio stream
            async for audio_event in audio_stream:
                stt_stream.push_frame(audio_event.frame)

            # Indicates the end of the audio stream
            stt_stream.end_input()

            # Wait for STT processing to complete
            await stt_task

    async def process_stt_stream(stream: AsyncIterable[SpeechEvent], participant: rtc.Participant, track: rtc.RemoteTrack):

        try:
            # Creating writer
            # writer = await room.local_participant.stream_text(
            #   topic="transcription",
            #   attributes={
            #       "lk.transcribed_track_id": track.sid,
            #       "lk.transcribed_participant_id": participant.identity
            #   }
            # )

            async for event in stream:
                if event.type == SpeechEventType.FINAL_TRANSCRIPT:
                    print(f"Final transcript: {event.alternatives[0].text}")
                    #await writer.write(event.alternatives[0].text)
                    await room.local_participant.send_text(
                      topic="lk.transcription",
                      attributes={
                          "lk.segment_id": str(uuid.uuid4()),
                          "lk.transcribed_track_id": track.sid,
                          "lk.transcribed_participant_id": participant.identity,
                          "lk.transcribed_participant_name": participant.name,
                          "lk.language": event.alternatives[0].language
                      },
                      text=event.alternatives[0].text
                    )
                elif event.type == SpeechEventType.INTERIM_TRANSCRIPT:
                    print(f"Interim transcript: {event.alternatives[0].text}")
                elif event.type == SpeechEventType.START_OF_SPEECH:
                    print("Start of speech")
                elif event.type == SpeechEventType.END_OF_SPEECH:
                    print("End of speech")
        finally:
            await stream.aclose()
            # await writer.aclose()


