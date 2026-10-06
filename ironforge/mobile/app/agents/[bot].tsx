import { useEffect, useMemo, useRef, useState } from 'react'
import { View, Text, ScrollView, Pressable, StyleSheet, Alert } from 'react-native'
import { Stack, useRouter, useLocalSearchParams } from 'expo-router'
import * as WebBrowser from 'expo-web-browser'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { mutate as globalMutate } from 'swr'
import { api, API_BASE, ApiError } from '@/api/client'
import type {
  LiveAgents,
  LiveAgent,
  EntitlementsResponse,
  AutomationPauseResponse,
  AutomationActivation,
  BrokerageConnections,
  BrokerageAccount,
  BrokerageConnection,
  AgentConfigResponse,
  ActivationPreviewResponse,
  ActivationResponse,
  EmberTradesResponse,
  EmberStatusResponse,
} from '@/api/types'
import { space, radius, type, font, agentAccent } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Card, SectionLabel, Money, Loading, ErrorState } from '@/components/ui'
import { Mascot } from '@/components/Brand'
import { Sheet, SheetHeader } from '@/components/Sheet'
import { Confetti } from '@/components/Confetti'
import { LiveTradeCard } from '@/components/LiveTradeCard'
import { showToast } from '@/notifications/toast'
import { soleConnection, brokerLabel, maskTail } from '@/api/brokerage'
import { track } from '@/analytics/track'
import { trackEvent } from '@/analytics/trackEvent'
import { agentAction, type AgentActionKind } from '@/agents/eligibility'
import type { AgentBot } from '@/agents/routes'
import {
  AGENT_LABEL,
  AGENT_DESCRIPTION,
  ACCOUNT_REQUIREMENTS,
  TRADING_SCHEDULE,
  RISK_SUMMARY,
} from '@/agents/copy'

function dotColorFor(dot: string, color: ColorTokens): string {
  const map: Record<string, string> = {
    green: color.pos,
    blue: color.spark,
    amber: color.warn,
    red: color.neg,
    gray: color.muted,
  }
  return map[dot] ?? color.muted
}

const PAUSE_COPY =
  "Stops new entries. Open positions continue to be managed by the agent's risk rules."

/**
 * Agent detail (APP-024) — one screen, five renderings, driven entirely by
 * agentAction(). Active/Paused get the live status + pause control (APP-028/029);
 * Add gets the activation flow (APP-025); Setup Required and Switch each get an
 * explanation and hand off to the web, because neither has an in-app endpoint.
 */
