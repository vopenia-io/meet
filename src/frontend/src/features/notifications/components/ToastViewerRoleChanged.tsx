import { useToast } from 'react-aria'
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { HStack } from '@/styled-system/jsx'
import { type ToastProps } from './Toast'
import { StyledToastContainer } from './StyledToastContainer'

/** Tells the local participant they became a participant, or a viewer again. */
export function ToastViewerRoleChanged({
  state,
  ...props
}: Readonly<ToastProps>) {
  const { t } = useTranslation('notifications', {
    keyPrefix: 'viewerRoleChanged',
  })
  const ref = useRef(null)
  const { toastProps, contentProps } = useToast(props, state, ref)

  return (
    <StyledToastContainer {...toastProps} ref={ref}>
      <HStack
        justify="center"
        alignItems="center"
        {...contentProps}
        padding={14}
        gap={0}
      >
        {t(props.toast.content.isViewer ? 'viewer' : 'participant')}
      </HStack>
    </StyledToastContainer>
  )
}
