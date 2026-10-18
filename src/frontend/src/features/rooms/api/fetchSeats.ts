import { fetchApi } from '@/api/fetchApi'
import { getTabId } from '@/features/rooms/api/requestEntry'

export type ApiSeats = {
  /** Whether a person joining now would be a viewer. */
  full: boolean
  /** Number of people who can speak in the room. */
  threshold: number
}

/**
 * The tab is given as when joining: a tab reloaded within the grace period
 * still holds its seat, and is not told the room is full.
 */
export const fetchSeats = (roomId: string) => {
  const tab = getTabId()
  const query = tab ? `?${new URLSearchParams({ tab })}` : ''
  return fetchApi<ApiSeats>(`/rooms/${roomId}/seats/${query}`)
}
