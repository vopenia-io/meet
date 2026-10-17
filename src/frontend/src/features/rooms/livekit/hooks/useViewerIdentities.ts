import { useEffect, useState } from 'react'
import { useRoomContext } from '@livekit/components-react'
import { Room, RoomEvent } from 'livekit-client'
import { getParticipantIsViewer } from '@/features/rooms/utils/getParticipantIsViewer'

const collectViewers = (room: Room): ReadonlySet<string> => {
  const viewers = new Set<string>()
  for (const participant of [
    room.localParticipant,
    ...room.remoteParticipants.values(),
  ]) {
    if (getParticipantIsViewer(participant)) viewers.add(participant.identity)
  }
  return viewers
}

const isSameSet = (a: ReadonlySet<string>, b: ReadonlySet<string>) =>
  a.size === b.size && [...a].every((identity) => b.has(identity))

/**
 * Identities of the viewers of the room, the local participant included.
 *
 * Only changes when someone joins, leaves, or becomes or stops being a
 * viewer: other attribute changes, such as raised hands, keep the same set.
 */
export const useViewerIdentities = (): ReadonlySet<string> => {
  const room = useRoomContext()
  const [viewers, setViewers] = useState(() => collectViewers(room))

  useEffect(() => {
    const update = () =>
      setViewers((previous) => {
        const next = collectViewers(room)
        return isSameSet(previous, next) ? previous : next
      })
    const onAttributesChanged = (changed: Record<string, string>) => {
      if ('viewer' in changed) update()
    }

    update()
    room
      // The local participant gets their attributes when connecting.
      .on(RoomEvent.Connected, update)
      .on(RoomEvent.ParticipantConnected, update)
      .on(RoomEvent.ParticipantDisconnected, update)
      .on(RoomEvent.ParticipantAttributesChanged, onAttributesChanged)
    return () => {
      room
        .off(RoomEvent.Connected, update)
        .off(RoomEvent.ParticipantConnected, update)
        .off(RoomEvent.ParticipantDisconnected, update)
        .off(RoomEvent.ParticipantAttributesChanged, onAttributesChanged)
    }
  }, [room])

  return viewers
}
