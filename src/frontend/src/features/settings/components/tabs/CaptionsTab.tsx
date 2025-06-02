import { Field, H } from '@/primitives'
import { useTranslation } from 'react-i18next'
import { useLanguageLabels } from '@/i18n/useLanguageLabels'
import { TabPanel, TabPanelProps } from '@/primitives/Tabs'

export type CaptionsTabProps = Pick<TabPanelProps, 'id'>

export const CaptionsTab = ({ id }: CaptionsTabProps) => {

  const { t } = useTranslation('settings', { keyPrefix: 'captions' })
  const { languagesList, currentLanguage } = useLanguageLabels()

  return (
    <TabPanel padding={'md'} flex id={id}>
      <H lvl={2}>{t('heading')}</H>
      <Field
        type="select"
        label={t('label')}
        items={languagesList}
        defaultSelectedKey={currentLanguage.key}
        onSelectionChange={(lang) => {
        // TODO Set new language transcription
        }}
      />
    </TabPanel>
  )
}
