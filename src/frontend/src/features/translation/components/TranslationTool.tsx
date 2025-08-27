import { ToolButton } from '@/features/rooms/livekit/components/Tools'
import { RiFileTextFill } from '@remixicon/react'
import { useStartTranslation } from '../hooks/useStartTranslation'
import { useStopTranslation } from '../hooks/useStopTranslation'
import { useRoomId } from '@/features/rooms/livekit/hooks/useRoomId'
import { translationKey, useTranslation as useT } from '../hooks/useTranslation'
import { useTranslation } from 'react-i18next'
import { useEffect, useState } from 'react'
import { captionPreferenceStore } from '@/stores/captionPreference'
import { useSnapshot } from 'valtio'
import { Language, TranslationSettings } from './TranslationSettings.tsx'
import { useConfig } from '@/api/useConfig.ts'
import { decodeNotificationDataReceived } from '@/features/notifications/utils.ts'
import { NotificationType } from '@/features/notifications/NotificationType.ts'
import { queryClient } from '@/api/queryClient.ts'
import { useRoomContext } from '@livekit/components-react'

// Deprecated: inline settings extracted to standalone component in TranslationSettings.tsx
// const TranslationSettings = () => {}

export const TranslationTool = () => {
  const { data: config } = useConfig()
  const { t } = useTranslation('rooms', { keyPrefix: 'moreTools' })

  useSnapshot(captionPreferenceStore) // keep reactive subscription if needed for side-effects
  const roomID = useRoomId()
  const room = useRoomContext()
  const { mutateAsync: startTranslation } = useStartTranslation()
  const { mutateAsync: stopTranslation } = useStopTranslation()
  const { data: translation, error, isLoading } = useT(roomID)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [selectedLanguages, setSelectedLanguages] = useState<Language[]>([])
  const [langs, setLangs] = useState<Language[]>([])

  useEffect(() => {
    if (!room || !roomID) return

    const handleDataReceived = (
      payload: Uint8Array    ) => {
      const notification = decodeNotificationDataReceived(payload)

      if (!notification) return

      switch (notification.type) {
        case NotificationType.TranslationStarted:
          break
        case NotificationType.TranslationStopped:
          break
        case NotificationType.TranslationError:
          break
        default:
          return
      }
      queryClient.invalidateQueries({ queryKey: translationKey(roomID) })
    }

    room.on('dataReceived', handleDataReceived)
    return () => {
      room.off('dataReceived', handleDataReceived)
    }
  }, [room, roomID])

  const isActive =
    roomID !== undefined &&
    translation != null &&
    error == null &&
    isLoading === false

  useEffect(() => {
    // ensure uniqueness (defensive)
    const uniqueLangs = Array.from(new Set(selectedLanguages))
    if (uniqueLangs.length !== selectedLanguages.length) {
      setSelectedLanguages(uniqueLangs)
    }
  }, [selectedLanguages])

  useEffect(() => {
    if (config?.translation?.enabled) {
      const availableLangs = config.translation.languages
      const langsArray = Object.entries(availableLangs).map(([code, name]) => ({
        code,
        name,
      }))
      setLangs(langsArray)
    } else {
      setLangs([])
    }
  }, [config])

  return (
    <div>
      <ToolButton
        icon={<RiFileTextFill size={24} color="white" />}
        title={t('tools.transcript.title')}
        description={t('tools.transcript.body')}
        onPress={() => setSettingsOpen(true)}
        isBetaFeature
        isActive={isActive}
      />
      {settingsOpen && (
        <TranslationSettings
          availableLanguages={langs}
          selectedLanguages={selectedLanguages}
          onChangeSelectedLanguages={setSelectedLanguages}
          isLoading={isLoading}
          isActive={isActive}
          onClose={() => setSettingsOpen(false)}
          onStart={async () => {
            if (!roomID) return
            await startTranslation({
              roomID,
              payload: { lang: selectedLanguages.map((l) => l.code) },
            })
            setSettingsOpen(false)
          }}
          onStop={async () => {
            if (!roomID) return
            await stopTranslation({ roomID })
            setSettingsOpen(false)
          }}
        />
      )}
    </div>
  )
}
