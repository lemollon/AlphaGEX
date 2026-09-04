import { useEffect, useMemo, useState } from 'react'
import { View, Text, ScrollView, TextInput, Pressable, RefreshControl, Alert, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
import useSWRInfinite from 'swr/infinite'
import { api } from '@/api/client'
import type { HistoryTrade, TradesPageResponse, TradesTotals } from '@/api/types'
import {
  getLedgerKey,
  mergeLedgerPages,
  ledgerTotal,
  ledgerTotals,
  hasMoreLedgerPages,
  type LedgerFilters,
} from '@/ledger/paging'
import { tradeDetailHref } from '@/ledger/detail'
import { color, space, radius, type, font, agentAccent } from '@/theme/tokens'
import { Card, Money, OutcomeBadge, AgentBadge, Loading, Empty, ErrorState } from '@/components/ui'
import { StatRow } from '@/components/StatRow'
import { AppHeader } from '@/components/Brand'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'

/**
 * Ledger — UX-004 (APP-017/018/020/021/052/053).
 *
 * Filtering moved server-side (APP-020): GET /api/live/trades now takes bot/days/q
 * query params and returns a cursor-paginated page instead of up to 300 rows per bot
 * in one shot. useSWRInfinite drives the "Load more" / onEndReached flow; a filter
 * change is a NEW key (getLedgerKey embeds the filters), so switching agent/range/
 * search always starts over at page 1 rather than filtering whatever pages happened
 * to already be loaded — `setSize(1)` below makes that explicit rather than relying
 * on SWR's cache alone.
 */
const RANGES = [
  { key: '30', label: 'Last 30 Days' },
  { key: '90', label: 'Last 90 Days' },
  { key: 'all', label: 'All Time' },
] as const

/**
 * APP-021 names the set: All Agents, Spark, Flame. It is FIXED, not derived from
 * whatever happens to be in the returned rows — a customer whose history holds only
 * Spark trades should still see that Flame exists, and the control must not change
 * shape as the date range changes.
 */
const AGENTS = [
  { key: 'all', label: 'All Agents' },
  { key: 'spark', label: 'Spark' },
  { key: 'flame', label: 'Flame' },
] as const

export default function LedgerScreen() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [agent, setAgent] = useState<string>('all')
  const [range, setRange] = useState<string>('30')

  const filters: LedgerFilters = useMemo(() => ({ agent, range, query }), [agent, range, query])

  const { data, error, isLoading, isValidating, size, setSize, mutate } = useSWRInfinite<TradesPageResponse>(
    getLedgerKey(filters),
    (p: string) => api<TradesPageResponse>(p),
    { refreshInterval: 60_000 },
  )

  // A filter change resets paging to page 1 — without this, switching from "Spark"
  // back to "All Agents" would keep whatever `size` the previous filter had reached
  // and fire that many requests against the new key on the first render.
  useEffect(() => {
    setSize(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent, range, query])

  const trades = mergeLedgerPages(data)
  const total = ledgerTotal(data)
  const totals = ledgerTotals(data)
  const canLoadMore = hasMoreLedgerPages(data)
  const loadingMore = isValidating && size > 0 && !!data && data.length < size

  if (isLoading && !data) return <Shell><Loading label="Loading your trade history…" /></Shell>
  if (error && !data) {
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
          <RefreshControl refreshing={isValidating && size === 1} onRefresh={() => mutate()} tintColor={color.accent} />
        }
        // The screen has always used a ScrollView, not a FlatList, so there is no
        // native onEndReached prop — this is its equivalent: within 200px of the
        // bottom, fetch the next page exactly the way the "Load more" button does.
        onScroll={({ nativeEvent }) => {
          const { layoutMeasurement, contentOffset, contentSize } = nativeEvent
          const nearBottom = layoutMeasurement.height + contentOffset.y >= contentSize.height - 200
          if (nearBottom && canLoadMore && !loadingMore) setSize(size + 1)
        }}
        scrollEventThrottle={200}
      >
        <Text style={s.title}>Ledger</Text>

        <KpiStrip totals={totals} />

        <Card style={{ marginBottom: space.lg }}>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>
            Trade History
          </Text>
          <Text style={[type.label, { color: color.textDim, marginTop: space.xs }]}>
            {trades.length} of {total} {total === 1 ? 'trade' : 'trades'}
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

        {trades.length === 0 ? (
          <Empty
            title="No completed trades"
            detail={
              total === 0 && agent === 'all' && range === '30' && !query
                ? 'Closed trades appear here once your agent finishes its first position.'
                : 'No trades match these filters. Try widening the date range.'
            }
          />
        ) : (
          <>
            {trades.map((t) => (
              <TradeCard key={t.id} trade={t} onPress={() => router.push(tradeDetailHref(t.id))} />
            ))}
            {canLoadMore ? (
              <Pressable
                onPress={() => setSize(size + 1)}
                disabled={loadingMore}
                style={[s.loadMore, loadingMore && { opacity: 0.5 }]}
                accessibilityRole="button"
              >
                <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
                  {loadingMore ? 'Loading…' : 'Load more'}
                </Text>
              </Pressable>
            ) : null}
          </>
        )}
      </ScrollView>
    </Shell>
  )
}

/**
 * Completed Trades / Win Rate — the top-of-Ledger KPI strip (approved mock,
 * handoff/ledger-kpis.md). `totals` is undefined until the first page loads,
 * which is when the skeleton shows instead of a flash of "0"/"—".
 */
function KpiStrip({ totals }: { totals: TradesTotals | undefined }) {
  const loading = !totals
  const zero = !!totals && totals.completed_trades === 0

  return (
    <Card style={{ marginBottom: space.lg }}>
      <StatRow
        variant="kpi"
        items={[
          {
            label: 'Completed Trades',
            value: zero ? '—' : (totals?.completed_trades ?? 0).toLocaleString('en-US'),
            tone: color.text,
            loading,
          },
          {
            label: 'Win Rate',
            value: zero ? '—' : formatWinRate(totals?.win_rate ?? null),
            tone: color.pos,
            loading,
          },
        ]}
      />
    </Card>
  )
}

/** "87%" for a whole number, "87.5%" otherwise — the mock shows the whole-number
 *  case. Null (no completed trades) is handled by the caller, not here. */
function formatWinRate(pct: number | null): string {
  if (pct == null) return '—'
  return Number.isInteger(pct) ? `${pct}%` : `${pct.toFixed(1)}%`
}

function TradeCard({ trade, onPress }: { trade: HistoryTrade; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={`Trade closed ${trade.close_date}`}>
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
    </Pressable>
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
  loadMore: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
    marginTop: space.sm,
  },
})
