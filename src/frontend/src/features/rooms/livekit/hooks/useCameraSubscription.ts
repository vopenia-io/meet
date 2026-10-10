import { type RefObject, useEffect } from 'react'
import { useSnapshot } from 'valtio'
import {
  isTrackReference,
  type TrackReferenceOrPlaceholder,
} from '@livekit/components-core'
import { RemoteTrackPublication, Track } from 'livekit-client'
import { subscriptionStore } from '@/stores/subscription'
import {
  holdCamera,
  releaseCamera,
} from '@/features/rooms/livekit/utils/cameraSubscriptions'

// A tile scrolled out of view keeps its camera a little while, so scrolling
// back and forth through the carousel does not resubscribe at every step.
const OFFSCREEN_RELEASE_DELAY_MS = 3000

/**
 * In a large room, subscribes to a remote camera while its tile is on screen
 * and drops it once the tile is gone. Below the threshold every camera is
 * subscribed anyway and this hook does nothing.
 */
export const useCameraSubscription = (
  trackRef: TrackReferenceOrPlaceholder,
  tileRef: RefObject<HTMLElement | null>
) => {
  const { isSelective } = useSnapshot(subscriptionStore)

  const publication =
    isTrackReference(trackRef) &&
    trackRef.source === Track.Source.Camera &&
    trackRef.publication instanceof RemoteTrackPublication
      ? trackRef.publication
      : undefined

  useEffect(() => {
    if (!isSelective || !publication) return

    let held = false
    let releaseTimer: ReturnType<typeof setTimeout> | undefined
    const hold = () => {
      clearTimeout(releaseTimer)
      if (held) return
      held = true
      holdCamera(publication)
    }
    const release = () => {
      clearTimeout(releaseTimer)
      if (!held) return
      held = false
      releaseCamera(publication)
    }

    const tile = tileRef.current
    // A picture-in-picture tile lives in another document, which this
    // window's IntersectionObserver does not watch: hold it while mounted.
    if (
      !tile ||
      typeof IntersectionObserver === 'undefined' ||
      tile.ownerDocument !== document
    ) {
      hold()
      return release
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        hold()
      } else {
        clearTimeout(releaseTimer)
        releaseTimer = setTimeout(release, OFFSCREEN_RELEASE_DELAY_MS)
      }
    })
    observer.observe(tile)
    return () => {
      observer.disconnect()
      release()
    }
  }, [isSelective, publication, tileRef])
}
