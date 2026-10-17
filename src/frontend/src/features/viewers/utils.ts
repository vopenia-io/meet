import type { Participant, Room } from 'livekit-client'
import { getParticipantIsAuthenticated } from '@/features/rooms/utils/getParticipantIsAuthenticated'
import { getParticipantIsViewer } from '@/features/rooms/utils/getParticipantIsViewer'

export const getParticipants = (room: Room): Participant[] => [
  room.localParticipant,
  ...room.remoteParticipants.values(),
]

/** Authenticated participants who are not viewers: they can let viewers speak. */
export const getAuthenticatedSpeakers = (room: Room): Participant[] =>
  getParticipants(room).filter(
    (participant) =>
      !getParticipantIsViewer(participant) &&
      getParticipantIsAuthenticated(participant)
  )

/**
 * Whether sending this participant back to viewers would leave nobody to
 * let viewers speak: the backend refuses it.
 */
export const getIsLastAuthenticatedSpeaker = (
  room: Room,
  participant: Participant
): boolean => {
  const speakers = getAuthenticatedSpeakers(room)
  return speakers.length === 1 && speakers[0].identity === participant.identity
}
