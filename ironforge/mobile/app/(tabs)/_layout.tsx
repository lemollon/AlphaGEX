import { Tabs } from 'expo-router'
import { color, font } from '@/theme/tokens'
import {
  ForgeTabIcon,
  LedgerTabIcon,
  CommunityTabIcon,
  AccountTabIcon,
} from '@/components/brand'

/**
 * The four approved bottom tabs (APP-003): Forge, Ledger, Community, Account.
 * Order and labels come from the Screen Map and are not ours to change.
 *
 * Icons are vector (see components/brand.tsx), not emoji. Emoji glyphs render in the
 * system font, so they differ between Android versions and OEM skins and cannot take
 * the focused accent colour — the tab bar is the most-seen chrome in the app and had
 * no business being the least controlled.
 */
export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: color.card,
          borderTopColor: color.border,
          height: 88,
          paddingTop: 10,
          paddingBottom: 8,
        },
        tabBarActiveTintColor: color.accent,
        tabBarInactiveTintColor: color.muted,
        tabBarLabelStyle: { fontFamily: font.bodyMedium, fontSize: 11, marginTop: 2 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Forge',
          tabBarIcon: ({ color: c }) => <ForgeTabIcon c={c} />,
        }}
      />
      <Tabs.Screen
        name="ledger"
        options={{
          title: 'Ledger',
          tabBarIcon: ({ color: c }) => <LedgerTabIcon c={c} />,
        }}
      />
      <Tabs.Screen
        name="community"
        options={{
          title: 'Community',
          tabBarIcon: ({ color: c }) => <CommunityTabIcon c={c} />,
        }}
      />
      <Tabs.Screen
        name="account"
        options={{
          title: 'Account',
          tabBarIcon: ({ color: c }) => <AccountTabIcon c={c} />,
        }}
      />
    </Tabs>
  )
}
