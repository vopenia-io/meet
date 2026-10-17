import { useTranslation } from 'react-i18next'
import { MenuItem } from 'react-aria-components'
import { RiEyeLine } from '@remixicon/react'
import type { Participant } from 'livekit-client'
import { useRoomContext } from '@livekit/components-react'
import { HStack } from '@/styled-system/jsx'
import { menuRecipe } from '@/primitives/menuRecipe'
import { reportError } from '@/features/analytics/telemetry'
import { useViewersActions } from '../api/useViewersActions'
import { getIsLastAuthenticatedSpeaker } from '../utils'

/**
 * Sends a participant back to viewers, the local participant included. The
 * last authenticated participant cannot: someone must stay able to let
 * viewers speak.
 */
export const BecomeViewerMenuItem = ({
  participant,
  variant,
}: {
  participant: Participant
  variant?: 'light' | 'dark'
}) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'viewers.becomeViewer' })
  const room = useRoomContext()
  const { becomeViewer, demoteParticipant } = useViewersActions()

  const isLast = getIsLastAuthenticatedSpeaker(room, participant)
  const name = participant.name || participant.identity

  const onAction = async () => {
    try {
      if (participant.isLocal) await becomeViewer(participant.identity)
      else await demoteParticipant(participant.identity)
    } catch (e) {
      reportError('generic_failure', e, { context: 'become_viewer' })
    }
  }

  return (
    <MenuItem
      aria-label={participant.isLocal ? t('self') : t('ariaLabel', { name })}
      className={menuRecipe({ icon: true, variant }).item}
      isDisabled={isLast}
      onAction={onAction}
    >
      <HStack gap={0.25}>
        <RiEyeLine size={20} aria-hidden />
        {isLast ? t('lastAuthenticated') : t('label')}
      </HStack>
    </MenuItem>
  )
}
