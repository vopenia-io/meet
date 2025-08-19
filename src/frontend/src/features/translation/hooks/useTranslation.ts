import { useQuery } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import { fetchTranslation } from '../api/fetchTranslation'

export const translationKey = (roomID: string) => [keys.translation, roomID] as const

export const useTranslation = (roomID: string | undefined) =>
  useQuery({
    queryKey: translationKey(roomID!),
    queryFn: () => fetchTranslation({ roomID: roomID! }),
    enabled: roomID !== undefined,
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
