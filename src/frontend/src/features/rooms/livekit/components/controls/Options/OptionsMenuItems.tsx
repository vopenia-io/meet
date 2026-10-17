import { Menu as RACMenu, MenuSection } from 'react-aria-components'
import { Separator } from '@/primitives/Separator'
import { FullScreenMenuItem } from './FullScreenMenuItem'
import { SettingsMenuItem } from './SettingsMenuItem'
import { FeedbackMenuItem } from './FeedbackMenuItem'
import { EffectsMenuItem } from './EffectsMenuItem'
import { SupportMenuItem } from './SupportMenuItem'
import { DocumentationMenuItem } from './DocumentationMenuItem'
import { TranscriptMenuItem } from './TranscriptMenuItem'
import { ScreenRecordingMenuItem } from './ScreenRecordingMenuItem'
import { PictureInPictureMenuItem } from '@/features/rooms/livekit/components/controls/Options/PictureInPictureMenuItem'
import { useIsViewer } from '@/features/rooms/livekit/hooks/useIsViewer'
import { useRoomContext } from '@livekit/components-react'
import { useRoomHasViewers } from '@/features/viewers/hooks/useRoomHasViewers'
import { BecomeViewerMenuItem } from '@/features/viewers/components/BecomeViewerMenuItem'

// @todo try refactoring it to use MenuList component
export const OptionsMenuItems = () => {
  const isViewer = useIsViewer()
  const hasViewers = useRoomHasViewers()
  const room = useRoomContext()
  return (
    <RACMenu
      style={{
        minWidth: '150px',
        width: '300px',
      }}
    >
      <MenuSection>
        <PictureInPictureMenuItem />
        <TranscriptMenuItem />
        <ScreenRecordingMenuItem />
        <FullScreenMenuItem />
        {!isViewer && <EffectsMenuItem />}
        {hasViewers && !isViewer && (
          <BecomeViewerMenuItem
            participant={room.localParticipant}
            variant="dark"
          />
        )}
      </MenuSection>
      <Separator />
      <MenuSection>
        <SupportMenuItem />
        <DocumentationMenuItem />
        <FeedbackMenuItem />
        <SettingsMenuItem />
      </MenuSection>
    </RACMenu>
  )
}
