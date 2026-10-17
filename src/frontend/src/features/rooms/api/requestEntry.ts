import { fetchApi } from '@/api/fetchApi'
import type { ApiLiveKit } from '@/features/rooms/api/ApiRoom'

export interface RequestEntryParams {
  roomId: string
  username?: string
}

export enum ApiLobbyStatus {
  IDLE = 'idle',
  WAITING = 'waiting',
  DENIED = 'denied',
  TIMEOUT = 'timeout',
  ACCEPTED = 'accepted',
}

export interface ApiRequestEntry {
  status: ApiLobbyStatus
  livekit?: ApiLiveKit
}

const TAB_ID_KEY = 'meet-tab-id'

/**
 * Id of this browser tab, kept across reloads. Each tab joins as its own
 * participant: two tabs sharing an identity would disconnect each other.
 */
const getTabId = (): string | undefined => {
  try {
    let tabId = sessionStorage.getItem(TAB_ID_KEY)
    if (!tabId) {
      tabId = crypto.randomUUID()
      sessionStorage.setItem(TAB_ID_KEY, tabId)
    }
    return tabId
  } catch {
    return undefined
  }
}

export const requestEntry = async ({
  roomId,
  username = '',
}: RequestEntryParams) => {
  return fetchApi<ApiRequestEntry>(`/rooms/${roomId}/request-entry/`, {
    method: 'POST',
    body: JSON.stringify({
      username,
      tab: getTabId(),
    }),
  })
}
