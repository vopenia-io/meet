import { useUser } from '@/features/auth/api/useUser'
import { useIsAdminOrOwner } from '@/features/rooms/livekit/hooks/useIsAdminOrOwner'
import { useIsViewer } from '@/features/rooms/livekit/hooks/useIsViewer'
import { useRoomHasViewers } from './useRoomHasViewers'

/**
 * Whether the local participant can let viewers speak, or send participants
 * back to viewers: owners and administrators, or any authenticated
 * participant who is not a viewer.
 */
export const useCanLetViewersSpeak = () => {
  const hasViewers = useRoomHasViewers()
  const isAdminOrOwner = useIsAdminOrOwner()
  const isViewer = useIsViewer()
  const { isLoggedIn } = useUser()
  return hasViewers && (isAdminOrOwner || (!!isLoggedIn && !isViewer))
}
