import { useEffect, useState } from 'react'
import { usePersistentUserChoices } from '@livekit/components-react'
import { useLocation, useParams } from 'wouter'
import { ErrorScreen } from '@/components/ErrorScreen'
import { useUser, UserAware } from '@/features/auth'
import { Conference } from '../components/Conference'
import { Join } from '../components/Join'
import { useKeyboardShortcuts } from '@/features/shortcuts/useKeyboardShortcuts'
import {
  isRoomValid,
  normalizeRoomId,
} from '@/features/rooms/utils/isRoomValid'
import { LocalUserChoices } from '@/stores/userChoices'

export const Room = () => {
  const { isLoggedIn } = useUser()
  const { userChoices: existingUserChoices } = usePersistentUserChoices()
  const [userConfig, setUserConfig] = useState<LocalUserChoices | null>(null)

  const { roomId } = useParams()
  const [location, setLocation] = useLocation()
  const initialRoomData = history.state?.initialRoomData
  const mode = isLoggedIn && history.state?.create ? 'create' : 'join'
  const skipJoinScreen = isLoggedIn && mode === 'create'

  useKeyboardShortcuts()

  const clearRouterState = () => {
    if (window?.history?.state) {
      window.history.replaceState({}, '')
    }
  }

  useEffect(() => {
    window.addEventListener('beforeunload', clearRouterState)
    return () => {
      window.removeEventListener('beforeunload', clearRouterState)
    }
  }, [])

  useEffect(() => {
    if (roomId && !isRoomValid(roomId)) {
      setLocation(normalizeRoomId(roomId))
    }
  }, [roomId, setLocation, location])

  if (!roomId) {
    return <ErrorScreen />
  }

  if (!userConfig && !skipJoinScreen) {
    return (
      <UserAware>
        <Join onSubmit={setUserConfig} roomId={roomId} />
      </UserAware>
    )
  }

  return (
    <UserAware>
      <Conference
        initialRoomData={initialRoomData}
        roomId={roomId}
        mode={mode}
        userConfig={{
          ...existingUserChoices,
          ...userConfig,
        }}
      />
    </UserAware>
  )
}
