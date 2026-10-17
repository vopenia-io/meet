import { useSnapshot } from 'valtio'
import { layoutStore } from '@/stores/layout'
import { useStartSubtitle } from '../api/startSubtitle'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import { useRoomContext } from '@livekit/components-react'
import { useEffect } from 'react'
import { RoomEvent } from 'livekit-client'
import { useIsViewer } from '@/features/rooms/livekit/hooks/useIsViewer'

export const useSubtitles = () => {
  const layoutSnap = useSnapshot(layoutStore)

  const room = useRoomContext()
  const apiRoomData = useRoomData()
  const { mutateAsync: startSubtitleRoom, isPending } = useStartSubtitle()
  const isViewer = useIsViewer()

  const toggleSubtitles = async () => {
    // Viewers cannot start the subtitles, they show those already started.
    if (!layoutSnap.showSubtitles && apiRoomData?.livekit && !isViewer) {
      await startSubtitleRoom({
        id: apiRoomData?.livekit?.room,
        token: apiRoomData?.livekit?.token,
      })
    }

    layoutStore.showSubtitles = !layoutSnap.showSubtitles
  }

  useEffect(() => {
    if (!room) return

    const closeSubtitles = () => {
      layoutStore.showSubtitles = false
    }
    room.on(RoomEvent.Disconnected, closeSubtitles)
    return () => {
      room.off(RoomEvent.Disconnected, closeSubtitles)
    }
  }, [room])

  return {
    areSubtitlesOpen: layoutSnap.showSubtitles,
    toggleSubtitles,
    areSubtitlesPending: isPending,
  }
}
