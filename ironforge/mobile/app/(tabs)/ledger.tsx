import { useMemo, useState } from 'react'
import { View, Text, ScrollView, TextInput, Pressable, RefreshControl, Alert, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import useSWR from 'swr'
import { api } from '@/api/client'
import type { HistoryTrade } from '@/api/types'
import { color, space, radius, type, font, agentAccent } from '@/theme/tokens'
import { Card, Money, OutcomeBadge, AgentBadge, Loading, Empty, ErrorState } from '@/components/ui'
import { AppHeader } from '@/components/Brand'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'

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

/**
 * APP-021 names the set: All Agents, Spark, Flame. It is FIXED, not derived from
 * whatever happens to be in the returned rows — a customer whose history holds only
 * Spark trades should still see that Flame exists, and the control must not change
 * shape as the date range changes.
 *
 * Matched on `bot` (the canonical id) rather than `strategy` (a display string).
 */
const AGENTS = [
  { key: 'all', label: 'All Agents' },
  { key: 'spark', label: 'Spark' },
  { key: 'flame', label: 'Flame' },
] as const

export default function LedgerScreen() {
  const { data, error, isLoading, mutate, isValidating } = useSWR<{ trades: HistoryTrade[] }>(
    '/api/live/trades',
    (p: string) => api(p),
    { refreshInterval: 60_000 },
  )

  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [agent, setAgent] = useState<string>('all')
  const [range, setRange] = useState<string>('30')

  const trades = data?.trades ?? []

  const filtered = useMemo(() => {
    const days = RANGES.find((r) => r.key === range)?.days ?? null
    const cutoff = days ? Date.now() - days * 86400_000 : null
    const q = query.trim().toLowerCase()
    return trades.filter((t) => {
      if (agent !== 'all' && t.bot !== agent) return false
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

          <View style={s.controls}>
            <Pressable
              onPress={() =>
                // Closing search must also clear it, or an invisible query keeps
                // filtering the list and the empty state reads as data loss.
                setSearchOpen((v) => {
                  if (v) setQuery('')
                  return !v
                })
              }
              accessibilityRole="button"
              accessibilityLabel={searchOpen ? 'Close search' : 'Search trades'}
              style={[s.iconBtn, searchOpen ? { borderColor: color.accent } : null]}
            >
              <Ionicons
                name={searchOpen ? 'close' : 'search'}
                size={17}
                color={searchOpen ? color.accent : color.textDim}
              />
            </Pressable>

            <Dropdown
              label={AGENTS.find((a) => a.key === agent)?.label ?? 'All Agents'}
              title="Filter by agent"
              options={AGENTS.map((a) => ({ key: a.key, label: a.label }))}
              onSelect={setAgent}
            />
            <Dropdown
              icon="calendar-outline"
              label={RANGES.find((r) => r.key === range)?.label ?? 'Last 30 Days'}
              title="Date range"
              options={RANGES.map((r) => ({ key: r.key, label: r.label }))}
              onSelect={setRange}
            />
          </View>

          {searchOpen ? (
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search trades"
              placeholderTextColor={color.muted}
              style={s.search}
              autoCorrect={false}
              autoFocus
            />
          ) : null}
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

/**
 * A dropdown control. UX-004 shows two labelled pickers with chevrons, not two wrapping
 * rows of chips.
 *
 * The picker itself is an Alert: it is the one presentation that is native, modal and
 * accessible on both platforms with no extra dependency, and these lists are three
 * items long.
 */
function Dropdown({
  label,
  title,
  options,
  onSelect,
  icon,
}: {
  label: string
  title: string
  options: Array<{ key: string; label: string }>
  onSelect: (key: string) => void
  icon?: React.ComponentProps<typeof Ionicons>['name']
}) {
  return (
    <Pressable
      onPress={() =>
        Alert.alert(title, undefined, [
          ...options.map((o) => ({ text: o.label, onPress: () => onSelect(o.key) })),
          { text: 'Cancel', style: 'cancel' as const },
        ])
      }
      accessibilityRole="button"
      accessibilityLabel={title + ', currently ' + label}
      style={s.dropdown}
    >
      {icon ? <Ionicons name={icon} size={15} color={color.textDim} /> : null}
      <Text style={[type.label, { color: color.text, fontFamily: font.bodyMedium }]}>{label}</Text>
      <Ionicons name="chevron-down" size={14} color={color.muted} />
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
  title: { ...type.title, color: color.text, fontFamily: font.display, marginBottom: space.lg },
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
  controls: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginTop: space.md },
  iconBtn: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    width: 38,
    height: 38,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dropdown: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    height: 38,
  },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.md },
})
