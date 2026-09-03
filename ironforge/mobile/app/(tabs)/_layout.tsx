import { useEffect } from 'react'
import { AppState, type AppStateStatus } from 'react-native'
import { Tabs } from 'expo-router'
import { color, font } from '@/theme/tokens'
import { ForgeIcon, LedgerIcon, CommunityIcon, AccountIcon } from '@/components/icons'
import { registerPushDevice, usePushNavigation } from '@/notifications/push'
import { useScreenTracking } from '@/analytics/screen-tracking'
import { initMonitoring } from '@/monitoring/sentry'

/**
 * Crash reporting has to be live before anything under the tabs can throw. The tabs
 * are the first screen group that only ever mounts once a customer is signed in
 * (app/_layout.tsx's auth gate), so this module's first import is as early as WP-E
 * can hook in without touching WP-A's app/_layout.tsx (SPEC.md file ownership).
 */
initMonitoring()

/**
 * The four approved bottom tabs (APP-003): Forge, Ledger, Community, Account.
 * Order and labels come from the Screen Map and are not ours to change.
 *
 * The icons used to be emoji rendered as <Text> (🛡 ▤ 👥 👤). The OS paints those in
 * its own colour, so they ignored the active tint entirely and never matched UX-002.
 * They are vector now — see components/icons.tsx.
 */
export default function TabsLayout() {
  // Push device registration (APP-034) — safe to call every time the tabs mount or
  // the app returns to the foreground; it no-ops when the token has not changed.
  // Tap routing (usePushNavigation) and automatic screen views live here too, since
  // the tabs are the one layout every signed-in screen sits under.
  usePushNavigation()
  useScreenTracking()

  useEffect(() => {
    void registerPushDevice()
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (next === 'active') void registerPushDevice()
    })
    return () => sub.remove()
  }, [])

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: color.card,
          borderTopColor: color.border,
          height: 88,
          paddingTop: 8,
        },
        tabBarActiveTintColor: color.accent,
        tabBarInactiveTintColor: color.muted,
        tabBarLabelStyle: { fontFamily: font.bodyMedium, fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Forge', tabBarIcon: ForgeIcon }}
      />
      <Tabs.Screen
        name="ledger"
        options={{ title: 'Ledger', tabBarIcon: LedgerIcon }}
      />
      <Tabs.Screen
        name="community"
        options={{ title: 'Community', tabBarIcon: CommunityIcon }}
      />
      <Tabs.Screen
        name="account"
        options={{ title: 'Account', tabBarIcon: AccountIcon }}
      />
    </Tabs>
  )
}
