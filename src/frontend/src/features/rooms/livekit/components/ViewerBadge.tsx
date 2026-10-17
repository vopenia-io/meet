import { useTranslation } from 'react-i18next'
import { css } from '@/styled-system/css'
import { useIsViewer } from '../hooks/useIsViewer'

/** Tells viewers why they have no microphone, camera or screen sharing. */
export const ViewerBadge = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'viewers' })
  const isViewer = useIsViewer()

  if (!isViewer) return null

  return (
    <span
      className={css({
        paddingX: '0.75rem',
        paddingY: '0.25rem',
        borderRadius: 'full',
        backgroundColor: 'primaryDark.100',
        color: 'white',
        fontSize: '0.875rem',
        whiteSpace: 'nowrap',
      })}
    >
      {t('badge')}
    </span>
  )
}
