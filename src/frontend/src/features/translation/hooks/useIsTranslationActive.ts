import { useTranslation } from './useTranslation'

const useIsTranslationActive = (roomID: string | undefined): boolean => {
  const { data, error } = useTranslation(roomID)
  if (!roomID) return false
  return data != null && error == null
}

export default useIsTranslationActive
