import { useMemo } from 'react'
import type { TrackReferenceOrPlaceholder } from '@livekit/components-core'
import { Track } from 'livekit-client'
import { useViewerIdentities } from '@/features/rooms/livekit/hooks/useViewerIdentities'

/**
 * Drop the tiles of viewers: they publish nothing, and hundreds of them
 * would bury the people who can speak under placeholders.
 */
export const useWithoutViewers = <T extends TrackReferenceOrPlaceholder>(
  tracks: T[]
): T[] => {
  const viewers = useViewerIdentities()
  return useMemo(
    () =>
      viewers.size === 0
        ? tracks
        : tracks.filter(
            (track) =>
              track.source === Track.Source.ScreenShare ||
              !viewers.has(track.participant.identity)
          ),
    [tracks, viewers]
  )
}