export default function AgentDetailScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()
  const params = useLocalSearchParams<{ bot: string }>()
  const bot = (
    params.bot === 'flame' ? 'flame' : params.bot === 'ember' ? 'ember' : 'spark'
  ) as AgentBot
  const label = AGENT_LABEL[bot]

  useEffect(() => {
    trackEvent('agent_sheet_open', { agent: bot })
  }, [bot])

  const agentsSWR = useSWR<LiveAgents>('/api/live/agents', (p: string) => api<LiveAgents>(p))
  const entitlementsSWR = useSWR<EntitlementsResponse>('/api/billing/entitlements', (p: string) =>
    api<EntitlementsResponse>(p),
  )
  const pauseSWR = useSWR<AutomationPauseResponse>('/api/v1/automation/pause', (p: string) =>
    api<AutomationPauseResponse>(p),
  )
  const connsSWR = useSWR<BrokerageConnections>('/api/brokerage/connections', (p: string) =>
    api<BrokerageConnections>(p),
  )

  const loading =
    agentsSWR.isLoading || entitlementsSWR.isLoading || pauseSWR.isLoading || connsSWR.isLoading
  const failed = agentsSWR.error || pauseSWR.error

  if (loading) {
    return (
      <Shell bot={bot} router={router}>
        <Loading label={`Loading ${label}…`} />
      </Shell>
    )
  }
  if (failed) {
    return (
      <Shell bot={bot} router={router}>
        <ErrorState
          message={`Could not load ${label} right now.`}
          onRetry={() => {
            agentsSWR.mutate()
            pauseSWR.mutate()
            connsSWR.mutate()
          }}
        />
      </Shell>
    )
  }

  const liveAgent = agentsSWR.data?.agents.find((a) => a.bot === bot) ?? null
  const eligibleAccounts = (connsSWR.data?.connections ?? []).flatMap((c) =>
    c.accounts
      .filter((a) => a.eligibility === 'eligible')
      .map((a) => ({ account: a, connection: c })),
  )
  const activations: AutomationActivation[] = pauseSWR.data?.activations ?? []
  const action = agentAction({
    bot,
    entitlements: entitlementsSWR.data?.bots ?? [],
    activations: activations.map((a) => ({ agent: a.agent, paused: a.paused })),
    eligibleAccountCount: eligibleAccounts.length,
  })

  return (
    <Shell
      bot={bot}
      router={router}
      left={<Mascot bot={bot} size={36} />}
      subtitle={liveAgent?.state?.headline ?? action.label}
      dotColor={liveAgent?.state ? dotColorFor(liveAgent.state.dot, color) : color.muted}
    >
      <ScrollView contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}>
        <Card>
          <SectionLabel>How it works</SectionLabel>
          <Text style={[type.body, { color: color.textDim }]}>{AGENT_DESCRIPTION[bot]}</Text>
          <Text style={[type.body, { color: color.textDim, marginTop: space.md }]}>
            {TRADING_SCHEDULE[bot]}
          </Text>
          <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
            Account requirements
          </Text>
          <Text style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
            {ACCOUNT_REQUIREMENTS}
          </Text>
          <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
            Risk summary
          </Text>
          <Text style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
            {RISK_SUMMARY}
          </Text>
        </Card>

        {/* Ember's own trade book/status (#3177) — shown to any Ember OWNER
            regardless of automation-activation state: Ember's execution
            (REFLEX) is a separate always-on sleeve, not gated the same way
            Spark/Flame's pause/resume activation rows are, so this must not
            wait on `action.kind` reaching 'active'/'paused'. */}
        {bot === 'ember' && (entitlementsSWR.data?.bots ?? []).includes('ember') ? (
          <EmberWorkspaceSection />
        ) : null}

        {action.kind === 'active' || action.kind === 'paused' ? (
          <CurrentAgentSection
            bot={bot}
            label={label}
            liveAgent={liveAgent}
            activation={activations.find((a) => a.agent === bot) ?? null}
            connections={connsSWR.data}
            agentsSWR={agentsSWR}
            connsSWR={connsSWR}
            pauseSWR={pauseSWR}
          />
        ) : action.kind === 'setup_required' ? (
          <SetupRequiredSection bot={bot} label={label} />
        ) : action.kind === 'switch' ? (
          <SwitchSection bot={bot} label={label} otherAgent={agentsSWR.data?.agents.find((a) => a.bot !== bot) ?? null} />
        ) : (
          <ActivationFlow bot={bot} label={label} eligibleAccounts={eligibleAccounts} />
        )}
      </ScrollView>
    </Shell>
  )
}

/**
 * Agent sheet chrome (mobile addendum §2 "Agent sheet"): agent-color accent border,
 * mascot + status header, close "X". Presented as a `transparentModal` route so the
 * tab underneath stays visible and sliding this away (drag, scrim tap, or Android
 * back) reveals it exactly where it was.
 */
function Shell({
  bot,
  router,
  children,
  left,
  subtitle,
  dotColor,
}: {
  bot: AgentBot
  router: ReturnType<typeof useRouter>
  children: React.ReactNode
  left?: React.ReactNode
  subtitle?: string
  dotColor?: string
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <>
      <Stack.Screen
        options={{ presentation: 'transparentModal', animation: 'fade', contentStyle: { backgroundColor: 'transparent' } }}
      />
      <Sheet accent={agentAccent(bot)} onClose={() => router.back()}>
        {(close) => (
          <>
            <SheetHeader
              title={AGENT_LABEL[bot]}
              subtitle={subtitle}
              left={left}
              right={
                dotColor ? <View style={[s.dot, { backgroundColor: dotColor, marginRight: space.sm }]} /> : null
              }
              onClose={close}
            />
            {children}
          </>
        )}
      </Sheet>
    </>
  )
}

