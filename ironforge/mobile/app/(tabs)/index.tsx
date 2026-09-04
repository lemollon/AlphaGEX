import { useState, useEffect } from 'react'
import { View, Text, ScrollView, RefreshControl, Pressable, StyleSheet, Alert } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { useRouter } from 'expo-router'
import * as WebBrowser from 'expo-web-browser'
import { api, ApiError } from '@/api/client'
import type {
  LiveSummary,
  LiveAgent,
  LiveAgents,
  LiveOpenPosition,
  HomeData,
  BrokerageConnections,
} from '@/api/types'
import { color, space, radius, type, font, agentAccent } from '@/theme/tokens'
import { Card, Money, Balance, SectionLabel, Loading, Empty, ErrorState } from '@/components/ui'
import { StatRow } from '@/components/StatRow'
import { AppHeader, Mascot } from '@/components/Brand'
import { PnlChart } from '@/components/PnlChart'
import { brokerLabel, soleConnection } from '@/api/brokerage'
import { totalCapital } from '@/live/capital'
import { agentStatItems } from '@/live/card-stats'
import { formatPeriodValue, periodTone, type PeriodTone } from '@/live/period-stats'
import {
  deriveLifecycleNodes,
  lifecycleFillFraction,
  formatLocalClock,
  minutesSince,
  formatElapsedMinutes,
  formatTargetStopCaption,
  formatAutoCloseCaption,
} from '@/live/lifecycle'
import { pickBanner, bannerActionHref } from '@/alerts/banner'

/**
 * Forge — UX-002 (APP-011/012/013/016) and UX-003 (APP-051).
 *
 * Agents come from /api/live/agents, which fans out over every bot the viewer owns and
 * returns each one's own state, account and trade. Before that endpoint existed this
 * screen composed /api/live/summary + /api/live/trade, which between them could only ever
 * describe ONE agent — so the mockup's two side-by-side tiles were unbuildable and this
 * file said so.
 *
 * /api/live/summary is still fetched, for the period row and the market clock; those are
 * viewer-level, not per-agent. Polling stays conservative: 60s for summary and agents,
 * never the 4s the web uses, which on a phone is a battery and cellular-data problem.
 */
