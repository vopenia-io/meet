import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useRemoteParticipants,
  useRoomContext,
} from '@livekit/components-react'
import { type Participant, ParticipantKind, RoomEvent } from 'livekit-client'
import { css } from '@/styled-system/css'
import { HStack, VStack } from '@/styled-system/jsx'
import { Button, Dialog, Field, Text } from '@/primitives'
import { useUser } from '@/features/auth/api/useUser'
import { useIsViewer } from '@/features/rooms/livekit/hooks/useIsViewer'
import { getParticipantIsViewer } from '@/features/rooms/utils/getParticipantIsViewer'
import { getParticipantIsAuthenticated } from '@/features/rooms/utils/getParticipantIsAuthenticated'
import { reportError } from '@/features/analytics/telemetry'
import { useRoomHasViewers } from '../hooks/useRoomHasViewers'
import { useLastSpokeAt } from '../hooks/useLastSpokeAt'
import { useViewersActions } from '../api/useViewersActions'
import { getAuthenticatedSpeakers, getParticipants } from '../utils'

const MINUTE = 60_000

type Choice = {
  identity: string
  name: string
  /** Minutes since the participant last spoke. */
  silentFor: number
}

/**
 * While no authenticated participant is there to let viewers speak, an
 * authenticated viewer can take the seat of an unauthenticated participant,
 * who becomes a viewer: the one silent for the longest is proposed first.
 */
export const TakeSeatPrompt = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'viewers.takeSeat' })
  const room = useRoomContext()
  const hasViewers = useRoomHasViewers()
  const isViewer = useIsViewer()
  const { isLoggedIn } = useUser()
  const getLastSpokeAt = useLastSpokeAt()
  const { takeSeat } = useViewersActions()

  const [isOpen, setIsOpen] = useState(false)
  const [choices, setChoices] = useState<Choice[]>([])
  const [selected, setSelected] = useState<string>()
  const [isPending, setIsPending] = useState(false)

  // Re-render when someone joins, leaves or changes role.
  useRemoteParticipants({
    updateOnlyOn: [
      RoomEvent.ParticipantConnected,
      RoomEvent.ParticipantDisconnected,
      RoomEvent.ParticipantAttributesChanged,
    ],
  })

  if (!hasViewers || !isViewer || !isLoggedIn) return null
  if (getAuthenticatedSpeakers(room).length > 0) return null

  const candidates = getParticipants(room).filter(
    (participant: Participant) =>
      !getParticipantIsViewer(participant) &&
      !getParticipantIsAuthenticated(participant) &&
      participant.kind !== ParticipantKind.SIP
  )

  if (candidates.length === 0) return null

  const open = () => {
    const now = Date.now()
    const sorted = candidates
      .map((participant) => ({
        identity: participant.identity,
        name: participant.name || participant.identity,
        silentFor: Math.floor((now - getLastSpokeAt(participant)) / MINUTE),
      }))
      .sort((a, b) => b.silentFor - a.silentFor)
    setChoices(sorted)
    setSelected(sorted[0]?.identity)
    setIsOpen(true)
  }

  const describe = ({ silentFor }: Choice) =>
    silentFor < 1 ? t('spokeRecently') : t('silentFor', { count: silentFor })

  const confirm = async () => {
    if (!selected) return
    setIsPending(true)
    try {
      await takeSeat(selected)
      setIsOpen(false)
    } catch (e) {
      reportError('generic_failure', e, { context: 'take_seat' })
    } finally {
      setIsPending(false)
    }
  }

  return (
    <>
      <HStack
        role="status"
        className={css({
          position: 'fixed',
          top: '1rem',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 10,
          maxWidth: 'calc(100% - 2rem)',
          backgroundColor: 'warning.subtle',
          color: 'greyscale.900',
          borderRadius: '8px',
          paddingX: '1rem',
          paddingY: '0.5rem',
          gap: '1rem',
        })}
      >
        <Text variant="sm">{t('banner')}</Text>
        <Button size="sm" variant="primary" onPress={open}>
          {t('open')}
        </Button>
      </HStack>
      <Dialog
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        title={t('title')}
        role="dialog"
      >
        <VStack alignItems="stretch" gap="1rem" maxWidth="28rem">
          <Text as="p" variant="body" margin={false}>
            {t('body')}
          </Text>
          <Field
            type="radioGroup"
            label={t('choose')}
            aria-label={t('choose')}
            value={selected}
            onChange={(value) => setSelected(value as string)}
            items={choices.map((choice) => ({
              value: choice.identity,
              label: choice.name,
              description: describe(choice),
            }))}
          />
          <HStack justify="end" gap="0.5rem">
            <Button variant="tertiary" onPress={() => setIsOpen(false)}>
              {t('cancel')}
            </Button>
            <Button variant="primary" isDisabled={isPending} onPress={confirm}>
              {t('confirm')}
            </Button>
          </HStack>
        </VStack>
      </Dialog>
    </>
  )
}
