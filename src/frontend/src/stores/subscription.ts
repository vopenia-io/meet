import { proxy } from 'valtio'

type State = {
  // In a large room the client subscribes only to what it plays: the cameras
  // its tiles show, the screen shares and the open microphones. Below the
  // threshold it subscribes to everything, as autoSubscribe would.
  isSelective: boolean
}

export const subscriptionStore = proxy<State>({
  isSelective: false,
})