/** Active or Paused: live status, assigned account, latest trade, pause/resume. */
function CurrentAgentSection({
  bot,
  label,
  liveAgent,
  activation,
  connections,
  agentsSWR,
  connsSWR,
  pauseSWR,
}: {
  bot: AgentBot
  label: string
  liveAgent: LiveAgent | null
  activation: AutomationActivation | null
  connections: BrokerageConnections | undefined
  agentsSWR: ReturnType<typeof useSWR<LiveAgents>>
  connsSWR: ReturnType<typeof useSWR<BrokerageConnections>>
  pauseSWR: ReturnType<typeof useSWR<AutomationPauseResponse>>
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const state = liveAgent?.state ?? null
  const trade = liveAgent?.trade ?? null
  const sole = soleConnection(connections)
  const accent = agentAccent(bot)

  return (
    <>
      <Card style={{ marginTop: space.lg, borderColor: accent }}>
        <SectionLabel>Current status</SectionLabel>
        {liveAgent?.error === 'state' || !state ? (
          <Text style={[type.body, { color: color.warn }]}>
            Status is unavailable for {label} right now.
          </Text>
        ) : (
          <>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              {state.headline}
            </Text>
            <Text style={[type.label, { color: color.textDim, marginTop: space.xs }]}>
              {state.subtitle}
            </Text>
            {state.check_line ? (
              <Text style={[type.label, { color: color.muted, marginTop: space.xs }]}>
                {state.check_line}
              </Text>
            ) : null}
          </>
        )}

        <View style={s.divider} />
        <Text style={[type.label, { color: color.muted }]}>Brokerage account</Text>
        <Text style={[type.body, { color: color.text, marginTop: space.xs }]}>
          {sole
            ? `${brokerLabel(sole.broker ?? sole.provider)}${sole.mask ? `  ${maskTail(sole.mask)}` : ''}`
            : 'Not available'}
        </Text>

        <View style={s.divider} />
        <Text style={[type.label, { color: color.muted, marginBottom: space.xs }]}>
          Latest trade
        </Text>
        {liveAgent?.error === 'trade' ? (
          <Text style={[type.body, { color: color.warn }]}>
            Position details are unavailable right now.
          </Text>
        ) : trade?.active ? (
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text }]}>Open position</Text>
            <Money value={trade.unrealized_pnl} />
          </View>
        ) : trade?.today_result ? (
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text }]}>Today&apos;s result</Text>
            <Money value={trade.today_result.pnl} />
          </View>
        ) : (
          <Text style={[type.body, { color: color.textDim }]}>No recent trade.</Text>
        )}
      </Card>

      {/* Embedded live-trade chart/progress/stage footer (10.4 design agentSheet()'s
          reproduced liveCard) — the SAME component the Forge tab's "Live now" strip
          uses, so the sheet is never a second, drifted description of the same open
          position. */}
      {trade?.active ? (
        <View style={{ marginTop: space.lg }}>
          <LiveTradeCard bot={bot} label={label} accent={accent} trade={trade} />
        </View>
      ) : null}

      <PerformanceSection liveAgent={liveAgent} accent={accent} />

      <PauseResumeControl
        bot={bot}
        label={label}
        activation={activation}
        agentsSWR={agentsSWR}
        connsSWR={connsSWR}
        pauseSWR={pauseSWR}
      />
    </>
  )
}

/**
 * Agent sheet KPI 2x2 + "last 20 trading days" bars (mobile addendum §2
 * "Agent sheet": "Today/Past week/Past month/Lifetime" 2x2 grid plus a
 * 20-trading-day bar chart with a wins caption). Sourced from GET
 * /api/live/agents' `kpis`/`daily20` (added alongside this screen — see
 * webapp's trades-history.ts computeAgentPeriodKpis/last20DailyBars), which
 * reuse the same closed-trade query the Forge card stats row already runs,
 * so this costs nothing extra on the wire.
 *
 * Renders nothing when `kpis` is absent (an app talking to a server from
 * before this field existed) rather than a row of fabricated zeros.
 */
function PerformanceSection({ liveAgent, accent }: { liveAgent: LiveAgent | null; accent: string }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const kpis = liveAgent?.kpis
  if (kpis === undefined) return null

  return (
    <Card style={{ marginTop: space.lg }}>
      <SectionLabel>Performance</SectionLabel>
      {kpis === null ? (
        <Text style={[type.body, { color: color.warn, marginTop: space.sm }]}>
          Performance is unavailable right now.
        </Text>
      ) : (
        <>
          <View style={s.kpiGrid}>
            <View style={s.kpiRow}>
              <KpiTile label="Today" value={kpis.today} />
              <KpiTile label="Past week" value={kpis.week} />
            </View>
            <View style={s.kpiRow}>
              <KpiTile label="Past month" value={kpis.month} />
              <KpiTile label="Lifetime" value={kpis.life} />
            </View>
          </View>

          {liveAgent?.daily20 && liveAgent.daily20.length > 0 ? (
            <>
              <View style={s.divider} />
              <View style={s.rowBetween}>
                <Text style={[type.label, { color: color.muted }]}>Last 20 trading days</Text>
                <Text style={[type.label, { color: color.muted }]}>
                  {liveAgent.daily20.filter((d) => d.pnl > 0).length} of {liveAgent.daily20.length} days up
                </Text>
              </View>
              <DailyBars days={liveAgent.daily20} accent={accent} />
            </>
          ) : null}
        </>
      )}
    </Card>
  )
}

