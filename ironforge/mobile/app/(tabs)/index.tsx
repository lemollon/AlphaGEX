import { useState, useEffect, useMemo, useRef } from 'react'
import { View, Text, ScrollView, RefreshControl, Pressable, StyleSheet, Alert, Platform, Linking, AppState, type AppStateStatus } from 'react-native'
import { useScrollToTop } from '@react-navigation/native'
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
  HomeData,
  LivePerformance,
  BrokerageConnections,
  MembershipResponse,
  MobileMe,
  EntitlementsResponse,
  EmberTradesResponse,
  EmberStatusResponse,
  EmberTradeRow,
  EmberStatusRow,
} from '@/api/types'
import { space, radius, type, font, agentAccent, color as staticColor } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Card, Money, Balance, SectionLabel, Loading, Empty, ErrorState, Button } from '@/components/ui'
import { AppHeader, Mascot } from '@/components/Brand'
import { AccountChart } from '@/components/AccountChart'
import { LiveTradeCard } from '@/components/LiveTradeCard'
import { totalCapital } from '@/live/capital'
import { formatPeriodValue, periodTone, type PeriodTone } from '@/live/period-stats'
import { periodSeries, HERO_PERIOD_LABEL, HERO_PERIOD_TILE_LABEL, type HeroPeriod, type AccountPoint } from '@/live/account-series'
import { greetingForHour } from '@/live/greeting'
import { emberClosedTradesToHistory } from '@/ledger/ember'
import { agentDetailHref, type AgentBot } from '@/agents/routes'
import { AGENT_LABEL, AGENT_BLURB, NEXT_SESSION_SHORT } from '@/agents/copy'
import { pickBanner, bannerActionHref, billingBannerMode } from '@/alerts/banner'
import { manageSubscriptionUrl } from '@/billing/store-policy'
import { isStale, staleLabel } from '@/live/staleness'
import { trackEvent } from '@/analytics/trackEvent'

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
  // Re-tap-tab-to-scroll-to-top (#231).
  const scrollRef = useRef<ScrollView>(null)
  useScrollToTop(scrollRef)
  // "Updated x seconds ago" (#268) — stamped on every successful summary/agents
  // refresh, whichever lands last (the 60s poll OR the faster positions push
  // below). Not tied to any ONE request's loading state: the point is "how long
  // since this screen's numbers were last confirmed fresh", not "is a fetch in
  // flight right now".
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number>(() => Date.now())
  // Ticks once a second ONLY so the "Updated x seconds ago" text (once stale) keeps
  // counting up without a real data refresh — the figure itself never depends on `now`.
  const [now, setNow] = useState<number>(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1_000)
    return () => clearInterval(id)
  }, [])
  const summary = useSWR<LiveSummary>('/api/live/summary', (p: string) => api<LiveSummary>(p), {
    refreshInterval: 60_000,
    onSuccess: () => setLastUpdatedAt(Date.now()),
  })
  const home = useSWR<HomeData>('/api/live/home', (p: string) => api<HomeData>(p), {
    refreshInterval: 60_000,
  })
  const agents = useSWR<LiveAgents>('/api/live/agents', (p: string) => api<LiveAgents>(p), {
    refreshInterval: 60_000,
    onSuccess: () => setLastUpdatedAt(Date.now()),
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
  // Ember ownership (#3177) — /api/live/agents never includes Ember (it has no
  // {bot}_positions table; LIVE_BOTS is spark/flame only), so an Ember owner's
  // row would otherwise be mis-derived as "unowned" from `list` below and show
  // an "Add Ember" tile despite already owning it. Same key the Account tab and
  // the agent sheet already fetch — SWR shares the cache.
  const entitlements = useSWR<EntitlementsResponse>('/api/billing/entitlements', (p: string) =>
    api<EntitlementsResponse>(p),
  )
  const ownsEmber = (entitlements.data?.bots ?? []).includes('ember')
  const emberTrades = useSWR<EmberTradesResponse>(ownsEmber ? '/api/ember/trades' : null, (p: string) =>
    api<EmberTradesResponse>(p),
    { refreshInterval: 60_000, shouldRetryOnError: false },
  )
  const emberStatus = useSWR<EmberStatusResponse>(ownsEmber ? '/api/ember/status' : null, (p: string) =>
    api<EmberStatusResponse>(p),
    { refreshInterval: 60_000, shouldRetryOnError: false },
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
            setLastUpdatedAt(Date.now())
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
        // Refetch summary/positions (#267) BEFORE reconnecting the push stream — a
        // phone backgrounded for minutes (or hours) coming back to a push-only
        // reconnect would leave the screen showing whatever it had when it went to
        // sleep until the next 60s poll happened to land. Firing these now means the
        // numbers are already correct the instant the stream (re)connects, not up to
        // a minute later.
        void summary.mutate()
        void agents.mutate()
        void performance.mutate()
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
    trialEndingSoon: billing.data?.membership?.trial_ending_soon,
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
  // 10.4 design: the top pill shows ONLY market status (Market open / Market closed) —
  // automation-paused is its own, separate signal shown per-agent (the compact row's
  // "Paused" status, the agent sheet's pill) rather than overloading this one element
  // with two unrelated facts. See fidelity audit "Greeting + market pill".
  const pillLabel = data.market.open ? 'Market open' : data.market.label
  const pillTone = data.market.open ? color.pos : color.muted

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
  // Ember is never in `ownedBots` (it is not in `list` — see the ownsEmber note
  // above) — exclude it from "unowned" separately rather than folding it into
  // ownedBots, since ember has none of the LiveAgent shape the rest of this
  // screen's rows read from.
  const unownedBots = ALL_BOTS.filter((b) => !ownedBots.includes(b) && !(b === 'ember' && ownsEmber))

  return (
    <Shell>
      <ScrollView
        ref={scrollRef}
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
              <AccountChart
                series={heroSeries}
                color={heroLineColor}
                onScrub={(point) => {
                  // Fires once per scrub gesture, not once per point under the
                  // finger — setScrub already runs on every frame of the drag.
                  if (point && !scrub) trackEvent('chart_scrub')
                  setScrub(point)
                }}
                periodLabel={HERO_PERIOD_LABEL[heroPeriod]}
              />
            ) : (
              <View style={s.chartEmpty}>
                <Text style={[type.label, { color: color.muted }]}>
                  No history yet for this period.
                </Text>
              </View>
            )}
          </View>

          {/* 2x2 grid, exactly — two fixed rows of two tiles (mobile addendum §2
              Forge tab: "2x2 period tiles"), not a flex-wrap row that happens to
              break after two on most screens. */}
          <View style={s.periodGrid}>
            {([['today', 'week'], ['month', 'life']] as HeroPeriod[][]).map((row, ri) => (
              <View key={ri} style={s.periodRow}>
                {row.map((p) => (
                  <Pressable
                    key={p}
                    onPress={() => {
                      setHeroPeriod(p)
                      trackEvent('period_select', { period: p })
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
            ))}
          </View>

          {/* Always rendered (10.4 design: the capital row is a fixed part of the hero
              card). A multi-account or disconnected customer sees honest "—"
              placeholders here rather than the row disappearing outright — the row's
              PRESENCE is part of the layout contract, even when there is no single
              account to attribute a number to. */}
          <View style={s.capitalRow}>
            <View style={s.capitalCol}>
              <Text style={[type.label, { color: color.muted }]}>Capital available</Text>
              <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, marginTop: 2 }]}>
                {availableCapital != null ? formatDollars(availableCapital) : '—'}
              </Text>
            </View>
            <View style={[s.capitalCol, s.capitalColDivider]}>
              <Text style={[type.label, { color: color.muted }]}>Held in trades</Text>
              <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, marginTop: 2 }]}>
                {heldCapital != null ? formatDollars(heldCapital) : '—'}
              </Text>
            </View>
          </View>
        </Card>

        {list.length > 0 ? (
          <>
            <View style={[s.rowBetween, { marginTop: space.xl, marginBottom: space.md }]}>
              <SectionLabel>Live now</SectionLabel>
              <Text style={[type.label, { color: isStale(lastUpdatedAt, now) ? color.warn : color.muted }]}>
                {isStale(lastUpdatedAt, now) ? staleLabel(lastUpdatedAt, now) : 'Updates every few seconds'}
              </Text>
            </View>
            {liveAgents.length > 0 ? (
              liveAgents.map((a) => (
                <LiveTradeCard
                  key={a.bot}
                  bot={a.bot}
                  label={a.label}
                  accent={agentAccent(a.bot)}
                  trade={a.trade!}
                  onPress={() => router.push(agentDetailHref(a.bot as AgentBot))}
                />
              ))
            ) : (
              // Mobile addendum §2: "Empty state names the next session ('Spark
              // trades at 8:30 AM, Flame at midday')" — no open trade right now,
              // every owned agent's own session instead of a silent gap.
              <Card>
                <Text style={[type.body, { color: color.textDim }]}>
                  No trade open right now. {list
                    .map((a) => `${a.label} trades ${NEXT_SESSION_SHORT[a.bot as AgentBot] ?? 'during market hours'}`)
                    .join(', ')}
                  .
                </Text>
              </Card>
            )}
          </>
        ) : null}

        <View style={[s.rowBetween, { marginTop: space.xl, marginBottom: space.md }]}>
          <SectionLabel>Your agents</SectionLabel>
        </View>

        {agents.isLoading ? (
          <Text style={[type.label, { color: color.muted }]}>Loading your agents…</Text>
        ) : list.length === 0 && !ownsEmber ? (
          <Empty
            title="No agents running"
            detail="Activate an agent and connect a brokerage account to see positions here."
          />
        ) : (
          idleAgents.map((a) => (
            <AgentRow key={a.bot} agent={a} onPress={() => router.push(agentDetailHref(a.bot as AgentBot))} />
          ))
        )}

        {ownsEmber ? (
          <EmberAgentRow
            trades={emberTrades.data?.trades ?? []}
            status={emberStatus.data?.status ?? null}
            onPress={() => router.push(agentDetailHref('ember'))}
          />
        ) : null}

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
 * Ember's "Your agents" row (#3177) — Ember has no LiveAgent (no
 * {bot}_positions table, see the ownsEmber note above `index.tsx`'s SWR
 * calls), so it cannot use AgentTile's state/trade shape. This is a simpler
 * row sized the same as AddAgentRow but for an OWNED agent: avatar, status
 * from /api/ember/status, today's realized P&L from /api/ember/trades
 * (summed over trades CLOSED today CT — Ember carries no live-unrealized
 * figure for an open position, so "today" here is realized-only, unlike
 * Spark/Flame's today_pnl which folds in an open position's unrealized P&L).
 */
