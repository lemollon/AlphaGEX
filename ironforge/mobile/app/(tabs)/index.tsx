import { useState, useEffect, useMemo } from 'react'
import { View, Text, ScrollView, RefreshControl, Pressable, StyleSheet, Alert, Platform, Linking, AppState, type AppStateStatus } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { useRouter } from 'expo-router'
import * as WebBrowser from 'expo-web-browser'
import { api, ApiError } from '@/api/client'
import { streamPositions } from '@/api/positionsStream'
import { mergeAgentsTrade } from '@/live/positions-merge'
import type {
  LiveSummary,
  LiveAgent,
  LiveAgents,
  LiveOpenPosition,
  HomeData,
  LivePerformance,
  BrokerageConnections,
  MembershipResponse,
  MobileMe,
  AutomationPauseResponse,
} from '@/api/types'
import { space, radius, type, font, agentAccent, color as staticColor } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Card, Money, Balance, SectionLabel, Loading, Empty, ErrorState, Button } from '@/components/ui'
import { StatRow } from '@/components/StatRow'
import { AppHeader, Mascot } from '@/components/Brand'
import { PnlChart } from '@/components/PnlChart'
import { AccountChart } from '@/components/AccountChart'
import { brokerLabel, maskTail, soleConnection } from '@/api/brokerage'
import { totalCapital } from '@/live/capital'
import { agentStatItems } from '@/live/card-stats'
import { formatPeriodValue, periodTone, type PeriodTone } from '@/live/period-stats'
import { periodSeries, HERO_PERIOD_LABEL, HERO_PERIOD_TILE_LABEL, type HeroPeriod, type AccountPoint } from '@/live/account-series'
import { greetingForHour } from '@/live/greeting'
import { agentDetailHref, type AgentBot } from '@/agents/routes'
import { AGENT_LABEL, AGENT_BLURB } from '@/agents/copy'
import {
  deriveLifecycleNodes,
  lifecycleFillFraction,
  formatLocalClock,
  minutesSince,
  formatElapsedMinutes,
  formatTargetStopCaption,
  formatAutoCloseCaption,
  formatSettleAtCloseCaption,
  isSettleAtExpiryBot,
} from '@/live/lifecycle'
import { pickBanner, bannerActionHref, billingBannerMode } from '@/alerts/banner'
import { manageSubscriptionUrl } from '@/billing/store-policy'

const ALL_BOTS: AgentBot[] = ['spark', 'flame', 'ember']

/**
 * Forge — UX-002 (APP-011/012/013/016), UX-003 (APP-051) and the 10.4 redesign's
 * Forge tab (handoff/ironforge-10.4-addendum.md §2): greeting + market pill, a
 * hero card (account value, period P&L, a scrubbable chart, 2x2 period tiles,
 * capital row), a "Live now" strip for open trades, and "Your agents" rows for
 * everything else (owned, status-only; unowned, an "Add" row).
 *
 * Agents come from /api/live/agents, which fans out over every bot the viewer owns and
 * returns each one's own state, account and trade — /api/live/summary still covers the
 * viewer-level pieces (period row, market clock), and /api/live/performance adds the
 * hero chart's Week/Month/Lifetime series from real closed-trade equity (see
 * live/account-series.ts for exactly how, and why it is a calendar- not trading-day
 * window). Every number on this screen traces to one of those endpoints, or to
 * /api/auth/mobile/me (first name) and /api/v1/automation/pause (the Paused pill) —
 * nothing here is invented, unlike the app.html prototype's seeded example data.
 */
