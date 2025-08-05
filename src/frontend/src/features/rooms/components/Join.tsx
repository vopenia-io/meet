import { useTranslation } from 'react-i18next'
import { usePreviewTracks } from '@livekit/components-react'
import { css } from '@/styled-system/css'
import { Screen } from '@/layout/Screen'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LocalVideoTrack, Track } from 'livekit-client'
import { H } from '@/primitives/H'
import { SelectToggleDevice } from '../livekit/components/controls/SelectToggleDevice'
import { Field } from '@/primitives/Field'
import { Button, Dialog, Text, Form } from '@/primitives'
import { HStack, VStack } from '@/styled-system/jsx'
import { Heading } from 'react-aria-components'
import { RiImageCircleAiFill } from '@remixicon/react'
import {
  EffectsConfiguration,
  EffectsConfigurationProps,
} from '../livekit/components/effects/EffectsConfiguration'
import { usePersistentUserChoices } from '../livekit/hooks/usePersistentUserChoices'
import { BackgroundProcessorFactory } from '../livekit/components/blur'
import { isMobileBrowser } from '@livekit/components-core'
import { fetchRoom } from '@/features/rooms/api/fetchRoom'
import { keys } from '@/api/queryKeys'
import { useLobby } from '../hooks/useLobby'
import { useQuery } from '@tanstack/react-query'
import { queryClient } from '@/api/queryClient'
import { ApiLobbyStatus, ApiRequestEntry } from '../api/requestEntry'
import { Spinner } from '@/primitives/Spinner'
import { ApiAccessLevel } from '../api/ApiRoom'
import { useLoginHint } from '@/hooks/useLoginHint'
import { LocalUserChoices } from '@/stores/userChoices'

const onError = (e: Error) => console.error('ERROR', e)

const Effects = ({
  videoTrack,
  onSubmit,
}: Pick<EffectsConfigurationProps, 'videoTrack' | 'onSubmit'>) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'join.effects' })
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const openDialog = () => setIsDialogOpen(true)

  if (!BackgroundProcessorFactory.isSupported() || isMobileBrowser()) {
    return
  }

  return (
    <>
      <Dialog
        isOpen={isDialogOpen}
        onOpenChange={setIsDialogOpen}
        role="dialog"
        type="flex"
        size="large"
      >
        <Heading
          slot="title"
          level={1}
          className={css({
            textStyle: 'h1',
            marginBottom: '0.25rem',
          })}
        >
          {t('title')}
        </Heading>
        <Text
          variant="subTitle"
          className={css({
            marginBottom: '1.5rem',
          })}
        >
          {t('subTitle')}
        </Text>
        <EffectsConfiguration videoTrack={videoTrack} onSubmit={onSubmit} />
      </Dialog>
      <div
        className={css({
          position: 'absolute',
          right: 0,
          bottom: '0',
          padding: '1rem',
          zIndex: '1',
        })}
      >
        <Button
          variant="whiteCircle"
          onPress={openDialog}
          tooltip={t('description')}
          aria-label={t('description')}
        >
          <RiImageCircleAiFill size={24} />
        </Button>
      </div>
      <div
        className={css({
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: '20%',
          backgroundImage:
            'linear-gradient(0deg, rgba(0,0,0,0.7) 0%, rgba(255,255,255,0) 100%)',
          borderBottomRadius: '1rem',
        })}
      />
    </>
  )
}

