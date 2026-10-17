import { useConfig } from '@/api/useConfig'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'

/** Whether people joining the room can become viewers. */
export const useRoomHasViewers = () => {
  const { data: config } = useConfig()
  const roomData = useRoomData()
  // Unregistered rooms have no id, and no viewers.
  return !!config?.viewers?.enabled && !!roomData?.id
}