export default function ForgeScreen() {
  const router = useRouter()
  const summary = useSWR<LiveSummary>('/api/live/summary', (p: string) => api<LiveSummary>(p), {
    refreshInterval: 60_000,
  })
  const home = useSWR<HomeData>('/api/live/home', (p: string) => api<HomeData>(p), {
    refreshInterval: 60_000,
  })
  const agents = useSWR<LiveAgents>('/api/live/agents', (p: string) => api<LiveAgents>(p), {
    refreshInterval: 60_000,
  })
  const conns = useSWR<BrokerageConnections>('/api/brokerage/connections', (p: string) =>
    api<BrokerageConnections>(p),
  )
  // Only 'caution' may be dismissed (APP-016) — everything more urgent persists, so this
  // is never checked for those severities.
  const [dismissedCaution, setDismissedCaution] = useState(false)

  const refreshing = summary.isValidating || agents.isValidating
  const reload = () => {
    summary.mutate()
    home.mutate()
    agents.mutate()
  }

  if (summary.isLoading) return <Shell><Loading label="Loading your account…" /></Shell>
  if (summary.error) {
    return (
      <Shell>
        <ErrorState message={String((summary.error as Error).message)} onRetry={reload} />
      </Shell>
    )
  }

  const data = summary.data
  // The server returns {empty:true} for a customer with no account mapping. That is an
  // honest empty state, NOT an error — and never a reason to show someone else's money.
  if (!data || data.empty) {
    return (
      <Shell>
        <Empty
          title="No account connected yet"
          detail="Once your agent is activated and a brokerage account is linked, your capital and positions appear here."
        />
      </Shell>
    )
  }

  const list = agents.data?.agents ?? []
  const capital = totalCapital(list, data)

  const banner = pickBanner({
    connections: conns.data,
    agents: list,
    membershipBadge: data.membership?.badge,
    marketCondition: data.market.condition,
    conditionLine: data.market.condition_line,
  })
  const showBanner = banner && !(banner.severity === 'caution' && dismissedCaution)

  async function onBannerPress() {
    if (!banner?.action) return
    if (banner.action.target === 'billing') {
      // Same call the Account tab's "Manage Membership and Billing" makes — the payment
      // -due banner opens the portal directly rather than making the customer find the
      // button a second time.
      try {
        const res = await api<{ ok: boolean; url: string }>('/api/billing/portal', {
          method: 'POST',
        })
        if (res.url) await WebBrowser.openBrowserAsync(res.url)
      } catch (e) {
        Alert.alert(
          'Billing unavailable',
          e instanceof ApiError ? e.humanMessage : (e as Error).message,
        )
      }
      return
    }
    const href = bannerActionHref(banner.action)
    if (href) router.push(href)
  }

  return (
    <Shell>
      <ScrollView
        contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={reload} tintColor={color.accent} />
        }
      >
        {showBanner && banner ? (
          <AlertBanner
            banner={banner}
            onPress={onBannerPress}
            onDismiss={() => setDismissedCaution(true)}
          />
        ) : null}

        <Card>
          <SectionLabel>Total Account Capital</SectionLabel>
          <Balance value={capital.value} />
          {capital.note ? (
            <Text style={[type.label, { color: color.muted, marginTop: space.xs }]}>
              {capital.note}
            </Text>
          ) : null}
          {/* Paper accounts must say so, every time — never let paper read as real money. */}
          {data.account.mode === 'paper' && data.account.disclosure ? (
            <Text style={[type.label, { color: color.warn, marginTop: space.sm }]}>
              {data.account.disclosure}
            </Text>
          ) : null}

          <View style={s.periodRow}>
            <Period label="Today" value={data.account.today_pnl} />
            <Period label="This Week" value={home.data?.wealth.weekly_income ?? null} />
            <Period label="This Month" value={home.data?.wealth.monthly_income ?? null} />
            <Period label="Lifetime" value={home.data?.wealth.lifetime_income ?? null} />
          </View>
        </Card>

        <View style={[s.rowBetween, { marginTop: space.xl, marginBottom: space.md }]}>
          <SectionLabel>Active Positions</SectionLabel>
          <View style={s.rowCenter}>
            <View style={[s.dot, { backgroundColor: data.market.open ? color.pos : color.muted }]} />
            <Text style={[type.body, { color: data.market.open ? color.pos : color.textDim }]}>
              {data.market.label}
            </Text>
          </View>
        </View>

        {agents.isLoading ? (
          <Text style={[type.label, { color: color.muted }]}>Loading your agents…</Text>
        ) : list.length === 0 ? (
          <Empty
            title="No agents running"
            detail="Activate an agent and connect a brokerage account to see positions here."
          />
        ) : (
          list.map((a) => (
            <AgentTile
              key={a.bot}
              agent={a}
              // Only attributable when there is exactly one connection — see soleConnection().
              connection={list.length === 1 ? soleConnection(conns.data) : null}
            />
          ))
        )}
      </ScrollView>
    </Shell>
  )
}

/**
 * The one prioritized banner above the agent tiles (APP-016). Colour carries severity,
 * never agent identity — pickBanner is agent-neutral by design, so this stays that way
 * too rather than tinting by whichever bot happens to be named in the text.
 */
function AlertBanner({
  banner,
  onPress,
  onDismiss,
}: {
  banner: NonNullable<ReturnType<typeof pickBanner>>
  onPress: () => void
  onDismiss: () => void
}) {
  return (
    <Pressable
      onPress={banner.action ? onPress : undefined}
      accessibilityRole={banner.action ? 'button' : undefined}
      style={[s.banner, { borderColor: banner.color, backgroundColor: `${banner.color}18` }]}
    >
      <Ionicons name="alert-circle" size={18} color={banner.color} />
      <Text style={[type.body, { color: color.text, flex: 1, marginLeft: space.sm }]}>
        {banner.text}
      </Text>
      {banner.action ? (
        <Text style={[type.label, { color: banner.color, fontFamily: font.bodyMedium }]}>
          {banner.action.label}
        </Text>
      ) : null}
      {banner.dismissible ? (
        <Pressable onPress={onDismiss} hitSlop={10} accessibilityLabel="Dismiss" style={{ marginLeft: space.md }}>
          <Ionicons name="close" size={18} color={color.muted} />
        </Pressable>
      ) : null}
    </Pressable>
  )
}

