import { proxy } from 'valtio'

type State = {
  isOpen: boolean
}

/** The dialog where a viewer checks their microphone before raising a hand. */
export const requestToSpeakStore = proxy<State>({
  isOpen: false,
})

export const openRequestToSpeak = () => {
  requestToSpeakStore.isOpen = true
}

export const closeRequestToSpeak = () => {
  requestToSpeakStore.isOpen = false
}
