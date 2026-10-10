import { useTranslation } from 'react-i18next'
import { Text } from '@/primitives'
import { css } from '@/styled-system/css'
import { HStack } from '@/styled-system/jsx'
import { RecordingMode } from '@/features/recording'
import { useRecordingWaitingForTracks } from '@/features/recording/hooks/useRecordingWaitingForTracks'
import { useRecordingStatuses } from '@/features/recording/hooks/useRecordingStatuses'
import { StyledToastContainer } from './StyledToastContainer'

export const RecordingWaitingForTracksNotification = () => {
  const { isStarting: isTranscriptStarting } = useRecordingStatuses(
    RecordingMode.Transcript
  )
  const { isStarting: isScreenRecordingStarting } = useRecordingStatuses(
    RecordingMode.ScreenRecording
  )
  // Listing the room's tracks follows every participant event: only do it
  // while a recording is starting.
  if (!isTranscriptStarting && !isScreenRecordingStarting) return null
  return <WaitingForTracksNotification />
}

const WaitingForTracksNotification = () => {
  const { t } = useTranslation('notifications')
  const isTranscriptWaiting = useRecordingWaitingForTracks(
    RecordingMode.Transcript
  )
  const isScreenRecordingWaiting = useRecordingWaitingForTracks(
    RecordingMode.ScreenRecording
  )

  if (!isTranscriptWaiting && !isScreenRecordingWaiting) return null

  return (
    <StyledToastContainer role="status">
      <HStack padding={14}>
        <Text
          margin={false}
          className={css({
            maxWidth: '22rem',
            wordBreak: 'break-word',
            overflowWrap: 'break-word',
            whiteSpace: 'normal',
          })}
        >
          {t(
            isTranscriptWaiting
              ? 'transcript.waitingForTracks'
              : 'screenRecording.waitingForTracks'
          )}
        </Text>
      </HStack>
    </StyledToastContainer>
  )
}