function KpiTile({ label, value }: { label: string; value: number | null }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <View style={s.kpiTile}>
      <Text style={[type.label, { color: color.muted }]}>{label}</Text>
      <Money value={value} size="title" />
    </View>
  )
}

/** A minimal up/down bar chart, oldest to newest left-to-right, centered on a
 *  zero line — plain Views (no SVG) since every bar is a flat rectangle. */
function DailyBars({ days, accent }: { days: Array<{ date: string; pnl: number }>; accent: string }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const maxAbs = Math.max(1, ...days.map((d) => Math.abs(d.pnl)))
  return (
    <View style={s.barsRow} accessibilityLabel={`Daily results over the last ${days.length} trading days`}>
      {days.map((d) => {
        const pct = Math.max(4, (Math.abs(d.pnl) / maxAbs) * 100)
        const up = d.pnl >= 0
        return (
          <View key={d.date} style={s.barCol}>
            <View style={s.barHalfTop}>
              {up ? <View style={[s.bar, { height: `${pct}%`, backgroundColor: color.pos }]} /> : null}
            </View>
            <View style={s.barZero} />
            <View style={s.barHalfBottom}>
              {!up ? <View style={[s.bar, { height: `${pct}%`, backgroundColor: color.neg }]} /> : null}
            </View>
          </View>
        )
      })}
    </View>
  )
}

/**
 * Ember's own trade book + status (PR #3177), inline on its agent sheet —
 * mirrors webapp's EmberWorkspaceClient.tsx (same endpoints, same "this is
 * Ember's OWN book, not your brokerage account" framing). Ember's execution
 * (REFLEX) has no pause/resume via /api/v1/automation/pause and no per-trade
 * strike/leg detail to show, so this is additive to — not a replacement for
 * — the generic CurrentAgentSection above it.
 */
function EmberWorkspaceSection() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const tradesSWR = useSWR<EmberTradesResponse>('/api/ember/trades', (p: string) => api<EmberTradesResponse>(p), {
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  })
  const statusSWR = useSWR<EmberStatusResponse>('/api/ember/status', (p: string) => api<EmberStatusResponse>(p), {
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  })
  const trades = tradesSWR.data?.trades ?? []
  const status = statusSWR.data?.status ?? null
  const openCount = Array.isArray(status?.open_positions) ? (status!.open_positions as unknown[]).length : 0

  return (
    <Card style={{ marginTop: space.lg }}>
      <SectionLabel>Ember&apos;s trade book</SectionLabel>
      <View style={s.rowBetween}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
          {status ? `Ember is ${status.state ?? 'reporting'}` : 'Waiting on Ember’s first report'}
        </Text>
        <Text style={[type.label, { color: color.muted }]}>{openCount} open</Text>
      </View>
      <Text style={[type.label, { color: color.muted, marginTop: space.xs }]}>
        Last update: {formatHeartbeat(status?.last_heartbeat ?? null)}
      </Text>

      <View style={s.divider} />
      {trades.length === 0 ? (
        <Text style={[type.body, { color: color.textDim }]}>
          Ember hasn&apos;t opened a position yet. Its trades show up here from Ember&apos;s own
          book, not your brokerage account&apos;s overall activity.
        </Text>
      ) : (
        trades.slice(0, 10).map((t) => {
          const pnl = t.pnl != null ? Number(t.pnl) : null
          return (
            <View key={t.id} style={s.rowBetween}>
              <View>
                <Text style={[type.body, { color: color.text }]}>{t.symbol}</Text>
                <Text style={[type.label, { color: color.muted }]}>
                  {t.status === 'closed' ? formatHeartbeat(t.closed_at) : 'Open'}
                </Text>
              </View>
              <Money value={pnl} />
            </View>
          )
        })
      )}
    </Card>
  )
}