export default function ForgeScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
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
  // Week/Month/Lifetime hero-chart series — a slower-moving number than the live
  // poll above (it only changes when a trade closes), so a long refresh interval
  // is honest rather than wasteful.
  const performance = useSWR<LivePerformance>('/api/live/performance', (p: string) =>
    api<LivePerformance>(p),
    { refreshInterval: 300_000 },
  )
  const conns = useSWR<BrokerageConnections>('/api/brokerage/connections', (p: string) =>
    api<BrokerageConnections>(p),
  )
  // First name for the greeting — same key the Account tab already fetches, so this
  // costs nothing extra there (SWR shares the cache).
  const me = useSWR<MobileMe>('/api/auth/mobile/me', (p: string) => api<MobileMe>(p))
  // Whether every owned agent is paused — the market pill's "Paused" state, same
  // activations the Agents overview and per-agent Pause switch already read.
  const pause = useSWR<AutomationPauseResponse>('/api/v1/automation/pause', (p: string) =>
    api<AutomationPauseResponse>(p),
  )

  // Sub-5s positions/P&L push (dev-handoff /ws/positions contract) — additive on
  // top of the 60s /api/live/agents poll above, never a replacement for it: state,
  // account and stats still come from that poll, this only pushes `trade` (open
  // positions + unrealized P&L) into the same cache faster. Foreground-only —
  // paused the instant the app backgrounds, reconnected on resume — and the 60s
  // poll keeps the screen live on its own if this never connects at all (no
  // EventSource in React Native; see api/positionsStream.ts for the pure-JS
  // `expo/fetch` reader, same pattern api/sparky.ts already uses for Ask Sparky).
  useEffect(() => {
    let stopped = false
    let controller: AbortController | null = null
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let retryCount = 0

    const disconnect = () => {
      controller?.abort()
      controller = null
      if (retryTimer) clearTimeout(retryTimer)
      retryTimer = undefined
    }

    const connect = () => {
      if (stopped || AppState.currentState !== 'active') return
      controller = new AbortController()
      streamPositions(
        {
          onPositions: (pushed) => {
            retryCount = 0
            void agents.mutate(
              (current) =>
                current ? { ...current, agents: mergeAgentsTrade(current.agents, pushed) } : current,
              { revalidate: false },
            )
          },
        },
        controller.signal,
      )
        .catch(() => {
          // The 60s poll above keeps the screen live either way — this only
          // decides how soon to try the fast path again.
        })
        .finally(() => {
          if (stopped || AppState.currentState !== 'active') return
          const delay = Math.min(30_000, 1_000 * 2 ** retryCount)
          retryCount += 1
          retryTimer = setTimeout(connect, delay)
        })
    }

    connect()
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (next === 'active') {
        disconnect()
        retryCount = 0
        connect()
      } else {
        disconnect()
      }
    })

    return () => {
      stopped = true
      sub.remove()
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- agents.mutate is a
    // stable reference for this key for the lifetime of the screen (SWR).
  }, [])

  // Same key/fetcher as the Account tab's membership card — SWR shares the cache, so
  // this costs nothing extra there. Only needed to decide what the payment-due banner
  // does on iOS (Apple IAP handoff §4): never open Stripe, and only offer Apple's own
  // subscription settings when the membership is actually Apple-provisioned.
  const billing = useSWR<MembershipResponse>('/api/billing/membership', (p: string) =>
    api<MembershipResponse>(p),
  )
  // Only 'caution' may be dismissed (APP-016) — everything more urgent persists, so this
  // is never checked for those severities.
  const [dismissedCaution, setDismissedCaution] = useState(false)
  const platform = Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : 'web'

  // Hero chart state — which period is charted, and the point under a finger while
  // dragging (mobile addendum §2 step 3: "tap a period tile to chart it, drag to
  // explore"). Scrubbing never mutates server data, just what the hero reads.
  const [heroPeriod, setHeroPeriod] = useState<HeroPeriod>('today')
  const [scrub, setScrub] = useState<AccountPoint | null>(null)

  const refreshing = summary.isValidating || agents.isValidating
  const reload = () => {
    summary.mutate()
    home.mutate()
    agents.mutate()
    performance.mutate()
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
    // Distinguish "never finished billing" (nothing else to do but resume enrollment)
    // from "paid but hasn't connected a broker/activated yet" (the generic empty state
    // is correct — Account tab's "Connect Another Brokerage" is the next step). Without
    // this, a customer who dropped off mid-signup sees a dead-end screen with no path
    // back into /enroll/*, and the ONLY way back in was signing out and back in again
    // (Leron, 2026-10-04 — found by actually walking a fresh signup through).
    const neverBilled = billing.data?.configured && !billing.data?.membership
    return (
      <Shell>
        {neverBilled ? (
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl }}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              Finish setting up your account
            </Text>
            <Text style={[type.body, { color: color.textDim, marginTop: space.sm, textAlign: 'center' }]}>
              Your signup never finished — pick up right where you left off.
            </Text>
            <View style={{ marginTop: space.lg, alignSelf: 'stretch' }}>
              <Button label="Continue setup" onPress={() => router.push('/enroll/plan')} />
            </View>
          </View>
        ) : (
          <Empty
            title="No account connected yet"
            detail="Once your agent is activated and a brokerage account is linked, your capital and positions appear here."
          />
        )}
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
  // The payment-due banner (Banner.action.target === 'billing') is the ONLY banner that
  // ever opens the Stripe portal — billingBannerMode guards it the same way the
  // Account tab's "Manage Membership and Billing" control is guarded (Apple IAP
  // handoff §4, follow-up to PR #2992): Apple rejected exposing that surface on iOS at
  // all, even restricted, so it must never render there, banner included.
  const billingMode = billingBannerMode(banner, platform, billing.data?.membership?.provider)
  const showBanner =
    banner && billingMode !== 'suppressed' && billingMode !== 'apple-manage' &&
    !(banner.severity === 'caution' && dismissedCaution)
  const showManageSubscriptionBanner = billingMode === 'apple-manage'

  async function onBannerPress() {
    if (!banner?.action) return
    if (banner.action.target === 'billing') {
      // Same call the Account tab's "Manage Membership and Billing" makes — the payment
      // -due banner opens the portal directly rather than making the customer find the
      // button a second time. Unreachable on iOS: billingBannerMode never returns
      // 'stripe' there, see showBanner above.
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

  async function onManageSubscriptionPress() {
    const url = manageSubscriptionUrl(billing.data?.membership?.provider ?? null, platform)
    if (url) await Linking.openURL(url).catch(() => {})
  }

  // Greeting + market pill (mobile addendum §2 Forge tab step 1).
  const firstName = me.data?.customer?.firstName
  const greeting = firstName ? `${greetingForHour(new Date().getHours())}, ${firstName}` : greetingForHour(new Date().getHours())
  const ownedBots = list.map((a) => a.bot)
  const allPaused =
    ownedBots.length > 0 &&
    ownedBots.every((bot) => pause.data?.activations.find((a) => a.agent === bot)?.paused)
  const pillLabel = allPaused ? 'Paused' : data.market.open ? 'Market open' : data.market.label
  const pillTone = allPaused ? color.warn : data.market.open ? color.pos : color.muted

  // Hero chart + period figures — same four numbers the period tiles show.
  const periodValues: Record<HeroPeriod, number | null> = {
    today: data.account.today_pnl,
    week: home.data?.wealth.weekly_income ?? null,
    month: home.data?.wealth.monthly_income ?? null,
    life: home.data?.wealth.lifetime_income ?? null,
  }
  const heroSeries = periodSeries(heroPeriod, data.intraday, performance.data?.equity_curve)
  const heroValue = scrub ? scrub.v : capital.value
  const heroChangeValue = periodValues[heroPeriod]
  const heroLineColor = (() => {
    const last = heroSeries[heroSeries.length - 1]
    const first = heroSeries[0]
    if (!last || !first) return color.pos
    return last.v >= first.v ? color.pos : color.neg
  })()

  // Capital available / held — only from a REAL buying-power figure, and only when
  // there is exactly one connected brokerage account to attribute it to (same "exactly
  // one, or nothing" rule soleConnection uses for the broker label — two accounts would
  // mean guessing whose buying power this is). "Held" is account value minus that
  // available balance — arithmetic on two real numbers, not a fabricated third one.
  const soleAccounts = conns.data?.connections?.length === 1 ? conns.data.connections[0].accounts : []
  const soleAccount = soleAccounts.length === 1 ? soleAccounts[0] : null
  const availableCapital = soleAccount?.buying_power_cents != null ? soleAccount.buying_power_cents / 100 : null
  const heldCapital = availableCapital != null && capital.value != null ? capital.value - availableCapital : null

  const liveAgents = list.filter((a) => a.trade?.active)
  const idleAgents = list.filter((a) => !a.trade?.active)
  const unownedBots = ALL_BOTS.filter((b) => !ownedBots.includes(b))

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
        ) : showManageSubscriptionBanner ? (
          <AlertBanner
            banner={{
              severity: 'payment',
              color: staticColor.warn,
              text: 'Your payment is past due. Manage your subscription in the App Store.',
              action: { label: 'Manage subscription', target: 'billing' },
              dismissible: false,
            }}
            onPress={onManageSubscriptionPress}
            onDismiss={() => {}}
          />
        ) : null}

        <View style={s.titleRow}>
          <View>
            <Text style={[type.label, { color: color.muted }]}>{greeting}</Text>
            <Text style={[type.title, { color: color.text, fontFamily: font.display, marginTop: 2 }]}>
              Forge
            </Text>
          </View>
          <View style={[s.marketPill, { backgroundColor: `${pillTone}22` }]}>
            <View style={[s.dot, { backgroundColor: pillTone }]} />
            <Text style={[type.label, { color: pillTone, fontFamily: font.bodyMedium }]}>{pillLabel}</Text>
          </View>
        </View>

        <Card style={{ marginTop: space.lg }}>
          <Text style={[type.label, { color: color.muted }]} numberOfLines={1}>
            {scrub ? formatPointStamp(scrub.t, heroPeriod) : 'Account value'}
          </Text>
          <Balance value={heroValue} />
          <Text style={[type.body, { marginTop: space.xs, fontFamily: font.bodyMedium }]}>
            {scrub ? (
              <Text style={{ color: color.muted }}>Drag to explore</Text>
            ) : (
              <>
                <Text style={{ color: periodToneColor(periodTone(heroChangeValue), color) }}>
                  {formatPeriodValue(heroChangeValue)}
                </Text>
                <Text style={{ color: color.muted }}> {HERO_PERIOD_LABEL[heroPeriod]}</Text>
              </>
            )}
          </Text>

          <View style={{ marginTop: space.md }}>
            {heroSeries.length >= 2 ? (
              <AccountChart series={heroSeries} color={heroLineColor} onScrub={setScrub} />
            ) : (
              <View style={s.chartEmpty}>
                <Text style={[type.label, { color: color.muted }]}>
                  No history yet for this period.
                </Text>
              </View>
            )}
          </View>

          <View style={s.periodTiles}>
            {(['today', 'week', 'month', 'life'] as HeroPeriod[]).map((p) => (
              <Pressable
                key={p}
                onPress={() => {
                  setHeroPeriod(p)
                  setScrub(null)
                }}
                accessibilityRole="button"
                accessibilityState={{ selected: heroPeriod === p }}
                style={[s.periodTile, heroPeriod === p && { backgroundColor: color.bg, borderColor: color.text }]}
              >
                <Text style={[type.label, { color: color.muted }]}>{HERO_PERIOD_TILE_LABEL[p]}</Text>
                <Text
                  style={[
                    s.periodTileValue,
                    { color: periodToneColor(periodTone(periodValues[p]), color) },
                  ]}
                  numberOfLines={1}
                >
                  {formatPeriodValue(periodValues[p])}
                </Text>
              </Pressable>
            ))}
          </View>

          {availableCapital != null ? (
            <View style={s.capitalRow}>
              <View style={s.capitalCol}>
                <Text style={[type.label, { color: color.muted }]}>Capital available</Text>
                <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, marginTop: 2 }]}>
                  {formatDollars(availableCapital)}
                </Text>
              </View>
              <View style={[s.capitalCol, s.capitalColDivider]}>
                <Text style={[type.label, { color: color.muted }]}>Held in trades</Text>
                <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, marginTop: 2 }]}>
                  {heldCapital != null ? formatDollars(heldCapital) : '—'}
                </Text>
              </View>
            </View>
          ) : null}
        </Card>

        {liveAgents.length > 0 ? (
          <>
            <View style={[s.rowBetween, { marginTop: space.xl, marginBottom: space.md }]}>
              <SectionLabel>Live now</SectionLabel>
              <Text style={[type.label, { color: color.muted }]}>Updates every few seconds</Text>
            </View>
            {liveAgents.map((a) => (
              <AgentTile
                key={a.bot}
                agent={a}
                connection={list.length === 1 ? soleConnection(conns.data) : null}
              />
            ))}
          </>
        ) : null}

        <View style={[s.rowBetween, { marginTop: space.xl, marginBottom: space.md }]}>
          <SectionLabel>Your agents</SectionLabel>
        </View>

        {agents.isLoading ? (
          <Text style={[type.label, { color: color.muted }]}>Loading your agents…</Text>
        ) : list.length === 0 ? (
          <Empty
            title="No agents running"
            detail="Activate an agent and connect a brokerage account to see positions here."
          />
        ) : idleAgents.length === 0 ? null : (
          idleAgents.map((a) => (
            <AgentTile
              key={a.bot}
              agent={a}
              connection={list.length === 1 ? soleConnection(conns.data) : null}
            />
          ))
        )}

        {unownedBots.map((bot) => (
          <AddAgentRow key={bot} bot={bot} onPress={() => router.push(agentDetailHref(bot))} />
        ))}

        <Text style={s.disclosure}>
          Options involve risk, including loss of money invested.
        </Text>
      </ScrollView>
    </Shell>
  )
}

