import { useTranslation } from 'react-i18next'
import { useSnapshot } from 'valtio'
import { RiPhoneFill, RiUserVoiceLine } from '@remixicon/react'
import { Button, Dialog, Text } from '@/primitives'
import { css } from '@/styled-system/css'
import { HStack } from '@/styled-system/jsx'
import {
  incomingCallStore,
  clearIncomingCall,
  setProcessing,
} from '@/stores/incomingCall'
import { acceptCall } from '../api/acceptCall'
import { declineCall } from '../api/declineCall'
import { navigateTo } from '@/navigation/navigateTo'

const formatPhoneNumber = (number: string): string => {
  if (!number) return 'Unknown'

  // US format
  if (number.startsWith('+1') && number.length === 12) {
    return `(${number.slice(2, 5)}) ${number.slice(5, 8)}-${number.slice(8)}`
  }

  // French format
  if (number.startsWith('+33') && number.length === 12) {
    const digits = number.slice(3)
    return `+33 ${digits[0]} ${digits.slice(1, 3)} ${digits.slice(3, 5)} ${digits.slice(5, 7)} ${digits.slice(7)}`
  }

  return number
}

export const IncomingCallDialog = () => {
  const { t } = useTranslation('calls')
  const { incomingCall, isProcessing } = useSnapshot(incomingCallStore)

  const handleAccept = async () => {
    if (!incomingCall) return

    setProcessing(true)
    try {
      const result = await acceptCall(incomingCall.call_id)
      clearIncomingCall()
      // Navigate to the room using the slug, skip join screen for phone calls
      // Pass all room data needed for the Conference component
      navigateTo('room', result.room.slug, {
        state: {
          initialRoomData: {
            id: result.room.id,
            name: result.room.name,
            slug: result.room.slug,
            livekit: {
              url: result.livekit.url,
              token: result.livekit.token,
              room: result.room.id, // LiveKit room name is the room UUID
            },
          },
          create: true,
          phoneCall: true, // Disable video for phone calls
        },
      })
    } catch (error) {
      console.error('Failed to accept call:', error)
      setProcessing(false)
    }
  }

  const handleDecline = async () => {
    if (!incomingCall) return

    setProcessing(true)
    try {
      await declineCall(incomingCall.call_id)
      clearIncomingCall()
    } catch (error) {
      console.error('Failed to decline call:', error)
      setProcessing(false)
    }
  }

  return (
    <Dialog
      isOpen={!!incomingCall}
      onClose={handleDecline}
      title={t('incomingCall', 'Incoming Call')}
      role="alertdialog"
    >
      <div
        className={css({
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '1.5rem',
          padding: '1rem 0',
        })}
      >
        {/* Caller icon */}
        <div
          className={css({
            width: '80px',
            height: '80px',
            borderRadius: '50%',
            backgroundColor: 'primary.100',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            animation: 'pulse 2s infinite',
          })}
        >
          <RiUserVoiceLine
            size={40}
            className={css({ color: 'primary.600' })}
          />
        </div>

        {/* Caller info */}
        <div className={css({ textAlign: 'center' })}>
          <Text
            as="span"
            variant="h2"
            className={css({ display: 'block', marginBottom: 0 })}
          >
            {formatPhoneNumber(incomingCall?.caller_number || '')}
          </Text>
          <Text
            as="p"
            variant="smNote"
            className={css({ marginTop: '0.25rem' })}
          >
            {t('callingYou', 'is calling you')}
          </Text>
        </div>

        {/* Action buttons */}
        <HStack gap="2rem" className={css({ marginTop: '0.5rem' })}>
          <Button
            variant="errorCircle"
            onPress={handleDecline}
            isDisabled={isProcessing}
            aria-label={t('decline', 'Decline')}
          >
            <RiPhoneFill
              size={28}
              style={{ transform: 'rotate(135deg)' }}
            />
          </Button>

          <Button
            variant="primary"
            onPress={handleAccept}
            isDisabled={isProcessing}
            aria-label={t('accept', 'Accept')}
            className={css({
              backgroundColor: 'success.600',
              borderRadius: '100%',
              width: '56px',
              height: '56px',
              padding: 0,
              '&[data-hovered]': {
                backgroundColor: 'success.700',
              },
              '&[data-pressed]': {
                backgroundColor: 'success.800',
              },
            })}
          >
            <RiPhoneFill size={28} />
          </Button>
        </HStack>

        {isProcessing && (
          <Text variant="sm" className={css({ color: 'gray.500' })}>
            {t('processing', 'Processing...')}
          </Text>
        )}
      </div>
    </Dialog>
  )
}
