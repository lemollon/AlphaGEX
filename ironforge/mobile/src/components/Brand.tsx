/**
 * Brand chrome — the app header and the agent mascots (APP-001, APP-003, APP-012).
 *
 * The wordmark is a 1:1 mirror of the web's src/components/Brand.tsx: the IF mark as a
 * raster asset, then IRON in white and FORGE in the marketing accent (#EE5A24). It is
 * deliberately TEXT rather than a second logo image — the web calls its Wordmark "the
 * single source of truth… do not reintroduce a second mark image", and rendering the
 * letters means the lockup can never go soft on a 3x screen.
 *
 * The mascots are the APPROVED art copied out of webapp/public, not new drawings:
 *   home/spark-mascot-glow.png -> assets/brand/mascot-spark.png
 *   home/flame-mascot-glow.png -> assets/brand/mascot-flame.png
 * Never regenerate these. They are signed off and they are what the mockups show.
 */
import { View, Text, Image, Pressable, StyleSheet } from 'react-native'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts (~3 MB,
// MaterialCommunityIcons alone is 1.3 MB). Ionicons is the only set used.
import Ionicons from '@expo/vector-icons/Ionicons'
import { color, space, font } from '@/theme/tokens'
import { useNotificationBell } from '@/notifications/bell'

const MARK = require('../../assets/brand/ironforge-mark.png')

const MASCOTS: Record<string, number> = {
  spark: require('../../assets/brand/mascot-spark.png'),
  flame: require('../../assets/brand/mascot-flame.png'),
}

export const SPARKY_AVATAR = require('../../assets/brand/sparky-avatar.png')

/** The IF mark + IRONFORGE lockup. */
export function Wordmark({ height = 26 }: { height?: number }) {
  return (
    <View style={s.lockup}>
      <Image source={MARK} style={{ height, width: height * 1.15 }} resizeMode="contain" />
      <Text style={[s.word, { fontSize: height * 0.78 }]}>
        <Text style={{ color: color.text }}>IRON</Text>
        <Text style={{ color: color.accent }}>FORGE</Text>
      </Text>
    </View>
  )
}

/**
 * Persistent app header (present on all four tabs in UX-002/004/005/006).
 *
 * The bell owns its own state via useNotificationBell so all four screens stay
 * identical without repeating the wiring. The dot means one true, actionable thing —
 * alerts are off — never a decorative unread badge, because a dot that is always on
 * teaches people to ignore it.
 */
export function AppHeader() {
  const { alert, onPress } = useNotificationBell()
  return (
    <View style={s.header}>
      <Wordmark />
      <Pressable
        onPress={onPress}
        hitSlop={12}
        accessibilityRole="button"
        accessibilityLabel={alert ? 'Notifications, action needed' : 'Notifications'}
        style={s.bell}
      >
        <Ionicons name="notifications-outline" size={24} color={color.text} />
        {alert ? <View style={s.dot} /> : null}
      </Pressable>
    </View>
  )
}

/** Spark / Flame mascot avatar. Falls back to nothing rather than a wrong agent's face. */
export function Mascot({ bot, size = 40 }: { bot: string; size?: number }) {
  const src = MASCOTS[bot]
  if (!src) return null
  return <Image source={src} style={{ width: size, height: size }} resizeMode="contain" />
}

const s = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: space.md,
  },
  lockup: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  word: {
    fontFamily: font.display,
    letterSpacing: 0.5,
  },
  bell: { padding: space.xs },
  dot: {
    position: 'absolute',
    top: 2,
    right: 2,
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: color.accent,
    borderWidth: 1.5,
    borderColor: color.bg,
  },
})
