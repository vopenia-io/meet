import { fetchApi } from '@/api/fetchApi'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'

/** Change the role of the participants of a room with viewers. */
export const useViewersActions = () => {
  const data = useRoomData()

  const post = (action: string, identity: string, token?: string) => {
    if (!data?.id) {
      throw new Error('Room id is not available')
    }
    return fetchApi(`rooms/${data.id}/${action}/`, {
      method: 'POST',
      ...(token && { headers: { Authorization: `Bearer ${token}` } }),
      body: JSON.stringify({ participant_identity: identity }),
    })
  }

  return {
    /** Let a viewer speak. */
    promoteViewer: (identity: string) => post('promote-viewer', identity),
    /** Send someone else back to viewers. */
    demoteParticipant: (identity: string) =>
      post('demote-participant', identity),
    /** Go back to viewers: the LiveKit token tells who asks, even signed out. */
    becomeViewer: (identity: string) =>
      post('demote-participant', identity, data?.livekit?.token),
    /** Take the seat of an unauthenticated participant. */
    takeSeat: (identity: string) => post('take-seat', identity),
  }
}
