import { useMutation, UseMutationOptions } from "@tanstack/react-query";
import { ApiError } from "@/api/ApiError";
import { stopTranslation, StopTranslationParams } from "../api/stopTranslation";
import { queryClient } from "@/api/queryClient";
import { translationKey } from "./useTranslation";

export function useStopTranslation(
  options?: UseMutationOptions<null, ApiError, StopTranslationParams>
) {
  return useMutation<null, ApiError, StopTranslationParams>({
    mutationFn: stopTranslation,
    ...options,
    onSuccess: async (data, variables, context) => {
      queryClient.setQueryData(translationKey(variables.roomID), null)
      await options?.onSuccess?.(data, variables, context)
    },
  })
}
