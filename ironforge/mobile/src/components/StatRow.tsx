import { useMemo } from 'react'
import { View, Text, StyleSheet } from 'react-native'
import { space, radius, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'

/**
 * Shared "row of equal columns, each a muted label over a bold value,
 * separated by 1px dividers" strip. PR #2956 built this shape once for the
 * Ledger Completed Trades / Win Rate KPI card; the Forge agent-card Account
 * Capital / Growth / Last 10 / Best Trade row (handoff/ledger-kpis.md PART 2)
 * is the same shape at a smaller size, so this is the one definition both
 * screens render from rather than two near-identical StyleSheets drifting
 * apart over time.
 *
 * `variant`:
 *  - 'kpi'  — Ledger: 34px bold value / 16px label, divider has side gutters.
 *  - 'card' — Forge: 20px bold value / 14px label, divider is flush (matches
 *             the approved mock's inset panel, whose columns already carry
 *             their own small horizontal padding).
 */
export interface StatItem {
  label: string
  /** Pre-formatted display value, e.g. "$5,000", "+6.8%", "8–2", "—". Callers
   *  own all number formatting and sign logic — this component only lays it out. */
  value: string
  /** Value colour. Defaults to color.text. */
  tone?: string
  /** Shows a skeleton block instead of the value while the source is loading. */
  loading?: boolean
  /** Optional smaller muted line directly under the value, e.g. "Started: $4,150" on the
   *  Forge card's Capital tile. Only rendered in 'card' variant, and never while loading —
   *  the skeleton already stands in for the whole column. */
  sub?: string
}

export function StatRow({
  items,
  variant = 'kpi',
  style,
}: {
  items: StatItem[]
  variant?: 'kpi' | 'card'
  style?: object
}) {
  const { colors: color, resolveTone } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const kpi = variant === 'kpi'
  const children: React.ReactNode[] = []

  items.forEach((item, i) => {
    if (i > 0) {
      children.push(<View key={`div-${item.label}`} style={kpi ? s.dividerKpi : s.dividerCard} />)
    }
    // `item.tone` may be a DARK-canonical hex handed down from a pure helper (e.g.
    // live/card-stats.ts) — resolveTone() is the identity function in dark scheme and
    // swaps to the light equivalent in light scheme; a caller-supplied tone that isn't
    // a recognized dark token passes through unchanged.
    const tone = item.tone ? resolveTone(item.tone) : color.text
    children.push(
      <View key={item.label} style={[s.col, kpi ? null : s.colCard]}>
        <Text style={[kpi ? s.labelKpi : s.labelCard, { color: color.muted }]} numberOfLines={1}>
          {item.label}
        </Text>
        {item.loading ? (
          <View style={kpi ? s.skeletonKpi : s.skeletonCard} />
        ) : (
          <>
            <Text style={[kpi ? s.valueKpi : s.valueCard, { color: tone }]}>
              {item.value}
            </Text>
            {!kpi && item.sub ? (
              // No numberOfLines cap: "Started: $4,150" is wider than a four-column
              // iPhone tile and used to clip to "Started: $4,…" with nothing to tap to
              // reveal the rest (UAT, 9/8). Wrapping at the space puts "Started:" over
              // the amount instead, so the whole figure is always readable.
              <Text style={s.subCard}>{item.sub}</Text>
            ) : null}
          </>
        )}
      </View>,
    )
  })

  return <View style={[s.row, style]}>{children}</View>
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'stretch' },
  col: { flex: 1, alignItems: 'center' },
  colCard: { paddingHorizontal: space.xs },

  labelKpi: { fontSize: 16, marginBottom: space.xs },
  valueKpi: {
    fontSize: 34,
    fontFamily: font.bodyBold,
    letterSpacing: -0.5,
    fontVariant: ['tabular-nums'],
  },
  skeletonKpi: {
    width: 56,
    height: 34,
    borderRadius: radius.sm,
    backgroundColor: color.border,
    opacity: 0.6,
  },
  dividerKpi: { width: 1, backgroundColor: color.border, marginHorizontal: space.md },

  labelCard: { fontSize: 14, marginBottom: space.xs },
  // Reduced from 20 (PR #2957) so the Capital tile's value plus its "Started: $X" sub-line
  // both fit on an iPhone-width card without truncating — same size across all four tiles
  // so the row still reads as one aligned strip.
  valueCard: {
    fontSize: 17,
    fontFamily: font.bodyBold,
    fontVariant: ['tabular-nums'],
  },
  subCard: {
    fontSize: 11,
    color: color.muted,
    marginTop: 1,
    textAlign: 'center',
  },
  skeletonCard: {
    width: 44,
    height: 20,
    borderRadius: radius.sm,
    backgroundColor: color.border,
    opacity: 0.6,
  },
  dividerCard: { width: 1, backgroundColor: color.border },
})
