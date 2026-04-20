'use client'

import React, { useState, useCallback, useEffect, useRef } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { getCTNow, getCTMinutes } from '@/lib/pt-tiers'
import StatusCard from './StatusCard'
import PerformanceCard from './PerformanceCard'
import EquityChart, { type Period } from './EquityChart'
import PositionTable from './PositionTable'
import TradeHistory from './TradeHistory'
import LogsTable from './LogsTable'
import PTTimeline from './PTTimeline'
import PdtCard from './PdtCard'
import PdtTabContent from './PdtTabContent'
import SignalsTable from './SignalsTable'
import ProductionTab from './dashboard/ProductionTab'

/* Error boundary to catch component crashes without breaking the whole page */
class ComponentErrorBoundary extends React.Component<
  { fallback: string; children: React.ReactNode },
  { hasError: boolean; error: string | null }
> {
  constructor(props: { fallback: string; children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          {this.props.fallback}: {this.state.error}
        </div>
      )
    }
    return this.props.children
  }
}

function TabError({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
      <p className="text-red-400 text-sm">Failed to load data: {message}</p>
    </div>
  )
}

function TabLoading() {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
      <p className="text-forge-muted text-sm animate-pulse">Loading...</p>
    </div>
  )
}

const ALL_TABS = ['Equity Curve', 'Production', 'Broker Equity', 'Performance', 'Positions', 'Trade History', 'Signals', 'Logs', 'PDT', 'Reconcile'] as const
type Tab = (typeof ALL_TABS)[number]

/** Only SPARK has sandbox/production accounts. FLAME and INFERNO are paper-only. */
const ACCOUNT_BOTS = new Set(['spark'])

/** Tabs that only make sense for bots with broker accounts */
const ACCOUNT_ONLY_TABS = new Set<Tab>(['Production', 'Broker Equity', 'Reconcile'])

/**
 * Bots gated by PDT. Empty for now: SPARK trades on a > $25K production
 * account (Iron Viper) which is exempt from FINRA Rule 4210's day-trade
 * cap, and FLAME / INFERNO are paper-only. Kept as a Set so re-adding a
 * bot later is a one-line change.
 */
const PDT_BOTS = new Set<string>()

/** View mode: Paper (sandbox combined) or Live (production) */
type ViewMode = 'paper' | 'live'

const STATUS_REFRESH = 15_000   // Status refreshes every 15s
const DATA_REFRESH = 30_000     // Tables/logs refresh every 30s
const LIVE_REFRESH = 10_000     // Live position monitor refreshes every 10s

