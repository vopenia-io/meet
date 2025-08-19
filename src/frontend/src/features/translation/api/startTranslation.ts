import { fetchApi } from '@/api/fetchApi'
import type { ApiTranslation, ApiTranslationMeta } from './fetchTranslation'

export type StartTranslationParams = {
  roomID: string
  payload: ApiTranslationMeta
}

export const startTranslation = ({
  roomID,
  payload,
}: StartTranslationParams): Promise<ApiTranslation> =>
  fetchApi<ApiTranslation>(`rooms/${roomID}/start-translation/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