/**
 * One shared size, format and baseline for all four figures — Today included —
 * so the row reads as a single line rather than Today looking like a
 * different kind of number from the other three. Whole dollars, a sign only
 * when non-zero, and a dash reserved for "could not load" (period-stats.ts).
 */
const periodToneColor: Record<PeriodTone, string> = {
  pos: color.pos,
  neg: color.neg,
  zero: color.muted,
  na: color.textDim,
}

function Period({ label, value }: { label: string; value: number | null }) {
  return (
    <View style={{ flex: 1, alignItems: 'center' }}>
      <Text
        style={[type.label, s.periodLabel, { color: color.muted }]}
        numberOfLines={1}
      >
        {label.toUpperCase()}
      </Text>
      <Text style={[s.periodValue, { color: periodToneColor[periodTone(value)] }]} numberOfLines={1}>
        {formatPeriodValue(value)}
      </Text>
    </View>
  )
}

/**
 * One agent tile with its lifecycle stepper, or — when the chart control is on — the
 * intraday P&L chart for the same trade (APP-051).
 */
function AgentTile({
  agent,
  connection,
}: {
  agent: LiveAgent
  connection: ReturnType<typeof soleConnection>
}) {
  const accent = agentAccent(agent.bot)
  const [showChart, setShowChart] = useState(false)

  const state = agent.state
  const trade = agent.trade
  const hasSeries = (trade?.spark_series?.length ?? 0) > 0

  return (
    <Card style={{ borderColor: accent, marginBottom: space.lg }}>
      <View style={s.rowBetween}>
        <View style={s.rowCenter}>
          <Mascot bot={agent.bot} size={38} />
          <View>
            <View style={s.rowCenter}>
              <Text
                style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}
              >
                {agent.label}
              </Text>
              {state ? (
                <View style={[s.pill, { borderColor: state.paused ? color.warn : color.pos }]}>
                  <Text style={[type.label, { color: state.paused ? color.warn : color.pos }]}>
                    {state.paused ? 'Paused' : 'Active'}
                  </Text>
                </View>
              ) : null}
              {agent.paper ? (
                <View style={[s.pill, { borderColor: color.warn }]}>
                  <Text style={[type.label, { color: color.warn }]}>Paper</Text>
                </View>
              ) : null}
            </View>
            {connection ? (
              <Text style={[type.label, { color: color.textDim, marginTop: 2 }]}>
                {brokerLabel(connection.broker ?? connection.provider)}
                {connection.mask ? `  •••• ${connection.mask}` : ''}
              </Text>
            ) : null}
          </View>
        </View>

        {/* Chart toggle (APP-051). Hidden when there is no series, rather than offering a
            control that opens an empty panel. */}
        {hasSeries ? (
          <Pressable
            onPress={() => setShowChart((v) => !v)}
            hitSlop={10}
            accessibilityRole="button"
            accessibilityLabel={showChart ? 'Show trade progress' : "Show today's profit and loss chart"}
            style={[
              s.chartBtn,
              { borderColor: accent, backgroundColor: showChart ? `${accent}22` : 'transparent' },
            ]}
          >
            <Ionicons name={showChart ? 'list-outline' : 'trending-up'} size={18} color={accent} />
          </Pressable>
        ) : null}
      </View>

      {/* Account Capital / Growth / Last 10 / Best Trade — LIFETIME, no filter
          (handoff/ledger-kpis.md PART 2). `agent.stats` is null only when the server
          couldn't compute it (both source queries must succeed); agentStatItems turns
          that into an honest "—" per column rather than throwing or hiding the row.
          No separate per-tile loading state: this tile does not mount until
          agents.data has already loaded (see the agents.isLoading gate above it). */}
      <View style={s.statsPanel}>
        <StatRow variant="card" items={agentStatItems(agent.stats, false)} />
      </View>

      {/* One agent failing must not blank the other — the server settles them separately,
          so a broken half says so instead of rendering as "nothing happening". */}
      {agent.error === 'state' || !state ? (
        <Text style={[type.label, { color: color.warn, marginTop: space.md }]}>
          Status is unavailable for {agent.label} right now.
        </Text>
      ) : (
        <>
          <Text
            style={[type.body, { color: color.text, marginTop: space.md, fontFamily: font.bodyMedium }]}
          >
            {state.headline}
          </Text>
          <Text style={[type.label, { color: color.textDim, marginTop: space.xs }]}>
            {state.subtitle}
          </Text>
        </>
      )}

      {/* Lifecycle line (UAT round two, mock #1) — same "has an open position"
          condition as the Target/Stop chart below it, so it never renders
          against a closed/no-trade tile. */}
      {trade?.active ? (
        <LifecycleLine
          accent={accent}
          openedAt={trade.opened_at}
          targetDollars={trade.target_dollars ?? null}
          stopDollars={trade.stop_dollars ?? null}
          autoCloseAt={trade.auto_close_at ?? null}
        />
      ) : null}

      {agent.error === 'trade' ? (
        <Text style={[type.label, { color: color.warn, marginTop: space.lg }]}>
          Position details are unavailable right now.
        </Text>
      ) : trade?.active ? (
        <>
          <View style={s.divider} />
          {/*
                UX-002 draws a rail PER TRADE, and there can be more than one: SPARK
                swings, so a leg opened yesterday is still open beside today's. The
                scalar fields only ever describe positions[0], which is exactly how the
                web page once hid a live position holding real money.

                Falls back to the single-trade shape when `positions` is absent, so an
                app newer than its API still renders.
              */}
              {(trade.positions?.length ?? 0) > 0 ? (
                trade.positions!.map((p, i) => (
                  <TradeRow
                    key={p.position_id || String(i)}
                    index={i}
                    position={p}
                    accent={accent}
                    // Only the newest trade can be at Target/Stop or Auto Close — the
                    // agent state describes it. Every other open leg is, by definition
                    // of still being open, being monitored.
                    step={i === 0 ? (state?.timeline_step ?? 1) : 1}
                    showChart={showChart}
                  />
                ))
              ) : showChart ? (
                // Legacy path: no per-position payload, so the only series available is
                // the agent's whole day. Correct when one trade is open, which is the
                // only case that can reach here.
                <PnlChart
                  series={trade.spark_series}
                  accent={accent}
                  status={stepLabel(state?.timeline_step ?? null)}
                  current={trade.unrealized_pnl}
                />
              ) : (
                <>
                  <View style={s.rowBetween}>
                    <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
                      Open position
                    </Text>
                    <Money value={trade.unrealized_pnl} size="title" />
                  </View>
                  <Stepper
                    step={state?.timeline_step ?? null}
                    accent={accent}
                    caption={state?.timeline_step === 1 ? 'Live' : null}
                  />
                </>
              )}
        </>
      ) : trade?.today_result ? (
        <>
          <View style={s.divider} />
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.textDim }]}>Today&apos;s result</Text>
            <Money value={trade.today_result.pnl} size="title" />
          </View>
        </>
      ) : (
        <Text style={[type.label, { color: color.muted, marginTop: space.lg }]}>
          No position open right now.
        </Text>
      )}
    </Card>
  )
}

