import { fetchApiNullable } from '@/api/fetchApi'

export type StopTranslationParams = {
  roomID: string
}

export const stopTranslation = ({
  roomID,
}: StopTranslationParams): Promise<null> =>
  fetchApiNullable<null>(`rooms/${roomID}/stop-translation/`, {
    method: 'POST',
  })