function EmberAgentRow({
  trades,
  status,
  onPress,
}: {
  trades: EmberTradeRow[]
  status: EmberStatusRow | null
  onPress: () => void
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const accent = agentAccent('ember')
  const history = emberClosedTradesToHistory(trades)
  const today = todayCtDateString()
  const closedToday = history.filter((t) => t.close_date === today)
  const todayPnl = closedToday.length > 0 ? closedToday.reduce((a, t) => a + t.pnl, 0) : null
  const openCount = Array.isArray(status?.open_positions) ? (status!.open_positions as unknown[]).length : 0
  const statusLabel = status ? (openCount > 0 ? 'Trade open' : 'Waiting') : 'Waiting'

  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={[s.addRow, { borderColor: accent }]}>
      <View style={[s.addAvatar, { backgroundColor: `${accent}22` }]}>
        <Mascot bot="ember" size={28} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[type.body, { color: accent, fontFamily: font.bodyBold }]}>Ember</Text>
        <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>
          {statusLabel}
          {openCount > 0 ? ` · ${openCount} open` : ''}
        </Text>
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <Money value={todayPnl} />
        <Text style={[type.label, { color: color.muted, marginTop: 1 }]}>today</Text>
      </View>
      <Ionicons name="chevron-forward" size={17} color={color.muted} style={{ marginLeft: space.sm }} />
    </Pressable>
  )
}

