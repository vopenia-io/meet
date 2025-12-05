import { proxy } from 'valtio'

export type IncomingCall = {
  call_id: string
  caller_number: string
  callee_number: string
  lobby_room_name: string
  sip_participant_identity: string
}

type State = {
  incomingCall: IncomingCall | null
  isProcessing: boolean
}

export const incomingCallStore = proxy<State>({
  incomingCall: null,
  isProcessing: false,
})

export const setIncomingCall = (call: IncomingCall | null) => {
  incomingCallStore.incomingCall = call
  incomingCallStore.isProcessing = false
}

export const setProcessing = (processing: boolean) => {
  incomingCallStore.isProcessing = processing
}

export const clearIncomingCall = () => {
  incomingCallStore.incomingCall = null
  incomingCallStore.isProcessing = false
}
