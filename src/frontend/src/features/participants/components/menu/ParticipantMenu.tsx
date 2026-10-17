import { Menu as RACMenu } from 'react-aria-components'
import { type Participant } from 'livekit-client'
import { PinMenuItem } from './items/PinMenuItem'
import { RemoveMenuItem } from './items/RemoveMenuItem'
import { PromoteMenuItem } from './items/PromoteMenuItem'
import { useIsAdminOrOwner } from '@/features/rooms/livekit/hooks/useIsAdminOrOwner'
import { useParticipantAttributes } from '@livekit/components-react'
import { ParticipantKind } from 'livekit-client'
import { useRoomHasViewers } from '@/features/viewers/hooks/useRoomHasViewers'
import { useCanLetViewersSpeak } from '@/features/viewers/hooks/useCanLetViewersSpeak'
import { BecomeViewerMenuItem } from '@/features/viewers/components/BecomeViewerMenuItem'

export const ParticipantMenu = ({
  participant,
}: {
  participant: Participant
}) => {
  const isLocalUserAdminOrOwner = useIsAdminOrOwner()

  const { attributes } = useParticipantAttributes({ participant })

  const isAdmin = attributes?.room_role === 'administrator'
  const isOwner = attributes?.room_role === 'owner'
  const isAuthenticated = attributes?.is_authenticated == 'true'

  const canManage = !participant.isLocal && isLocalUserAdminOrOwner && !isOwner

  const hasViewers = useRoomHasViewers()
  const canLetViewersSpeak = useCanLetViewersSpeak()
  const canBecomeViewer =
    hasViewers &&
    attributes?.viewer !== 'true' &&
    participant.kind !== ParticipantKind.SIP &&
    (participant.isLocal ||
      (canLetViewersSpeak &&
        (isLocalUserAdminOrOwner || (!isAdmin && !isOwner))))

  return (
    <RACMenu
      style={{
        minWidth: '100px',
      }}
    >
      <PinMenuItem participant={participant} />
      {canManage && (
        <RemoveMenuItem
          identity={participant.identity}
          displayedName={participant.name}
        />
      )}
      {canManage && isAuthenticated && (
        <PromoteMenuItem
          identity={participant.identity}
          isAdmin={isAdmin}
          displayedName={participant.name}
        />
      )}
      {canBecomeViewer && <BecomeViewerMenuItem participant={participant} />}
    </RACMenu>
  )
}
