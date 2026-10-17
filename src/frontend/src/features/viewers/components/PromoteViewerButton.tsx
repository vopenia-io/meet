import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Participant } from 'livekit-client'
import { Button } from '@/primitives'
import { reportError } from '@/features/analytics/telemetry'
import { useViewersActions } from '../api/useViewersActions'

/** Lets a viewer with a raised hand speak. */
export const PromoteViewerButton = ({
  participant,
}: {
  participant: Participant
}) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'viewers' })
  const { promoteViewer } = useViewersActions()
  const [isPending, setIsPending] = useState(false)
  const name = participant.name || participant.identity

  const promote = async () => {
    setIsPending(true)
    try {
      await promoteViewer(participant.identity)
    } catch (e) {
      reportError('generic_failure', e, { context: 'promote_viewer' })
    } finally {
      setIsPending(false)
    }
  }

  return (
    <Button
      size="sm"
      variant="primary"
      isDisabled={isPending}
      onPress={promote}
      aria-label={t('promote.ariaLabel', { name })}
      data-attr="participants-promote-viewer"
    >
      {t('promote.label')}
    </Button>
  )
}
