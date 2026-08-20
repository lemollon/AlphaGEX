/**
 * The header bell (APP-033).
 *
 * There is no notification inbox screen yet, so the bell is NOT a link to a stub. It
 * does the one real job available: it carries the contextual permission ask that
 * APP-033 requires — "request OS notification permission contextually after explaining
 * value; do not prompt at first frame".
 *
 * The dot therefore means something true and actionable — alerts are off — rather than
 * being a decorative unread badge. Once permission is granted the dot goes away and the
 * bell stops asking. When the user has explicitly denied, the OS will not re-prompt, so
 * we send them to Settings instead of firing a request that silently no-ops.
 */
import { useCallback, useEffect, useState } from 'react'
import { Alert, Linking } from 'react-native'
import * as Notifications from 'expo-notifications'

type Status = 'unknown' | 'granted' | 'undetermined' | 'denied'

export function useNotificationBell(): { alert: boolean; onPress: () => void } {
  const [status, setStatus] = useState<Status>('unknown')

  useEffect(() => {
    let cancelled = false
    Notifications.getPermissionsAsync()
      .then((p) => {
        if (cancelled) return
        setStatus(p.granted ? 'granted' : p.canAskAgain ? 'undetermined' : 'denied')
      })
      .catch(() => {
        // A device that cannot report permission state is not a reason to nag.
        if (!cancelled) setStatus('granted')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const onPress = useCallback(() => {
    if (status === 'granted') {
      Alert.alert(
        'Alerts are on',
        'You will be notified when a trade opens, hits its target or stop, and when your brokerage needs attention.',
      )
      return
    }
    if (status === 'denied') {
      Alert.alert(
        'Alerts are turned off',
        'Notifications are disabled for IronForge in your device settings. Turn them on to hear about trade activity and brokerage problems.',
        [
          { text: 'Not now', style: 'cancel' },
          { text: 'Open Settings', onPress: () => void Linking.openSettings() },
        ],
      )
      return
    }
    Alert.alert(
      'Turn on trade alerts?',
      'IronForge will notify you when a trade opens, reaches its profit target or stop, and if your brokerage connection needs attention. Nothing else.',
      [
        { text: 'Not now', style: 'cancel' },
        {
          text: 'Turn on',
          onPress: () => {
            Notifications.requestPermissionsAsync()
              .then((p) => setStatus(p.granted ? 'granted' : p.canAskAgain ? 'undetermined' : 'denied'))
              .catch(() => setStatus('denied'))
          },
        },
      ],
    )
  }, [status])

  // Never flash a dot before we know the answer.
  return { alert: status === 'undetermined' || status === 'denied', onPress }
}
