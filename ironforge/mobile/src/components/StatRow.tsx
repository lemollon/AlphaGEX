import { View, Text, StyleSheet } from 'react-native'
import { color, space, radius, font } from '@/theme/tokens'

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
  const kpi = variant === 'kpi'
  const children: React.ReactNode[] = []

  items.forEach((item, i) => {
    if (i > 0) {
      children.push(<View key={`div-${item.label}`} style={kpi ? s.dividerKpi : s.dividerCard} />)
    }
    children.push(
      <View key={item.label} style={[s.col, kpi ? null : s.colCard]}>
        <Text style={[kpi ? s.labelKpi : s.labelCard, { color: color.muted }]} numberOfLines={1}>
          {item.label}
        </Text>
        {item.loading ? (
          <View style={kpi ? s.skeletonKpi : s.skeletonCard} />
        ) : (
          <Text style={[kpi ? s.valueKpi : s.valueCard, { color: item.tone ?? color.text }]}>
            {item.value}
          </Text>
        )}
      </View>,
    )
  })

  return <View style={[s.row, style]}>{children}</View>
}

const s = StyleSheet.create({
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
  valueCard: {
    fontSize: 20,
    fontFamily: font.bodyBold,
    fontVariant: ['tabular-nums'],
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
