import { fetchApi } from '@/api/fetchApi'

export type InitiateCallResponse = {
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
  sip_call_id: string
  phone_number: string
}

export const initiateCall = async (
  phoneNumber: string
): Promise<InitiateCallResponse> => {
  return fetchApi<InitiateCallResponse>('/calls/initiate/', {
    method: 'POST',
    body: JSON.stringify({ phone_number: phoneNumber }),
  })
}
