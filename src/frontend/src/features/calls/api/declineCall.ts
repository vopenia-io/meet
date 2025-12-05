import { fetchApi } from '@/api/fetchApi'

export const declineCall = async (callId: string): Promise<void> => {
  await fetchApi('/calls/decline/', {
    method: 'POST',
    body: JSON.stringify({ call_id: callId }),
  })
}
