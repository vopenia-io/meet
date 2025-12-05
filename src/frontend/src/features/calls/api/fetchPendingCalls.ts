import { fetchApi } from '@/api/fetchApi'
import { IncomingCall } from '@/stores/incomingCall'

export type PendingCallsResponse = {
  calls: IncomingCall[]
}

export const fetchPendingCalls = async (): Promise<PendingCallsResponse> => {
  return fetchApi<PendingCallsResponse>('/calls/pending/')
}
