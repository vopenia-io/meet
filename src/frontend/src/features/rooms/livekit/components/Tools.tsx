import { A, Div, H, P, Text } from '@/primitives'
import { css } from '@/styled-system/css'
import { Button as RACButton } from 'react-aria-components'
import { RiFileTextFill, RiLiveFill } from '@remixicon/react'

const ActionButton = ({ icon, title, description, onPress }) => {
  return (
    <RACButton
      className={css({
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'start',
        paddingY: '0.5rem',
        paddingX: '0.75rem 1.5rem',
        borderRadius: '5px',
        gap: '1.25rem',
        width: 'full',
        textAlign: 'start',
        '&[data-hovered]': {
          backgroundColor: 'primary.50',
          cursor: 'pointer',
        },
      })}
      onPress={onPress}
    >
      <div
        className={css({
          height: '50px',
          minWidth: '50px',
          borderRadius: '25px',
          backgroundColor: 'primary.800',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
        })}
      >
        {icon}
      </div>
      <div>
        <Text margin={false} as="h3">
          {title}
        </Text>
        <Text as={'p'} variant={'smNote'} wrap={'pretty'}>
          {description}
        </Text>
      </div>
    </RACButton>
  )
}

export const Tools = () => {
  return (
    <Div
      display="flex"
      overflowY="scroll"
      padding="0 0.75rem"
      flexGrow={1}
      flexDirection="column"
      alignItems="start"
    >
      <Text
        variant="note"
        wrap="balance"
        className={css({
          textStyle: 'sm',
          paddingX: '0.75rem',
        })}
        margin={'md'}
      >
        Nous essayons d'intégrer plus d'outils dans visio blablabzlab,{' '}
        <A href="/">En savoir plus</A>.
      </Text>
      <ActionButton
        icon={<RiFileTextFill size={24} color={'white'} />}
        title={'Transcription'}
        description={
          'Transcrivez votre réunion et recevez son résultat à la fin.'
        }
      />
      <ActionButton
        icon={<RiLiveFill size={24} color={'white'} />}
        title={'Enregistrement'}
        description={'Enregistrer votre réunion pour la rejouer à la demande.'}
      />
      {/*<ActionButton />*/}
      {/*<ActionButton />*/}
    </Div>
  )
}
