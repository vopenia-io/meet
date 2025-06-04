import { css } from "@/styled-system/css";
import { layoutStore } from "@/stores/layout.ts";
import { useSnapshot } from "valtio";
import {useMaybeRoomContext} from "@livekit/components-react";
import {useEffect, useState} from "react";
import { TextStreamReader } from "livekit-client";
import { useTranslation } from "react-i18next";
import { captionPreferenceStore } from "@/stores/captionPreference";
import {Avatar} from "@/components/Avatar.tsx";
import { Text } from '@/primitives'

interface Segment {
  id: string,
  language: string
  participantId: string,
  participantName: string,
  text: string,
  timestamp: number
}

export const Segments = () => {

  const room = useMaybeRoomContext()
  const preference = useSnapshot(captionPreferenceStore)
  const { t, i18n } = useTranslation('settings')
  const [transcriptions, setTranscriptions] = useState<{[id: string]: Segment}>({})

  useEffect(() => {
    if (!room) {
      return
    }

    const updateTranscriptions = async (reader: TextStreamReader, participantInfo: {identity: string}) => {
      const message = await reader.readAll();

      console.log(reader.info);

      const newSegment: Segment = {
        id: reader.info.attributes?.['lk.segment_id'] ?? "",
        text: message,
        language: reader.info.attributes?.['lk.language'] ?? "",
        participantId: reader.info.attributes?.['lk.transcribed_participant_id'] ?? "",
        participantName: reader.info.attributes?.['lk.transcribed_participant_name'] ?? "",

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
      room.unregisterTextStreamHandler("lk.transcription");
    }
  }, [room])


  const layoutSnap = useSnapshot(layoutStore)
  if (!layoutSnap.showSubtitle) return

  return (
    <div className={css({
      height: '150px',
      width: '100%',
      position: 'absolute',
      bottom: '0px',
      color: 'white'
    })}>
      <ul className={css(
        {
          width: '80%',
          margin: 'auto'
        }
      )}>
        {Object.values(transcriptions)
          .sort((a, b) => b.timestamp - a.timestamp)
          .filter(a => a.language === preference.language)
          .map((segment) => (
            <li key={segment.id} className={css({
              display: "flex",
              flexDirection: 'column'
            })}>
              <span className={css({
                display: 'flex',
                flexDirection: 'row'
              })}><Avatar name={segment.participantName} bgColor={'red'} context="list" notification /> <span className={css({
                marginLeft: "10px"
              })}>{segment.participantName}</span></span>
              <Text className={css({
                fontSize: '24px'
              })}>{segment.text}</Text>
            </li>
          ))}
      </ul>
    </div>
  )
}