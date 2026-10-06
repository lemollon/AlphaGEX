/**
 * "You're offline" banner (mobile fidelity #294). Subscribes to live/connectivity.ts,
 * which infers online/offline from the app's own request traffic (no NetInfo — see
 * that module's header for why). Mounted once in app/_layout.tsx, same shape as
 * ToastHost, so it sits above every screen without each one wiring its own.
 *
 * Deliberately not dismissible: it clears itself the moment a request succeeds,
 * which is a more honest signal than a customer tapping it away and forgetting the
 * data underneath might still be stale.
 */
import { useEffect, useState } from 'react'
import { View, Text, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { isOffline, subscribeConnectivity } from '@/live/connectivity'
import { space, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'

export function ConnectivityBanner() {
  const { colors: color } = useTheme()
  const [offline, setOfflineState] = useState(isOffline())

  useEffect(() => subscribeConnectivity(setOfflineState), [])

  if (!offline) return null

  return (
    <SafeAreaView edges={['top']} style={styles.wrap} pointerEvents="none">
      <View style={[styles.banner, { backgroundColor: color.warn }]}>
        <Text style={[type.label, { color: color.bg, fontFamily: font.bodyMedium }]}>
          You&apos;re offline — showing the last saved data
        </Text>
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', top: 0, left: 0, right: 0, zIndex: 70 },
  banner: { paddingVertical: space.xs, paddingHorizontal: space.md, alignItems: 'center' },
})
