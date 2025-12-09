import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RiPhoneFill } from '@remixicon/react'
import { Button, Text } from '@/primitives'
import { css } from '@/styled-system/css'
import { HStack, VStack } from '@/styled-system/jsx'
import { initiateCall } from '@/features/calls/api/initiateCall'
import { navigateTo } from '@/navigation/navigateTo'
import { Input as RACInput } from 'react-aria-components'

// E.164: +33612345678 or local French: 0612345678
const isValidPhoneNumber = (number: string): boolean => {
  const e164Regex = /^\+[1-9]\d{1,14}$/
  const frenchLocalRegex = /^0[1-9]\d{8}$/
  return e164Regex.test(number) || frenchLocalRegex.test(number)
}

export const OutboundCallInput = () => {
  const { t } = useTranslation('home')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cleanNumber = phoneNumber.replace(/\s/g, '')
  const isValid = isValidPhoneNumber(cleanNumber)

  const handleCall = async () => {
    if (!isValid || isLoading) return

    setIsLoading(true)
    setError(null)

    try {
      const result = await initiateCall(cleanNumber)

      // Navigate to room
      navigateTo('room', result.room.slug, {
        state: {
          initialRoomData: {
            id: result.room.id,
            name: result.room.name,
            slug: result.room.slug,
            livekit: {
              url: result.livekit.url,
              token: result.livekit.token,
              room: result.room.id,
            },
          },
          create: true,
          phoneCall: true,
        },
      })
    } catch {
      setError(t('outboundCall.error'))
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && isValid && !isLoading) {
      handleCall()
    }
  }

  return (
    <VStack
      gap="0.5rem"
      alignItems="flex-start"
      width="100%"
      maxWidth="30rem"
      className={css({ marginTop: '1.5rem' })}
    >
      <Text
        as="label"
        variant="sm"
        className={css({ fontWeight: 'medium', marginBottom: 0 })}
      >
        {t('outboundCall.label')}
      </Text>
      <HStack gap="0.5rem" width="100%">
        <RACInput
          type="tel"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('outboundCall.placeholder')}
          className={css({
            flex: 1,
            width: 'full',
            paddingY: '0.5rem',
            paddingX: '0.75rem',
            border: '1px solid',
            borderColor: 'control.border',
            color: 'control.text',
            borderRadius: 4,
            transition: 'all 200ms',
            fontSize: '1rem',
            '&:focus': {
              outline: 'none',
              borderColor: 'primary.400',
              boxShadow: '0 0 0 2px token(colors.primary.100)',
            },
          })}
        />
        <Button
          onPress={handleCall}
          isDisabled={!isValid || isLoading}
          loading={isLoading}
          aria-label={t('outboundCall.callButton')}
          className={css({
            backgroundColor: isValid ? 'success.600' : 'greyscale.300',
            borderRadius: 4,
            width: '48px',
            height: '48px',
            minWidth: '48px',
            padding: 0,
            color: 'white',
            '&[data-hovered]': {
              backgroundColor: isValid ? 'success.700' : 'greyscale.300',
            },
            '&[data-pressed]': {
              backgroundColor: 'success.800',
            },
            '&[data-disabled]': {
              backgroundColor: 'greyscale.300',
              cursor: 'not-allowed',
            },
          })}
        >
          <RiPhoneFill size={24} />
        </Button>
      </HStack>
      {error && (
        <Text variant="sm" className={css({ color: 'error.500', marginTop: 0 })}>
          {error}
        </Text>
      )}
    </VStack>
  )
}