/** "{Today/Past week/...} · {date}" — the hero label while scrubbing. */
function formatPointStamp(t: number, period: HeroPeriod): string {
  const d = new Date(t)
  if (period === 'today') {
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  }
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatDollars(v: number): string {
  return `$${Math.round(v).toLocaleString('en-US')}`
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
  const { colors: color, resolveTone } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  // banner.color is a DARK-canonical hex from alerts/banner.ts (a pure, tested
  // function) — translate it to the active scheme here, at the render site.
  const tone = resolveTone(banner.color)
  return (
    <Pressable
      onPress={banner.action ? onPress : undefined}
      accessibilityRole={banner.action ? 'button' : undefined}
      style={[s.banner, { borderColor: tone, backgroundColor: `${tone}18` }]}
    >
      <Ionicons name="alert-circle" size={18} color={tone} />
      <Text style={[type.body, { color: color.text, flex: 1, marginLeft: space.sm }]}>
        {banner.text}
      </Text>
      {banner.action ? (
        <Text style={[type.label, { color: tone, fontFamily: font.bodyMedium }]}>
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

function periodToneColor(tone: PeriodTone, color: ColorTokens): string {
  const map: Record<PeriodTone, string> = {
    pos: color.pos,
    neg: color.neg,
    zero: color.muted,
    na: color.textDim,
  }
  return map[tone]
}

/** "Add {Agent}" row for a bot this viewer doesn't own yet (mobile addendum §2
 *  Forge tab step 7: "unowned-agent rows → add sheet"). Links to the existing
 *  /agents/{bot} screen rather than a bottom sheet — that screen already owns the
 *  real entitlement/eligibility/pricing flow (see src/agents/eligibility.ts),
 *  and a second, Forge-local copy of that logic (with a hardcoded "$50/mo" tag,
 *  the way the app.html prototype does it) would be guessing at a billing-
 *  sensitive number this screen has no real source for. */
function AddAgentRow({ bot, onPress }: { bot: AgentBot; onPress: () => void }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const accent = agentAccent(bot)
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={[s.addRow, { borderColor: color.border }]}>
      <View style={[s.addAvatar, { backgroundColor: `${accent}22` }]}>
        <Mascot bot={bot} size={28} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
          {`Add ${AGENT_LABEL[bot]}`}
        </Text>
        <Text style={[type.label, { color: color.muted, marginTop: 2 }]} numberOfLines={1}>
          {AGENT_BLURB[bot]}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={17} color={color.muted} />
    </Pressable>
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
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
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
                {connection.mask ? `  ${maskTail(connection.mask)}` : ''}
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

      {/* Capital (live balance, "Started: $X" sub-line) / Growth / Last 10 / Best Trade —
          LIFETIME, no filter (handoff/ledger-kpis.md PART 2). `agent.stats` is null only
          when the server couldn't compute it (both source queries must succeed);
          agentStatItems turns that into an honest "—" per column rather than throwing or
          hiding the row. No separate per-tile loading state: this tile does not mount
          until agents.data has already loaded (see the agents.isLoading gate above it). */}
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
          bot={agent.bot}
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
                One P&L row PER TRADE, and there can be more than one: SPARK swings, so
                a leg opened yesterday is still open beside today's. The scalar fields
                only ever describe positions[0], which is exactly how the web page once
                hid a live position holding real money.

                No dot rail under the row any more — the LifecycleLine above already
                walks Opened → Monitoring → Target/Stop → Auto Close for this position,
                and a second copy of the same four steps read as duplicate (UAT, 9/8).
                The row keeps what the lifecycle line does not show: the trade's own
                unrealized P&L, and the chart when the toggle is on.

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
                <View style={s.rowBetween}>
                  <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
                    Open position
                  </Text>
                  <Money value={trade.unrealized_pnl} size="title" />
                </View>
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
 * This is the ONLY step rail on the card. The older per-trade Stepper (which read
 * CustomerState.timeline_step and showed "Target / Stop" as current once a position
 * was being monitored) was removed 9/8 after UAT flagged it as a duplicate of this
 * line. Monitoring itself is the current node for as long as the position is open,
 * since Target/Stop and Auto Close describe outcomes the backend cannot yet
 * detect live.
 */
function LifecycleLine({
  accent,
  bot,
  openedAt,
  targetDollars,
  stopDollars,
  autoCloseAt,
}: {
  accent: string
  bot: string
  openedAt: string | null
  targetDollars: number | null
  stopDollars: number | null
  autoCloseAt: string | null
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  // Forces a re-render once a minute so the Monitoring caption ("37 min")
  // ticks forward on its own — the position doesn't otherwise change shape
  // between 60s agent polls.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  const settleAtExpiry = isSettleAtExpiryBot(bot)
  const nodes = deriveLifecycleNodes(false, bot)
  const fillPct = lifecycleFillFraction(nodes) * 75 // track spans the middle 75% of the row
  // FLAME/SPARK hold every position to settlement — no stop, no early auto-close —
  // so their last two captions say that plainly rather than reusing the generic
  // "$target / −$stop" and "by 2:45 PM" copy that describes a different strategy.
  const captions = [
    formatLocalClock(openedAt) ?? '—',
    openedAt ? formatElapsedMinutes(minutesSince(openedAt)) : '—',
    settleAtExpiry ? 'Hold to close' : formatTargetStopCaption(targetDollars, stopDollars),
    settleAtExpiry ? formatSettleAtCloseCaption(autoCloseAt) : formatAutoCloseCaption(autoCloseAt),
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
 * One open trade: title, its own P&L, and — when the chart toggle is on — its own
 * intraday chart. UX-002 also drew a step rail here; that went 9/8 because the
 * LifecycleLine above the divider already shows the same four steps for the position.
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
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  // Each trade draws its OWN series. Draws nothing under the row when this position
  // has no marks yet — a position opened before the scanner started recording them
  // has nothing to plot, and an empty chart frame says less than the P&L figure does.
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
      ) : null}
    </View>
  )
}

/** timeline_step is 0..4; there are four labels, so a step of 4 rests on the last.
 *  Only the chart's status caption reads these now — the per-trade dot rail that
 *  drew them is gone (see LifecycleLine). */
const STEP_LABELS: readonly string[] = ['Opened', 'Monitoring', 'Target / Stop', 'Auto Close']

function stepLabel(step: number | null): string {
  const i = Math.min(Math.max(step ?? 0, 0), STEP_LABELS.length - 1)
  return STEP_LABELS[i]
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

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md,
    marginBottom: space.lg,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  marketPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    marginTop: 2,
  },
  chartEmpty: {
    height: 150,
    alignItems: 'center',
    justifyContent: 'center',
  },
  periodTiles: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.xs,
    marginTop: space.lg,
  },
  periodTile: {
    flexBasis: '48%',
    flexGrow: 1,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
  },
  periodTileValue: {
    fontSize: 16,
    lineHeight: 20,
    fontFamily: font.bodyBold,
    fontVariant: ['tabular-nums'],
    marginTop: 2,
  },
  capitalRow: {
    flexDirection: 'row',
    marginTop: space.lg,
    borderTopColor: color.border,
    borderTopWidth: 1,
    paddingTop: space.lg,
  },
  capitalCol: { flex: 1 },
  capitalColDivider: { borderLeftWidth: 1, borderLeftColor: color.border, paddingLeft: space.lg },
  disclosure: {
    ...type.label,
    color: color.muted,
    textAlign: 'center',
    marginTop: space.xl,
    paddingHorizontal: space.md,
  },
  addRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.md,
    marginBottom: space.md,
  },
  addAvatar: {
    width: 38,
    height: 38,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
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