/**
 * The open-position lifecycle line — UAT round two, mock #1
 * ("Open-position lifecycle with the real open time"). Four nodes on one
 * track: Opened → Monitoring → Target/Stop → Auto Close.
 *
 * State derivation and every caption are pure functions in live/lifecycle.ts
 * (tested there); this is presentation only, plus the once-a-minute tick that
 * keeps "N min" current without the customer having to pull to refresh.
 *
 * Distinct from the older Stepper below: Stepper reads CustomerState.timeline_step
 * directly and (by that convention) shows "Target / Stop" as current once a
 * position is being monitored. This line is the newer, approved design —
 * Monitoring itself is the current node for as long as the position is open,
 * since Target/Stop and Auto Close describe outcomes the backend cannot yet
 * detect live.
 */
function LifecycleLine({
  accent,
  openedAt,
  targetDollars,
  stopDollars,
  autoCloseAt,
}: {
  accent: string
  openedAt: string | null
  targetDollars: number | null
  stopDollars: number | null
  autoCloseAt: string | null
}) {
  // Forces a re-render once a minute so the Monitoring caption ("37 min")
  // ticks forward on its own — the position doesn't otherwise change shape
  // between 60s agent polls.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  const nodes = deriveLifecycleNodes(false)
  const fillPct = lifecycleFillFraction(nodes) * 75 // track spans the middle 75% of the row
  const captions = [
    formatLocalClock(openedAt) ?? '—',
    openedAt ? formatElapsedMinutes(minutesSince(openedAt)) : '—',
    formatTargetStopCaption(targetDollars, stopDollars),
    formatAutoCloseCaption(autoCloseAt),
  ]

  return (
    <View style={s.lifecycle} accessibilityLabel="Trade lifecycle">
      {/* Track first so it paints BEHIND the node dots, not over them. */}
      <View style={s.lifecycleTrack} />
      <View style={[s.lifecycleFill, { width: `${fillPct}%`, backgroundColor: accent }]} />
      <View style={s.lifecycleNodes}>
        {nodes.map((node, i) => {
          const nodeColor =
            node.status === 'done' ? color.pos : node.status === 'current' ? accent : color.border
          return (
            <View
              key={node.label}
              style={s.lifecycleNode}
              accessible
              accessibilityRole="text"
              accessibilityLabel={`${node.label}, ${node.status}, ${captions[i]}`}
            >
              <View
                style={[
                  s.lifecycleHalo,
                  node.status === 'current' ? { backgroundColor: `${accent}2E` } : null,
                ]}
              >
                <View
                  style={[
                    s.lifecycleDot,
                    {
                      borderColor: nodeColor,
                      backgroundColor: node.status === 'future' ? color.card : nodeColor,
                    },
                  ]}
                >
                  {node.status === 'done' ? (
                    <Ionicons name="checkmark" size={12} color={color.bg} />
                  ) : null}
                </View>
              </View>
              <Text
                style={[
                  type.label,
                  {
                    color: node.status === 'future' ? color.muted : nodeColor,
                    fontFamily: font.bodyMedium,
                    marginTop: space.xs,
                    textAlign: 'center',
                  },
                ]}
              >
                {node.label}
              </Text>
              <Text style={[type.label, { color: color.muted, marginTop: 1, textAlign: 'center' }]}>
                {captions[i]}
              </Text>
            </View>
          )
        })}
      </View>
    </View>
  )
}

