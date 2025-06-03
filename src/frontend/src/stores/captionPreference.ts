import { proxy } from 'valtio'

type State = {
  language: string
}

export const captionPreferenceStore = proxy<State>({
  language: "fr",
})
