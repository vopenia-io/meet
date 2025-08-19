import { useTranslation } from './useTranslation'

const useIsTranslationEnabled = (roomID: string | undefined): boolean => {
  if (!roomID) return false
  const { data, error } = useTranslation(roomID)
  return data != null && error == null
}

export default useIsTranslationEnabled