function formatHeartbeat(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/** Pause / Resume — APP-028/029. */
function PauseResumeControl({
  bot,
  label,
  activation,
  agentsSWR,
  connsSWR,
  pauseSWR,
}: {
  bot: AgentBot
  label: string
  activation: AutomationActivation | null
  agentsSWR: ReturnType<typeof useSWR<LiveAgents>>
  connsSWR: ReturnType<typeof useSWR<BrokerageConnections>>
  pauseSWR: ReturnType<typeof useSWR<AutomationPauseResponse>>
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const [pending, setPending] = useState(false)
  const paused = activation?.paused ?? false
  const accent = agentAccent(bot)

  async function doToggle(nextPaused: boolean) {
    setPending(true)
    try {
      const res = await api<AutomationPauseResponse>('/api/v1/automation/pause', {
        method: 'POST',
        body: { paused: nextPaused, agent: bot },
      })
      pauseSWR.mutate(res, { revalidate: false })
      // Shared SWR cache key with the Forge tab — this is what makes AgentTile there
      // reflect the new paused state without that screen doing anything itself.
      void globalMutate('/api/live/agents')
      track(nextPaused ? 'agent_pause_confirmed' : 'agent_resume_confirmed', { agent: bot })
      trackEvent(nextPaused ? 'agent_pause' : 'agent_resume', { agent: bot })

      // Floating snackbar (10.4 design `toast()` — "Spark paused"), not a blocking
      // native dialog: the pause/resume itself already asked for confirmation via
      // confirmToggle below, so this is just quick feedback that it happened.
      showToast(nextPaused ? `${label} paused` : `${label} resumed`)
    } catch (e) {
      showToast(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setPending(false)
    }
  }

  function confirmToggle(nextPaused: boolean) {
    Alert.alert(nextPaused ? `Pause ${label}?` : `Resume ${label}?`, PAUSE_COPY, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: nextPaused ? 'Pause' : 'Resume',
        style: nextPaused ? 'destructive' : 'default',
        onPress: () => void doToggle(nextPaused),
      },
    ])
  }

  /**
   * Resume preflight: re-fetch before offering the confirm, and refuse with the
   * reason rather than let a resume race an account that just went bad (SPEC.md).
   */
  async function handleResumeTap() {
    setPending(true)
    try {
      const [freshAgents, freshConns] = await Promise.all([agentsSWR.mutate(), connsSWR.mutate()])
      const fresh = freshAgents?.agents.find((a) => a.bot === bot) ?? null
      const key = fresh?.state?.key
      if (key === 'BLOCKED' || key === 'ACTION_REQUIRED') {
        Alert.alert(
          'Cannot resume yet',
          fresh?.state?.check_line ?? `${label} cannot resume trading right now.`,
        )
        return
      }
      const disconnected = (freshConns?.connections ?? []).some(
        (c) => c.status === 'disconnected' || c.status === 'revoked' || c.status === 'expired',
      )
      if (disconnected) {
        Alert.alert(
          'Cannot resume yet',
          'A connected brokerage needs attention before trading can resume. Fix it from Account first.',
        )
        return
      }
      confirmToggle(false)
    } finally {
      setPending(false)
    }
  }

  return (
    <Pressable
      onPress={() => (paused ? void handleResumeTap() : confirmToggle(true))}
      disabled={pending || !activation}
      // Full-width FILLED pill (10.4 design `.btn-c`/`.btn-stop` — "Pause {Name}" is
      // agent-accent, "Resume {Name}" is the up colour), not the bordered ghost this
      // used to be — see fidelity audit "Pause/Resume button".
      style={[
        s.pauseResumeBtn,
        { backgroundColor: paused ? color.pos : accent, opacity: pending || !activation ? 0.5 : 1 },
      ]}
    >
      <Ionicons name="pause" size={16} color={color.bg} />
      <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>
        {pending ? 'Working…' : paused ? `Resume ${label}` : `Pause ${label}`}
      </Text>
    </Pressable>
  )
}

function SetupRequiredSection({ bot, label }: { bot: AgentBot; label: string }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <Card style={{ marginTop: space.lg }}>
      <SectionLabel>Setup required</SectionLabel>
      <Text style={[type.body, { color: color.textDim }]}>
        No eligible brokerage account is connected yet. Connect one that is funded and
        approved for automated options trading so {label} can be activated.
      </Text>
      <Pressable
        onPress={() => void WebBrowser.openBrowserAsync(`${API_BASE}/account/brokerage`)}
        style={[s.actionBtn, { borderColor: color.accent, marginTop: space.lg }]}
      >
        <Text style={[type.body, { color: color.accentText, fontFamily: font.bodyMedium }]}>
          Connect a brokerage on the web
        </Text>
      </Pressable>
    </Card>
  )
}

