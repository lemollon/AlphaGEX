import { Tabs } from 'expo-router'
import { color, font } from '@/theme/tokens'
import { ForgeIcon, LedgerIcon, CommunityIcon, AccountIcon } from '@/components/icons'

/**
 * The four approved bottom tabs (APP-003): Forge, Ledger, Community, Account.
 * Order and labels come from the Screen Map and are not ours to change.
 *
 * The icons used to be emoji rendered as <Text> (🛡 ▤ 👥 👤). The OS paints those in
 * its own colour, so they ignored the active tint entirely and never matched UX-002.
 * They are vector now — see components/icons.tsx.
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
