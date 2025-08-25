import { RiTranslateAi2 } from '@remixicon/react'
import { css } from '@/styled-system/css'
import { ToggleButton } from '@/primitives'
import { ToggleButtonProps } from '@/primitives/ToggleButton'
import { layoutStore } from '@/stores/layout.ts'
import { useSnapshot } from 'valtio'
import { useLayout } from '../../hooks/useLayout'
import useIsTranslationEnabled from '@/features/translation/hooks/useIsTranslationEnabled'
import { useRoomId } from '../../hooks/useRoomId'

export const SubtitleToggle = ({
  onPress,
  ...props
}: Partial<ToggleButtonProps>) => {
  const layoutSnap = useSnapshot(layoutStore)

  const roomID = useRoomId()
  const { toggleSubtitle, displaySubtitle } = useLayout()

  const isTranslationEnabled = useIsTranslationEnabled(roomID)
  if (!isTranslationEnabled) {
    displaySubtitle(false)
    return null
  }
  return (
    <div
      className={css({
        position: 'relative',
        display: 'inline-block',
      })}
    >
      <ToggleButton
        square
        variant="primaryDark"
        isSelected={layoutSnap.showSubtitle}
        onPress={(e) => {
          toggleSubtitle()

          // // todo - trigger agent to join the room and transcribe

          onPress?.(e)
        }}
        {...props}
      >
        <RiTranslateAi2 />
      </ToggleButton>
    </div>
  )
}
