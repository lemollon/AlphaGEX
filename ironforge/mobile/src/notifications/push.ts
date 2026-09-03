/**
 * Push device registration + tap routing (APP-034/035).
 *
 * Two halves that must both work for a customer to ever see a notification:
 *
 *   1. registerPushDevice()/unregisterPushDevice() — the token round-trip with
 *      POST/DELETE /api/notifications/devices. This is NOT the permission ask —
 *      that stays in notifications/bell.ts (APP-033's "contextual, not at first
 *      frame"). This module only acts once permission is ALREADY granted, and is
 *      safe to call on every foreground/sign-in: it no-ops when nothing changed.
 *
 *   2. usePushNavigation() — what happens when a customer TAPS a delivered push.
 *      The routing decision itself is pure (route-for.ts) so it can be unit
 *      tested without expo-notifications in the loop; this hook is just the glue
 *      between the native listener and the router.
 *
 * setNotificationHandler is a MODULE-LEVEL side effect (not inside a component),
 * matching expo-notifications' own contract: it must be registered before any
 * notification can arrive, which for a cold start showing a notification means
 * before the first screen mounts.
 */
import { useEffect } from 'react'
import { Platform } from 'react-native'
import { useRouter } from 'expo-router'
import Constants from 'expo-constants'
import * as Notifications from 'expo-notifications'
import * as Device from 'expo-device'
import { api } from '@/api/client'
import { getItem, setItem, deleteItem } from '@/api/storage'
import { tradeDetailHref } from '@/ledger/detail'
import { agentDetailHref } from '@/agents/routes'
import { routeFor, type PushNavData } from '@/notifications/route-for'

const PUSH_TOKEN_KEY = 'ironforge.pushToken'

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
})

// Default Android channel. app.config.ts's expo-notifications plugin points
// `defaultChannel` at this same id ("alerts") — declaring it there only edits the
// manifest; the channel itself has to exist on the device before the OS will use it.
if (Platform.OS === 'android') {
  void Notifications.setNotificationChannelAsync('alerts', {
    name: 'Alerts',
    importance: Notifications.AndroidImportance.DEFAULT,
  })
}

/**
 * Register (or re-confirm) this device's push token with the server.
 *
 * Safe to call every time the app comes to the foreground: if the token has not
 * changed since the last successful registration, this is a no-op past the local
 * token fetch — no network call, no server write. Does nothing (silently) when
 * permission has not been granted; that ask belongs to notifications/bell.ts.
 */
export async function registerPushDevice(): Promise<void> {
  try {
    const perms = await Notifications.getPermissionsAsync()
    if (!perms.granted) return

    const platform = Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : null
    if (!platform) return

    const projectId = (
      Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined
    )?.eas?.projectId
    if (!projectId) return

    const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId })
    if (!token) return

    const previous = await getItem(PUSH_TOKEN_KEY)
    if (previous === token) return

    await api('/api/notifications/devices', {
      method: 'POST',
      body: {
        expoPushToken: token,
        platform,
        // iOS reports a real model id ("iPhone7,2"); Android reports null there, so
        // the OS build id is the fallback that actually identifies the handset.
        deviceId: Device.modelId ?? Device.osBuildId ?? undefined,
        appVersion: Constants.expoConfig?.version,
      },
    })
    await setItem(PUSH_TOKEN_KEY, token)
  } catch (e) {
    // Fire-and-forget by contract (SPEC.md) — a flaky network call must never block
    // sign-in or app foregrounding.
    console.warn('[push] registerPushDevice failed', e)
  }
}

/**
 * Unregister this device. WP-C's sign-out handler MUST await this BEFORE clearing
 * tokens — the server call above still needs a valid session to authenticate.
 */
export async function unregisterPushDevice(): Promise<void> {
  try {
    const token = await getItem(PUSH_TOKEN_KEY)
    if (!token) return
    await api('/api/notifications/devices', {
      method: 'DELETE',
      body: { expoPushToken: token },
    })
  } catch (e) {
    console.warn('[push] unregisterPushDevice failed', e)
  } finally {
    await deleteItem(PUSH_TOKEN_KEY).catch(() => {})
  }
}

/**
 * Routes a tapped notification to the right screen — a cold-start tap (the app was
 * not running) via getLastNotificationResponseAsync, and a background/foreground tap
 * via the live listener. Mounted once, in app/(tabs)/_layout.tsx.
 */
export function usePushNavigation(): void {
  const router = useRouter()

  useEffect(() => {
    function handle(data: unknown) {
      const href = routeFor(data as PushNavData, { tradeDetailHref, agentDetailHref })
      if (href) router.push(href)
    }

    let cancelled = false
    Notifications.getLastNotificationResponseAsync()
      .then((response) => {
        if (!cancelled && response) handle(response.notification.request.content.data)
      })
      .catch(() => {})

    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      handle(response.notification.request.content.data)
    })
    return () => {
      cancelled = true
      sub.remove()
    }
  }, [router])
}
