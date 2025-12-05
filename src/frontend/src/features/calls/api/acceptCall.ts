import { fetchApi } from '@/api/fetchApi'

export type AcceptCallResponse = {
  status: string
  room: {
    id: string
    name: string
    slug: string
  }
  livekit: {
    url: string
    token: string
  }
  caller_number: string
}

export const acceptCall = async (callId: string): Promise<AcceptCallResponse> => {
  return fetchApi<AcceptCallResponse>('/calls/accept/', {
    method: 'POST',
    body: JSON.stringify({ call_id: callId }),
  })
}
