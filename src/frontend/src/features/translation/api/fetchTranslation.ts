import { fetchApiNullable } from '@/api/fetchApi'

export type ApiTranslationMeta = {
  lang: string[]
}

export type ApiTranslation = {
  meta: ApiTranslationMeta
  roomID: string
  id: string
}

export const fetchTranslation = ({
  roomID,
}: {
  roomID: string
}): Promise<ApiTranslation | null> =>
  fetchApiNullable<ApiTranslation>(`rooms/${roomID}/fetch-translation/`)
