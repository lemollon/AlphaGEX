import { View, Text, Pressable, StyleSheet } from 'react-native'
import Svg, { Path, Circle, Rect, G } from 'react-native-svg'
import { color, space, font } from '@/theme/tokens'

/**
 * Brand chrome for the mobile app, drawn to the approved UX mockups (UX-002..UX-006).
 *
 * Everything here is VECTOR rather than a bundled PNG. The mark appears at four
 * different sizes across the app (header, tab bar, empty states) and a raster asset
 * would either be soft on a 3x display or bloat the bundle four times over. It also
 * means the mark inherits the accent colour instead of baking it in, so the focused
 * tab tint works without a second file.
 */

/** The IF monogram mark — a solid bar (I) beside an orange F, per the mockups. */
export function IFMark({ size = 28, tint = color.wordmark }: { size?: number; tint?: string }) {
  // 32x32 viewBox. The "I" is a plain white slab; the "F" is the accent colour with
  // two arms. Drawn as rects rather than a font glyph so it renders identically
  // regardless of whether Oswald has finished loading.
  return (
    <Svg width={size} height={size} viewBox="0 0 32 32">
      <Rect x="2" y="4" width="6" height="24" fill={color.text} />
      <G fill={tint}>
        <Rect x="12" y="4" width="6" height="24" />
        <Rect x="18" y="4" width="12" height="6" />
        <Rect x="18" y="14" width="9" height="6" />
      </G>
    </Svg>
  )
}

/** IRON (white) + FORGE (orange), the locked-up wordmark. */
export function Wordmark({ size = 20 }: { size?: number }) {
  return (
    <Text style={{ fontFamily: font.display, fontSize: size, letterSpacing: 1.5 }}>
      <Text style={{ color: color.text }}>IRON</Text>
      <Text style={{ color: color.wordmark }}>FORGE</Text>
    </Text>
  )
}

/** Notification bell. `unread` drives the accent dot from the mockups. */
export function BellIcon({ size = 24, unread = false }: { size?: number; unread?: boolean }) {
  return (
    <View>
      <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <Path
          d="M12 3a6 6 0 0 0-6 6v3.6L4.5 16h15L18 12.6V9a6 6 0 0 0-6-6Z"
          stroke={color.text}
          strokeWidth={1.7}
          strokeLinejoin="round"
        />
        <Path
          d="M9.5 19a2.5 2.5 0 0 0 5 0"
          stroke={color.text}
          strokeWidth={1.7}
          strokeLinecap="round"
        />
      </Svg>
      {unread ? (
        <View
          style={{
            position: 'absolute',
            top: -1,
            right: -1,
            width: 10,
            height: 10,
            borderRadius: 5,
            backgroundColor: color.wordmark,
          }}
        />
      ) : null}
    </View>
  )
}

/**
 * The persistent app header: mark + wordmark on the left, bell on the right.
 * Present on all four tabs in the mockups, so it lives here rather than being
 * re-typed per screen.
 */
export function AppHeader({ unread = false, onBell }: { unread?: boolean; onBell?: () => void }) {
  return (
    <View style={s.header}>
      <View style={s.brandRow}>
        <IFMark size={30} />
        <View style={{ width: space.sm }} />
        <Wordmark size={20} />
      </View>
      <Pressable onPress={onBell} hitSlop={12} accessibilityLabel="Notifications">
        <BellIcon unread={unread} />
      </Pressable>
    </View>
  )
}

/**
 * Per-agent flame avatar. Spark reads blue and Flame orange in the mockups, which is
 * the same identity mapping as agentColor in the theme — so the colour is passed in
 * rather than re-derived here, keeping one source of truth for what a bot looks like.
 */