function SwitchSection({
  bot,
  label,
  otherAgent,
}: {
  bot: AgentBot
  label: string
  otherAgent: LiveAgent | null
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const otherLabel = otherAgent?.label ?? (bot === 'spark' ? 'Flame' : 'Spark')
  const hasOpenTrade = otherAgent?.trade?.active === true

  return (
    <Card style={{ marginTop: space.lg }}>
      <SectionLabel>Switch required</SectionLabel>
      <Text style={[type.body, { color: color.textDim }]}>
        {otherLabel} is already active on your only eligible brokerage account. Activating{' '}
        {label} would mean switching that account from {otherLabel} to {label} — it is not
        something both agents can do on the same account at once.
      </Text>
      {hasOpenTrade ? (
        <Text style={[type.body, { color: color.warn, marginTop: space.md }]}>
          {otherLabel} currently has an open position, so switching is not available until it
          closes.
        </Text>
      ) : null}
      <Pressable
        onPress={() => void WebBrowser.openBrowserAsync(`${API_BASE}/agents/${bot}`)}
        style={[s.actionBtn, { borderColor: color.accent, marginTop: space.lg }]}
      >
        <Text style={[type.body, { color: color.accentText, fontFamily: font.bodyMedium }]}>
          Manage on the web
        </Text>
      </Pressable>
    </Card>
  )
}

type EligibleAccount = { account: BrokerageAccount; connection: BrokerageConnection }

/**
 * Add — the 10.4 design's SINGLE screen (fidelity audit "Add-agent sheet"): pitch,
 * price/trial/due-today/community facts, inline risk + authorization
 * acknowledgements, one "Start free trial" button — not the old 4-step wizard
 * (select account -> ack -> review -> confirm) as four separate screens.
 *
 * Collapsing the STEPS does not collapse the SERVER CONTRACT: this still calls the
 * exact same three endpoints, in the exact same order, with the exact same payload,
 * that the old wizard did —
 *   POST /api/v1/agent-configs          (account_id -> config_id)
 *   POST /api/v1/activations/preview    (config_id -> snapshot + blockers + preview_hash)
 *   POST /api/v1/activations            (config_id + both acks + preview_hash -> activation)
 * — it only changes WHEN the first two fire: automatically, the moment an account is
 * known, instead of waiting for a "Continue" tap, so the facts/blockers are already on
 * screen by the time someone reaches the checkboxes. A real blocker from the preview
 * (an unfunded account, a missing authorization, whatever the server decided) still
 * blocks activation and still routes to the same "Finish setup on the web" handoff —
 * nothing here bypasses that decision or invents a local substitute for it.
 *
 * With exactly one eligible account (the common case) it is auto-selected and no
 * picker ever shows, per spec. With more than one, a compact inline picker — the
 * prototype never defines this case, since its mock data never has two — stays above
 * the single-screen content and re-triggers the same auto-preview-fetch on change.
 */
function ActivationFlow({
  bot,
  label,
  eligibleAccounts,
}: {
  bot: AgentBot
  label: string
  eligibleAccounts: EligibleAccount[]
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()
  const [accountId, setAccountId] = useState<string | null>(
    eligibleAccounts.length === 1 ? eligibleAccounts[0].account.id : null,
  )
  const [riskAck, setRiskAck] = useState(false)
  const [authAck, setAuthAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [configId, setConfigId] = useState<string | null>(null)
  const [preview, setPreview] = useState<ActivationPreviewResponse | null>(null)
  const [activated, setActivated] = useState<ActivationResponse | null>(null)
  const [idemKey] = useState(() => generateIdempotencyKey())
  // Confetti (mobile addendum §2 "Add-agent sheet": "confetti in agent color on
  // success") — fires once, the moment activation succeeds, then clears itself.
  const [showConfetti, setShowConfetti] = useState(false)
  // Which accountId the preview on screen (or in flight) belongs to — guards the
  // auto-fetch effect below from re-firing for the account it already fetched, while
  // still re-firing the moment a multi-account picker changes the selection.
  const previewedFor = useRef<string | null>(null)

  useEffect(() => {
    trackEvent('add_agent_start', { agent: bot })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires once per sheet mount.
  }, [])

  function openWebHandoff() {
    void WebBrowser.openBrowserAsync(`${API_BASE}/agents/${bot}`)
  }

  async function loadPreview(id: string) {
    setBusy(true)
    setFailure(null)
    try {
      const cfg = await api<AgentConfigResponse>('/api/v1/agent-configs', {
        method: 'POST',
        body: { agent_code: bot, broker_account_id: id, config: {} },
      })
      setConfigId(cfg.id)
      const prev = await api<ActivationPreviewResponse>('/api/v1/activations/preview', {
        method: 'POST',
        body: { config_id: cfg.id },
      })
      setPreview(prev)
    } catch (e) {
      setFailure(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  // Auto-fetch the preview the instant an account is known — this is what makes the
  // facts/blockers already be on screen instead of behind a "Continue" tap.
  useEffect(() => {
    if (!accountId || previewedFor.current === accountId) return
    previewedFor.current = accountId
    setConfigId(null)
    setPreview(null)
    void loadPreview(accountId)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadPreview is stable
    // for this component's lifetime; accountId is the only real dependency.
  }, [accountId])

  async function confirmActivate() {
    if (!configId || !preview) return
    setBusy(true)
    setFailure(null)
    try {
      // A 2xx from this call is the only thing allowed to say "activated" — api()
      // throws on anything else, so reaching the next line already proves it.
      const res = await api<ActivationResponse>('/api/v1/activations', {
        method: 'POST',
        headers: { 'Idempotency-Key': idemKey },
        body: {
          config_id: configId,
          risk_acknowledged: true,
          authorization_acknowledged: true,
          preview_hash: preview.preview_hash,
        },
      })
      setActivated(res)
      void globalMutate('/api/live/agents')
      void globalMutate('/api/v1/automation/pause')
      setShowConfetti(true)
      trackEvent('add_agent_complete', { agent: bot })
    } catch (e) {
      setFailure(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (eligibleAccounts.length === 0) {
    return <SetupRequiredSection bot={bot} label={label} />
  }

  if (activated) {
    return (
      <View style={{ marginTop: space.lg }}>
        <Card>
          <View style={s.rowCenter}>
            <Ionicons name="checkmark-circle" size={22} color={color.pos} />
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, marginLeft: space.sm }]}>
              {label} activated
            </Text>
          </View>
          <Text style={[type.body, { color: color.textDim, marginTop: space.md }]}>
            {activated.account_mask ? `Trading on ${maskTail(activated.account_mask)}. ` : ''}
            Your trial is now active.
          </Text>
          <Pressable
            onPress={() => router.replace('/agents')}
            style={[s.primaryBtn, { marginTop: space.lg }]}
          >
            <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>Done</Text>
          </Pressable>
        </Card>
        {showConfetti ? (
          <Confetti colors={[agentAccent(bot), color.pos, color.text]} onDone={() => setShowConfetti(false)} />
        ) : null}
      </View>
    )
  }

  const s1 = preview?.snapshot ?? null
  const hasBlockers = (preview?.blockers.length ?? 0) > 0
  const canSubmit = !!accountId && !!preview && !hasBlockers && riskAck && authAck && !busy

  return (
    <Card style={{ marginTop: space.lg }}>
      <SectionLabel>{`Add ${label}`}</SectionLabel>
      <Text style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
        {AGENT_DESCRIPTION[bot]}
      </Text>

      {eligibleAccounts.length > 1 ? (
        <View style={{ marginTop: space.lg }}>
          <Text style={[type.label, { color: color.muted, marginBottom: space.xs }]}>Account</Text>
          {eligibleAccounts.map(({ account, connection }) => {
            const selected = account.id === accountId
            return (
              <Pressable
                key={account.id}
                onPress={() => setAccountId(account.id)}
                style={[s.selectRow, selected && { borderColor: color.accent }]}
              >
                <Ionicons
                  name={selected ? 'radio-button-on' : 'radio-button-off'}
                  size={20}
                  color={selected ? color.accent : color.muted}
                />
                <Text style={[type.body, { color: color.text, marginLeft: space.sm }]}>
                  {brokerLabel(connection.broker ?? connection.provider)}
                  {account.mask ? `  ${maskTail(account.mask)}` : ''}
                </Text>
              </Pressable>
            )
          })}
        </View>
      ) : null}

      {!preview ? (
        <Text style={[type.body, { color: color.muted, marginTop: space.lg }]}>
          {busy ? 'Loading your trial details…' : 'Choose an account to continue.'}
        </Text>
      ) : (
        <>
          <ReviewRow
            label="Account"
            value={s1?.account_mask ? maskTail(s1.account_mask) : 'Not available'}
          />
          {s1?.plan ? <ReviewRow label="Price" value={`$${s1.plan.price_monthly}/month`} /> : null}
          {s1?.trial ? (
            <ReviewRow label="Free trial" value={`${s1.trial.eligible_days_total} trading days`} />
          ) : null}
          <ReviewRow label="Due today" value="$0.00" />
          <ReviewRow label="Community" value="Already included" />

          {hasBlockers ? (
            <>
              <Text style={[type.label, { color: color.warn, marginTop: space.lg }]}>
                A few things need to be finished before {label} can be activated:
              </Text>
              {preview!.blockers.map((b, i) => (
                <Text key={b.code + i} style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
                  • {b.message}
                </Text>
              ))}
              <Pressable
                onPress={openWebHandoff}
                style={[s.primaryBtn, { backgroundColor: color.accent, marginTop: space.lg }]}
              >
                <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>
                  Finish setup on the web
                </Text>
              </Pressable>
            </>
          ) : (
            <>
              {/* Inline acknowledgements (10.4 design: right on the single screen, not
                  a separate step). */}
              <View style={{ marginTop: space.lg }}>
                <CheckRow
                  checked={riskAck}
                  onToggle={() => setRiskAck((v) => !v)}
                  label="I understand automated options trading involves risk, including the risk of loss."
                />
                <CheckRow
                  checked={authAck}
                  onToggle={() => setAuthAck((v) => !v)}
                  label={`I authorize ${label} to place trades in my selected brokerage account.`}
                />
              </View>

              {failure ? (
                <Text style={[type.body, { color: color.neg, marginTop: space.md }]}>{failure}</Text>
              ) : null}

              <Pressable
                onPress={() => void confirmActivate()}
                disabled={!canSubmit}
                style={[s.primaryBtn, { marginTop: space.lg, opacity: canSubmit ? 1 : 0.5 }]}
              >
                <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>
                  {busy ? 'Starting…' : 'Start free trial'}
                </Text>
              </Pressable>
            </>
          )}
        </>
      )}
    </Card>
  )
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <View style={[s.rowBetween, { marginTop: space.sm }]}>
      <Text style={[type.body, { color: color.textDim }]}>{label}</Text>
      <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>{value}</Text>
    </View>
  )
}

function CheckRow({
  checked,
  onToggle,
  label,
}: {
  checked: boolean
  onToggle: () => void
  label: string
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <Pressable onPress={onToggle} style={s.checkRow} accessibilityRole="checkbox" accessibilityState={{ checked }}>
      <Ionicons
        name={checked ? 'checkbox' : 'square-outline'}
        size={20}
        color={checked ? color.accent : color.muted}
      />
      <Text style={[type.body, { color: color.text, flex: 1, marginLeft: space.sm }]}>{label}</Text>
    </Pressable>
  )
}

/** Non-cryptographic v4-shaped id — good enough for a per-attempt dedupe key. */
function generateIdempotencyKey(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
  kpiGrid: { marginTop: space.md, gap: space.xs },
  kpiRow: { flexDirection: 'row', gap: space.xs },
  kpiTile: {
    flex: 1,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
  },
  barsRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    height: 90,
    marginTop: space.sm,
    gap: 2,
  },
  barCol: { flex: 1, justifyContent: 'center' },
  barHalfTop: { flex: 1, justifyContent: 'flex-end' },
  barHalfBottom: { flex: 1, justifyContent: 'flex-start' },
  barZero: { height: 1, backgroundColor: color.border },
  bar: { width: '100%', borderRadius: 3, minHeight: 2 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomColor: color.border,
    borderBottomWidth: 1,
  },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowCenter: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.md },
  actionBtn: {
    marginTop: space.lg,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  pauseResumeBtn: {
    marginTop: space.lg,
    flexDirection: 'row',
    gap: space.sm,
    borderRadius: radius.pill,
    paddingVertical: space.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryBtn: {
    marginTop: space.lg,
    backgroundColor: color.accent,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  selectRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    padding: space.md,
    marginTop: space.sm,
  },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', marginTop: space.md },
  })
