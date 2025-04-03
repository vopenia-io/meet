import { css } from '@/styled-system/css'
import { Text } from '@/primitives'
import { useTranslation } from 'react-i18next'
import { useRoomContext } from '@livekit/components-react'
import { Spinner } from '@/primitives/Spinner'
import { useEffect, useMemo, useState } from 'react'
import { RemoteParticipant, RoomEvent } from 'livekit-client'
import { decodeNotificationDataReceived } from '@/features/notifications/utils.ts'
import { NotificationType } from '@/features/notifications/NotificationType.ts'
import { useSnapshot } from 'valtio/index'
import {
  TranscriptionStatus,
  transcriptionStore,
} from '@/stores/transcription.ts'

export const TranscriptStateToast = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'recording' })
  const room = useRoomContext()

  const transcriptionSnap = useSnapshot(transcriptionStore)

  useEffect(() => {
    if (room.isRecording) {
      transcriptionStore.status = TranscriptionStatus.STARTED
    }
  }, [])

  useEffect(() => {
    const handleDataReceived = (
      payload: Uint8Array,
      participant?: RemoteParticipant
    ) => {
      const notification = decodeNotificationDataReceived(payload)

      if (!participant || !notification) return

      switch (notification.type) {
        case NotificationType.TranscriptionStarted:
          transcriptionStore.status = TranscriptionStatus.STARTING
          break
        case NotificationType.TranscriptionStopped:
          transcriptionStore.status = TranscriptionStatus.STOPPING
          break
        default:
          return
      }
    }

    const handleRecordingStatusChanged = (status) => {
      transcriptionStore.status = status
        ? TranscriptionStatus.STARTED
        : TranscriptionStatus.STOPPED
    }

    room.on(RoomEvent.DataReceived, handleDataReceived)
    room.on(RoomEvent.RecordingStatusChanged, handleRecordingStatusChanged)

    return () => {
      room.off(RoomEvent.DataReceived, handleDataReceived)
      room.off(RoomEvent.RecordingStatusChanged, handleRecordingStatusChanged)
    }
  }, [room])

  const message = useMemo(() => {
    switch (transcriptionSnap.status) {
      case TranscriptionStatus.STOPPING:
        return t('transcriptStopping')
      case TranscriptionStatus.STARTING:
        return t('transcriptStarting')
      default:
        return t('transcriptStarted')
    }
  }, [transcriptionSnap])

  if (transcriptionSnap.status == TranscriptionStatus.STOPPED) return

  return (
    <div
      className={css({
        display: 'flex',
        position: 'fixed',
        top: '10px',
        left: '10px',
        paddingY: '0.25rem',
        paddingX: '0.75rem 0.75rem',
        backgroundColor: 'primaryDark.100',
        borderColor: 'white',
        border: '1px solid',
        color: 'white',
        borderRadius: '4px',
        gap: '0.5rem',
      })}
    >
      <Spinner size={20} variant="black" />
      <Text
        variant={'sm'}
        className={css({
          fontWeight: '500 !important',
        })}
      >
        {message}
      </Text>
    </div>
  )
}
