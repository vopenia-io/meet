import type { RemoteTrackPublication } from 'livekit-client'
import { subscriptionStore } from '@/stores/subscription'

// Cameras held by a visible tile, counted per track: the same camera can be
// shown twice (grid and picture-in-picture), and only the last tile to let
// it go may drop the subscription.
const holders = new Map<string, number>()

export const isCameraHeld = (trackSid: string) => holders.has(trackSid)

export const holdCamera = (publication: RemoteTrackPublication) => {
  const count = (holders.get(publication.trackSid) ?? 0) + 1
  holders.set(publication.trackSid, count)
  if (!publication.isDesired) publication.setSubscribed(true)
}

export const releaseCamera = (publication: RemoteTrackPublication) => {
  const count = (holders.get(publication.trackSid) ?? 0) - 1
  if (count > 0) {
    holders.set(publication.trackSid, count)
    return
  }
  holders.delete(publication.trackSid)
  // Back below the threshold every track stays subscribed.
  if (subscriptionStore.isSelective && publication.isDesired) {
    publication.setSubscribed(false)
  }
}
