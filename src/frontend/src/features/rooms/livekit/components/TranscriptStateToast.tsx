import { css } from '@/styled-system/css'
import { Text } from '@/primitives'
import { useTranslation } from 'react-i18next'
import { useRoomContext } from '@livekit/components-react'
import { Spinner } from '@/primitives/Spinner'

export const TranscriptStateToast = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'recording' })

  const room = useRoomContext()
  if (!room?.isRecording) return

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
        {t('transcript')}
      </Text>
    </div>
  )
}
