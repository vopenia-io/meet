import { css } from "@/styled-system/css";
import { layoutStore } from "@/stores/layout.ts";
import { useSnapshot } from "valtio";
import {useMaybeRoomContext} from "@livekit/components-react";
import {useEffect, useState} from "react";
import {Participant, RoomEvent, TextStreamReader, TrackPublication, TranscriptionSegment} from "livekit-client";
import {ParticipantInfo} from "@livekit/protocol"

interface Segment {
  id: string,
  text: string,
  timestamp: number
}

export const Segments = () => {

  const room = useMaybeRoomContext()
  const [transcriptions, setTranscriptions] = useState<{[id: string]: Segment}>({})

  useEffect(() => {
    if (!room) {
      return
    }

    // const updateTranscriptions = (
    //   segments: TranscriptionSegment[],
    //   participant?: Participant,
    //   publication?: TrackPublication
    // ) => {
    //   setTranscriptions((prev) => {
    //     const newTranscriptions = { ...prev }
    //     for (const segment of segments) {
    //       newTranscriptions[segment.id] = segment
    //     }
    //     return newTranscriptions
    //   })
    // }

    const updateTranscriptions = async (reader: TextStreamReader, participantInfo: {identity: string}) => {
      const message = await reader.readAll();
      console.log(reader.info);
      if (reader.info.attributes['lk.transcribed_track_id']) {
        console.log(`New transcription from ${participantInfo.identity}: ${message}`);
      } else {
        console.log(`New message from ${participantInfo.identity}: ${message}`);
      }

      const newSegment: Segment = {
        id: reader.info.attributes['lk.segment_id'],
        text: message,
        timestamp: reader.info.timestamp
      }

      setTranscriptions((prev) => {
        const newTranscriptions = {...prev};
        newTranscriptions[newSegment.id] = newSegment;

        return newTranscriptions;
      });
    }

    room.registerTextStreamHandler('lk.transcription', updateTranscriptions);

    return () => {
    //room.off(RoomEvent.TranscriptionReceived, updateTranscriptions)
      room.unregisterTextStreamHandler("lk.transcription");
    }
  }, [room])


  const layoutSnap = useSnapshot(layoutStore)
  if (!layoutSnap.showSubtitle) return

  return (
    <div className={css({
      backgroundColor: 'white',
      height: '150px',
      width: '100%',
      position: 'absolute',
      bottom: '0px'
    })}>
      <ul>
        {Object.values(transcriptions)
          .sort((a, b) => b.timestamp - a.timestamp)
          .map((segment) => (
            <li key={segment.id}>{segment.text}</li>
          ))}
      </ul>
    </div>
  )
}