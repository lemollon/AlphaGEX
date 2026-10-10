/**
 * Brand chrome — the app header and the agent mascots (APP-001, APP-003, APP-012).
 *
 * The wordmark is TEXT only — "IRON" in white, "FORGE" in the marketing accent
 * (#EE5A24) — matching the design doc's app bar exactly (`.wm` — "IRON<b>FORGE</b>",
 * no icon). The app used to also render a raster "1F" mark (assets/brand/
 * ironforge-mark.png) beside the text; that asset predates the current design and
 * has been retired (coordinator follow-up, 2026-10-06) — the design's own app bar
 * has never shown a mark, only the lockup. Rendering the letters means the
 * wordmark can never go soft on a 3x screen the way a raster image could.
 *
 * The mascots are the APPROVED art copied out of webapp/public, not new drawings:
 *   home/spark-mascot-glow.png -> assets/brand/mascot-spark.png
 *   home/flame-mascot-glow.png -> assets/brand/mascot-flame.png
 *   marketing/ember-mascot.webp -> assets/brand/mascot-ember.webp
 * Never regenerate these. They are signed off and they are what the mockups show.
 */
import { useMemo } from 'react'
import { View, Text, Image, Pressable, StyleSheet } from 'react-native'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts (~3 MB,
// MaterialCommunityIcons alone is 1.3 MB). Ionicons is the only set used.
import Ionicons from '@expo/vector-icons/Ionicons'
import { space, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { useNotificationBell } from '@/notifications/bell'
import { useUnreadNotificationsCount } from '@/notifications/useUnreadCount'

const MASCOTS: Record<string, number> = {
  spark: require('../../assets/brand/mascot-spark.png'),
  flame: require('../../assets/brand/mascot-flame.png'),
  ember: require('../../assets/brand/mascot-ember.webp'),
}

export const SPARKY_AVATAR = require('../../assets/brand/sparky-avatar.png')

/** The IRONFORGE wordmark, text only — see the file comment above. */
export function Wordmark({ height = 26 }: { height?: number }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <View style={s.lockup}>
      <Text style={[s.word, { fontSize: height * 0.78 }]}>
        <Text style={{ color: color.text }}>IRON</Text>
        <Text style={{ color: color.accentText }}>FORGE</Text>
      </Text>
    </View>
  )
}

/**
 * Persistent app header (present on all four tabs in UX-002/004/005/006).
 *
 * The bell owns its own state via useNotificationBell so all four screens stay
 * identical without repeating the wiring. The permission half of the dot means one
 * true, actionable thing — alerts are off. The 10.4 gap audit added a second, equally
 * true reason for the same dot: unread rows in the real notification history feed
 * (GET /api/v1/notifications, see src/notifications/useUnreadCount.ts) — never a
 * decorative badge, since a dot that is always on teaches people to ignore it.
 *
 * Mobile addendum §2 "Notifications sheet": tapping the bell opens the notifications
 * sheet. The contextual permission ask (APP-033 — explain value before the OS prompt)
 * still comes first when permission hasn't been decided yet or was denied; only once
 * alerts are already on does the bell open the history feed at app/notifications.tsx.
 */
export function AppHeader() {
  const { colors: color, scheme, setPreference } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()
  const { alert, status, onPress } = useNotificationBell()
  const unreadCount = useUnreadNotificationsCount()
  // Design-spec §Mobile app "App bar every tab: wordmark, dark-mode toggle, bell" —
  // a one-tap light/dark swap living next to the bell on all four tabs, same spot the
  // app.html prototype's `.th-sun`/`.th-moon` pair occupies. This flips the SAVED
  // preference straight to the opposite scheme ('system' is still reachable from the
  // fuller Appearance picker on the Account tab); persistence is ThemeContext's job,
  // already wired through preference.ts.
  return (
    <View style={s.header}>
      <Wordmark />
      <View style={s.iconGroup}>
        <Pressable
          onPress={() => setPreference(scheme === 'dark' ? 'light' : 'dark')}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel={scheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          style={s.iconBtn}
        >
          <Ionicons name={scheme === 'dark' ? 'sunny-outline' : 'moon-outline'} size={20} color={color.text} />
        </Pressable>
        <Pressable
          onPress={() => (status === 'granted' ? router.push('/notifications') : onPress())}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel={
            alert ? 'Notifications, action needed' : unreadCount > 0 ? 'Notifications, unread' : 'Notifications'
          }
          style={s.bell}
        >
          <Ionicons name="notifications-outline" size={24} color={color.text} />
          {alert || unreadCount > 0 ? <View style={s.dot} /> : null}
        </Pressable>
      </View>
    </View>
  )
}

/** Spark / Flame mascot avatar. Falls back to nothing rather than a wrong agent's face. */
export function Mascot({ bot, size = 40 }: { bot: string; size?: number }) {
  const src = MASCOTS[bot]
  if (!src) return null
  return <Image source={src} style={{ width: size, height: size }} resizeMode="contain" />
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
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
    iconGroup: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
    iconBtn: { padding: space.xs },
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
