import { useMemo, useState } from 'react'
import { View, Text, ScrollView, TextInput, Pressable, RefreshControl, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import useSWR from 'swr'
import { api } from '@/api/client'
import type { HistoryTrade } from '@/api/types'
import { color, space, radius, type, font, agentAccent } from '@/theme/tokens'
import { Card, Money, OutcomeBadge, AgentBadge, Loading, Empty, ErrorState } from '@/components/ui'
import { AppHeader } from '@/components/brand'

/**
 * Ledger — UX-004 (APP-017/018/020/021/052/053).
 *
 * GET /api/live/trades already returns exactly the approved card fields, including a
 * normalized outcome_kind that maps 1:1 to the three badge states. Ticker and return %
 * are intentionally ABSENT from the card per UX-004 — do not add them back.
 *
 * Filtering is client-side: the endpoint returns up to 300 rows per bot in one shot, so
 * a round trip per keystroke would be strictly worse. Filters combine, and any change
 * resets scroll position — which is the mobile equivalent of "filter changes reset
 * pagination".
 */
const RANGES = [
  { key: '30', label: 'Last 30 Days', days: 30 },
  { key: '90', label: 'Last 90 Days', days: 90 },
  { key: 'all', label: 'All Time', days: null },
] as const

export default function LedgerScreen() {
  const { data, error, isLoading, mutate, isValidating } = useSWR<{ trades: HistoryTrade[] }>(
    '/api/live/trades',
    (p: string) => api(p),
    { refreshInterval: 60_000 },
  )

  const [query, setQuery] = useState('')
  const [agent, setAgent] = useState<string>('all')
  const [range, setRange] = useState<string>('30')

  const trades = data?.trades ?? []

  const agents = useMemo(() => {
    const set = new Set(trades.map((t) => t.strategy))
    return ['all', ...Array.from(set)]
  }, [trades])

  const filtered = useMemo(() => {
    const days = RANGES.find((r) => r.key === range)?.days ?? null
    const cutoff = days ? Date.now() - days * 86400_000 : null
    const q = query.trim().toLowerCase()
    return trades.filter((t) => {
      if (agent !== 'all' && t.strategy !== agent) return false
      if (cutoff && new Date(t.close_date).getTime() < cutoff) return false
      if (q) {
        const hay = `${t.strategy} ${t.outcome} ${t.close_date} ${t.underlying}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [trades, agent, range, query])

  if (isLoading) return <Shell><Loading label="Loading your trade history…" /></Shell>
  if (error) {
    return (
      <Shell>
        <ErrorState message={String((error as Error).message)} onRetry={() => mutate()} />
      </Shell>
    )
  }

  return (
    <Shell>
      <ScrollView
        contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}
        refreshControl={
          <RefreshControl refreshing={isValidating} onRefresh={() => mutate()} tintColor={color.accent} />
        }
      >
        <Text style={s.title}>Ledger</Text>

        <Card style={{ marginBottom: space.lg }}>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>
            Trade History
          </Text>
          <Text style={[type.label, { color: color.textDim, marginTop: space.xs }]}>
            {filtered.length} completed {filtered.length === 1 ? 'trade' : 'trades'}
          </Text>

          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search"
            placeholderTextColor={color.muted}
            style={s.search}
            autoCorrect={false}
          />

          <View style={s.chipRow}>
            {agents.map((a) => (
              <Chip
                key={a}
                label={a === 'all' ? 'All Agents' : a}
                active={agent === a}
                onPress={() => setAgent(a)}
              />
            ))}
          </View>
          <View style={s.chipRow}>
            {RANGES.map((r) => (
              <Chip key={r.key} label={r.label} active={range === r.key} onPress={() => setRange(r.key)} />
            ))}
          </View>
        </Card>

        {filtered.length === 0 ? (
          <Empty
            title="No completed trades"
            detail={
              trades.length === 0
                ? 'Closed trades appear here once your agent finishes its first position.'
                : 'No trades match these filters. Try widening the date range.'
            }
          />
        ) : (
          filtered.map((t) => <TradeCard key={t.id} trade={t} />)
        )}
      </ScrollView>
    </Shell>
  )
}

function TradeCard({ trade }: { trade: HistoryTrade }) {
  return (
    <Card style={{ marginBottom: space.md }}>
      <View style={s.rowBetween}>
        <AgentBadge name={trade.strategy} accent={agentAccent(trade.bot)} />
        <Money value={trade.pnl} size="title" />
      </View>
      <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, marginTop: space.sm }]}>
        {formatDate(trade.close_date)}
      </Text>

      <View style={s.divider} />

      <View style={s.rowBetween}>
        <Field label="Opened" value={trade.opened_ct ?? '—'} />
        <Field label="Closed" value={trade.closed_ct ?? '—'} />
        <View style={{ alignItems: 'center' }}>
          <Text style={[type.label, { color: color.muted, marginBottom: space.xs }]}>Outcome</Text>
          <OutcomeBadge kind={trade.outcome_kind} label={trade.outcome} />
        </View>
      </View>
    </Card>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ alignItems: 'center' }}>
      <Text style={[type.label, { color: color.muted, marginBottom: space.xs }]}>{label}</Text>
      <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>{value}</Text>
    </View>
  )
}

function Chip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={[s.chip, active && { backgroundColor: color.accent, borderColor: color.accent }]}
    >
      <Text style={[type.label, { color: active ? color.text : color.textDim, fontFamily: font.bodyMedium }]}>
        {label}
      </Text>
    </Pressable>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }} edges={['top']}>
      <AppHeader />
      {children}
    </SafeAreaView>
  )
}

/** close_date is a plain CT date string from the server — parse as local, not UTC. */
function formatDate(d: string): string {
  const [y, m, day] = d.split('-').map(Number)
  if (!y || !m || !day) return d
  return new Date(y, m - 1, day).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

const s = StyleSheet.create({
  // Large bold sans page title per UX-004 — the display face is reserved for the
  // wordmark and numerics, not headings.
  title: {
    color: color.text,
    fontFamily: font.bodyBold,
    fontSize: 34,
    letterSpacing: -0.5,
    marginBottom: space.lg,
  },
  search: {
    marginTop: space.md,
    backgroundColor: color.bg,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    color: color.text,
    fontSize: 15,
  },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  chip: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.md },
})
