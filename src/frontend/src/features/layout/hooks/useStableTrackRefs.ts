import { useMemo, useRef } from 'react'
import {
  getTrackReferenceId,
  type TrackReferenceOrPlaceholder,
} from '@livekit/components-core'

/**
 * useTracks builds a new reference object for every track on each update, so
 * every tile sees a new context value and re-renders when anyone joins,
 * leaves or publishes. This keeps the previous object while the participant,
 * source and publication behind it are unchanged: memoized tiles then only
 * render for their own events.
 */
export function useStableTrackRefs(
  tracks: TrackReferenceOrPlaceholder[]
): TrackReferenceOrPlaceholder[] {
  const cache = useRef(new Map<string, TrackReferenceOrPlaceholder>())

  return useMemo(() => {
    const next = new Map<string, TrackReferenceOrPlaceholder>()
    const stable = tracks.map((track) => {
      const id = getTrackReferenceId(track)
      const previous = cache.current.get(id)
      const kept =
        previous &&
        previous.participant === track.participant &&
        previous.source === track.source &&
        previous.publication === track.publication
          ? previous
          : track
      next.set(id, kept)
      return kept
    })
    cache.current = next
    return stable
  }, [tracks])
}
