import { useEffect, useMemo, useRef, useState } from 'react'
import { View, Text, ScrollView, TextInput, Pressable, RefreshControl, StyleSheet } from 'react-native'
import { useScrollToTop } from '@react-navigation/native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
import useSWR from 'swr'
import useSWRInfinite from 'swr/infinite'
import { api } from '@/api/client'
import type {
  HistoryTrade,
  TradesPageResponse,
  TradesTotals,
  EntitlementsResponse,
  EmberTradesResponse,
} from '@/api/types'
import {
  getLedgerKey,
  mergeLedgerPages,
  ledgerTotal,
  ledgerTotals,
  hasMoreLedgerPages,
  groupTradesByDay,
  totalsFromTrades,
  rangeCutoffDate,
  LEDGER_RANGES,
  type LedgerFilters,
} from '@/ledger/paging'
import { emberClosedTradesToHistory } from '@/ledger/ember'
import { tradeDetailHref } from '@/ledger/detail'
import { space, radius, type, font, agentAccent } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Card, Money, OutcomeBadge, AgentBadge, Loading, Empty, ErrorState } from '@/components/ui'
import { AppHeader, Mascot } from '@/components/Brand'
import { Sheet, SheetHeader } from '@/components/Sheet'
import { AGENT_LABEL } from '@/agents/copy'
import type { AgentBot } from '@/agents/routes'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'

/**
 * Ledger — 10.4 redesign (handoff/ironforge-10.4-addendum.md §2 "Ledger tab"),
 * replacing the prior dropdown-filtered flat list (UX-004 / APP-017/018/020/
 * 021/052/053) with the design's summary card, chip filters and day-grouped
 * rows.
 *
 * Spark/Flame still come from GET /api/live/trades, server-side filtered and
 * cursor-paginated (src/ledger/paging.ts) — unchanged plumbing, new
 * presentation. Ember is a SEPARATE agent with its own trade book (PR #3177,
 * GET /api/ember/trades) that /api/live/trades has never covered — selecting
 * the Ember chip switches the whole screen onto that endpoint, adapted into
 * the same row shape by src/ledger/ember.ts, with search/range filtering and
 * the summary totals computed client-side (no cursor API exists for it yet).
 * Agent chips only ever show agents this viewer actually owns (GET
 * /api/billing/entitlements) — never a fixed All/Spark/Flame list a
 * non-owner would see and tap into nothing.
 */
const AGENT_CHIP_BOTS: AgentBot[] = ['spark', 'flame', 'ember']