/**
 * One open trade: title, its own P&L, its own rail — UX-002.
 *
 * Titled "Trade 1 / Trade 2" as the approved layout does, but a leg held overnight
 * also says which day it is on. The mockup's invented data had no swung legs; the real
 * product does, and a customer looking at two identical-looking rows needs to know one
 * of them is yesterday's.
 */
function TradeRow({
  index,
  position,
  accent,
  step,
  showChart,
}: {
  index: number
  position: LiveOpenPosition
  accent: string
  step: number | null
  showChart: boolean
}) {
  // Each trade draws its OWN series. Falls back to the rail when this position has no
  // marks yet — a position opened before the scanner started recording them has
  // nothing to plot, and an empty chart frame says less than the rail does.
  const series = position.series ?? []
  const chart = showChart && series.length > 1
  return (
    <View style={index > 0 ? { marginTop: space.lg } : undefined}>
      <View style={s.rowBetween}>
        <View>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
            {`Trade ${index + 1}`}
          </Text>
          {position.held_overnight ? (
            <Text style={[type.label, { color: color.textDim, marginTop: 1 }]}>
              {`Opened ${position.opened_date_label} · Day ${position.day_number}`}
            </Text>
          ) : null}
        </View>
        {/* null P&L renders as "—", never $0.00 — quotes were unavailable, not flat. */}
        <Money value={position.unrealized_pnl} size="title" />
      </View>
      {chart ? (
        <PnlChart
          series={series}
          accent={accent}
          status={stepLabel(step)}
          current={position.unrealized_pnl}
        />
      ) : (
        <Stepper step={step} accent={accent} caption={step === 1 ? 'Live' : null} />
      )}
    </View>
  )
}

