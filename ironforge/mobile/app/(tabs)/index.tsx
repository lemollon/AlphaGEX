import { useState } from 'react'
import { View, Text, ScrollView, RefreshControl, Pressable, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { api } from '@/api/client'
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
import { AppHeader, Mascot } from '@/components/Brand'
import { PnlChart } from '@/components/PnlChart'
import { brokerLabel, soleConnection } from '@/api/brokerage'
import { totalCapital } from '@/live/capital'

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

  return (
    <Shell>
      <ScrollView
        contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={reload} tintColor={color.accent} />
        }
      >
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
            <Period label="This Week" value={home.data?.week_income ?? null} />
            <Period label="This Month" value={home.data?.month_income ?? null} />
            <Period label="Lifetime" value={home.data?.lifetime_income ?? null} />
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

function Period({ label, value }: { label: string; value: number | null }) {
  return (
    <View style={{ flex: 1, alignItems: 'center' }}>
      <Text style={[type.label, { color: color.muted, marginBottom: space.xs }]}>
        {label.toUpperCase()}
      </Text>
      <Money value={value} />
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

      {agent.error === 'trade' ? (
        <Text style={[type.label, { color: color.warn, marginTop: space.lg }]}>
          Position details are unavailable right now.
        </Text>
      ) : trade?.active ? (
        <>
          <View style={s.divider} />
          {showChart ? (
            <PnlChart
              series={trade.spark_series}
              accent={accent}
              status={stepLabel(state?.timeline_step ?? null)}
              current={trade.unrealized_pnl}
            />
          ) : (
            <>
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
                  />
                ))
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
}: {
  index: number
  position: LiveOpenPosition
  accent: string
  step: number | null
}) {
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
      <Stepper step={step} accent={accent} caption={step === 1 ? 'Live' : null} />
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
  periodRow: {
    flexDirection: 'row',
    marginTop: space.xl,
    borderTopColor: color.border,
    borderTopWidth: 1,
    paddingTop: space.lg,
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
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.lg },
  stepper: { flexDirection: 'row', marginTop: space.lg },
  stepDot: { width: 16, height: 16, borderRadius: 8, borderWidth: 2 },
})