export default function LedgerScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()
  // Re-tap-tab-to-scroll-to-top (#231) — the standard React Navigation hook, which
  // listens for a second tap on this tab's own icon while it is already focused.
  const scrollRef = useRef<ScrollView>(null)
  useScrollToTop(scrollRef)
  const [query, setQuery] = useState('')
  const [agent, setAgent] = useState<string>('all')
  // 10.4 design `ledger()`: the Month chip (`st.ledgerRange==='21'`) is selected by
  // default, not Week — the chips and their order already matched; only the
  // default selection was off.
  const [range, setRange] = useState<string>('21')
  // Styled sheet for a tapped Ember trade — there is no /api/live/trades/[id]
  // equivalent for Ember (PR #3177 only shipped the list + status), so this opens
  // a sheet built entirely from the row the list already fetched, rather than a
  // route that would have nothing further to load.
  const [emberSheetTrade, setEmberSheetTrade] = useState<HistoryTrade | null>(null)

  const entitlements = useSWR<EntitlementsResponse>('/api/billing/entitlements', (p: string) =>
    api<EntitlementsResponse>(p),
  )
  const ownedBots = entitlements.data?.bots ?? []
  const ownsEmber = ownedBots.includes('ember')

  const sparkFlameAgent = agent === 'ember' ? 'all' : agent
  const filters: LedgerFilters = useMemo(
    () => ({ agent: sparkFlameAgent, range, query }),
    [sparkFlameAgent, range, query],
  )

  const { data, error, isLoading, isValidating, size, setSize, mutate } = useSWRInfinite<TradesPageResponse>(
    agent === 'ember' ? () => null : getLedgerKey(filters),
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

  const emberSWR = useSWR<EmberTradesResponse>(
    agent === 'ember' && ownsEmber ? '/api/ember/trades' : null,
    (p: string) => api<EmberTradesResponse>(p),
    { refreshInterval: 60_000, shouldRetryOnError: false },
  )

  const sparkFlameTrades = mergeLedgerPages(data)
  const total = ledgerTotal(data)
  const serverTotals = ledgerTotals(data)
  const canLoadMore = hasMoreLedgerPages(data)
  const loadingMore = isValidating && size > 0 && !!data && data.length < size

  // Ember's own list is NOT cursor-paginated — it is filtered/searched entirely
  // client-side from the one /api/ember/trades response, the same way the
  // app.html prototype filters its already-fully-loaded example data, except
  // every row here is real.
  const emberAll = useMemo(() => emberClosedTradesToHistory(emberSWR.data?.trades ?? []), [emberSWR.data])
  const emberCutoff = rangeCutoffDate(range)
  const emberFiltered = useMemo(() => {
    let rows = emberAll
    if (emberCutoff) rows = rows.filter((t) => t.close_date >= emberCutoff)
    const q = query.trim().toLowerCase()
    if (q) {
      rows = rows.filter((t) =>
        `${t.strategy} ${formatDate(t.close_date)} ${t.outcome} ${t.pnl}`.toLowerCase().includes(q),
      )
    }
    return rows
  }, [emberAll, emberCutoff, query])

  const trades = agent === 'ember' ? emberFiltered : sparkFlameTrades
  const totals = agent === 'ember' ? totalsFromTrades(emberFiltered) : serverTotals
  const dayGroups = useMemo(() => groupTradesByDay(trades), [trades])

  const loading = agent === 'ember' ? emberSWR.isLoading : isLoading && !data
  const loadError = agent === 'ember' ? emberSWR.error : error && !data

  const agentChips = [
    { key: 'all', label: 'All Agents' },
    ...AGENT_CHIP_BOTS.filter((b) => b === 'ember' ? ownsEmber : ownedBots.includes(b)).map((b) => ({
      key: b,
      label: AGENT_LABEL[b],
    })),
  ]

  function reload() {
    void mutate()
    void emberSWR.mutate()
  }

  function openTrade(t: HistoryTrade) {
    if (t.bot === 'ember') {
      setEmberSheetTrade(t)
      return
    }
    router.push(tradeDetailHref(t.id))
  }

  if (loading) return <Shell><Loading label="Loading your trade history…" /></Shell>
  if (loadError) {
    return (
      <Shell>
        <ErrorState message={String(((agent === 'ember' ? emberSWR.error : error) as Error).message)} onRetry={reload} />
      </Shell>
    )
  }

  return (
    <Shell>
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}
        refreshControl={
          <RefreshControl
            refreshing={agent === 'ember' ? emberSWR.isValidating : isValidating && size === 1}
            onRefresh={reload}
            tintColor={color.accent}
          />
        }
        // The screen has always used a ScrollView, not a FlatList, so there is no
        // native onEndReached prop — this is its equivalent: within 200px of the
        // bottom, fetch the next page.
        onScroll={({ nativeEvent }) => {
          if (agent === 'ember') return
          const { layoutMeasurement, contentOffset, contentSize } = nativeEvent
          const nearBottom = layoutMeasurement.height + contentOffset.y >= contentSize.height - 200
          if (nearBottom && canLoadMore && !loadingMore) setSize(size + 1)
        }}
        scrollEventThrottle={200}
      >
        <View style={s.titleRow}>
          <Text style={s.title}>Ledger</Text>
          <Text style={[type.label, { color: color.muted }]}>Every trade, every outcome</Text>
        </View>

        <SummaryCard totals={totals} />

        <View style={s.search}>
          <Ionicons name="search" size={16} color={color.muted} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search trades"
            placeholderTextColor={color.muted}
            style={s.searchInput}
            autoCorrect={false}
          />
        </View>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={s.chipScroll}
          contentContainerStyle={s.chipRow}
        >
          {agentChips.map((c) => {
            const active = agent === c.key
            return (
              <Pressable
                key={c.key}
                onPress={() => setAgent(c.key)}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                style={[s.chip, active && { backgroundColor: color.text, borderColor: color.text }]}
              >
                {c.key !== 'all' ? <Mascot bot={c.key} size={18} /> : null}
                <Text style={[type.label, { color: active ? color.bg : color.textDim, fontFamily: font.bodyMedium }]}>
                  {c.label}
                </Text>
              </Pressable>
            )
          })}
        </ScrollView>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={s.chipScroll}
          contentContainerStyle={s.chipRow}
        >
          {LEDGER_RANGES.map((r) => {
            const active = range === r.key
            return (
              <Pressable
                key={r.key}
                onPress={() => setRange(r.key)}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                style={[s.chip, active && { backgroundColor: color.text, borderColor: color.text }]}
              >
                <Text style={[type.label, { color: active ? color.bg : color.textDim, fontFamily: font.bodyMedium }]}>
                  {r.label}
                </Text>
              </Pressable>
            )
          })}
        </ScrollView>

        {trades.length === 0 ? (
          <Empty
            title="No trades match"
            detail={
              total === 0 && agent === 'all' && !query
                ? 'Closed trades appear here once your agent finishes its first position.'
                : 'Try another filter or search.'
            }
          />
        ) : (
          <>
            {dayGroups.map((g) => (
              <View key={g.date} style={{ marginBottom: space.md }}>
                <View style={s.dayHeader}>
                  <Text style={[type.label, { color: color.muted, fontFamily: font.bodyMedium }]}>
                    {formatDayLabel(g.date)}
                  </Text>
                  <Text style={[type.label, { color: g.net >= 0 ? color.pos : color.neg, fontFamily: font.bodyMedium }]}>
                    {signed(g.net)}
                  </Text>
                </View>
                <Card>
                  {g.trades.map((t, i) => (
                    <TradeRow key={t.id} trade={t} last={i === g.trades.length - 1} onPress={() => openTrade(t)} />
                  ))}
                </Card>
              </View>
            ))}
            {agent !== 'ember' && canLoadMore ? (
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
      {emberSheetTrade ? (
        <EmberTradeSheet trade={emberSheetTrade} onClose={() => setEmberSheetTrade(null)} />
      ) : null}
    </Shell>
  )
}

/** The 3-col summary card (10.4 app.html `.card.sum`): Net P&L / Trades / Up%,
 *  over whatever population the active filters resolve to. `totals` is
 *  undefined only while the FIRST page/response hasn't loaded yet. */
function SummaryCard({ totals }: { totals: TradesTotals | undefined }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const loading = !totals
  const net = totals?.net_pnl ?? 0
  const upPct = totals && totals.completed_trades > 0 ? Math.round((totals.win_rate ?? 0)) : null

  return (
    <Card style={{ marginBottom: space.lg, flexDirection: 'row' }}>
      <SummaryCol label="Net P&L" value={loading ? '—' : signed(net)} tone={loading ? color.textDim : net >= 0 ? color.pos : color.neg} />
      <View style={s.sumDivider} />
      <SummaryCol label="Trades" value={loading ? '—' : String(totals?.completed_trades ?? 0)} tone={color.text} />
      <View style={s.sumDivider} />
      <SummaryCol label="Up" value={loading || upPct == null ? '—' : `${upPct}%`} tone={color.text} />
    </Card>
  )
}

function SummaryCol({ label, value, tone }: { label: string; value: string; tone: string }) {
  const { colors: color } = useTheme()
  return (
    <View style={{ flex: 1 }}>
      <Text style={[type.label, { color: color.muted }]}>{label}</Text>
      <Text style={[type.title, { color: tone, fontFamily: font.bodyBold, fontSize: 18, marginTop: 2 }]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  )
}

function TradeRow({ trade, last, onPress }: { trade: HistoryTrade; last: boolean; onPress: () => void }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${trade.strategy} trade, ${formatDate(trade.close_date)}`}
      style={[s.tradeRow, !last && { borderBottomWidth: 1, borderBottomColor: color.border }]}
    >
      <Mascot bot={trade.bot} size={34} />
      <View style={{ flex: 1, marginLeft: space.md }}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 15 }]}>
          {trade.strategy}
        </Text>
        <Text style={[type.label, { color: color.muted, marginTop: 1 }]}>
          {trade.opened_ct ?? '—'} – {trade.closed_ct ?? '—'}
          {trade.contracts ? ` · ${trade.contracts} contract${trade.contracts > 1 ? 's' : ''}` : ''}
        </Text>
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <Money value={trade.pnl} />
        <View style={{ marginTop: 3 }}>
          <OutcomeBadge kind={trade.outcome_kind} label={trade.outcome} />
        </View>
      </View>
    </Pressable>
  )
}

/**
 * Ember closed-trade sheet (fidelity audit "Ember row tap → trade detail") — a
 * styled bottom sheet instead of the native Alert.alert this used to open. Built
 * entirely from the HistoryTrade row the Ledger list already has (there is no
 * per-trade detail endpoint for Ember yet, so no sparkline/legs/timeline here —
 * only the fields genuinely available: result, opened/closed, contracts, outcome).
 */
function EmberTradeSheet({ trade, onClose }: { trade: HistoryTrade; onClose: () => void }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const accent = agentAccent('ember')
  return (
    <Sheet accent={accent} onClose={onClose}>
      {(close) => (
        <>
          <SheetHeader title="Trade" onClose={close} />
          <View style={{ padding: space.lg, paddingTop: 0 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
              <AgentBadge name="Ember" accent={accent} />
              <OutcomeBadge kind={trade.outcome_kind} label={trade.outcome} />
            </View>
            <Text style={[type.title, { color: color.text, fontFamily: font.display, marginTop: space.md }]}>
              {formatDate(trade.close_date)}
            </Text>

            <Card style={{ marginTop: space.lg }}>
              <Text style={[type.label, { color: color.muted }]}>Result</Text>
              <Money value={trade.pnl} size="hero" />
              <View style={s.emberFactsRow}>
                <EmberFact label="Opened" value={trade.opened_ct ?? '—'} />
                <EmberFact label="Closed" value={trade.closed_ct ?? '—'} />
              </View>
              <View style={s.emberFactsRow}>
                <EmberFact label="Contracts" value={String(trade.contracts)} />
                <EmberFact
                  label="Credit"
                  value={trade.credit != null ? `$${trade.credit.toFixed(2)}` : '—'}
                />
              </View>
            </Card>
          </View>
        </>
      )}
    </Sheet>
  )
}

function EmberFact({ label, value }: { label: string; value: string }) {
  const { colors: color } = useTheme()
  return (
    <View style={{ flex: 1 }}>
      <Text style={[type.label, { color: color.muted, marginBottom: 2 }]}>{label}</Text>
      <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>{value}</Text>
    </View>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  const { colors: color } = useTheme()
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }} edges={['top']}>
      <AppHeader />
      {children}
    </SafeAreaView>
  )
}

function signed(v: number): string {
  const a = Math.abs(v).toFixed(2)
  return v > 0 ? `+$${a}` : v < 0 ? `-$${a}` : '$0.00'
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

/** The day header's "Weekday, Month D" label (10.4 app.html day-h). */
function formatDayLabel(d: string): string {
  const [y, m, day] = d.split('-').map(Number)
  if (!y || !m || !day) return d
  return new Date(y, m - 1, day).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
  titleRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    marginBottom: space.lg,
  },
  title: { ...type.title, color: color.text, fontFamily: font.display },
  sumDivider: { width: 1, backgroundColor: color.border, marginHorizontal: space.md },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: color.card,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    marginBottom: space.md,
  },
  searchInput: {
    flex: 1,
    paddingVertical: space.md,
    color: color.text,
    fontSize: 15,
  },
  chipScroll: { marginBottom: space.md },
  chipRow: { flexDirection: 'row', gap: space.sm, paddingRight: space.lg },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  dayHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: space.xs,
    paddingBottom: space.sm,
  },
  tradeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: space.md,
  },
  emberFactsRow: {
    flexDirection: 'row',
    gap: space.lg,
    marginTop: space.lg,
  },
  loadMore: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
    marginTop: space.sm,
  },
  })
