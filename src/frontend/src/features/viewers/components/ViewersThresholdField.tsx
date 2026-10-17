import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Field } from '@/primitives'
import { useConfig } from '@/api/useConfig'
import { usePatchRoom } from '@/features/rooms/api/patchRoom'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import { reportError } from '@/features/analytics/telemetry'

const parseThreshold = (value: string): number | null | undefined => {
  if (!value.trim()) return null
  const threshold = Number(value)
  return Number.isInteger(threshold) && threshold >= 1 ? threshold : undefined
}

/**
 * Number of people who can speak in the room: beyond it, arrivals join as
 * viewers. Left empty, the default of the instance applies.
 */
export const ViewersThresholdField = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'admin.viewers' })
  const { data: config } = useConfig()
  const { mutateAsync: patchRoom } = usePatchRoom()
  const data = useRoomData()
  const configuration = data?.configuration
  const saved = configuration?.viewers_threshold
  const [draft, setDraft] = useState<string>()

  if (!config?.viewers?.enabled || !data?.slug) return null

  const value = draft ?? (saved ? String(saved) : '')

  const save = async () => {
    if (draft === undefined) return
    const threshold = parseThreshold(draft)
    setDraft(undefined)
    if (threshold === undefined || threshold === (saved ?? null)) return
    try {
      await patchRoom({
        roomId: data.slug,
        room: {
          configuration: { ...configuration, viewers_threshold: threshold },
        },
      })
    } catch (error) {
      reportError('generic_failure', error, {
        context: 'update_viewers_threshold',
      })
    }
  }

  return (
    <Field
      type="text"
      inputMode="numeric"
      label={t('label')}
      description={t('description', {
        count: config.viewers.default_threshold,
      })}
      value={value}
      onChange={setDraft}
      onBlur={save}
      onKeyDown={(event) => {
        if (event.key === 'Enter') void save()
      }}
      validate={(value) =>
        parseThreshold(value) === undefined ? t('invalid') : null
      }
      wrapperProps={{
        noMargin: true,
        fullWidth: true,
      }}
    />
  )
}
