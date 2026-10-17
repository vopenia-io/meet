import { useIsAdminOrOwner } from './useIsAdminOrOwner'
import { useIsViewer } from './useIsViewer'
import type { Participant } from 'livekit-client'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'

export const useCanMute = (participant: Participant) => {
  const apiRoomData = useRoomData()
  const isAdminOrOwner = useIsAdminOrOwner()
  // Viewers cannot mute the people who can speak.
  const isViewer = useIsViewer()
  return (
    participant.isLocal ||
    isAdminOrOwner ||
    (!isViewer && apiRoomData?.configuration?.everyone_can_mute !== false)
  )
}
