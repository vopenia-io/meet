import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSnapshot } from 'valtio'
import { useIsRecording, useRoomContext } from '@livekit/components-react'
import { css } from '@/styled-system/css'
import { VStack } from '@/styled-system/jsx'
import { Button, Dialog, H, Text } from '@/primitives'
import { permissionsStore, openPermissionsDialog } from '@/stores/permissions'
import {
  closeRequestToSpeak,
  requestToSpeakStore,
} from '@/stores/requestToSpeak'
import { requestDevicePermission } from '@/features/rooms/livekit/utils/mediaPermissions'
import { useRaisedHand } from '@/features/rooms/livekit/hooks/useRaisedHand'
import { useIsViewer } from '@/features/rooms/livekit/hooks/useIsViewer'
import { JoinPreview } from '@/features/rooms/components/Join'

const allowMicrophone = async () => {
  const granted = await requestDevicePermission('audioinput', 'room')
  // Blocked by the browser or the system: explain how to unblock it.
  if (!granted) openPermissionsDialog('audioinput')
}

/**
 * A viewer asking to speak checks their microphone and camera first, in the
 * same preview as when joining: the hand can only be raised once the
 * microphone is allowed, so that the participants who let them in hear them
 * right away. Nothing is published from here.
 */
export const RequestToSpeakDialog = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'viewers.requestToSpeak' })
  const { isOpen } = useSnapshot(requestToSpeakStore)
  const { isMicrophoneGranted } = useSnapshot(permissionsStore)
  const isRecording = useIsRecording()

  const room = useRoomContext()
  const { isHandRaised, toggleRaisedHand } = useRaisedHand({
    participant: room.localParticipant,
  })

  // Let in meanwhile: there is nothing left to ask.
  const isViewer = useIsViewer()
  useEffect(() => {
    if (!isViewer) closeRequestToSpeak()
  }, [isViewer])

  const raiseHand = async () => {
    if (!isHandRaised) await toggleRaisedHand()
    closeRequestToSpeak()
  }

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => {
        requestToSpeakStore.isOpen = open
      }}
      aria-label={t('title')}
      role="dialog"
      type="flex"
      size="large"
    >
      <JoinPreview>
        <VStack alignItems="stretch" width="100%" gap="1rem">
          <H lvl={1} margin="sm" centered>
            {t('title')}
          </H>
          <Text as="p" variant="note" centered>
            {t('body')}
          </Text>
          {isRecording && (
            <Text
              as="p"
              variant="note"
              className={css({
                backgroundColor: 'danger.subtle',
                borderRadius: '8px',
                paddingX: '1rem',
                paddingY: '0.75rem',
              })}
            >
              {t('recording')}
            </Text>
          )}
          {!isMicrophoneGranted && (
            <>
              <Text as="p" variant="note" centered>
                {t('microphoneRequired')}
              </Text>
              <Button variant="secondary" fullWidth onPress={allowMicrophone}>
                {t('allowMicrophone')}
              </Button>
            </>
          )}
          <Button
            variant="primary"
            fullWidth
            isDisabled={!isMicrophoneGranted}
            onPress={raiseHand}
          >
            {t('raiseHand')}
          </Button>
          <Button variant="tertiary" fullWidth onPress={closeRequestToSpeak}>
            {t('cancel')}
          </Button>
        </VStack>
      </JoinPreview>
    </Dialog>
  )
}