export default function BotDashboard({
  bot,
  accent,
}: {
  bot: 'flame' | 'spark' | 'inferno'
  accent: 'amber' | 'blue' | 'red'
}) {
  const hasAccounts = ACCOUNT_BOTS.has(bot)
  const [tab, setTab] = useState<Tab>('Equity Curve')
  const [equityPeriod, setEquityPeriod] = useState<Period>('intraday')
  const [viewMode, setViewMode] = useState<ViewMode>('paper')

  // Query string fragment for account_type filtering (appended to all API calls)
  // Paper = sandbox combined (all sandbox accounts), Live = production only
  const buildPq = () => {
    if (!hasAccounts) return ''
    return `account_type=${viewMode === 'live' ? 'production' : 'sandbox'}`
  }
  const pq = buildPq()
  const pqSep = (url: string) => url.includes('?') ? `${url}&${pq}` : `${url}?${pq}`
  const withPerson = (url: string) => pq ? pqSep(url) : url

  /* ---- Status (always fetched) ---- */
  const { data: status, error: statusErr } = useSWR(
    withPerson(`/api/${bot}/status`),
    fetcher,
    { refreshInterval: STATUS_REFRESH },
  )

  /* ---- Derive production person for Broker Equity tab ---- */
  const [brokerPerson, setBrokerPerson] = useState<string | null>(null)
  useEffect(() => {
    if (brokerPerson) return
    const prodAccts = (status?.sandbox_accounts || []).filter((a: any) => a.account_type === 'production')
    if (prodAccts.length > 0) setBrokerPerson(prodAccts[0].name)
  }, [status, brokerPerson])

  /* ---- Config (always fetched, slow refresh) ----
     Config is siloed by account_type so Paper edits don't bleed into Live
     (and vice versa). Fetch the scope that matches the current view mode. */
  const configAccountType = viewMode === 'live' ? 'production' : 'sandbox'
  const { data: config } = useSWR(
    `/api/${bot}/config?account_type=${configAccountType}`,
    fetcher,
    { refreshInterval: 60_000 },
  )

  /* ---- Equity curve (historical, fetched based on period) ---- */
  const historicalPeriod = equityPeriod === 'intraday' ? 'all' : equityPeriod
  const { data: equity } = useSWR(
    tab === 'Equity Curve' ? withPerson(`/api/${bot}/equity-curve?period=${historicalPeriod}`) : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Intraday snapshots ---- */
  const { data: intraday } = useSWR(
    tab === 'Equity Curve' && equityPeriod === 'intraday'
      ? withPerson(`/api/${bot}/equity-curve/intraday`)
      : null,
    fetcher,
    { refreshInterval: LIVE_REFRESH },
  )

  /* ---- Broker (production) equity curve — production bot only ---- */
  const [brokerPeriod, setBrokerPeriod] = useState<'intraday' | '1d' | '1w' | '1m' | '3m' | 'all'>('intraday')
  const { data: brokerEquity } = useSWR(
    hasAccounts && tab === 'Broker Equity' && brokerPerson
      ? `/api/accounts/production/equity-curve?person=${encodeURIComponent(brokerPerson)}&mode=${brokerPeriod === 'intraday' ? 'intraday' : 'historical'}&period=${brokerPeriod === 'intraday' ? '1d' : brokerPeriod}`
      : null,
    fetcher,
    { refreshInterval: LIVE_REFRESH },
  )

  /* ---- Position monitor (live MTM) — always fetched so StatusCard unrealized P&L is accurate ---- */
  const { data: positionMonitor, error: posMonitorErr } = useSWR(
    withPerson(`/api/${bot}/position-monitor`),
    fetcher,
    { refreshInterval: LIVE_REFRESH },
  )

  /* ---- Fallback positions (simple DB query, no Tradier MTM) — used when position-monitor fails ---- */
  const { data: fallbackPositions } = useSWR(
    posMonitorErr && tab === 'Positions' ? withPerson(`/api/${bot}/positions`) : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Position detail (per-leg quotes, sandbox P&L, metrics) ---- */
  const { data: positionDetail } = useSWR(
    tab === 'Positions' ? withPerson(`/api/${bot}/position-detail`) : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Performance ---- */
  const { data: perf, error: perfErr } = useSWR(
    tab === 'Performance' ? withPerson(`/api/${bot}/performance`) : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Trade history ---- */
  const { data: trades, error: tradesErr } = useSWR(
    tab === 'Trade History' ? withPerson(`/api/${bot}/trades`) : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Logs ---- */
  const { data: logs, error: logsErr } = useSWR(
    tab === 'Logs' ? withPerson(`/api/${bot}/logs`) : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Signals ---- */
  const { data: signalsData, error: signalsErr } = useSWR(
    tab === 'Signals' ? withPerson(`/api/${bot}/signals`) : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Pending orders (production bot only — lightweight, always fetched with status) ---- */
  const { data: pendingData } = useSWR(
    hasAccounts ? withPerson(`/api/${bot}/pending-orders`) : null,
    fetcher,
    { refreshInterval: STATUS_REFRESH },
  )

  /* ---- Production pause state (production bot only, polled every 15s so
         the banner flips quickly after a toggle) ---- */
  const { data: pauseState, mutate: mutatePause } = useSWR<{
    paused: boolean
    paused_at: string | null
    paused_by: string | null
    paused_reason: string | null
  }>(
    hasAccounts ? `/api/${bot}/production-pause` : null,
    fetcher,
    { refreshInterval: STATUS_REFRESH },
  )
  const [pauseBusy, setPauseBusy] = useState(false)
  const [pauseErr, setPauseErr] = useState<string | null>(null)
  async function togglePause(next: boolean) {
    setPauseBusy(true)
    setPauseErr(null)
    try {
      const body: Record<string, unknown> = { paused: next, by: 'dashboard' }
      if (next) {
        const reason = typeof window !== 'undefined'
          ? window.prompt('Reason for pausing production trading (optional):') || 'operator paused'
          : 'operator paused'
        body.reason = reason
      }
      const res = await fetch(`/api/${bot}/production-pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await mutatePause()
    } catch (e: unknown) {
      setPauseErr(e instanceof Error ? e.message : String(e))
    } finally {
      setPauseBusy(false)
    }
  }

  /* ---- PDT ---- */
  const { data: pdtData, error: pdtErr, mutate: mutatePdt } = useSWR(
    tab === 'PDT' && PDT_BOTS.has(bot) ? withPerson(`/api/${bot}/pdt`) : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Reconcile (production bot only) ---- */
  const { data: reconData, error: reconErr } = useSWR(
    tab === 'Reconcile' && hasAccounts ? withPerson(`/api/${bot}/reconcile`) : null,
    fetcher,
    { refreshInterval: 60_000 },
  )

  const onPeriodChange = useCallback((p: Period) => setEquityPeriod(p), [])

  /* ---- Auto EOD close: when past 2:45 PM CT and positions still open, trigger close ---- */
  const eodCloseTriggered = useRef(false)
  const [eodCloseResult, setEodCloseResult] = useState<{ closed: number; total_pnl: number } | null>(null)

  useEffect(() => {
    // Only trigger once per page load, and only when we have position data
    if (eodCloseTriggered.current) return
    const positions = positionMonitor?.positions
    if (!positions || positions.length === 0) return

    const ctMins = getCTMinutes(getCTNow())
    if (ctMins < 885) return // Not past 2:45 PM CT

    eodCloseTriggered.current = true

    fetch(`/api/${bot}/eod-close`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) return null
        return res.json()
      })
      .then((data) => {
        if (data && data.closed > 0) {
          setEodCloseResult({ closed: data.closed, total_pnl: data.total_realized_pnl })
        }
      })
      .catch(() => {
        // Non-fatal — scanner will catch it on next cycle
      })
  }, [positionMonitor, bot])

  if (statusErr) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-400">
          Failed to load {bot.toUpperCase()} status: {statusErr.message}
        </p>
      </div>
    )
  }

  /* ---- Stale scanner banner (removed — not needed) ---- */

  const accentActive =
    accent === 'amber' ? 'border-amber-400 text-amber-400'
    : accent === 'red' ? 'border-red-400 text-red-400'
    : 'border-blue-400 text-blue-400'

  return (
    <div className="space-y-6">
      {/* Title + Paper/Live Toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <h1
            className={`text-2xl font-bold ${accent === 'amber' ? 'text-amber-400' : accent === 'red' ? 'text-red-400' : 'text-blue-400'}`}
          >
            {bot.toUpperCase()}
          </h1>
          <span className="text-forge-muted">
            {bot === 'flame' ? '2DTE' : bot === 'inferno' ? '0DTE' : '1DTE'} Iron Condor
          </span>
        </div>
        {hasAccounts ? (
          <div className="flex items-center gap-1 bg-forge-bg/80 rounded-lg p-0.5 border border-forge-border">
            <button
              onClick={() => setViewMode('paper')}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'paper'
                  ? 'bg-forge-card text-white shadow-sm'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              Paper Trading
            </button>
            <button
              onClick={() => setViewMode('live')}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'live'
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30 shadow-sm'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              Live Trading
            </button>
          </div>
        ) : (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-gray-500/15 text-gray-400 border border-gray-600/30 uppercase tracking-wider">
            Paper Only
          </span>
        )}
      </div>

      {/* Production pause banner — production bot only. Rendered even in
          Paper view (as a compact info card) so an operator toggling back
          to Live can immediately see the current state. Prominent red card
          with resume button when paused; muted strip with pause button when
          live. */}
      {hasAccounts && pauseState && (
        <div>
          {pauseState.paused ? (
            <div className="rounded-xl border-2 border-red-500/60 bg-red-500/15 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-bold text-red-300 uppercase tracking-wider">
                    PRODUCTION TRADING PAUSED
                  </p>
                  <p className="text-xs text-red-200/90 mt-1">
                    {bot.toUpperCase()} will NOT place real-money orders on the live account.
                    Paper and sandbox trading continue normally.
                  </p>
                  {pauseState.paused_reason && (
                    <p className="text-xs text-red-200/70 mt-1">
                      Reason: <span className="font-mono">{pauseState.paused_reason}</span>
                    </p>
                  )}
                  {pauseState.paused_at && (
                    <p className="text-[10px] text-red-200/60 mt-0.5">
                      Paused at {new Date(pauseState.paused_at).toLocaleString('en-US', { timeZone: 'America/Chicago' })}
                      {pauseState.paused_by ? ` by ${pauseState.paused_by}` : ''}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => togglePause(false)}
                  disabled={pauseBusy}
                  className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors border ${
                    pauseBusy
                      ? 'bg-gray-500/20 text-gray-400 border-gray-500/30 cursor-wait'
                      : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30'
                  }`}
                >
                  {pauseBusy ? 'Working...' : 'Resume Production'}
                </button>
              </div>
              {pauseErr && (
                <p className="text-xs text-red-400 mt-2">Toggle failed: {pauseErr}</p>
              )}
            </div>
          ) : viewMode === 'live' ? (
            <div className="rounded-xl border border-forge-border bg-forge-card/60 px-3 py-2 flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-wider text-forge-muted">
                Production trading: <span className="text-emerald-400 font-semibold">ACTIVE</span>
              </span>
              <button
                onClick={() => togglePause(true)}
                disabled={pauseBusy}
                className={`px-3 py-1 rounded text-xs font-semibold transition-colors border ${
                  pauseBusy
                    ? 'bg-gray-500/20 text-gray-400 border-gray-500/30 cursor-wait'
                    : 'bg-red-500/15 text-red-300 border-red-500/30 hover:bg-red-500/25'
                }`}
              >
                {pauseBusy ? 'Working...' : 'Pause Production'}
              </button>
            </div>
          ) : null}
        </div>
      )}

      {/* Status card */}
      {status && (
        <ComponentErrorBoundary fallback="Status card error">
          <StatusCard
            data={status}
            accent={accent}
            config={config}
            bot={bot}
            liveUnrealizedPnl={positionMonitor?.total_unrealized_pnl}
            liveUnrealizedPct={positionMonitor?.total_unrealized_pnl_pct}
            pendingOrderCount={status?.pending_order_count ?? pendingData?.pending_count}
            quotesDelayed={positionMonitor?.quotes_delayed}
            quoteAgeSeconds={positionMonitor?.quote_age_seconds}
            todaysClosedTrades={positionMonitor?.todays_closed_trades}
            viewMode={viewMode}
          />
        </ComponentErrorBoundary>
      )}

      {/* EOD auto-close result banner */}
      {eodCloseResult && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
          EOD auto-close: {eodCloseResult.closed} position{eodCloseResult.closed !== 1 ? 's' : ''} closed
          {' '}| P&L: {eodCloseResult.total_pnl >= 0 ? '+' : ''}${eodCloseResult.total_pnl.toFixed(2)}
        </div>
      )}

      {/* PDT Management — production bot only (production account under $25K) */}
      {PDT_BOTS.has(bot) && (
        <ComponentErrorBoundary fallback="PDT card error">
          <PdtCard bot={bot} accent={accent} botStatus={status} accountType={hasAccounts ? (viewMode === 'live' ? 'production' : 'sandbox') : undefined} />
        </ComponentErrorBoundary>
      )}

      {/* PT Timeline */}
      <ComponentErrorBoundary fallback="PT timeline error">
        <PTTimeline />
      </ComponentErrorBoundary>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-forge-border">
        {ALL_TABS.filter(t => (!ACCOUNT_ONLY_TABS.has(t) || hasAccounts) && (t !== 'PDT' || PDT_BOTS.has(bot))).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? accentActive
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {tab === 'Equity Curve' && (
          <ComponentErrorBoundary fallback="Equity chart error">
            <EquityChart
              data={equity?.curve || []}
              intradayData={intraday?.snapshots}
              startingCapital={equity?.starting_capital || status?.account?.starting_capital || 10000}
              color={accent === 'amber' ? '#f59e0b' : accent === 'red' ? '#ef4444' : '#3b82f6'}
              title={`${bot.toUpperCase()} Equity Curve`}
              liveUnrealizedPnl={positionMonitor?.total_unrealized_pnl}
              period={equityPeriod}
              onPeriodChange={onPeriodChange}
            />
          </ComponentErrorBoundary>
        )}
        {tab === 'Production' && hasAccounts && (
          <ComponentErrorBoundary fallback="Production tab error">
            <ProductionTab bot={bot} person={brokerPerson} accent={accent} />
          </ComponentErrorBoundary>
        )}
        {tab === 'Broker Equity' && (
          <ComponentErrorBoundary fallback="Broker equity error">
            <BrokerEquityTab
              data={brokerEquity}
              person={brokerPerson || 'Production'}
              period={brokerPeriod}
              onPeriodChange={setBrokerPeriod}
              accent={accent}
            />
          </ComponentErrorBoundary>
        )}
        {tab === 'Performance' && (
          perfErr
            ? <TabError message={perfErr.message} />
            : perf ? <PerformanceCard data={perf} label={bot.toUpperCase()} /> : <TabLoading />
        )}
        {tab === 'Positions' && (
          <>
            {posMonitorErr && !positionMonitor && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 mb-4 text-sm text-amber-400">
                Live position monitor unavailable — showing positions without real-time P&L
              </div>
            )}
            <PositionTable
              positions={positionMonitor?.positions || fallbackPositions?.positions || []}
              spotPrice={positionMonitor?.spot_price}
              tradierConnected={positionMonitor?.tradier_connected}
              detailData={positionDetail}
              bot={bot}
              todaysClosedTrades={positionMonitor?.todays_closed_trades}
            />
          </>
        )}
        {tab === 'Trade History' && (
          tradesErr
            ? <TabError message={tradesErr.message} />
            : trades ? <TradeHistory trades={trades.trades} bot={bot} /> : <TabLoading />
        )}
        {tab === 'Signals' && (
          signalsErr
            ? <TabError message={signalsErr.message} />
            : signalsData ? <SignalsTable signals={signalsData.signals} /> : <TabLoading />
        )}
        {tab === 'Logs' && (
          logsErr
            ? <TabError message={logsErr.message} />
            : logs ? <LogsTable logs={logs.logs} /> : <TabLoading />
        )}
        {tab === 'PDT' && (
          pdtErr
            ? <TabError message={pdtErr.message} />
            : <PdtTabContent
                bot={bot}
                pdtData={pdtData}
                botStatus={status}
                onPdtUpdate={() => mutatePdt()}
              />
        )}
        {tab === 'Reconcile' && hasAccounts && (
          reconErr
            ? <TabError message={reconErr.message} />
            : !reconData
              ? <TabLoading />
              : <ComponentErrorBoundary fallback="Reconcile error">
                  <ReconcileTab data={reconData} apiUrl={withPerson(`/api/${bot}/reconcile`)} />
                </ComponentErrorBoundary>
        )}
      </div>
    </div>
  )
}

/* ================================================================
   Broker Equity Tab — real Tradier account equity curve
   ================================================================ */

const BROKER_PERIODS = [
  { label: 'Intraday', value: 'intraday' as const },
  { label: '1W', value: '1w' as const },
  { label: '1M', value: '1m' as const },
  { label: '3M', value: '3m' as const },
  { label: 'All', value: 'all' as const },
]

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function BrokerEquityTab({
  data,
  person,
  period,
  onPeriodChange,
  accent,
}: {
  data: any
  person: string
  period: string
  onPeriodChange: (p: 'intraday' | '1d' | '1w' | '1m' | '3m' | 'all') => void
  accent: 'amber' | 'blue' | 'red'
}) {
  const points = data?.mode === 'intraday' ? data?.snapshots : data?.curve
  const accentColor = accent === 'amber' ? '#f59e0b' : accent === 'red' ? '#ef4444' : '#3b82f6'

  if (!data) return <TabLoading />

  if (!points || points.length === 0) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-white">Broker Equity — {person}</h3>
          <div className="flex gap-1">
            {BROKER_PERIODS.map((p) => (
              <button
                key={p.value}
                onClick={() => onPeriodChange(p.value)}
                className={`px-2 py-1 text-xs rounded ${
                  period === p.value
                    ? 'bg-forge-border text-white'
                    : 'text-forge-muted hover:text-white'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
          <p className="text-forge-muted text-sm">
            No broker equity snapshots yet — data will appear after the next scan cycle
          </p>
        </div>
      </div>
    )
  }

  const first = points[0]
  const last = points[points.length - 1]
  const firstEquity = first?.total_equity ?? 0
  const lastEquity = last?.total_equity ?? 0
  const change = lastEquity - firstEquity
  const changePct = firstEquity > 0 ? (change / firstEquity) * 100 : 0

  // Find min/max for Y-axis
  const equities = points.map((p: any) => p.total_equity ?? 0).filter((v: number) => v > 0)
  if (equities.length === 0) return <TabLoading />
  const minEq = Math.min(...equities)
  const maxEq = Math.max(...equities)
  const range = maxEq - minEq || 1
  const yMin = minEq - range * 0.1
  const yMax = maxEq + range * 0.1

  return (
    <div className="space-y-4">
      {/* Header with period selector */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-white">Broker Equity — {person}</h3>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xl font-bold text-white">
              ${lastEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span className={`text-sm font-medium ${change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {change >= 0 ? '+' : ''}{change.toFixed(2)} ({changePct.toFixed(2)}%)
            </span>
            {last.open_positions > 0 && (
              <span className="text-xs text-forge-muted">
                {last.open_positions} position{last.open_positions !== 1 ? 's' : ''} open
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-1">
          {BROKER_PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => onPeriodChange(p.value)}
              className={`px-2 py-1 text-xs rounded ${
                period === p.value
                  ? 'bg-forge-border text-white'
                  : 'text-forge-muted hover:text-white'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* SVG Chart */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
        <svg viewBox="0 0 800 300" className="w-full h-64">
          {/* Grid lines */}
          {Array.from({ length: 5 }).map((_, i) => {
            const y = 20 + (i * 260) / 4
            const val = yMax - (i * (yMax - yMin)) / 4
            return (
              <g key={i}>
                <line x1="60" y1={y} x2="780" y2={y} stroke="#374151" strokeWidth="0.5" />
                <text x="55" y={y + 4} textAnchor="end" fill="#6b7280" fontSize="10">
                  ${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </text>
              </g>
            )
          })}
          {/* Equity line */}
          <polyline
            fill="none"
            stroke={accentColor}
            strokeWidth="2"
            points={points
              .map((p: any, i: number) => {
                const x = 60 + (i / Math.max(1, points.length - 1)) * 720
                const y = 20 + ((yMax - p.total_equity) / (yMax - yMin)) * 260
                return `${x},${y}`
              })
              .join(' ')}
          />
          {/* Fill area */}
          <polygon
            fill={accentColor}
            fillOpacity="0.1"
            points={[
              `60,280`,
              ...points.map((p: any, i: number) => {
                const x = 60 + (i / Math.max(1, points.length - 1)) * 720
                const y = 20 + ((yMax - p.total_equity) / (yMax - yMin)) * 260
                return `${x},${y}`
              }),
              `${60 + 720},280`,
            ].join(' ')}
          />
          {/* Time labels */}
          {Array.from({ length: 5 }).map((_, i) => {
            const idx = Math.round((i / 4) * (points.length - 1))
            const p = points[idx]
            if (!p) return null
            const x = 60 + (idx / Math.max(1, points.length - 1)) * 720
            const ts = new Date(p.timestamp)
            const label = period === 'intraday'
              ? ts.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' })
              : ts.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/Chicago' })
            return (
              <text key={i} x={x} y={295} textAnchor="middle" fill="#6b7280" fontSize="10">
                {label}
              </text>
            )
          })}
        </svg>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
          <p className="text-xs text-forge-muted">Day P&L</p>
          <p className={`text-sm font-bold ${(last.day_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {(last.day_pnl ?? 0) >= 0 ? '+' : ''}${(last.day_pnl ?? 0).toFixed(2)}
          </p>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
          <p className="text-xs text-forge-muted">Unrealized P&L</p>
          <p className={`text-sm font-bold ${(last.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {(last.unrealized_pnl ?? 0) >= 0 ? '+' : ''}${(last.unrealized_pnl ?? 0).toFixed(2)}
          </p>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
          <p className="text-xs text-forge-muted">Option BP</p>
          <p className="text-sm font-bold text-white">
            ${(last.option_buying_power ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </p>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
          <p className="text-xs text-forge-muted">Snapshots</p>
          <p className="text-sm font-bold text-white">{points.length}</p>
        </div>
      </div>
    </div>
  )
}

/* ================================================================
   Reconcile Tab — FLAME ↔ Tradier Sandbox comparison
   ================================================================ */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ReconcileTab({ data, apiUrl }: { data: any; apiUrl: string }) {
  const s = data?.summary
  const positions = data?.positions || []
  const orphans = data?.orphans || {}
  const checks = data?.checks || []

  const passChecks = checks.filter((c: any) => c.pass)
  const failChecks = checks.filter((c: any) => !c.pass)
  const orphanCount = Object.values(orphans).reduce((sum: number, arr: any) => sum + (arr as any[]).length, 0)

  const [closing, setClosing] = useState(false)
  const [closeResult, setCloseResult] = useState<any>(null)

  return (
    <div className="space-y-4">
      {/* Verdict banner */}
      <div className={`rounded-xl border p-4 ${
        s?.verdict === 'ALL_MATCH'
          ? 'border-emerald-500/30 bg-emerald-500/10'
          : 'border-red-500/30 bg-red-500/10'
      }`}>
        <div className="flex items-center justify-between">
          <div>
            <p className={`text-lg font-bold ${s?.verdict === 'ALL_MATCH' ? 'text-emerald-400' : 'text-red-400'}`}>
              {s?.verdict === 'ALL_MATCH' ? 'ALL MATCH' : 'MISMATCH DETECTED'}
            </p>
            <p className="text-sm text-forge-muted mt-1">
              {s?.passed}/{s?.total_checks} checks passed
              {failChecks.length > 0 && <span className="text-red-400 ml-2">{failChecks.length} failed</span>}
              {orphanCount > 0 && <span className="text-yellow-400 ml-2">{orphanCount} orphan legs in Tradier</span>}
            </p>
          </div>
          <div className="text-right text-xs text-forge-muted">
            <p>{s?.paper_positions} paper position{s?.paper_positions !== 1 ? 's' : ''}</p>
            <p>Accounts: {s?.sandbox_accounts?.join(', ')}</p>
          </div>
        </div>
      </div>

      {/* Failed checks */}
      {failChecks.length > 0 && (
        <div className="rounded-xl border border-red-500/30 bg-forge-card/80 p-4">
          <p className="text-sm font-semibold text-red-400 mb-2">Failed Checks</p>
          <div className="space-y-1">
            {failChecks.map((c: any, i: number) => (
              <div key={i} className="text-xs">
                <span className="text-red-400 font-mono">FAIL</span>
                <span className="text-gray-300 ml-2">{c.name}</span>
                <span className="text-gray-500 ml-2">{c.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-position comparison */}
      {positions.map((pos: any) => (
        <div key={pos.position_id} className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-sm font-semibold text-gray-200">
                {pos.ticker} {pos.expiration} &middot; {pos.contracts} contracts
              </p>
              <p className="text-xs text-forge-muted font-mono">{pos.position_id}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-forge-muted">Paper Entry Credit</p>
              <p className="text-sm font-semibold text-gray-200">${pos.paper_entry_credit?.toFixed(4)}</p>
            </div>
          </div>

          {/* Paper P&L */}
          <div className="grid grid-cols-2 gap-4 mb-3 pb-3 border-b border-forge-border/30">
            <div>
              <p className="text-xs text-forge-muted">Paper Unrealized</p>
              <p className={`text-sm font-semibold ${(pos.paper_unrealized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {pos.paper_unrealized_pnl != null
                  ? `${pos.paper_unrealized_pnl >= 0 ? '+' : ''}$${pos.paper_unrealized_pnl.toFixed(2)}`
                  : '—'}
                {pos.paper_unrealized_pct != null && (
                  <span className="text-xs ml-1">({pos.paper_unrealized_pct.toFixed(1)}% of credit)</span>
                )}
              </p>
            </div>
          </div>

          {/* Per-account comparison */}
          <div className="space-y-3">
            {Object.entries(pos.accounts || {}).map(([acctName, acct]: [string, any]) => (
              <div key={acctName} className="bg-forge-bg/50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-gray-300">{acctName}</span>
                  <span className={`text-[10px] font-mono ${acct.all_legs_found ? 'text-emerald-400' : 'text-red-400'}`}>
                    {acct.all_legs_found ? '4/4 LEGS' : 'MISSING LEGS'}
                  </span>
                </div>

                {acct.all_legs_found && (
                  <div className="grid grid-cols-3 gap-3 text-xs">
                    {/* Entry credit comparison */}
                    <div>
                      <p className="text-forge-muted">Tradier Entry</p>
                      <p className="font-medium text-gray-200">
                        ${(acct.implied_entry_credit ?? 0).toFixed(4)}
                        <span className={`ml-1 ${Math.abs(acct.entry_credit_diff_pct ?? 0) < 5 ? 'text-emerald-400' : 'text-red-400'}`}>
                          ({(acct.entry_credit_diff_pct ?? 0) >= 0 ? '+' : ''}{(acct.entry_credit_diff_pct ?? 0).toFixed(1)}%)
                        </span>
                      </p>
                    </div>
                    {/* Tradier unrealized */}
                    <div>
                      <p className="text-forge-muted">Tradier Unrealized</p>
                      <p className={`font-medium ${(acct.total_gain_loss ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {(acct.total_gain_loss ?? 0) >= 0 ? '+' : ''}${(acct.total_gain_loss ?? 0).toFixed(2)}
                        {acct.tradier_unrealized_pct != null && (
                          <span className="ml-1">({acct.tradier_unrealized_pct.toFixed(1)}%)</span>
                        )}
                      </p>
                    </div>
                    {/* Diff */}
                    <div>
                      <p className="text-forge-muted">Diff (Paper − Tradier)</p>
                      <p className={`font-medium ${Math.abs(acct.unrealized_pct_diff ?? 0) < 5 ? 'text-emerald-400' : 'text-yellow-400'}`}>
                        {(acct.unrealized_pct_diff ?? 0) >= 0 ? '+' : ''}{(acct.unrealized_pct_diff ?? 0).toFixed(1)}pp
                        <span className="text-forge-muted ml-1">
                          (${(acct.unrealized_pnl_diff ?? 0) >= 0 ? '+' : ''}{(acct.unrealized_pnl_diff ?? 0).toFixed(2)})
                        </span>
                      </p>
                    </div>
                  </div>
                )}

                {/* Missing legs detail */}
                {!acct.all_legs_found && (
                  <div className="mt-2 space-y-1">
                    {acct.legs?.map((leg: any) => (
                      <div key={leg.occ_symbol} className={`text-[10px] font-mono flex justify-between ${leg.qty_match ? 'text-gray-500' : 'text-red-400'}`}>
                        <span>{leg.occ_symbol}</span>
                        <span>paper={leg.paper_qty} tradier={leg.tradier_qty}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Orphans */}
      {orphanCount > 0 && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-yellow-400">
              Orphan Tradier Positions ({orphanCount} legs)
            </p>
            <button
              onClick={async () => {
                if (closing) return
                setClosing(true)
                setCloseResult(null)
                try {
                  const res = await fetch(apiUrl, { method: 'POST' })
                  const json = await res.json()
                  setCloseResult(json)
                } catch (err: unknown) {
                  setCloseResult({ error: err instanceof Error ? err.message : String(err) })
                } finally {
                  setClosing(false)
                }
              }}
              disabled={closing}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                closing
                  ? 'bg-yellow-500/20 text-yellow-400/50 cursor-wait'
                  : 'bg-yellow-500/30 text-yellow-300 hover:bg-yellow-500/50'
              }`}
            >
              {closing ? 'Closing...' : 'Close Orphans'}
            </button>
          </div>
          <p className="text-xs text-yellow-400/70 mb-3">
            These Tradier positions have no matching paper position.
            Close them to free buying power and stop the data integrity warning.
          </p>

          {/* Close result banner */}
          {closeResult && (
            <div className={`rounded-lg border p-3 mb-3 text-xs ${
              closeResult.error
                ? 'border-red-500/30 bg-red-500/10 text-red-400'
                : closeResult.total_failed > 0
                  ? 'border-yellow-500/30 bg-yellow-500/10 text-yellow-400'
                  : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
            }`}>
              {closeResult.error
                ? `Error: ${closeResult.error}`
                : `Closed ${closeResult.total_closed}/${closeResult.total_orphans_found} orphan legs` +
                  (closeResult.total_failed > 0 ? ` (${closeResult.total_failed} failed — market may be closed)` : '')
              }
            </div>
          )}

          {Object.entries(orphans).map(([acctName, legs]: [string, any]) => (
            <div key={acctName} className="mb-2">
              <p className="text-xs font-medium text-gray-300 mb-1">{acctName}</p>
              <div className="space-y-0.5">
                {legs.map((leg: any) => (
                  <div key={leg.symbol} className="text-[10px] font-mono text-yellow-400/80 flex justify-between">
                    <span>{leg.symbol}</span>
                    <span>qty={leg.quantity} G/L=${leg.gain_loss?.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* All checks (collapsed) */}
      {passChecks.length > 0 && (
        <details className="rounded-xl border border-forge-border bg-forge-card/80">
          <summary className="p-3 text-sm text-forge-muted cursor-pointer hover:text-gray-300">
            {passChecks.length} passing checks (click to expand)
          </summary>
          <div className="px-3 pb-3 space-y-0.5">
            {passChecks.map((c: any, i: number) => (
              <div key={i} className="text-[10px]">
                <span className="text-emerald-400 font-mono">PASS</span>
                <span className="text-gray-400 ml-2">{c.name}</span>
                <span className="text-gray-600 ml-2">{c.detail}</span>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* No positions */}
      {positions.length === 0 && orphanCount === 0 && (
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
          <p className="text-forge-muted text-sm">No open positions to reconcile</p>
        </div>
      )}
    </div>
  )
}
