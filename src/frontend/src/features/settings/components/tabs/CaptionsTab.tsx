import { Field, H } from '@/primitives'
import { useTranslation } from 'react-i18next'
import { useLanguageLabels } from '@/i18n/useLanguageLabels'
import { TabPanel, TabPanelProps } from '@/primitives/Tabs'
import { captionPreferenceStore } from '@/stores/captionPreference'
import { useSnapshot } from 'valtio'

export type CaptionsTabProps = Pick<TabPanelProps, 'id'>

export const CaptionsTab = ({ id }: CaptionsTabProps) => {
  const { t } = useTranslation('settings', { keyPrefix: 'captions' })
  const { languagesList } = useLanguageLabels()
  const preference = useSnapshot(captionPreferenceStore)

  return (
    <TabPanel padding={'md'} flex id={id}>
      <H lvl={2}>{t('heading')}</H>
      <Field
        type="select"
        label={t('label')}
        items={languagesList}
        defaultSelectedKey={preference.language}
        onSelectionChange={(lang) => {
          // TODO Set new language transcription
          captionPreferenceStore.language = lang?.toString() || ''
        }}
      />
    </TabPanel>
  )
}
