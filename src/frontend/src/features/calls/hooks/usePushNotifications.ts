import { useEffect, useRef } from 'react'
import { useSnapshot } from 'valtio'
import {
  setIncomingCall,
  clearIncomingCall,
  IncomingCall,
  incomingCallStore,
} from '@/stores/incomingCall'
import { fetchPendingCalls } from '../api/fetchPendingCalls'
import { useUser } from '@/features/auth'

const POLLING_INTERVAL_MS = 3000 // Poll every 3 seconds

/**
 * Hook to handle incoming call notifications.
 *
 * Uses polling to check for pending calls since push notifications
 * require device registration. Also listens for service worker messages
 * and BroadcastChannel for future push notification support.
 */
export const usePushNotifications = () => {
  const { isLoggedIn } = useUser()
  const { incomingCall } = useSnapshot(incomingCallStore)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    // Handle messages from service worker (for future push notification support)
    const handleServiceWorkerMessage = (event: MessageEvent) => {
      const data = event.data

      if (data?.type === 'incoming_call') {
        const call: IncomingCall = {
          call_id: data.call_id,
          caller_number: data.caller_number,
          callee_number: data.callee_number,
          lobby_room_name: data.lobby_room_name,
          sip_participant_identity: data.sip_participant_identity,
        }
        setIncomingCall(call)
      } else if (data?.type === 'call_cancelled') {
        clearIncomingCall()
      }
    }

    // Listen for messages from service worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener(
        'message',
        handleServiceWorkerMessage
      )
    }

    // Also listen for BroadcastChannel (alternative communication method)
    const channel = new BroadcastChannel('incoming-calls')
    channel.addEventListener('message', (event) => {
      handleServiceWorkerMessage(event)
    })

    return () => {
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.removeEventListener(
          'message',
          handleServiceWorkerMessage
        )
      }
      channel.close()
    }
  }, [])

  // Polling for pending calls
  useEffect(() => {
    if (!isLoggedIn) {
      // Clear polling if user logs out
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
      return
    }

    const checkPendingCalls = async () => {
      try {
        const response = await fetchPendingCalls()
        if (response.calls && response.calls.length > 0) {
          // Show the first pending call (or update if different call)
          const currentCallId = incomingCallStore.incomingCall?.call_id
          if (currentCallId !== response.calls[0].call_id) {
            setIncomingCall(response.calls[0])
          }
        } else {
          // No pending calls - clear any shown popup
          if (incomingCallStore.incomingCall) {
            clearIncomingCall()
          }
        }
      } catch (error) {
        // Silently ignore polling errors (user might not be authenticated)
        console.debug('Failed to fetch pending calls:', error)
      }
    }

    // Initial check
    checkPendingCalls()

    // Set up polling
    pollingRef.current = setInterval(checkPendingCalls, POLLING_INTERVAL_MS)

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }
  }, [isLoggedIn]) // Don't depend on incomingCall - we always want to poll
}

/**
 * Manually trigger an incoming call (for testing purposes).
 * This can be called from the browser console:
 *
 * window.simulateIncomingCall('+33612345678')
 */
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).simulateIncomingCall = (callerNumber: string = '+33612345678') => {
    const call: IncomingCall = {
      call_id: `test-${Date.now()}`,
      caller_number: callerNumber,
      callee_number: '+33535005942',
      lobby_room_name: `sip-lobby-test-${Date.now()}`,
      sip_participant_identity: 'sip-test-participant',
    }
    setIncomingCall(call)
  }
}
