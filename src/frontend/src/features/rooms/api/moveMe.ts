import { fetchApi } from '@/api/fetchApi'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import { getLiveKitAuthHeaders } from '../utils/getLiveKitAuthHeaders'

export type MoveMeResponse = {
  status: string
  node: string
  region: string
}

/**
 * Asks the backend to have the SFU move this participant to another node,
 * of `region` if one is named (`/moveme [region]` in the chat).
 */
export const useMoveMe = () => {
  const data = useRoomData()

  const moveMe = async (region: string) => {
    if (!data?.id) {
      throw new Error('Room id is not available')
    }

    const token = data?.livekit?.token

    if (!token) {
      throw new Error('LiveKit token is not available')
    }

    return fetchApi<MoveMeResponse>(`rooms/${data.id}/move-me/`, {
      method: 'POST',
      headers: getLiveKitAuthHeaders(token),
      body: JSON.stringify({ region }),
    })
  }

  return { moveMe }
}