export const Join = ({
  onSubmit,
  roomId,
}: {
  onSubmit: (choices: LocalUserChoices) => void
  roomId: string
}) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'join' })

  const {
    userChoices: {
      audioEnabled,
      videoEnabled,
      audioDeviceId,
      videoDeviceId,
      processorSerialized,
      username,
    },
    saveAudioInputEnabled,
    saveVideoInputEnabled,
    saveAudioInputDeviceId,
    saveVideoInputDeviceId,
    saveUsername,
    saveProcessorSerialized,
  } = usePersistentUserChoices()

  const [processor, setProcessor] = useState(
    BackgroundProcessorFactory.deserializeProcessor(processorSerialized)
  )

  useEffect(() => {
    saveProcessorSerialized(processor?.serialize())
  }, [
    processor,
    saveProcessorSerialized,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    JSON.stringify(processor?.serialize()),
  ])

  const tracks = usePreviewTracks(
    {
      audio: { deviceId: audioDeviceId },
      video: { deviceId: videoDeviceId },
    },
    onError
  )

  const videoTrack = useMemo(
    () =>
      tracks?.filter(
        (track) => track.kind === Track.Kind.Video
      )[0] as LocalVideoTrack,
    [tracks]
  )

  const audioTrack = useMemo(
    () =>
      tracks?.filter(
        (track) => track.kind === Track.Kind.Audio
      )[0] as LocalVideoTrack,
    [tracks]
  )

  const videoEl = useRef(null)

  useEffect(() => {
    const videoElement = videoEl.current as HTMLVideoElement | null

    const handleVideoLoaded = () => {
      if (videoElement) {
        videoElement.style.opacity = '1'
      }
    }

    if (videoElement && videoTrack && videoEnabled) {
      videoTrack.unmute()
      videoTrack.attach(videoElement)
      videoElement.addEventListener('loadedmetadata', handleVideoLoaded)
    }

    return () => {
      videoTrack?.detach()
      videoElement?.removeEventListener('loadedmetadata', handleVideoLoaded)
    }
  }, [videoTrack, videoEnabled])

  const enterRoom = useCallback(() => {
    onSubmit({
      audioEnabled,
      videoEnabled,
      audioDeviceId,
      videoDeviceId,
      username,
      processorSerialized: processor?.serialize(),
    })
  }, [
    onSubmit,
    audioEnabled,
    videoEnabled,
    audioDeviceId,
    videoDeviceId,
    username,
    processor,
  ])

  // Room data strategy:
  // 1. Initial fetch is performed to check access and get LiveKit configuration
  // 2. Data remains valid for 6 hours to avoid unnecessary refetches
  // 3. State is manually updated via queryClient when a waiting participant is accepted
  // 4. No automatic refetching or revalidation occurs during this period
  // todo - refactor in a hook
  const {
    data: roomData,
    error,
    isError,
    refetch: refetchRoom,
  } = useQuery({
    /* eslint-disable @tanstack/query/exhaustive-deps */
    queryKey: [keys.room, roomId],
    queryFn: () => fetchRoom({ roomId, username }),
    staleTime: 6 * 60 * 60 * 1000, // By default, LiveKit access tokens expire 6 hours after generation
    retry: false,
    enabled: false,
  })

  useEffect(() => {
    if (isError && error?.statusCode == 404) {
      // The room component will handle the room creation if the user is authenticated
      enterRoom()
    }
  }, [isError, error, enterRoom])

  const handleAccepted = (response: ApiRequestEntry) => {
    queryClient.setQueryData([keys.room, roomId], {
      ...roomData,
      livekit: response.livekit,
    })
    enterRoom()
  }

  const { status, startWaiting } = useLobby({
    roomId,
    username,
    onAccepted: handleAccepted,
  })

  const { openLoginHint } = useLoginHint()

  const handleSubmit = async () => {
    const { data } = await refetchRoom()

    if (!data?.livekit) {
      // Display a message to inform the user that by logging in, they won't have to wait for room entry approval.
      if (data?.access_level == ApiAccessLevel.TRUSTED) {
        openLoginHint()
      }
      startWaiting()
      return
    }

    enterRoom()
  }

  // This hook is used to setup the persisted user choice processor on initialization.
  // So it's on purpose that processor is not included in the deps.
  // We just want to wait for the videoTrack to be loaded to apply the default processor.
  useEffect(() => {
    if (processor && videoTrack && !videoTrack.getProcessor()) {
      videoTrack.setProcessor(processor)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoTrack])

  const renderWaitingState = () => {
    switch (status) {
      case ApiLobbyStatus.TIMEOUT:
        return (
          <VStack alignItems="center" textAlign="center">
            <H lvl={1} margin={false} centered>
              {t('timeoutInvite.title')}
            </H>
            <Text as="p" variant="note">
              {t('timeoutInvite.body')}
            </Text>
          </VStack>
        )

      case ApiLobbyStatus.DENIED:
        return (
          <VStack alignItems="center" textAlign="center">
            <H lvl={1} margin={false} centered>
              {t('denied.title')}
            </H>
            <Text as="p" variant="note">
              {t('denied.body')}
            </Text>
          </VStack>
        )

      case ApiLobbyStatus.WAITING:
        return (
          <VStack alignItems="center" textAlign="center">
            <H lvl={1} margin={false} centered>
              {t('waiting.title')}
            </H>
            <Text
              as="p"
              variant="note"
              className={css({ marginBottom: '1.5rem' })}
            >
              {t('waiting.body')}
            </Text>
            <Spinner />
          </VStack>
        )

      default:
        return (
          <Form
            onSubmit={handleSubmit}
            submitLabel={t('joinLabel')}
            submitButtonProps={{
              fullWidth: true,
            }}
          >
            <VStack marginBottom={1}>
              <H lvl={1} margin="sm" centered>
                {t('heading')}
              </H>
              <Field
                type="text"
                onChange={saveUsername}
                label={t('usernameLabel')}
                defaultValue={username}
                validate={(value) => !value && t('errors.usernameEmpty')}
                wrapperProps={{
                  noMargin: true,
                  fullWidth: true,
                }}
                labelProps={{
                  center: true,
                }}
                maxLength={50}
              />
            </VStack>
          </Form>
        )
    }
  }

  return (
    <Screen footer={false}>
      <div
        className={css({
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          flexGrow: 1,
          lg: {
            alignItems: 'center',
          },
        })}
      >
        <div
          className={css({
            display: 'flex',
            height: 'auto',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '2rem',
            padding: '0 2rem',
            flexDirection: 'column',
            minWidth: 0,
            width: '100%',
            lg: {
              flexDirection: 'row',
              width: 'auto',
              height: '570px',
            },
          })}
        >
          <div
            className={css({
              width: '100%',
              lg: {
                width: '740px',
              },
            })}
          >
            <div
              className={css({
                borderRadius: '1rem',
                overflow: 'hidden',
                position: 'relative',
                width: '100%',
                height: 'auto',
                aspectRatio: 16 / 9,
                '--tw-shadow':
                  '0 10px 15px -5px #00000010, 0 4px 5px -6px #00000010',
                '--tw-shadow-colored':
                  '0 10px 15px -5px var(--tw-shadow-color), 0 8px 10px -6px var(--tw-shadow-color)',
                boxShadow:
                  'var(--tw-ring-offset-shadow, 0 0 #0000), var(--tw-ring-shadow, 0 0 #0000), var(--tw-shadow)',
                backgroundColor: 'black',
              })}
            >
              {videoTrack && videoEnabled ? (
                // eslint-disable-next-line jsx-a11y/media-has-caption
                <video
                  ref={videoEl}
                  width="1280"
                  height="720"
                  className={css({
                    display: 'block',
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    transform: 'rotateY(180deg)',
                    opacity: 0,
                    transition: 'opacity 0.3s ease-in-out',
                    borderRadius: '1rem',
                  })}
                  disablePictureInPicture
                  disableRemotePlayback
                />
              ) : (
                <div
                  className={css({
                    width: '100%',
                    height: '100%',
                    color: 'white',
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                  })}
                >
                  <p
                    className={css({
                      fontSize: '24px',
                      fontWeight: '300',
                    })}
                  >
                    {!videoEnabled && t('cameraDisabled')}
                    {videoEnabled && !videoTrack && t('cameraStarting')}
                  </p>
                </div>
              )}
              <Effects videoTrack={videoTrack} onSubmit={setProcessor} />
            </div>
            <HStack justify="center" padding={1.5}>
              <SelectToggleDevice
                source={Track.Source.Microphone}
                initialState={audioEnabled}
                track={audioTrack}
                initialDeviceId={audioDeviceId}
                onChange={(enabled) => saveAudioInputEnabled(enabled)}
                onDeviceError={(error) => console.error(error)}
                onActiveDeviceChange={(deviceId) =>
                  saveAudioInputDeviceId(deviceId ?? '')
                }
                variant="tertiary"
              />
              <SelectToggleDevice
                source={Track.Source.Camera}
                initialState={videoEnabled}
                track={videoTrack}
                initialDeviceId={videoDeviceId}
                onChange={(enabled) => saveVideoInputEnabled(enabled)}
                onDeviceError={(error) => console.error(error)}
                onActiveDeviceChange={(deviceId) =>
                  saveVideoInputDeviceId(deviceId ?? '')
                }
                variant="tertiary"
              />
            </HStack>
          </div>
          <div
            className={css({
              width: '100%',
              flexShrink: 0,
              padding: '0',
              sm: {
                width: '448px',
                padding: '0 3rem 9rem 3rem',
              },
            })}
          >
            {renderWaitingState()}
          </div>
        </div>
      </div>
    </Screen>
  )
}
