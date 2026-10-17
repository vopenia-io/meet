import type { Participant } from 'livekit-client'

/**
 * Viewers join a room once all the seats for the people who can speak are
 * taken: they see and hear the room but cannot publish anything.
 */
export const getParticipantIsViewer = (participant: Participant): boolean =>
  participant.attributes?.viewer === 'true'
