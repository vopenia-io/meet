import { useEffect } from 'react'
import { useRoomContext } from '@livekit/components-react'
import {
  type Participant,
  RemoteTrackPublication,
  RoomEvent,
  Track,
  type TrackPublication,
} from 'livekit-client'
import { useConfig } from '@/api/useConfig'
import { subscriptionStore } from '@/stores/subscription'
import { isCameraHeld } from '@/features/rooms/livekit/utils/cameraSubscriptions'

// A muted microphone keeps its subscription this long: whoever just muted
// often speaks again soon, and resubscribing costs a renegotiation.
const MUTED_MICROPHONE_GRACE_MS = 30_000

// Leave the selective mode only well below the threshold, so a room hovering
// around it does not flip every subscription back and forth.
const HYSTERESIS = 0.8

// When the room crosses the threshold, give the visible tiles time to hold
// their camera before dropping the others.
const CAMERA_SWEEP_DELAY_MS = 1000

/**
 * Drives subscriptions when the room connects with autoSubscribe off.
 *
 * Up to the threshold, every remote track is subscribed, as autoSubscribe
 * would. Above it, each client takes only what it plays: the cameras its
 * tiles show (see useCameraSubscription), the screen shares, and the open
 * microphones. Muted microphones and off-screen cameras send nothing worth
 * receiving, but each subscription still costs a transceiver, an m= section
 * in every renegotiation, and a forwarding slot on the server.
 */
export const SubscriptionManager = () => {
  const room = useRoomContext()
  const { data } = useConfig()
  const threshold = data?.selective_subscription_threshold
  // Muted microphones stay subscribed up to this size: subscribing on unmute
  // clips the first words of whoever starts speaking. Defaults to the video
  // threshold.
  const audioThreshold =
    data?.selective_audio_subscription_threshold ?? threshold

  useEffect(() => {
    if (!threshold || !audioThreshold) return

    let isSelective = false
    let isAudioSelective = false
    let sweepTimer: ReturnType<typeof setTimeout> | undefined
    const muteTimers = new Map<string, ReturnType<typeof setTimeout>>()

    const setSubscribed = (pub: RemoteTrackPublication, want: boolean) => {
      if (pub.isDesired !== want) pub.setSubscribed(want)
    }

    const clearMuteTimer = (trackSid: string) => {
      clearTimeout(muteTimers.get(trackSid))
      muteTimers.delete(trackSid)
    }

    const apply = (pub: RemoteTrackPublication) => {
      if (!isSelective) {
        clearMuteTimer(pub.trackSid)
        setSubscribed(pub, true)
        return
      }
      switch (pub.source) {
        case Track.Source.Camera:
          // Tiles subscribe what they show; drop what nobody shows.
          if (!isCameraHeld(pub.trackSid)) setSubscribed(pub, false)
          return
        case Track.Source.Microphone:
          if (!pub.isMuted || !isAudioSelective) {
            clearMuteTimer(pub.trackSid)
            setSubscribed(pub, true)
          } else if (pub.isDesired && !muteTimers.has(pub.trackSid)) {
            muteTimers.set(
              pub.trackSid,
              setTimeout(() => {
                muteTimers.delete(pub.trackSid)
                if (isSelective && isAudioSelective && pub.isMuted) {
                  setSubscribed(pub, false)
                }
              }, MUTED_MICROPHONE_GRACE_MS)
            )
          }
          return
        default:
          setSubscribed(pub, true)
      }
    }

    const forEachPublication = (
      callback: (pub: RemoteTrackPublication) => void
    ) =>
      room.remoteParticipants.forEach((participant) =>
        participant.trackPublications.forEach(callback)
      )

    const updateMode = () => {
      const count = room.remoteParticipants.size + 1
      const nextAudio = isAudioSelective
        ? count > Math.floor(audioThreshold * HYSTERESIS)
        : count > audioThreshold
      if (nextAudio !== isAudioSelective) {
        isAudioSelective = nextAudio
        forEachPublication((pub) => {
          if (pub.source === Track.Source.Microphone) apply(pub)
        })
      }
      const next = isSelective
        ? count > Math.floor(threshold * HYSTERESIS)
        : count > threshold
      if (next === isSelective) return
      isSelective = next
      subscriptionStore.isSelective = next
      clearTimeout(sweepTimer)
      if (next) {
        forEachPublication((pub) => {
          if (pub.source !== Track.Source.Camera) apply(pub)
        })
        sweepTimer = setTimeout(
          () =>
            forEachPublication((pub) => {
              if (pub.source === Track.Source.Camera) apply(pub)
            }),
          CAMERA_SWEEP_DELAY_MS
        )
      } else {
        forEachPublication(apply)
      }
    }

    const onPublished = (pub: RemoteTrackPublication) => apply(pub)
    const onMuteChanged = (pub: TrackPublication, participant: Participant) => {
      if (!participant.isLocal && pub instanceof RemoteTrackPublication) {
        apply(pub)
      }
    }
    const onUnpublished = (pub: RemoteTrackPublication) =>
      clearMuteTimer(pub.trackSid)
    const onReconnected = () => {
      updateMode()
      forEachPublication(apply)
    }

    updateMode()
    forEachPublication(apply)

    room.on(RoomEvent.ParticipantConnected, updateMode)
    room.on(RoomEvent.ParticipantDisconnected, updateMode)
    room.on(RoomEvent.TrackPublished, onPublished)
    room.on(RoomEvent.TrackUnpublished, onUnpublished)
    room.on(RoomEvent.TrackMuted, onMuteChanged)
    room.on(RoomEvent.TrackUnmuted, onMuteChanged)
    room.on(RoomEvent.Connected, onReconnected)
    room.on(RoomEvent.Reconnected, onReconnected)
    return () => {
      room.off(RoomEvent.ParticipantConnected, updateMode)
      room.off(RoomEvent.ParticipantDisconnected, updateMode)
      room.off(RoomEvent.TrackPublished, onPublished)
      room.off(RoomEvent.TrackUnpublished, onUnpublished)
      room.off(RoomEvent.TrackMuted, onMuteChanged)
      room.off(RoomEvent.TrackUnmuted, onMuteChanged)
      room.off(RoomEvent.Connected, onReconnected)
      room.off(RoomEvent.Reconnected, onReconnected)
      clearTimeout(sweepTimer)
      muteTimers.forEach(clearTimeout)
      subscriptionStore.isSelective = false
    }
  }, [room, threshold, audioThreshold])

  return null
}
