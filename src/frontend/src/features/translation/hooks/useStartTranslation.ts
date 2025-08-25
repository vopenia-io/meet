import { useMutation, UseMutationOptions } from '@tanstack/react-query'
import { ApiTranslation } from '../api/fetchTranslation'
import { ApiError } from '@/api/ApiError'
import {
  startTranslation,
  StartTranslationParams,
} from '../api/startTranslation'
import { queryClient } from '@/api/queryClient'
import { translationKey } from './useTranslation'

export function useStartTranslation(
  options?: UseMutationOptions<ApiTranslation, ApiError, StartTranslationParams>
) {
  return useMutation<ApiTranslation, ApiError, StartTranslationParams>({
    mutationFn: startTranslation,
    ...options,
    onSuccess: async (data, variables, context) => {
      queryClient.setQueryData(translationKey(variables.roomID), data)
      await options?.onSuccess?.(data, variables, context)
    },
  })
}