function todayCtDateString(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '00'
  return `${get('year')}-${get('month')}-${get('day')}`
}

/**
 * Compact "Your agents" row (10.4 design `.arow`) — avatar, name + status, today's
 * P&L, chevron. One owned agent per row, idle (no open trade right now — those get
 * LiveTradeCard above instead). Replaces the old full-size stats Card every agent
 * used to render here regardless of whether it had anything live to show; the same
 * balance/growth/last-10/best-trade figures this row no longer repeats inline are
 * one tap away on the agent sheet (PerformanceSection there already shows them).
 */
function AgentRow({ agent, onPress }: { agent: LiveAgent; onPress: () => void }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const accent = agentAccent(agent.bot)
  const state = agent.state
  // Real server copy when available (CustomerState.headline, e.g. "Waiting for next
  // session") — never a locally re-derived status string guessing at what the server
  // already said authoritatively.
  const status = agent.error === 'state' || !state ? 'Status unavailable' : state.headline
  const todayPnl = agent.trade?.today_result?.pnl ?? null

  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={[s.arow, { borderColor: color.border }]}>
      <Mascot bot={agent.bot} size={38} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={[type.body, { color: accent, fontFamily: font.bodyBold }]} numberOfLines={1}>
          {agent.label}
        </Text>
        <Text style={[type.label, { color: color.muted, marginTop: 2 }]} numberOfLines={1}>
          {status}
        </Text>
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <Money value={todayPnl} />
        <Text style={[type.label, { color: color.muted, marginTop: 1 }]}>today</Text>
      </View>
      <Ionicons name="chevron-forward" size={17} color={color.muted} style={{ marginLeft: space.sm }} />
    </Pressable>
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
  periodGrid: {
    marginTop: space.lg,
    gap: space.xs,
  },
  periodRow: {
    flexDirection: 'row',
    gap: space.xs,
  },
  periodTile: {
    flex: 1,
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
  // Compact idle-agent row (10.4 design `.arow`) — same shape as addRow (avatar +
  // name column + trailing content), kept as its own style rather than reusing
  // addRow directly since the two carry different border-colour semantics
  // (addRow is themed per-agent, arow is a plain divider row).
  arow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderBottomWidth: 1,
    paddingVertical: space.md,
  },
  })
