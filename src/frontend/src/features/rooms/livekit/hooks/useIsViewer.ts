import type { Participant } from 'livekit-client'
import {
  useParticipantAttribute,
  useRoomContext,
} from '@livekit/components-react'

/**
 * Whether a participant, the local one by default, is a viewer. It follows
 * the attribute set by the backend, so it changes when someone is promoted
 * or goes back to viewers.
 */
export const useIsViewer = (participant?: Participant) => {
  const room = useRoomContext()
  const viewer = useParticipantAttribute('viewer', {
    participant: participant ?? room.localParticipant,
  })
  return viewer === 'true'
}
