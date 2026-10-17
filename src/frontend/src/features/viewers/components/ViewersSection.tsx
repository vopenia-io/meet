import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ListBox,
  ListBoxItem,
  ListLayout,
  SearchField,
  Virtualizer,
} from 'react-aria-components'
import type { Participant } from 'livekit-client'
import { css } from '@/styled-system/css'
import { HStack } from '@/styled-system/jsx'
import { Input } from '@/primitives'
import { Avatar } from '@/components/Avatar'
import { getParticipantColor } from '@/features/rooms/utils/getParticipantColor'
import { ParticipantName } from '@/features/participants/components/ParticipantName'
import { ParticipantsCollapsibleSection } from '@/features/participants/components/ParticipantsCollapsibleSection'

const ROW_HEIGHT = 44
// Past this many viewers, the list scrolls on its own.
const MAX_VISIBLE_ROWS = 8

const getName = (participant: Participant) =>
  participant.name || participant.identity

/**
 * Viewers of the room. There can be hundreds of them: they are searchable,
 * and only the rows on screen are rendered.
 */
export const ViewersSection = ({ viewers }: { viewers: Participant[] }) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'viewers.section' })
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    if (!query) return viewers
    return viewers.filter((viewer) =>
      getName(viewer).toLocaleLowerCase().includes(query)
    )
  }, [viewers, search])

  return (
    <ParticipantsCollapsibleSection
      heading={t('heading')}
      count={viewers.length}
    >
      <SearchField
        aria-label={t('search')}
        value={search}
        onChange={setSearch}
        className={css({ width: 'full', marginBottom: '0.5rem' })}
      >
        <Input placeholder={t('search')} />
      </SearchField>
      <Virtualizer
        layout={ListLayout}
        layoutOptions={{ rowHeight: ROW_HEIGHT }}
      >
        <ListBox
          aria-label={t('heading')}
          items={filtered.map((viewer) => ({ id: viewer.identity, viewer }))}
          selectionMode="none"
          renderEmptyState={() => t('empty')}
          style={{
            display: 'block',
            width: '100%',
            height: `${Math.min(Math.max(filtered.length, 1), MAX_VISIBLE_ROWS) * ROW_HEIGHT}px`,
            overflow: 'auto',
          }}
        >
          {({ viewer }) => (
            <ListBoxItem textValue={getName(viewer)} style={{ width: '100%' }}>
              <HStack height={`${ROW_HEIGHT}px`} minW="0">
                <Avatar
                  name={getName(viewer)}
                  bgColor={getParticipantColor(viewer)}
                />
                <ParticipantName
                  displayedName={getName(viewer)}
                  isLocal={viewer.isLocal}
                />
              </HStack>
            </ListBoxItem>
          )}
        </ListBox>
      </Virtualizer>
    </ParticipantsCollapsibleSection>
  )
}
