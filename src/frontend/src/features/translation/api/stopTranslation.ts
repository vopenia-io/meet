import { fetchApi } from '@/api/fetchApi'
import type { ApiTranslation } from './fetchTranslation'

export type StopTranslationParams = {
  roomID: string
}

export const stopTranslation = ({
  roomID,
}: StopTranslationParams): Promise<ApiTranslation> =>
  fetchApi<ApiTranslation>(`rooms/${roomID}/stop-translation/`, {
    method: 'POST',
  })