/** timeline_step is 0..4; there are four labels, so a step of 4 rests on the last. */
const STEP_LABELS: readonly string[] = ['Opened', 'Monitoring', 'Target / Stop', 'Auto Close']

function stepLabel(step: number | null): string {
  const i = Math.min(Math.max(step ?? 0, 0), STEP_LABELS.length - 1)
  return STEP_LABELS[i]
}

/**
 * Opened → Monitoring → Target/Stop → Auto Close, driven by CustomerState.timeline_step.
 *
 * UX-002 puts a small caption under the step the trade is actually sitting on — "Live"
 * while it is being watched. Without it the active ring and a completed dot look nearly
 * identical at a glance, which is the one thing a customer opens this screen to tell
 * apart: is it working right now, or is it done?
 */
function Stepper({
  step,
  accent,
  caption,
}: {
  step: number | null
  accent: string
  caption?: string | null
}) {
  const current = step ?? 0
  return (
    <View style={s.stepper}>
      {STEP_LABELS.map((l, i) => {
        const done = i < current
        const active = i === current
        const c = done || active ? accent : color.border
        return (
          <View key={l} style={{ flex: 1, alignItems: 'center' }}>
            <View style={[s.stepDot, { borderColor: c, backgroundColor: done ? c : 'transparent' }]} />
            <Text
              style={[
                type.label,
                { color: active ? color.text : color.muted, marginTop: space.xs, textAlign: 'center' },
              ]}
            >
              {l}
            </Text>
            {active && caption ? (
              <Text style={[type.label, { color: accent, marginTop: 1, textAlign: 'center' }]}>
                {caption}
              </Text>
            ) : null}
          </View>
        )
      })}
    </View>
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

const s = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md,
    marginBottom: space.lg,
  },
  periodRow: {
    flexDirection: 'row',
    marginTop: space.xl,
    borderTopColor: color.border,
    borderTopWidth: 1,
    paddingTop: space.lg,
  },
  // Fixed label height so a longer word ("This Month") never wraps and pushes
  // the value below it out of line with the other three columns' baseline.
  periodLabel: { height: 14, marginBottom: space.xs },
  periodValue: {
    fontSize: 16,
    lineHeight: 20,
    fontFamily: font.bodyBold,
    fontVariant: ['tabular-nums'],
  },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowCenter: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  pill: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  chartBtn: {
    borderWidth: 1,
    borderRadius: radius.md,
    width: 38,
    height: 38,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Inset panel background: color.bg reads darker than the card's own color.card,
  // matching the approved mock's slightly-recessed --card-2 without a new token.
  statsPanel: {
    marginTop: space.md,
    backgroundColor: color.bg,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.lg,
    paddingVertical: space.md,
  },
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.lg },
  stepper: { flexDirection: 'row', marginTop: space.lg },
  stepDot: { width: 16, height: 16, borderRadius: 8, borderWidth: 2 },
  lifecycle: { marginTop: space.md, position: 'relative' },
  lifecycleNodes: { flexDirection: 'row' },
  lifecycleNode: { flex: 1, alignItems: 'center' },
  // 32px halo around a 24px dot — the "soft halo" ring is a plain tinted
  // circle behind the dot rather than a CSS box-shadow, which RN has no
  // equivalent for; only the current node gets a non-transparent halo.
  lifecycleHalo: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  lifecycleDot: { width: 24, height: 24, borderRadius: 12, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  // Positioned to cross through the halo's vertical center (16px) minus half
  // the line's own height, so the 3px track visually threads through every dot.
  lifecycleTrack: {
    position: 'absolute',
    top: 14.5,
    left: '12.5%',
    right: '12.5%',
    height: 3,
    borderRadius: 2,
    backgroundColor: color.border,
  },
  lifecycleFill: {
    position: 'absolute',
    top: 14.5,
    left: '12.5%',
    height: 3,
    borderRadius: 2,
  },
})
