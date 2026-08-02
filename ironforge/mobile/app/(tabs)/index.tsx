import { View, Text, ScrollView, RefreshControl, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import useSWR from 'swr'
import { api } from '@/api/client'
import type { LiveSummary, LiveTrade, HomeData } from '@/api/types'
import { color, space, radius, type, font, agentAccent, pnlColor } from '@/theme/tokens'
import { Card, Money, Balance, SectionLabel, Loading, Empty, ErrorState } from '@/components/ui'

/**
 * Forge — UX-002 (APP-011/012/013/016).
 *
 * Three endpoints because the approved layout spans three payloads: summary (capital,
 * today, market), home (week/month/lifetime), trade (active position + intraday P&L).
 * A single aggregated endpoint is the right eventual shape — noted as G5 in the plan —
 * but composing here keeps the app shippable against what the server serves today.
 *
 * Polling is conservative: 60s for summary, 30s for the live trade. The web polls
 * community every 4s, which on a phone is a battery and data problem; nothing here
 * goes below 30s.
 */
export default function ForgeScreen() {
  const summary = useSWR<LiveSummary>('/api/live/summary', (p: string) => api(p), {
    refreshInterval: 60_000,
  })
  const home = useSWR<HomeData>('/api/live/home', (p: string) => api(p), { refreshInterval: 60_000 })
  const trade = useSWR<LiveTrade>('/api/live/trade', (p: string) => api(p), {
    refreshInterval: 30_000,
  })

  const refreshing = summary.isValidating || trade.isValidating
  const reload = () => {
    summary.mutate()
    home.mutate()
    trade.mutate()
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
          <Balance value={data.account.value} />
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

        <AgentTile
          bot={data.viewer?.bot ?? 'spark'}
          state={data.state}
          trade={trade.data}
          loading={trade.isLoading}
        />
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
 * One agent tile with its lifecycle stepper.
 *
 * UX-002 shows multiple concurrent trades per agent; the current API returns a single
 * LiveTrade, so this renders the one it has rather than faking a second. Expanding to
 * per-trade requires the aggregated endpoint (G5) — deliberately not stubbed with
 * invented rows.
 */
function AgentTile({
  bot,
  state,
  trade,
  loading,
}: {
  bot: string
  state: LiveSummary['state']
  trade: LiveTrade | undefined
  loading: boolean
}) {
  const accent = agentAccent(bot)
  const name = bot.charAt(0).toUpperCase() + bot.slice(1)

  return (
    <Card style={{ borderColor: accent }}>
      <View style={s.rowBetween}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
          {name}
        </Text>
        <View style={[s.pill, { borderColor: state.paused ? color.warn : color.pos }]}>
          <Text style={[type.label, { color: state.paused ? color.warn : color.pos }]}>
            {state.paused ? 'Paused' : 'Active'}
          </Text>
        </View>
      </View>

      <Text style={[type.body, { color: color.text, marginTop: space.md, fontFamily: font.bodyMedium }]}>
        {state.headline}
      </Text>
      <Text style={[type.label, { color: color.textDim, marginTop: space.xs }]}>{state.subtitle}</Text>

      {loading ? (
        <Text style={[type.label, { color: color.muted, marginTop: space.lg }]}>Loading position…</Text>
      ) : trade?.active ? (
        <>
          <View style={s.divider} />
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              Open position
            </Text>
            <Money value={trade.unrealized_pnl} size="title" />
          </View>
          <Stepper step={state.timeline_step} accent={accent} />
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

/** Opened → Monitoring → Target/Stop → Auto Close, driven by CustomerState.timeline_step. */
function Stepper({ step, accent }: { step: number | null; accent: string }) {
  const labels = ['Opened', 'Monitoring', 'Target / Stop', 'Auto Close']
  const current = step ?? 0
  return (
    <View style={s.stepper}>
      {labels.map((l, i) => {
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
          </View>
        )
      })}
    </View>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }} edges={['top']}>{children}</SafeAreaView>
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
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.lg },
  stepper: { flexDirection: 'row', marginTop: space.lg },
  stepDot: { width: 16, height: 16, borderRadius: 8, borderWidth: 2 },
})