export function AgentAvatar({ tint, size = 44 }: { tint: string; size?: number }) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color.bg,
        borderWidth: 1,
        borderColor: tint,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Svg width={size * 0.58} height={size * 0.58} viewBox="0 0 24 24">
        <Path
          d="M13 2c.6 3.2-.9 4.9-2.4 6.5C9 10.2 7.5 11.8 7.5 14.5A6.5 6.5 0 0 0 20 17c.4-3.3-1.3-5.2-2.8-6.8-1.2-1.3-2.3-2.5-2.3-4.2 0-1.6.6-3 1.1-4-1.2.4-2.3 1.1-3 2Z"
          fill={tint}
        />
        <Path
          d="M10 14.2c.3 1.5-.5 2.3-1.2 3.1-.6.7-1.3 1.5-1.3 2.7A3.2 3.2 0 0 0 12 21c.2-1.6-.6-2.5-1.3-3.3-.6-.6-1.1-1.2-1.1-2 0-.8.3-1.4.5-1.9-.6.2-1.1.5-1.5 1Z"
          fill={color.bg}
          opacity={0.55}
        />
      </Svg>
    </View>
  )
}

/** Large screen title, e.g. "Ledger" / "Community" / "Account". */
export function ScreenTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <View style={s.titleRow}>
      <Text style={s.title}>{children}</Text>
      {right}
    </View>
  )
}

// ── Tab bar icons ───────────────────────────────────────────────────────────────
// Stroked outlines that fill with the accent when focused, matching the mockups.

export function ForgeTabIcon({ c }: { c: string }) {
  // Shield containing the IF monogram.
  return (
    <Svg width={26} height={26} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 2.5 4.5 5.4v6.2c0 4.6 3.1 8.4 7.5 9.9 4.4-1.5 7.5-5.3 7.5-9.9V5.4L12 2.5Z"
        stroke={c}
        strokeWidth={1.6}
        strokeLinejoin="round"
      />
      <Rect x="8.4" y="8" width="1.9" height="8" fill={c} />
      <Rect x="11.6" y="8" width="1.9" height="8" fill={c} />
      <Rect x="13.5" y="8" width="3.4" height="1.9" fill={c} />
      <Rect x="13.5" y="11.2" width="2.6" height="1.9" fill={c} />
    </Svg>
  )
}

export function LedgerTabIcon({ c }: { c: string }) {
  return (
    <Svg width={26} height={26} viewBox="0 0 24 24" fill="none">
      <Rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke={c} strokeWidth={1.6} />
      <Path d="M7.5 9.5h9M7.5 13.5h5" stroke={c} strokeWidth={1.6} strokeLinecap="round" />
    </Svg>
  )
}

export function CommunityTabIcon({ c }: { c: string }) {
  return (
    <Svg width={26} height={26} viewBox="0 0 24 24" fill="none">
      <Circle cx="9" cy="8.5" r="3.1" stroke={c} strokeWidth={1.6} />
      <Circle cx="16.5" cy="9.5" r="2.4" stroke={c} strokeWidth={1.6} />
      <Path
        d="M3.5 18.5c0-2.8 2.5-4.6 5.5-4.6s5.5 1.8 5.5 4.6"
        stroke={c}
        strokeWidth={1.6}
        strokeLinecap="round"
      />
      <Path
        d="M16 14.2c2.5.2 4.5 1.8 4.5 4.3"
        stroke={c}
        strokeWidth={1.6}
        strokeLinecap="round"
      />
    </Svg>
  )
}

export function AccountTabIcon({ c }: { c: string }) {
  return (
    <Svg width={26} height={26} viewBox="0 0 24 24" fill="none">
      <Circle cx="12" cy="8.5" r="3.6" stroke={c} strokeWidth={1.6} />
      <Path
        d="M4.8 19.5c0-3.4 3.2-5.6 7.2-5.6s7.2 2.2 7.2 5.6"
        stroke={c}
        strokeWidth={1.6}
        strokeLinecap="round"
      />
    </Svg>
  )
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
  brandRow: { flexDirection: 'row', alignItems: 'center' },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    marginBottom: space.md,
  },
  title: { color: color.text, fontFamily: font.bodyBold, fontSize: 34, letterSpacing: -0.5 },
})
