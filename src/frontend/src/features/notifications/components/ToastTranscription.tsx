import { useToast } from '@react-aria/toast'
import { useRef } from 'react'

import { StyledToastContainer, ToastProps } from './Toast'
import { HStack } from '@/styled-system/jsx'
import { useTranslation } from 'react-i18next'
import { NotificationType } from '../NotificationType'

export function ToastTranscription({ state, ...props }: ToastProps) {
  const { t } = useTranslation('notifications')
  const ref = useRef(null)
  const { toastProps, contentProps } = useToast(props, state, ref)
  const participant = props.toast.content.participant

  return (
    <StyledToastContainer {...toastProps} ref={ref}>
      <HStack
        justify="center"
        alignItems="center"
        {...contentProps}
        padding={14}
        gap={0}
      >
        {t(
          props.toast.content.type == NotificationType.TranscriptionStarted
            ? 'recordingStarted'
            : 'recordingStopped',
          {
            name: participant.name,
          }
        )}
      </HStack>
    </StyledToastContainer>
  )
}
