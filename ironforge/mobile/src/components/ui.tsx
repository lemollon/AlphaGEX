/**
 * Shared primitives (APP-002, APP-004/005/006).
 *
 * The webapp has no component library — it styles with Tailwind classes plus shared
 * string constants (cardStyles.ts). So the mobile design system is built from the
 * tokens rather than lifted, and these are the pieces every screen composes.
 */
import { View, Text, ActivityIndicator, Pressable, Image, StyleSheet } from 'react-native'
import type { ReactNode } from 'react'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { color, space, radius, type, font, outcomeColor, pnlColor } from '@/theme/tokens'

export function Card({ children, style }: { children: ReactNode; style?: object }) {
  return <View style={[s.card, style]}>{children}</View>
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <Text style={s.sectionLabel}>{String(children).toUpperCase()}</Text>
}

/** Money, always signed, always green/red. Never agent colour — that reads as branding. */
export function Money({
  value,
  size = 'body',
}: {
  value: number | null | undefined
  size?: 'hero' | 'title' | 'body'
}) {
  if (value == null) return <Text style={[s.dim, type[size]]}>—</Text>
  const sign = value >= 0 ? '+' : '-'
  const text = `${sign}$${Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
  return <Text style={[type[size], { color: pnlColor(value), fontFamily: font.bodyBold }]}>{text}</Text>
}

/** Plain currency with no sign — for a balance, where +/- would be nonsense. */
export function Balance({ value }: { value: number | null | undefined }) {
  if (value == null) return <Text style={[s.dim, type.hero]}>—</Text>
  return (
    <Text style={[type.hero, { color: color.text, fontFamily: font.display }]}>
      ${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
    </Text>
  )
}

/** Profit Target / Auto Close / Stop Loss — driven by the API's normalized outcome_kind. */
export function OutcomeBadge({ kind, label }: { kind: string; label: string }) {
  const c = outcomeColor[kind] ?? color.textDim
  return (
    <View style={[s.badge, { borderColor: c }]}>
      <Text style={[type.label, { color: c, fontFamily: font.bodyMedium }]}>{label}</Text>
    </View>
  )
}

export function AgentBadge({ name, accent }: { name: string; accent: string }) {
  return (
    <View style={[s.badge, { borderColor: accent }]}>
      <Text style={[type.label, { color: accent, fontFamily: font.bodyMedium }]}>{name}</Text>
    </View>
  )
}

/**
 * A tappable settings row: icon, label, optional detail, chevron (UX-006).
 *
 * `icon` takes either an Ionicons name or an image source, because Help & Support puts
 * the Sparky avatar in the same column as a glyph.
 */
export function Row({
  icon,
  image,
  label,
  detail,
  onPress,
  first = false,
  tint,
  badge,
}: {
  icon?: React.ComponentProps<typeof Ionicons>['name']
  image?: number
  label: string
  detail?: string
  onPress: () => void
  first?: boolean
  tint?: string
  badge?: ReactNode
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={detail ? `${label}. ${detail}` : label}
      style={[s.row, !first && s.rowDivider]}
    >
      {image ? (
        <Image source={image} style={{ width: 30, height: 30 }} resizeMode="contain" />
      ) : icon ? (
        <Ionicons name={icon} size={22} color={tint ?? color.textDim} />
      ) : null}
      <View style={{ flex: 1 }}>
        <View style={s.rowHead}>
          <Text style={[type.body, { color: tint ?? color.text, fontFamily: font.bodyMedium }]}>
            {label}
          </Text>
          {badge}
        </View>
        {detail ? (
          <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>{detail}</Text>
        ) : null}
      </View>
      <Ionicons name="chevron-forward" size={17} color={color.muted} />
    </Pressable>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <View style={s.centered}>
      <ActivityIndicator color={color.accent} />
      <Text style={[s.dim, type.body, { marginTop: space.md }]}>{label}</Text>
    </View>
  )
}

/**
 * Empty state (APP-005). Always says WHY there is nothing, never just "no data" —
 * an unexplained blank screen on a trading app reads as breakage.
 */
export function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <View style={s.centered}>
      <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>{title}</Text>
      <Text style={[s.dim, type.body, { marginTop: space.sm, textAlign: 'center' }]}>{detail}</Text>
    </View>
  )
}

/** Error state (APP-006) — always paired with a retry, never a dead end. */
export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <View style={s.centered}>
      <Text style={[type.body, { color: color.neg, fontFamily: font.bodyMedium }]}>
        Something went wrong
      </Text>
      <Text style={[s.dim, type.body, { marginTop: space.sm, textAlign: 'center' }]}>{message}</Text>
      <Pressable onPress={onRetry} style={s.retry}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>Try again</Text>
      </Pressable>
    </View>
  )
}

const s = StyleSheet.create({
  card: {
    backgroundColor: color.card,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  sectionLabel: {
    ...type.section,
    color: color.muted,
    fontFamily: font.bodyMedium,
    marginBottom: space.md,
  },
  badge: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    alignSelf: 'flex-start',
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.md },
  rowDivider: { borderTopWidth: 1, borderTopColor: color.border },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dim: { color: color.textDim },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl },
  retry: {
    marginTop: space.lg,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
  },
})
