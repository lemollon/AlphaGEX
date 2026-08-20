/**
 * Tab bar icons (APP-003).
 *
 * These were emoji rendered as <Text> — 🛡 ▤ 👥 👤 — which the OS paints in its own
 * colour and style, so the tab bar never matched the mockups on any device and could
 * not take the active tint at all. Ledger / Community / Account come from Ionicons,
 * which ships with Expo; Forge is the IF mark inside a shield, drawn as vector so it
 * stays crisp and takes the focus colour.
 */
import { View } from 'react-native'
import Svg, { Path } from 'react-native-svg'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts (~3 MB,
// MaterialCommunityIcons alone is 1.3 MB). Ionicons is the only set used.
import Ionicons from '@expo/vector-icons/Ionicons'
import { color } from '@/theme/tokens'

const SIZE = 26

/** Shield outline with the IF mark centred — the Forge tab. */
export function ForgeIcon({ focused }: { focused: boolean }) {
  const tint = focused ? color.accent : color.muted
  return (
    <View style={{ width: SIZE, height: SIZE, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={SIZE} height={SIZE} viewBox="0 0 24 24">
        <Path
          d="M12 2.5 20 5.5v6.2c0 4.6-3.2 8.4-8 9.8-4.8-1.4-8-5.2-8-9.8V5.5L12 2.5Z"
          stroke={tint}
          strokeWidth={1.7}
          strokeLinejoin="round"
          fill={focused ? `${color.accent}22` : 'none'}
        />
        {/* The IF monogram, reduced to its two strokes so it survives 26px. */}
        <Path d="M9.4 8.4v7.2" stroke={tint} strokeWidth={1.9} strokeLinecap="round" />
        <Path
          d="M12.4 15.6V8.4h3.4M12.4 11.8h2.7"
          stroke={tint}
          strokeWidth={1.7}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </Svg>
    </View>
  )
}

export function LedgerIcon({ focused }: { focused: boolean }) {
  return (
    <Ionicons
      name={focused ? 'book' : 'book-outline'}
      size={SIZE - 2}
      color={focused ? color.accent : color.muted}
    />
  )
}

export function CommunityIcon({ focused }: { focused: boolean }) {
  return (
    <Ionicons
      name={focused ? 'people' : 'people-outline'}
      size={SIZE - 1}
      color={focused ? color.accent : color.muted}
    />
  )
}

export function AccountIcon({ focused }: { focused: boolean }) {
  return (
    <Ionicons
      name={focused ? 'person' : 'person-outline'}
      size={SIZE - 3}
      color={focused ? color.accent : color.muted}
    />
  )
}
