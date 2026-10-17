import { useEffect, useRef } from 'react'
import { useRoomContext } from '@livekit/components-react'
import { type Participant, RoomEvent } from 'livekit-client'

/**
 * When each participant last spoke, as seen since joining. Someone who has not
 * spoken since then is considered silent since they, or we, joined.
 *
 * Reads refs: call the returned function from event handlers, not render.
 */
export const useLastSpokeAt = () => {
  const room = useRoomContext()
  const lastSpokeAt = useRef(new Map<string, number>())
  const joinedAt = useRef(0)

  useEffect(() => {
    joinedAt.current = Date.now()
  }, [])

  useEffect(() => {
    const onActiveSpeakers = (speakers: Participant[]) => {
      const now = Date.now()
      for (const speaker of speakers) {
        lastSpokeAt.current.set(speaker.identity, now)
      }
    }
    room.on(RoomEvent.ActiveSpeakersChanged, onActiveSpeakers)
    return () => {
      room.off(RoomEvent.ActiveSpeakersChanged, onActiveSpeakers)
    }
  }, [room])

  return (participant: Participant) =>
    lastSpokeAt.current.get(participant.identity) ??
    Math.max(participant.joinedAt?.getTime() ?? 0, joinedAt.current)
}
