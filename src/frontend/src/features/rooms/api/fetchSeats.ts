import { fetchApi } from '@/api/fetchApi'

export type ApiSeats = {
  /** Whether a person joining now would be a viewer. */
  full: boolean
  /** Number of people who can speak in the room. */
  threshold: number
}

export const fetchSeats = (roomId: string) =>
  fetchApi<ApiSeats>(`/rooms/${roomId}/seats/`)
