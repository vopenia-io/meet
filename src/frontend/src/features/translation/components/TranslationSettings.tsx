import { useState, useEffect } from 'react'
import { css } from '@/styled-system/css'
import { Button, Field, Text } from '@/primitives'

export type Language = {
  code: string
  name: string
}

export interface TranslationSettingsProps {
  availableLanguages: Language[]
  selectedLanguages: Language[]
  onChangeSelectedLanguages: (langs: Language[]) => void
  isLoading: boolean
  isActive: boolean
  onClose: () => void
  onStart: () => void | Promise<void>
  onStop: () => void | Promise<void>
}

// export const TranslationSettings = ({
//   availableLanguages,
//   selectedLanguages,
//   onChangeSelectedLanguages,
//   isLoading,
//   isActive,
//   onClose,
//   onStart,
//   onStop,
// }: TranslationSettingsProps) => {
//   const [newLanguage, setNewLanguage] = useState<Language | null>(null)

//   useEffect(() => {
//     if (!newLanguage) return
//     if (selectedLanguages.includes(newLanguage)) {
//       setNewLanguage(null)
//     }
//   }, [newLanguage, selectedLanguages])

//   useEffect(() => {
//     const uniqueLangs = Array.from(new Set(selectedLanguages))
//     if (uniqueLangs.length !== selectedLanguages.length) {
//       onChangeSelectedLanguages(uniqueLangs)
//     }
//   }, [selectedLanguages, onChangeSelectedLanguages])

//   return (
//     <div
//       tabIndex={-1}
//       className={css({
//         position: 'fixed',
//         top: '50%',
//         left: '50%',
//         transform: 'translate(-50%, -50%)',
//         backgroundColor: 'white',
//         borderRadius: '8px',
//         boxShadow: '0 4px 8px rgba(0, 0, 0, 0.2)',
//         padding: '1rem',
//         zIndex: 1000,
//         maxW: '520px',
//         w: '90%',
//       })}
//     >
//       <Text as="h1">Settings</Text>
//       {selectedLanguages.map((lang) => (
//         <div
//           key={lang.code}
//           className={css({
//             marginBottom: '0.5rem',
//             display: 'flex',
//             flexDirection: 'row',
//             alignItems: 'center',
//             justifyContent: 'space-between',
//           })}
//         >
//           <Text as="span">{lang.name} - ({lang.code})</Text>
//           <Button
//             size="sm"
//             variant="danger"
//             onClick={() =>
//               onChangeSelectedLanguages(
//                 selectedLanguages.filter((l) => l !== lang)
//               )
//             }
//           >
//             Remove
//           </Button>
//         </div>
//       ))}
//       <div
//         className={css({
//           display: 'flex',
//           flexDirection: 'row',
//           gap: '1rem',
//           marginY: '1rem',
//           alignItems: 'center',
//           justifyContent: 'space-between',
//         })}
//       >
//         <Field
//           label="Language"
//           type="select"
//           items={availableLanguages
//             .filter((l) => !selectedLanguages.map(sl => sl.code).includes(l.code))
//             .map((lang) => ({
//               key: lang.code,
//               value: lang.code,
//               label: lang.name,
//             }))}
//           onSelectionChange={(key) =>
//             setNewLanguage(key ? availableLanguages.find((l) => l.code === key) || null : null)
//           }
//           selectedKey={newLanguage?.code}
//         />
//         <Button
//           size="sm"
//           onClick={() => {
//             if (newLanguage) {
//               onChangeSelectedLanguages([...selectedLanguages, newLanguage])
//               setNewLanguage(null)
//             }
//           }}
//         >
//           Add
//         </Button>
//       </div>
//       <div
//         className={css({
//           display: 'flex',
//           gap: '0.5rem',
//           justifyContent: 'flex-end',
//           mt: '1rem',
//         })}
//       >
//         <Button
//           variant="secondary"
//           onClick={onClose}
//           isPending={isLoading}
//           isDisabled={isActive}
//         >
//           Close
//         </Button>
//         {isActive ? (
//           <Button
//             variant="secondary"
//             onClick={onStop}
//             isPending={isLoading}
//             isDisabled={!isActive}
//           >
//             Stop
//           </Button>
//         ) : (
//           <Button onClick={onStart} isDisabled={selectedLanguages.length === 0}>
//             Start
//           </Button>
//         )}
//       </div>
//     </div>
//   )
// }

export const TranslationSettings = ({
  availableLanguages,
  selectedLanguages,
  onChangeSelectedLanguages,
  isLoading,
  isActive,
  onClose,
  onStart,
  onStop,
}: TranslationSettingsProps) => {
  const [newLanguage, setNewLanguage] = useState<Language | null>(null)

  useEffect(() => {
    if (!newLanguage) return
    if (selectedLanguages.includes(newLanguage)) {
      setNewLanguage(null)
    }
  }, [newLanguage, selectedLanguages])

  useEffect(() => {
    const uniqueLangs = Array.from(new Set(selectedLanguages))
    if (uniqueLangs.length !== selectedLanguages.length) {
      onChangeSelectedLanguages(uniqueLangs)
    }
  }, [selectedLanguages, onChangeSelectedLanguages])

  return (
    <div
      tabIndex={-1}
      className={css({
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        backgroundColor: 'white',
        borderRadius: '8px',
        boxShadow: '0 4px 8px rgba(0, 0, 0, 0.2)',
        padding: '1rem',
        zIndex: 1000,
        maxW: '520px',
        w: '90%',
      })}
    >
      <Text as="h1">Settings</Text>

      <Field
        label="Language"
        type="checkboxGroup"
        items={availableLanguages.map((lang) => ({
          key: lang.code,
          value: lang.code,
          label: lang.name,
        }))}
        onChange={(values) => {
          const selected = availableLanguages.filter((lang) =>
            values.includes(lang.code)
          )
          onChangeSelectedLanguages(selected)
        }}
      />
      <div
        className={css({
          display: 'flex',
          gap: '0.5rem',
          justifyContent: 'flex-end',
          mt: '1rem',
        })}
      >
        <Button
          variant="secondary"
          onClick={onClose}
          isPending={isLoading}
          isDisabled={isActive}
        >
          Close
        </Button>
        {isActive ? (
          <Button
            variant="secondary"
            onClick={onStop}
            isPending={isLoading}
            isDisabled={!isActive}
          >
            Stop
          </Button>
        ) : (
          <Button onClick={onStart} isDisabled={selectedLanguages.length === 0}>
            Start
          </Button>
        )}
      </div>
    </div>
  )
}
