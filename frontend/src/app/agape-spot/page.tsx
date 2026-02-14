'use client'

import { useState, useMemo } from 'react'
import useSWR from 'swr'
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Area, AreaChart,
} from 'recharts'
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Eye,
  RefreshCw,
  Wallet,
  History,
  BarChart3,
  Layers,
  ArrowRight,
  Calendar,
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'

// ==============================================================================
// TYPES
// ==============================================================================

type TickerId = 'ALL' | 'ETH-USD' | 'BTC-USD' | 'XRP-USD' | 'SHIB-USD' | 'DOGE-USD' | 'MSTU-USD'

interface WinTrackerData {
  ticker: string
  alpha: number
  beta: number
  total_trades: number
  win_probability: number
  is_cold_start: boolean
  cold_start_floor: number
  positive_funding_wins: number
  positive_funding_losses: number
  negative_funding_wins: number
  negative_funding_losses: number
  neutral_funding_wins: number
  neutral_funding_losses: number
  should_use_ml: boolean
  regime_probabilities: {
    POSITIVE: number
    NEGATIVE: number
    NEUTRAL: number
  }
}

interface TickerSummary {
  ticker: string
  current_price: number
  open_positions: number
  total_pnl: number
  return_pct: number
  win_rate: number | null
  total_trades: number
  unrealized_pnl: number
  win_tracker?: WinTrackerData | null
}

// ==============================================================================
// CONSTANTS
// ==============================================================================

const API = process.env.NEXT_PUBLIC_API_URL || ''

const TICKERS: TickerId[] = ['ALL', 'ETH-USD', 'BTC-USD', 'XRP-USD', 'SHIB-USD', 'DOGE-USD', 'MSTU-USD']

const TICKER_META: Record<string, { symbol: string; label: string; colorClass: string; hexColor: string; bgActive: string; borderActive: string; textActive: string; bgCard: string; borderCard: string }> = {
  'ALL':      { symbol: 'ALL',  label: 'All Coins',  colorClass: 'cyan',   hexColor: '#06B6D4', bgActive: 'bg-cyan-600',   borderActive: 'border-cyan-500',   textActive: 'text-cyan-400',   bgCard: 'bg-cyan-950/30',   borderCard: 'border-cyan-700/40' },
  'ETH-USD':  { symbol: 'ETH',  label: 'Ethereum',   colorClass: 'cyan',   hexColor: '#06B6D4', bgActive: 'bg-cyan-600',   borderActive: 'border-cyan-500',   textActive: 'text-cyan-400',   bgCard: 'bg-cyan-950/30',   borderCard: 'border-cyan-700/40' },
  'BTC-USD':  { symbol: 'BTC',  label: 'Bitcoin',    colorClass: 'amber',  hexColor: '#F59E0B', bgActive: 'bg-amber-600',  borderActive: 'border-amber-500',  textActive: 'text-amber-400',  bgCard: 'bg-amber-950/30',  borderCard: 'border-amber-700/40' },
  'XRP-USD':  { symbol: 'XRP',  label: 'Ripple',     colorClass: 'blue',   hexColor: '#3B82F6', bgActive: 'bg-blue-600',   borderActive: 'border-blue-500',   textActive: 'text-blue-400',   bgCard: 'bg-blue-950/30',   borderCard: 'border-blue-700/40' },
  'SHIB-USD': { symbol: 'SHIB', label: 'Shiba Inu',  colorClass: 'orange', hexColor: '#F97316', bgActive: 'bg-orange-600', borderActive: 'border-orange-500', textActive: 'text-orange-400', bgCard: 'bg-orange-950/30', borderCard: 'border-orange-700/40' },
  'DOGE-USD': { symbol: 'DOGE', label: 'Dogecoin',   colorClass: 'yellow', hexColor: '#EAB308', bgActive: 'bg-yellow-600', borderActive: 'border-yellow-500', textActive: 'text-yellow-400', bgCard: 'bg-yellow-950/30', borderCard: 'border-yellow-700/40' },
  'MSTU-USD': { symbol: 'MSTU', label: '2X MSTR ETF', colorClass: 'purple', hexColor: '#A855F7', bgActive: 'bg-purple-600', borderActive: 'border-purple-500', textActive: 'text-purple-400', bgCard: 'bg-purple-950/30', borderCard: 'border-purple-700/40' },
}

const SECTION_TABS = [
  { id: 'overview' as const,    label: 'Overview',      icon: Layers },
  { id: 'positions' as const,   label: 'Positions',     icon: Wallet },
  { id: 'performance' as const, label: 'Performance',   icon: BarChart3 },
  { id: 'equity' as const,      label: 'Equity Curve',  icon: TrendingUp },
  { id: 'logs' as const,        label: 'Logs',          icon: History },
]
type SectionTabId = typeof SECTION_TABS[number]['id']

const TOTAL_CAPITAL = 14000

const TIME_FRAMES = [
  { id: 'today', label: 'Today', days: 0 },
  { id: '7d',    label: '7D',    days: 7 },
  { id: '14d',   label: '14D',   days: 14 },
  { id: '30d',   label: '30D',   days: 30 },
  { id: '90d',   label: '90D',   days: 90 },
  { id: 'all',   label: 'ALL',   days: 365 },
] as const
type TimeFrameId = typeof TIME_FRAMES[number]['id']

// ==============================================================================
// SWR FETCHER
// ==============================================================================

const fetcher = (url: string) => fetch(`${API}${url}`).then(r => {
  if (!r.ok) throw new Error(`API error ${r.status}`)
  return r.json()
})

// ==============================================================================
// SWR HOOKS
// ==============================================================================

function useAgapeSpotSummary() {
  return useSWR('/api/agape-spot/summary', fetcher, { refreshInterval: 10_000 })
}

function useAgapeSpotStatus(ticker?: string) {
  const url = ticker && ticker !== 'ALL'
    ? `/api/agape-spot/status?ticker=${ticker}`
    : '/api/agape-spot/status'
  return useSWR(url, fetcher, { refreshInterval: 10_000 })
}

function useAgapeSpotPositions(ticker?: string) {
  const param = ticker && ticker !== 'ALL' ? `?ticker=${ticker}` : ''
  return useSWR(`/api/agape-spot/positions${param}`, fetcher, { refreshInterval: 10_000 })
}

function useAgapeSpotPerformance(ticker?: string) {
  const param = ticker && ticker !== 'ALL' ? `?ticker=${ticker}` : ''
  return useSWR(`/api/agape-spot/performance${param}`, fetcher, { refreshInterval: 30_000 })
}

function useAgapeSpotEquityCurve(ticker?: string, days: number = 30) {
  const params = new URLSearchParams()
  if (ticker && ticker !== 'ALL') params.set('ticker', ticker)
  params.set('days', String(days))
  const qs = params.toString()
  return useSWR(`/api/agape-spot/equity-curve?${qs}`, fetcher, { refreshInterval: 30_000 })
}

function useAgapeSpotIntradayEquity(ticker?: string) {
  const params = new URLSearchParams()
  if (ticker && ticker !== 'ALL') params.set('ticker', ticker)
  const qs = params.toString()
  return useSWR(`/api/agape-spot/equity-curve/intraday${qs ? `?${qs}` : ''}`, fetcher, { refreshInterval: 15_000 })
}

function useAgapeSpotClosedTrades(ticker?: string, limit: number = 50) {
  const params = new URLSearchParams()
  if (ticker && ticker !== 'ALL') params.set('ticker', ticker)
  params.set('limit', String(limit))
  return useSWR(`/api/agape-spot/closed-trades?${params.toString()}`, fetcher, { refreshInterval: 60_000 })
}

function useAgapeSpotScanActivity(ticker?: string, limit: number = 30) {
  const params = new URLSearchParams()
  if (ticker && ticker !== 'ALL') params.set('ticker', ticker)
  params.set('limit', String(limit))
  return useSWR(`/api/agape-spot/scan-activity?${params.toString()}`, fetcher, { refreshInterval: 15_000 })
}

function useAgapeSpotMLStatus() {
  return useSWR('/api/agape-spot/ml/status', fetcher, { refreshInterval: 30_000 })
}

// ==============================================================================
// HELPERS
// ==============================================================================

function pnlColor(val: number): string {
  if (val > 0) return 'text-green-400'
  if (val < 0) return 'text-red-400'
  return 'text-gray-400'
}

function fmtUsd(val: number | null | undefined, decimals = 2): string {
  if (val == null) return '---'
  const prefix = val >= 0 ? '' : '-'
  return `${prefix}$${Math.abs(val).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return '---'
  const prefix = val >= 0 ? '+' : ''
  return `${prefix}${val.toFixed(2)}%`
}

function fmtPrice(val: number | null | undefined): string {
  if (val == null) return '---'
  if (val < 0.01) return `$${val.toFixed(6)}`
  if (val < 1) return `$${val.toFixed(4)}`
  return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

// ==============================================================================
// DATA TRANSFORMS (pure functions, no hooks)
// ==============================================================================

/** Compute drawdown % from equity points. Each output point gets a `drawdown` field (always <= 0). */
function computeDrawdown(points: any[], startingCapital: number): any[] {
  if (!points || points.length === 0) return []
  let peak = startingCapital
  return points.map(p => {
    const eq = p.equity ?? startingCapital
    if (eq > peak) peak = eq
    const dd = peak > 0 ? ((eq - peak) / peak) * 100 : 0
    return { ...p, drawdown: Math.round(dd * 100) / 100 }
  })
}

/**
 * Fill daily P&L from equity curve into a contiguous array of days.
 * Equity curve only has entries for trade days. We fill gaps with pnl=null.
 * Returns array sorted oldest→newest.
 *
 * Backend equity point: { date: "YYYY-MM-DD", daily_pnl: number, trades: number }
 */
function buildHeatmapDays(equityPoints: any[]): { date: string; pnl: number | null; trades: number }[] {
  if (!equityPoints || equityPoints.length === 0) return []
  const pnlMap = new Map<string, { pnl: number; trades: number }>()
  for (const p of equityPoints) {
    if (p.date) pnlMap.set(p.date, { pnl: p.daily_pnl ?? 0, trades: p.trades ?? 0 })
  }
  const first = new Date(equityPoints[0].date + 'T12:00:00')
  const today = new Date()
  today.setHours(12, 0, 0, 0)
  const days: { date: string; pnl: number | null; trades: number }[] = []
  const d = new Date(first)
  while (d <= today) {
    const ds = d.toISOString().slice(0, 10)
    const entry = pnlMap.get(ds)
    days.push({ date: ds, pnl: entry?.pnl ?? null, trades: entry?.trades ?? 0 })
    d.setDate(d.getDate() + 1)
  }
  return days
}

// ==============================================================================
// MAIN PAGE COMPONENT
// ==============================================================================

export default function AgapeSpotPage() {
  const [selectedTicker, setSelectedTicker] = useState<TickerId>('ALL')
  const [activeTab, setActiveTab] = useState<SectionTabId>('overview')
  const sidebarPadding = useSidebarPadding()

  // Global data
  const { data: summaryData, isLoading: summaryLoading } = useAgapeSpotSummary()
  const { data: statusData, isLoading: statusLoading, mutate: refreshStatus } = useAgapeSpotStatus(selectedTicker)

  const isAllView = selectedTicker === 'ALL'

  // Loading state
  if (summaryLoading && !summaryData && statusLoading && !statusData) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen bg-gray-950">
          <div className="text-center space-y-3">
            <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin mx-auto" />
            <p className="text-gray-400 text-sm">Loading AGAPE-SPOT...</p>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <Navigation />
      <main className={`min-h-screen bg-gray-950 text-white px-4 pb-6 md:px-6 pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-7xl mx-auto space-y-5">

          {/* ================================================================ */}
          {/* PAGE HEADER                                                      */}
          {/* ================================================================ */}
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl md:text-3xl font-bold text-white">
                  AGAPE-SPOT <span className="text-cyan-400">Multi-Coin</span>
                </h1>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-green-900/40 border border-green-500/40 rounded-full text-xs font-semibold text-green-400">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  24/7 ACTIVE
                </span>
              </div>
              <p className="text-gray-500 text-sm mt-1">
                Long-only spot trading across ETH, XRP, SHIB, DOGE on Coinbase
              </p>
            </div>
            <button
              onClick={() => refreshStatus()}
              disabled={statusLoading}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${statusLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* ================================================================ */}
          {/* LIVE PRICE TICKER STRIP                                          */}
          {/* ================================================================ */}
          <PriceTickerStrip tickers={summaryData?.data?.tickers} />

          {/* ================================================================ */}
          {/* COIN SELECTOR                                                    */}
          {/* ================================================================ */}
          <div className="flex gap-2 overflow-x-auto pb-1">
            {TICKERS.map((ticker) => {
              const meta = TICKER_META[ticker]
              const isActive = selectedTicker === ticker
              const summary: TickerSummary | undefined = summaryData?.data?.tickers?.[ticker]
              return (
                <button
                  key={ticker}
                  onClick={() => { setSelectedTicker(ticker); setActiveTab('overview') }}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-all whitespace-nowrap ${
                    isActive
                      ? `${meta.bgActive} border-transparent text-white shadow-lg`
                      : 'bg-gray-900 border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white hover:border-gray-600'
                  }`}
                >
                  <span className="font-bold">{meta.symbol}</span>
                  {ticker !== 'ALL' && summary?.current_price != null && (
                    <span className={`text-xs font-mono ${isActive ? 'text-white/80' : 'text-gray-500'}`}>
                      {fmtPrice(summary.current_price)}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* ================================================================ */}
          {/* ALL VIEW - Combined Summary                                      */}
          {/* ================================================================ */}
          {isAllView && <AllCoinsDashboard summaryData={summaryData?.data} />}

          {/* ================================================================ */}
          {/* SINGLE COIN VIEW                                                 */}
          {/* ================================================================ */}
          {!isAllView && (
            <>
              {/* Coin header stats */}
              <SingleCoinHeader ticker={selectedTicker} statusData={statusData?.data} />

              {/* Section Tabs */}
              <div className="flex gap-1.5 border-b border-gray-800 pb-2 overflow-x-auto">
                {SECTION_TABS.map((tab) => {
                  const isActive = activeTab === tab.id
                  const meta = TICKER_META[selectedTicker]
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors whitespace-nowrap text-sm font-medium ${
                        isActive
                          ? `${meta.bgCard} ${meta.textActive} border ${meta.borderCard}`
                          : 'text-gray-400 hover:text-white hover:bg-gray-800'
                      }`}
                    >
                      <tab.icon className="w-4 h-4" />
                      {tab.label}
                    </button>
                  )
                })}
              </div>

              {/* Tab Content */}
              <div className="space-y-5">
                {activeTab === 'overview' && (
                  <OverviewTab ticker={selectedTicker} />
                )}
                {activeTab === 'positions' && (
                  <PositionsTab ticker={selectedTicker} />
                )}
                {activeTab === 'performance' && (
                  <PerformanceTab ticker={selectedTicker} />
                )}
                {activeTab === 'equity' && (
                  <EquityCurveTab ticker={selectedTicker} />
                )}
                {activeTab === 'logs' && (
                  <LogsTab ticker={selectedTicker} />
                )}
              </div>
            </>
          )}

        </div>
      </main>
    </>
  )
}

// ==============================================================================
// ALL COINS DASHBOARD
// ==============================================================================

function AllCoinsDashboard({ summaryData }: { summaryData: any }) {
  const [eqTimeFrame, setEqTimeFrame] = useState<TimeFrameId>('today')
  const isIntraday = eqTimeFrame === 'today'
  const eqDays = TIME_FRAMES.find(tf => tf.id === eqTimeFrame)?.days ?? 30

  const tickers = summaryData?.tickers || {}
  const totals = summaryData?.totals || {}

  const totalPnl = totals.total_pnl ?? 0
  const totalReturn = totals.return_pct ?? 0
  const totalUnrealized = totals.unrealized_pnl ?? 0
  const totalTrades = totals.total_trades ?? 0
  const totalPositions = totals.open_positions ?? 0

  // Historical equity curve (non-intraday)
  const { data: equityData } = useAgapeSpotEquityCurve(undefined, eqDays)
  // Intraday equity curve (5-min snapshots)
  const { data: intradayData } = useAgapeSpotIntradayEquity(undefined)
  const equityPoints = isIntraday
    ? (intradayData?.data_points || [])
    : (equityData?.data?.equity_curve || [])

  const drawdownPoints = useMemo(
    () => computeDrawdown(equityPoints, TOTAL_CAPITAL),
    [equityPoints],
  )

  // Heatmap uses historical (non-intraday) data with daily_pnl field
  const histPoints = equityData?.data?.equity_curve || []
  const heatmapDays = useMemo(() => buildHeatmapDays(histPoints), [histPoints])

  return (
    <div className="space-y-5">
      {/* Combined totals row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricCard label="Total Capital" value={fmtUsd(TOTAL_CAPITAL)} color="text-white" />
        <MetricCard label="Total P&L" value={fmtUsd(totalPnl)} color={pnlColor(totalPnl)} />
        <MetricCard label="Return" value={fmtPct(totalReturn)} color={pnlColor(totalReturn)} />
        <MetricCard label="Unrealized" value={fmtUsd(totalUnrealized)} color={pnlColor(totalUnrealized)} />
        <MetricCard label="Open Positions" value={String(totalPositions)} color="text-cyan-400" />
      </div>

      {/* Per-coin summary cards (with sparklines) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {(['ETH-USD', 'BTC-USD', 'XRP-USD', 'SHIB-USD', 'DOGE-USD', 'MSTU-USD'] as const).map((ticker) => (
          <CoinCard key={ticker} ticker={ticker} data={tickers[ticker]} />
        ))}
      </div>

      {/* Capital Allocation Rankings */}
      <AllocationRankings allocator={summaryData?.capital_allocator} />

      {/* Combined Equity Curve */}
      <SectionCard
        title={isIntraday ? "Today's Combined Equity (5-min)" : "Combined Equity Curve"}
        icon={<TrendingUp className="w-5 h-5 text-cyan-400" />}
        headerRight={
          <div className="flex items-center gap-3">
            {isIntraday && intradayData && (
              <span className={`text-xs font-mono ${pnlColor(intradayData.day_pnl ?? 0)}`}>
                Day P&L: {fmtUsd(intradayData.day_pnl)}
              </span>
            )}
            <TimeFrameSelector selected={eqTimeFrame} onChange={setEqTimeFrame} />
          </div>
        }
      >
        {equityPoints.length === 0 ? (
          <EmptyBox message={isIntraday ? "No intraday snapshots yet. The bot saves equity every 5 minutes." : "No equity data yet. Trades will populate this chart."} />
        ) : (
          <>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityPoints} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="eqFillAll" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#06B6D4" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis
                    dataKey={isIntraday ? 'time' : 'date'}
                    tick={{ fill: '#6b7280', fontSize: 11 }}
                    tickFormatter={(v: string) => {
                      if (isIntraday) {
                        return v?.slice(0, 5) || v
                      }
                      const d = new Date(v + 'T00:00:00')
                      return `${d.getMonth() + 1}/${d.getDate()}`
                    }}
                  />
                  <YAxis
                    tick={{ fill: '#6b7280', fontSize: 11 }}
                    tickFormatter={(v: number) => `$${v.toLocaleString()}`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
                    labelStyle={{ color: '#9ca3af' }}
                    formatter={(value: number) => [`$${value.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, 'Equity']}
                    labelFormatter={(label: string) => isIntraday ? `Time: ${label}` : label}
                  />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="#06B6D4"
                    strokeWidth={2}
                    fill="url(#eqFillAll)"
                    dot={(props: any) => {
                      const { cx, cy, payload, key } = props
                      if (!payload?.trades || payload.trades === 0) return <g key={key} />
                      const color = (payload.daily_pnl ?? 0) >= 0 ? '#4ade80' : '#f87171'
                      return <circle key={key} cx={cx} cy={cy} r={4} fill={color} stroke="#111827" strokeWidth={1.5} />
                    }}
                    activeDot={{ r: 5, strokeWidth: 2 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <DrawdownChart points={drawdownPoints} isIntraday={isIntraday} />
          </>
        )}
      </SectionCard>

      {/* Daily P&L Heatmap (historical only) */}
      {!isIntraday && heatmapDays.length > 1 && (
        <PnlHeatmap days={heatmapDays} />
      )}

      {/* Recent activity across all coins */}
      <AllCoinsRecentTrades />
    </div>
  )
}

function AllCoinsRecentTrades() {
  const { data: closedData } = useAgapeSpotClosedTrades(undefined, 20)
  const trades = closedData?.data || []

  if (trades.length === 0) return null

  return (
    <SectionCard title="Recent Closed Trades (All Coins)" icon={<History className="w-5 h-5 text-gray-400" />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Time</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Ticker</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Side</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Qty</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Entry</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Exit</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">P&L</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {trades.map((t: any, i: number) => {
              const tickerKey = t.ticker || t.symbol || 'ETH-USD'
              const meta = TICKER_META[tickerKey] || TICKER_META['ETH-USD']
              return (
                <tr key={i} className="hover:bg-gray-800/30">
                  <td className="px-3 py-2 text-gray-500 font-mono text-xs">
                    {t.close_time ? new Date(t.close_time).toLocaleString() : '---'}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`font-bold text-xs ${meta.textActive}`}>{meta.symbol}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-xs font-bold text-green-400">LONG</span>
                  </td>
                  <td className="px-3 py-2 text-gray-300 font-mono text-xs">
                    {t.quantity ?? '---'}
                  </td>
                  <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(t.entry_price)}</td>
                  <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(t.close_price)}</td>
                  <td className="px-3 py-2 text-right">
                    <span className={`font-mono font-semibold text-xs ${pnlColor(t.realized_pnl ?? 0)}`}>
                      {fmtUsd(t.realized_pnl)}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

// ==============================================================================
// SINGLE COIN HEADER
// ==============================================================================

function SingleCoinHeader({ ticker, statusData }: { ticker: TickerId; statusData: any }) {
  const meta = TICKER_META[ticker]
  const status = statusData?.data ?? statusData
  const tickerDetails = status?.ticker_details?.[ticker] ?? status
  const price = tickerDetails?.current_price ?? status?.current_price
  const openPos = tickerDetails?.open_positions ?? status?.open_positions ?? 0
  const unrealizedPnl = tickerDetails?.total_unrealized_pnl ?? status?.total_unrealized_pnl ?? 0

  return (
    <div className={`rounded-xl border p-4 ${meta.bgCard} ${meta.borderCard}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className={`text-2xl font-bold ${meta.textActive}`}>{meta.symbol}</span>
          <span className="text-gray-400 text-sm">{meta.label}</span>
          <ArrowRight className="w-4 h-4 text-gray-600" />
          <span className="text-white font-mono text-lg">{fmtPrice(price)}</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="text-right">
            <span className="text-gray-500 text-xs block">Open</span>
            <span className="text-white font-mono">{openPos}</span>
          </div>
          <div className="text-right">
            <span className="text-gray-500 text-xs block">Unrealized</span>
            <span className={`font-mono ${pnlColor(unrealizedPnl)}`}>{fmtUsd(unrealizedPnl)}</span>
          </div>
        </div>
      </div>
      <p className="text-gray-500 text-xs">
        Long-only spot trading on Coinbase. P&L = (exit - entry) x quantity.
      </p>
    </div>
  )
}

// ==============================================================================
// OVERVIEW TAB (single coin)
// ==============================================================================

function OverviewTab({ ticker }: { ticker: TickerId }) {
  const { data: statusData } = useAgapeSpotStatus(ticker)
  const { data: perfData } = useAgapeSpotPerformance(ticker)

  const status = statusData?.data ?? statusData
  const perf = perfData?.data ?? perfData
  const meta = TICKER_META[ticker]

  const startingCapital = status?.starting_capital ?? 2000
  const currentBalance = status?.paper_account?.current_balance ?? status?.current_balance ?? startingCapital
  const cumulativePnl = perf?.total_pnl ?? status?.paper_account?.cumulative_pnl ?? 0
  const returnPct = perf?.return_pct ?? status?.paper_account?.return_pct ?? 0
  const winRate = perf?.win_rate ?? status?.paper_account?.win_rate
  const totalTrades = perf?.total_trades ?? status?.paper_account?.total_trades ?? 0

  return (
    <div className="space-y-5">
      {/* Capital summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="Starting Capital" value={fmtUsd(startingCapital)} color="text-white" />
        <MetricCard label="Current Balance" value={fmtUsd(currentBalance)} color={pnlColor(currentBalance - startingCapital)} />
        <MetricCard label="Cumulative P&L" value={fmtUsd(cumulativePnl)} color={pnlColor(cumulativePnl)} />
        <MetricCard label="Return" value={fmtPct(returnPct)} color={pnlColor(returnPct)} />
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Win Rate"
          value={winRate != null ? `${Number(winRate).toFixed(1)}%` : '---'}
          color={winRate != null && winRate >= 55 ? 'text-green-400' : winRate != null && winRate >= 45 ? 'text-yellow-400' : 'text-gray-400'}
        />
        <MetricCard label="Total Trades" value={String(totalTrades)} color="text-white" />
        <MetricCard label="Profit Factor" value={perf?.profit_factor != null ? String(perf.profit_factor) : '---'} color="text-white" />
        <MetricCard label="Mode" value={(status?.mode || 'paper').toUpperCase()} color={status?.mode === 'live' ? 'text-green-400' : 'text-yellow-400'} />
      </div>

      {/* Bayesian Win Tracker */}
      {status?.win_tracker && (
        <SectionCard title="Bayesian Win Tracker" icon={<Eye className={`w-5 h-5 ${meta.textActive}`} />}>
          <BayesianTrackerDetail tracker={status.win_tracker} color={meta.textActive} />
        </SectionCard>
      )}

      {/* ML Shadow Advisor */}
      <SectionCard title="ML Shadow Advisor" icon={<BarChart3 className={`w-5 h-5 ${meta.textActive}`} />}>
        <MLShadowPanel ticker={ticker} />
      </SectionCard>

      {/* Configuration */}
      <SectionCard title="Configuration" icon={<Activity className={`w-5 h-5 ${meta.textActive}`} />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Exchange</span>
            <p className="text-white font-mono">Coinbase</p>
          </div>
          <div>
            <span className="text-gray-500">Instrument</span>
            <p className={`font-mono ${meta.textActive}`}>{ticker}</p>
          </div>
          <div>
            <span className="text-gray-500">Direction</span>
            <p className="text-green-400 font-mono">LONG ONLY</p>
          </div>
          <div>
            <span className="text-gray-500">Market Hours</span>
            <p className="text-cyan-400 font-mono">24/7</p>
          </div>
          <div>
            <span className="text-gray-500">Risk Per Trade</span>
            <p className="text-white font-mono">{status?.risk_per_trade_pct ?? 5}%</p>
          </div>
          <div>
            <span className="text-gray-500">Cooldown</span>
            <p className="text-white font-mono">{status?.cooldown_minutes ?? 5} min</p>
          </div>
          <div>
            <span className="text-gray-500">Prophet</span>
            <p className="text-white font-mono">{status?.require_oracle ? 'Required' : 'Advisory'}</p>
          </div>
          <div>
            <span className="text-gray-500">Cycles Run</span>
            <p className="text-white font-mono">{status?.cycle_count ?? 0}</p>
          </div>
        </div>
      </SectionCard>
    </div>
  )
}

// ==============================================================================
// POSITIONS TAB
// ==============================================================================

function PositionsTab({ ticker }: { ticker: TickerId }) {
  const { data: posData, isLoading } = useAgapeSpotPositions(ticker)
  const positions = posData?.data || []
  const meta = TICKER_META[ticker]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    )
  }

  if (positions.length === 0) {
    return (
      <EmptyBox message={`No open positions for ${ticker}. The bot is scanning for opportunities.`} />
    )
  }

  return (
    <div className="space-y-3">
      {positions.map((pos: any, idx: number) => (
        <div key={pos.position_id || idx} className={`rounded-xl border p-4 ${meta.bgCard} ${meta.borderCard}`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <span className="px-2 py-1 rounded text-xs font-bold bg-green-900/50 text-green-400">
                LONG
              </span>
              {pos.account_label && (
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                  pos.account_label === 'paper' || pos.account_label?.endsWith('_fallback')
                    ? 'bg-yellow-900/50 text-yellow-400 border border-yellow-700/50'
                    : 'bg-emerald-900/50 text-emerald-400 border border-emerald-700/50'
                }`}>
                  {pos.account_label?.endsWith('_fallback') ? 'PAPER' : pos.account_label === 'paper' ? 'PAPER' : 'LIVE'}
                </span>
              )}
              <span className="text-white font-mono font-semibold">
                {pos.quantity ?? pos.eth_quantity ?? '---'} {TICKER_META[ticker].symbol} @ {fmtPrice(pos.entry_price)}
              </span>
              {pos.trailing_active && (
                <span className="px-2 py-0.5 bg-cyan-900/50 text-cyan-300 text-xs rounded font-mono">
                  TRAILING @ {fmtPrice(pos.current_stop)}
                </span>
              )}
            </div>
            <span className={`text-lg font-mono font-bold ${pnlColor(pos.unrealized_pnl ?? 0)}`}>
              {fmtUsd(pos.unrealized_pnl)}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
            <div>
              <span className="text-gray-500">Current Price</span>
              <p className="text-white font-mono">{fmtPrice(pos.current_price)}</p>
            </div>
            <div>
              <span className="text-gray-500">Stop Loss</span>
              <p className="text-red-400 font-mono">{pos.stop_loss ? fmtPrice(pos.stop_loss) : 'Trailing'}</p>
            </div>
            <div>
              <span className="text-gray-500">Take Profit</span>
              <p className="text-green-400 font-mono">{pos.take_profit ? fmtPrice(pos.take_profit) : 'No-Loss Trail'}</p>
            </div>
            <div>
              <span className="text-gray-500">Prophet</span>
              <p className="text-gray-300">
                {pos.oracle_advice || 'Advisory'}
                {pos.oracle_win_probability ? ` (${(pos.oracle_win_probability * 100).toFixed(0)}%)` : ''}
              </p>
            </div>
            <div>
              <span className="text-gray-500">Opened</span>
              <p className="text-white">{pos.open_time ? new Date(pos.open_time).toLocaleString() : '---'}</p>
            </div>
            <div>
              <span className="text-gray-500">ID</span>
              <p className="text-white font-mono">{pos.position_id?.slice(0, 8) || '---'}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ==============================================================================
// PERFORMANCE TAB
// ==============================================================================

function PerformanceTab({ ticker }: { ticker: TickerId }) {
  const { data: perfData, isLoading } = useAgapeSpotPerformance(ticker)
  const perf = perfData?.data ?? perfData

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    )
  }

  if (!perf) {
    return <EmptyBox message={`No performance data available for ${ticker}.`} />
  }

  const meta = TICKER_META[ticker]

  return (
    <div className="space-y-5">
      <SectionCard title="Performance Statistics" icon={<BarChart3 className={`w-5 h-5 ${meta.textActive}`} />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Total Trades</span>
            <p className="text-white font-mono text-lg">{perf.total_trades ?? 0}</p>
          </div>
          <div>
            <span className="text-gray-500">Win Rate</span>
            <p className={`font-mono text-lg ${
              (perf.win_rate ?? 0) >= 55 ? 'text-green-400' : (perf.win_rate ?? 0) >= 45 ? 'text-yellow-400' : 'text-red-400'
            }`}>
              {perf.win_rate != null ? `${Number(perf.win_rate).toFixed(1)}%` : '---'}
            </p>
          </div>
          <div>
            <span className="text-gray-500">Total P&L</span>
            <p className={`font-mono text-lg ${pnlColor(perf.total_pnl ?? 0)}`}>
              {fmtUsd(perf.total_pnl)}
            </p>
          </div>
          <div>
            <span className="text-gray-500">Return</span>
            <p className={`font-mono text-lg ${pnlColor(perf.return_pct ?? 0)}`}>
              {fmtPct(perf.return_pct)}
            </p>
          </div>
          <div>
            <span className="text-gray-500">Profit Factor</span>
            <p className="text-white font-mono">{perf.profit_factor ?? '---'}</p>
          </div>
          <div>
            <span className="text-gray-500">Avg Win</span>
            <p className="text-green-400 font-mono">{perf.avg_win != null ? fmtUsd(perf.avg_win) : '---'}</p>
          </div>
          <div>
            <span className="text-gray-500">Avg Loss</span>
            <p className="text-red-400 font-mono">{perf.avg_loss != null ? fmtUsd(-Math.abs(perf.avg_loss)) : '---'}</p>
          </div>
          <div>
            <span className="text-gray-500">Unrealized P&L</span>
            <p className={`font-mono ${pnlColor(perf.unrealized_pnl ?? 0)}`}>
              {fmtUsd(perf.unrealized_pnl)}
            </p>
          </div>
          <div>
            <span className="text-gray-500">Best Trade</span>
            <p className="text-green-400 font-mono">{perf.best_trade != null ? fmtUsd(perf.best_trade) : '---'}</p>
          </div>
          <div>
            <span className="text-gray-500">Worst Trade</span>
            <p className="text-red-400 font-mono">{perf.worst_trade != null ? fmtUsd(perf.worst_trade) : '---'}</p>
          </div>
          <div>
            <span className="text-gray-500">Wins</span>
            <p className="text-green-400 font-mono">{perf.wins ?? 0}</p>
          </div>
          <div>
            <span className="text-gray-500">Losses</span>
            <p className="text-red-400 font-mono">{perf.losses ?? 0}</p>
          </div>
        </div>
      </SectionCard>

      {/* Closed Trades */}
      <ClosedTradesTable ticker={ticker} />
    </div>
  )
}

function ClosedTradesTable({ ticker }: { ticker: TickerId }) {
  const { data: closedData } = useAgapeSpotClosedTrades(ticker, 50)
  const trades = closedData?.data || []
  const meta = TICKER_META[ticker]

  if (trades.length === 0) return null

  return (
    <SectionCard title={`Closed Trades (${trades.length})`} icon={<History className={`w-5 h-5 ${meta.textActive}`} />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Closed</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Side</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Qty</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Entry</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Exit</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">P&L</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {trades.map((trade: any, i: number) => (
              <tr key={i} className="hover:bg-gray-800/30">
                <td className="px-3 py-2 text-gray-500 font-mono text-xs">
                  {trade.close_time ? new Date(trade.close_time).toLocaleString() : '---'}
                </td>
                <td className="px-3 py-2">
                  <span className="text-xs font-bold text-green-400">LONG</span>
                </td>
                <td className="px-3 py-2 text-gray-300 font-mono text-xs">
                  {trade.quantity ?? trade.eth_quantity ?? '---'}
                </td>
                <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(trade.entry_price)}</td>
                <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(trade.close_price)}</td>
                <td className="px-3 py-2 text-right">
                  <span className={`font-mono font-semibold text-xs ${pnlColor(trade.realized_pnl ?? 0)}`}>
                    {fmtUsd(trade.realized_pnl)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    trade.close_reason?.includes('PROFIT') ? 'bg-green-900/30 text-green-300' :
                    trade.close_reason?.includes('STOP') ? 'bg-red-900/30 text-red-300' :
                    trade.close_reason?.includes('TRAIL') ? 'bg-cyan-900/30 text-cyan-300' :
                    'text-gray-400'
                  }`}>
                    {trade.close_reason || '---'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

// ==============================================================================
// EQUITY CURVE TAB
// ==============================================================================

function EquityCurveTab({ ticker }: { ticker: TickerId }) {
  const [eqTimeFrame, setEqTimeFrame] = useState<TimeFrameId>('today')
  const isIntraday = eqTimeFrame === 'today'
  const eqDays = TIME_FRAMES.find(tf => tf.id === eqTimeFrame)?.days ?? 30

  const { data: equityData, isLoading: histLoading } = useAgapeSpotEquityCurve(ticker, eqDays)
  const { data: intradayData, isLoading: intradayLoading } = useAgapeSpotIntradayEquity(ticker)
  const meta = TICKER_META[ticker]
  const points = isIntraday
    ? (intradayData?.data_points || [])
    : (equityData?.data?.equity_curve || [])
  const gradientId = `eqFill-${ticker.replace('-', '')}`
  const isLoading = isIntraday ? intradayLoading : histLoading

  const startCap = equityData?.data?.starting_capital ?? 1000
  const drawdownPoints = useMemo(() => computeDrawdown(points, startCap), [points, startCap])
  const histPoints = equityData?.data?.equity_curve || []
  const heatmapDays = useMemo(() => buildHeatmapDays(histPoints), [histPoints])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    )
  }

  if (points.length === 0) {
    return (
      <SectionCard
        title={isIntraday ? `${meta.symbol} Today (5-min)` : `${meta.symbol} Equity Curve`}
        icon={<TrendingUp className={`w-5 h-5 ${meta.textActive}`} />}
        headerRight={<TimeFrameSelector selected={eqTimeFrame} onChange={setEqTimeFrame} />}
      >
        <EmptyBox message={isIntraday
          ? `No intraday snapshots for ${ticker} yet. The bot saves equity every 5 minutes.`
          : `No equity data for ${ticker} yet. Complete trades to populate this chart.`
        } />
      </SectionCard>
    )
  }

  return (
    <SectionCard
      title={isIntraday ? `${meta.symbol} Today (5-min)` : `${meta.symbol} Equity Curve`}
      icon={<TrendingUp className={`w-5 h-5 ${meta.textActive}`} />}
      headerRight={
        <div className="flex items-center gap-3">
          {isIntraday && intradayData && (
            <span className={`text-xs font-mono ${pnlColor(intradayData.day_pnl ?? 0)}`}>
              Day P&L: {fmtUsd(intradayData.day_pnl)}
            </span>
          )}
          <TimeFrameSelector selected={eqTimeFrame} onChange={setEqTimeFrame} />
        </div>
      }
    >
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={meta.hexColor} stopOpacity={0.3} />
                <stop offset="95%" stopColor={meta.hexColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey={isIntraday ? 'time' : 'date'}
              tick={{ fill: '#6b7280', fontSize: 11 }}
              tickFormatter={(v: string) => {
                if (isIntraday) {
                  return v?.slice(0, 5) || v
                }
                const d = new Date(v + 'T00:00:00')
                return `${d.getMonth() + 1}/${d.getDate()}`
              }}
            />
            <YAxis
              tick={{ fill: '#6b7280', fontSize: 11 }}
              tickFormatter={(v: number) => `$${v.toLocaleString()}`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: number) => [`$${value.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, 'Equity']}
              labelFormatter={(label: string) => isIntraday ? `Time: ${label}` : label}
            />
            <Area
              type="monotone"
              dataKey="equity"
              stroke={meta.hexColor}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              dot={(props: any) => {
                const { cx, cy, payload, key } = props
                if (!payload?.trades || payload.trades === 0) return <g key={key} />
                const color = (payload.daily_pnl ?? 0) >= 0 ? '#4ade80' : '#f87171'
                return <circle key={key} cx={cx} cy={cy} r={4} fill={color} stroke="#111827" strokeWidth={1.5} />
              }}
              activeDot={{ r: 5, strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {/* Drawdown sub-chart */}
      <DrawdownChart points={drawdownPoints} isIntraday={isIntraday} />
      {/* Daily P&L Heatmap (historical only) */}
      {!isIntraday && heatmapDays.length > 1 && (
        <div className="mt-4">
          <PnlHeatmap days={heatmapDays} />
        </div>
      )}
    </SectionCard>
  )
}

// ==============================================================================
// LOGS TAB
// ==============================================================================

function LogsTab({ ticker }: { ticker: TickerId }) {
  const { data: scanData, isLoading } = useAgapeSpotScanActivity(ticker, 40)
  const scans = scanData?.data || []
  const meta = TICKER_META[ticker]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    )
  }

  if (scans.length === 0) {
    return <EmptyBox message={`No scan activity for ${ticker} yet.`} />
  }

  return (
    <SectionCard title={`Scan Activity (${scans.length})`} icon={<Activity className={`w-5 h-5 ${meta.textActive}`} />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Time</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Price</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Signal</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Bayes</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">ML</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Prophet</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Outcome</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {scans.map((scan: any, i: number) => (
              <tr key={i} className="hover:bg-gray-800/30">
                <td className="px-3 py-2 text-gray-500 font-mono text-xs">
                  {scan.timestamp ? new Date(scan.timestamp).toLocaleTimeString() : '---'}
                </td>
                <td className="px-3 py-2 text-white font-mono text-xs">
                  {fmtPrice(scan.price ?? scan.eth_price ?? scan.current_price)}
                </td>
                <td className="px-3 py-2">
                  <span className={`text-xs font-semibold ${
                    scan.combined_signal === 'LONG' ? 'text-green-400' :
                    scan.combined_signal === 'SHORT' ? 'text-red-400' :
                    scan.combined_signal === 'RANGE_BOUND' ? 'text-yellow-400' :
                    'text-gray-500'
                  }`}>
                    {scan.combined_signal || '---'}
                    {scan.combined_confidence ? ` (${scan.combined_confidence})` : ''}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {scan.bayesian_probability != null
                    ? <span className={scan.bayesian_probability >= 0.55 ? 'text-green-400' : scan.bayesian_probability >= 0.45 ? 'text-yellow-400' : 'text-red-400'}>
                        {(scan.bayesian_probability * 100).toFixed(0)}%
                      </span>
                    : <span className="text-gray-600">---</span>
                  }
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {scan.ml_probability != null
                    ? <span className={scan.ml_probability >= 0.55 ? 'text-purple-400' : scan.ml_probability >= 0.45 ? 'text-yellow-400' : 'text-red-400'}>
                        {(scan.ml_probability * 100).toFixed(0)}%
                      </span>
                    : <span className="text-gray-600">---</span>
                  }
                </td>
                <td className="px-3 py-2 text-xs text-gray-400">{scan.oracle_advice || '---'}</td>
                <td className="px-3 py-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    scan.outcome?.includes('TRADED') ? 'bg-cyan-900/50 text-cyan-300' :
                    scan.outcome?.includes('ERROR') ? 'bg-red-900/50 text-red-300' :
                    scan.outcome?.includes('SKIP') ? 'bg-gray-800 text-gray-500' :
                    'bg-gray-800 text-gray-500'
                  }`}>
                    {scan.outcome || '---'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

// ==============================================================================
// SHARED UI PRIMITIVES
// ==============================================================================

function MetricCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-xl font-bold font-mono ${color}`}>{value}</div>
    </div>
  )
}

function SectionCard({ title, icon, children, headerRight }: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
  headerRight?: React.ReactNode
}) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          {icon}
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
        </div>
        {headerRight}
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

function TimeFrameSelector({ selected, onChange }: { selected: TimeFrameId; onChange: (id: TimeFrameId) => void }) {
  return (
    <div className="flex gap-1">
      {TIME_FRAMES.map((tf) => (
        <button
          key={tf.id}
          onClick={() => onChange(tf.id)}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            selected === tf.id
              ? 'bg-cyan-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'
          }`}
        >
          {tf.label}
        </button>
      ))}
    </div>
  )
}

// ==============================================================================
// ML SHADOW PANEL
// ==============================================================================

function MLShadowPanel({ ticker }: { ticker: string }) {
  const { data: mlData, error: mlError, mutate: refreshML } = useAgapeSpotMLStatus()
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const ml = mlData?.data
  const phase = ml?.phase ?? 'COLLECTING'
  const comp = ml?.shadow_comparison

  const phaseColors: Record<string, string> = {
    COLLECTING: 'bg-gray-700 text-gray-300',
    TRAINING: 'bg-blue-900/50 text-blue-400 border border-blue-700/40',
    SHADOW: 'bg-yellow-900/40 text-yellow-400 border border-yellow-700/40',
    ELIGIBLE: 'bg-green-900/40 text-green-400 border border-green-700/40',
    PROMOTED: 'bg-purple-900/40 text-purple-400 border border-purple-700/40',
  }

  const phaseLabels: Record<string, string> = {
    COLLECTING: 'Collecting Data',
    TRAINING: 'Model Trained',
    SHADOW: 'Shadow Running',
    ELIGIBLE: 'Ready to Promote',
    PROMOTED: 'Active (Live)',
  }

  async function mlAction(action: 'train' | 'promote' | 'revoke' | 'reject') {
    setActionLoading(action)
    setActionMessage(null)
    try {
      const res = await fetch(`${API}/api/agape-spot/ml/${action}`, { method: 'POST' })
      const json = await res.json()
      setActionMessage(json.message || (json.success ? 'Done' : 'Failed'))
      refreshML()
    } catch (e: any) {
      setActionMessage(`Error: ${e.message}`)
    } finally {
      setActionLoading(null)
    }
  }

  // Show informational state if ML module not available yet
  if (mlError || mlData?.data_unavailable) {
    return (
      <div className="text-sm text-gray-500">
        ML shadow advisor module loading... Shadow predictions will appear once the backend ML module is available.
      </div>
    )
  }

  // Loading state
  if (!mlData) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <RefreshCw className="w-4 h-4 animate-spin" /> Loading ML status...
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Phase badge + model info */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className={`px-2.5 py-1 rounded text-xs font-bold ${phaseColors[phase] || phaseColors.COLLECTING}`}>
            {phaseLabels[phase] || phase}
          </span>
          {ml?.is_trained && (
            <span className="text-xs text-gray-500">
              v{ml.model_version} &middot; {ml.samples ?? 0} samples
            </span>
          )}
        </div>
        {ml?.training_date && (
          <span className="text-xs text-gray-600">
            Trained {new Date(ml.training_date).toLocaleDateString()}
          </span>
        )}
      </div>

      {/* Shadow comparison stats */}
      {comp && comp.resolved_predictions > 0 && (
        <div>
          <div className="text-xs text-gray-400 mb-2">Shadow Comparison (ML vs Bayesian)</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-gray-800/50 rounded-lg p-2.5 text-center">
              <span className="text-gray-500 text-[10px] block">ML Brier</span>
              <span className={`font-mono font-bold text-sm ${comp.ml_brier <= comp.bayesian_brier ? 'text-green-400' : 'text-red-400'}`}>
                {comp.ml_brier.toFixed(4)}
              </span>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-2.5 text-center">
              <span className="text-gray-500 text-[10px] block">Bayes Brier</span>
              <span className="font-mono font-bold text-sm text-gray-300">{comp.bayesian_brier.toFixed(4)}</span>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-2.5 text-center">
              <span className="text-gray-500 text-[10px] block">Improvement</span>
              <span className={`font-mono font-bold text-sm ${comp.brier_improvement_pct > 0 ? 'text-green-400' : comp.brier_improvement_pct < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                {comp.brier_improvement_pct > 0 ? '+' : ''}{comp.brier_improvement_pct.toFixed(1)}%
              </span>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-2.5 text-center">
              <span className="text-gray-500 text-[10px] block">Resolved</span>
              <span className="font-mono font-bold text-sm text-white">{comp.resolved_predictions}</span>
            </div>
          </div>

          {/* Accuracy + Catastrophic miss rate */}
          <div className="grid grid-cols-3 gap-3 mt-2">
            <div className="bg-gray-800/50 rounded-lg p-2.5 text-center">
              <span className="text-gray-500 text-[10px] block">ML Accuracy</span>
              <span className="font-mono font-bold text-sm text-white">{(comp.ml_accuracy * 100).toFixed(1)}%</span>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-2.5 text-center">
              <span className="text-gray-500 text-[10px] block">Bayes Accuracy</span>
              <span className="font-mono font-bold text-sm text-gray-300">{(comp.bayesian_accuracy * 100).toFixed(1)}%</span>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-2.5 text-center">
              <span className="text-gray-500 text-[10px] block">Catastrophic Miss</span>
              <span className={`font-mono font-bold text-sm ${comp.catastrophic_miss_rate <= 0.10 ? 'text-green-400' : 'text-red-400'}`}>
                {(comp.catastrophic_miss_rate * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Promotion blockers */}
      {comp?.promotion_blockers && comp.promotion_blockers.length > 0 && phase !== 'PROMOTED' && (
        <div className="bg-gray-800/30 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1.5">Promotion Blockers</div>
          <ul className="space-y-1">
            {comp.promotion_blockers.map((b: string, i: number) => (
              <li key={i} className="text-xs text-yellow-400/80 flex items-start gap-1.5">
                <span className="text-yellow-500 mt-0.5">&#x2022;</span>
                {b}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Action buttons - always visible */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => mlAction('train')}
          disabled={actionLoading !== null}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-900/40 text-blue-400 border border-blue-700/40 hover:bg-blue-800/50 disabled:opacity-40 transition-colors"
        >
          {actionLoading === 'train' ? 'Training...' : ml?.is_trained ? 'Retrain Model' : 'Train Model'}
        </button>
        {phase !== 'PROMOTED' && ml?.is_trained && (
          <button
            onClick={() => mlAction('promote')}
            disabled={actionLoading !== null || phase !== 'ELIGIBLE'}
            title={phase !== 'ELIGIBLE' ? 'Not yet eligible - resolve promotion blockers first' : 'Promote ML to control live trading'}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-green-900/40 text-green-400 border border-green-700/40 hover:bg-green-800/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {actionLoading === 'promote' ? 'Promoting...' : 'Promote ML'}
          </button>
        )}
        {phase === 'PROMOTED' && (
          <button
            onClick={() => mlAction('revoke')}
            disabled={actionLoading !== null}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-900/40 text-red-400 border border-red-700/40 hover:bg-red-800/50 disabled:opacity-40 transition-colors"
          >
            {actionLoading === 'revoke' ? 'Revoking...' : 'Revoke ML'}
          </button>
        )}
        {ml?.is_trained && phase !== 'PROMOTED' && (
          <button
            onClick={() => mlAction('reject')}
            disabled={actionLoading !== null}
            title="Delete trained model and start fresh"
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-800 text-gray-400 border border-gray-700 hover:bg-gray-700 hover:text-red-400 disabled:opacity-40 transition-colors"
          >
            {actionLoading === 'reject' ? 'Discarding...' : 'Discard Model'}
          </button>
        )}
      </div>

      {/* Action feedback */}
      {actionMessage && (
        <div className="text-xs text-gray-400 bg-gray-800/40 rounded px-3 py-2">
          {actionMessage}
        </div>
      )}
    </div>
  )
}

// ==============================================================================
// BAYESIAN WIN TRACKER COMPONENTS
// ==============================================================================

function BayesianTrackerCompact({ tracker, color }: { tracker: WinTrackerData; color: string }) {
  const prob = (tracker.win_probability * 100).toFixed(0)
  const probColor = tracker.win_probability >= 0.55
    ? 'text-green-400'
    : tracker.win_probability >= 0.45
      ? 'text-yellow-400'
      : 'text-red-400'

  return (
    <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-700/50">
      <div className="flex items-center gap-2">
        <span className="text-gray-500 text-xs">Bayesian</span>
        {tracker.is_cold_start && (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-yellow-900/40 text-yellow-400 border border-yellow-700/40">
            LEARNING
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 text-xs font-mono">
        <span className={probColor}>{prob}%</span>
        <span className="text-gray-600">|</span>
        <RegimeDot label="+" prob={tracker.regime_probabilities.POSITIVE} />
        <RegimeDot label="-" prob={tracker.regime_probabilities.NEGATIVE} />
        <RegimeDot label="~" prob={tracker.regime_probabilities.NEUTRAL} />
      </div>
    </div>
  )
}

function RegimeDot({ label, prob }: { label: string; prob: number }) {
  const pct = (prob * 100).toFixed(0)
  const c = prob >= 0.55 ? 'text-green-400' : prob >= 0.45 ? 'text-yellow-400' : 'text-red-400'
  return (
    <span className={c} title={`${label === '+' ? 'Positive' : label === '-' ? 'Negative' : 'Neutral'} funding: ${pct}%`}>
      {label}{pct}
    </span>
  )
}

function BayesianTrackerDetail({ tracker, color }: { tracker: WinTrackerData; color: string }) {
  const prob = tracker.win_probability
  const regimes = [
    { key: 'POSITIVE', label: 'Positive Funding', wins: tracker.positive_funding_wins, losses: tracker.positive_funding_losses, prob: tracker.regime_probabilities.POSITIVE, dotColor: 'bg-green-400' },
    { key: 'NEGATIVE', label: 'Negative Funding', wins: tracker.negative_funding_wins, losses: tracker.negative_funding_losses, prob: tracker.regime_probabilities.NEGATIVE, dotColor: 'bg-red-400' },
    { key: 'NEUTRAL', label: 'Neutral Funding', wins: tracker.neutral_funding_wins, losses: tracker.neutral_funding_losses, prob: tracker.regime_probabilities.NEUTRAL, dotColor: 'bg-yellow-400' },
  ]

  const probBarWidth = Math.max(5, Math.min(95, prob * 100))
  const gatePosition = 50 // 0.50 gate threshold

  return (
    <div className="space-y-4">
      {/* Overall probability with gate visualization */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-gray-400 text-sm">Overall Win Probability</span>
          <div className="flex items-center gap-2">
            {tracker.is_cold_start && (
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-yellow-900/40 text-yellow-400 border border-yellow-700/40">
                LEARNING ({tracker.total_trades}/10)
              </span>
            )}
            {tracker.should_use_ml && (
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-purple-900/40 text-purple-400 border border-purple-700/40">
                ML READY
              </span>
            )}
            <span className={`text-lg font-bold font-mono ${prob >= 0.55 ? 'text-green-400' : prob >= 0.45 ? 'text-yellow-400' : 'text-red-400'}`}>
              {(prob * 100).toFixed(1)}%
            </span>
          </div>
        </div>
        {/* Probability bar with gate marker */}
        <div className="relative h-3 bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${prob >= 0.50 ? 'bg-green-500' : 'bg-red-500'}`}
            style={{ width: `${probBarWidth}%` }}
          />
          {/* Gate line at 50% */}
          <div
            className="absolute top-0 h-full w-0.5 bg-white/60"
            style={{ left: `${gatePosition}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-gray-600 mt-1">
          <span>0%</span>
          <span className="text-gray-500">50% gate</span>
          <span>100%</span>
        </div>
      </div>

      {/* Per-regime breakdown */}
      <div>
        <span className="text-gray-400 text-sm block mb-2">Regime Win Rates</span>
        <div className="space-y-2">
          {regimes.map((r) => {
            const total = r.wins + r.losses
            const barWidth = total > 0 ? Math.max(5, r.prob * 100) : 50
            const regimeColor = r.prob >= 0.55 ? 'text-green-400' : r.prob >= 0.45 ? 'text-yellow-400' : 'text-red-400'
            return (
              <div key={r.key}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${r.dotColor}`} />
                    <span className="text-gray-400 text-xs">{r.label}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs font-mono">
                    <span className="text-gray-500">{r.wins}W/{r.losses}L</span>
                    <span className={regimeColor}>{(r.prob * 100).toFixed(0)}%</span>
                  </div>
                </div>
                <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${r.prob >= 0.50 ? 'bg-green-500/60' : 'bg-red-500/60'}`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div className="bg-gray-800/50 rounded-lg p-2 text-center">
          <span className="text-gray-500 block">Trades Tracked</span>
          <span className="text-white font-mono font-bold">{tracker.total_trades}</span>
        </div>
        <div className="bg-gray-800/50 rounded-lg p-2 text-center">
          <span className="text-gray-500 block">Alpha / Beta</span>
          <span className="text-white font-mono font-bold">{tracker.alpha.toFixed(0)} / {tracker.beta.toFixed(0)}</span>
        </div>
        <div className="bg-gray-800/50 rounded-lg p-2 text-center">
          <span className="text-gray-500 block">Phase</span>
          <span className={`font-mono font-bold ${tracker.is_cold_start ? 'text-yellow-400' : tracker.should_use_ml ? 'text-purple-400' : 'text-green-400'}`}>
            {tracker.is_cold_start ? 'Cold Start' : tracker.should_use_ml ? 'ML Ready' : 'Bayesian'}
          </span>
        </div>
      </div>
    </div>
  )
}

// ==============================================================================
// ENHANCEMENT: Live Price Ticker Strip
// ==============================================================================

function PriceTickerStrip({ tickers }: { tickers: Record<string, TickerSummary> | undefined }) {
  if (!tickers) return null
  const coins = ['ETH-USD', 'BTC-USD', 'XRP-USD', 'SHIB-USD', 'DOGE-USD', 'MSTU-USD'] as const
  return (
    <div className="flex items-center gap-4 overflow-x-auto py-2 px-3 bg-gray-900/60 rounded-lg border border-gray-800/50">
      {coins.map(ticker => {
        const meta = TICKER_META[ticker]
        const data = tickers[ticker]
        if (!data) return null
        const ret = data.return_pct ?? 0
        return (
          <div key={ticker} className="flex items-center gap-2 whitespace-nowrap">
            <span className={`text-xs font-bold ${meta.textActive}`}>{meta.symbol}</span>
            <span className="text-white font-mono text-sm">{fmtPrice(data.current_price)}</span>
            <span className={`text-xs font-mono ${pnlColor(ret)}`}>
              {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ==============================================================================
// CAPITAL ALLOCATION RANKINGS
// ==============================================================================

interface AllocRanking {
  ticker: string
  score: number
  allocation_pct: number
  total_trades: number
  wins: number
  win_rate: number
  profit_factor: number
  total_pnl: number
  recent_pnl: number
}

function AllocationRankings({ allocator }: { allocator: { rankings: AllocRanking[]; total_tickers: number } | null | undefined }) {
  if (!allocator || !allocator.rankings || allocator.rankings.length === 0) return null

  const rankings = allocator.rankings

  return (
    <SectionCard
      title="Live Capital Allocation"
      icon={<BarChart3 className="w-5 h-5 text-purple-400" />}
    >
      <p className="text-xs text-gray-500 mb-3">
        Ranked by performance. Better performers get a bigger share of the live account balance.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-500 font-medium">#</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Ticker</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Allocation</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Score</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Win Rate</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Profit Factor</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Total P&L</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">24h P&L</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Trades</th>
            </tr>
          </thead>
          <tbody>
            {rankings.map((r, idx) => {
              const meta = TICKER_META[r.ticker] || TICKER_META['ALL']
              const barWidth = Math.max(r.allocation_pct * 100, 2)
              return (
                <tr key={r.ticker} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="px-3 py-2.5 text-gray-400 font-mono">{idx + 1}</td>
                  <td className="px-3 py-2.5">
                    <span className={`font-bold ${meta.textActive}`}>{meta.symbol}</span>
                    <span className="text-gray-500 text-xs ml-1.5">{meta.label}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-16 h-2 bg-gray-800 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${barWidth}%`, backgroundColor: meta.hexColor }}
                        />
                      </div>
                      <span className="text-white font-mono text-xs w-10 text-right">
                        {(r.allocation_pct * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-300 font-mono text-xs">
                    {r.score.toFixed(3)}
                  </td>
                  <td className="px-3 py-2.5 text-right text-white font-mono text-xs">
                    {r.total_trades > 0 ? `${(r.win_rate * 100).toFixed(0)}%` : '---'}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-xs">
                    <span className={r.profit_factor >= 1.5 ? 'text-emerald-400' : r.profit_factor >= 1.0 ? 'text-yellow-400' : 'text-red-400'}>
                      {r.total_trades > 0 ? r.profit_factor.toFixed(1) : '---'}
                    </span>
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs ${r.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {r.total_trades > 0 ? `$${r.total_pnl.toFixed(2)}` : '---'}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs ${r.recent_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {r.recent_pnl !== 0 ? `$${r.recent_pnl.toFixed(2)}` : '---'}
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-300 font-mono text-xs">
                    {r.total_trades}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

// ==============================================================================
// ENHANCEMENT: Per-coin card with sparkline
// ==============================================================================

function CoinCard({ ticker, data }: { ticker: string; data: TickerSummary | undefined }) {
  // Each CoinCard is its own component so the hook call is valid (not in a loop)
  const { data: intradayData } = useAgapeSpotIntradayEquity(ticker)
  // Response shape: { data_points: [{ time, equity, ... }], day_pnl, ... }
  const sparkPoints = intradayData?.data_points || []
  const dayPnl = intradayData?.day_pnl ?? null

  const meta = TICKER_META[ticker]
  const pnl = data?.total_pnl ?? 0
  const returnPct = data?.return_pct ?? 0

  return (
    <div className={`rounded-xl border p-4 ${meta.bgCard} ${meta.borderCard} transition-colors`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`font-bold text-lg ${meta.textActive}`}>{meta.symbol}</span>
          <span className="text-gray-500 text-xs">{meta.label}</span>
        </div>
        <span className="text-white font-mono text-sm">{fmtPrice(data?.current_price)}</span>
      </div>
      <div className="grid grid-cols-2 gap-y-2 text-sm">
        <div>
          <span className="text-gray-500 text-xs">P&L</span>
          <p className={`font-mono font-semibold ${pnlColor(pnl)}`}>{fmtUsd(pnl)}</p>
        </div>
        <div>
          <span className="text-gray-500 text-xs">Return</span>
          <p className={`font-mono font-semibold ${pnlColor(returnPct)}`}>{fmtPct(returnPct)}</p>
        </div>
        <div>
          <span className="text-gray-500 text-xs">Open</span>
          <p className="text-white font-mono">{data?.open_positions ?? 0}</p>
        </div>
        <div>
          <span className="text-gray-500 text-xs">Trades</span>
          <p className="text-white font-mono">{data?.total_trades ?? 0}</p>
        </div>
        <div>
          <span className="text-gray-500 text-xs">Win Rate</span>
          <p className="text-white font-mono">
            {data?.win_rate != null ? `${data.win_rate.toFixed(1)}%` : '---'}
          </p>
        </div>
        <div>
          <span className="text-gray-500 text-xs">Day P&L</span>
          <p className={`font-mono ${pnlColor(dayPnl ?? 0)}`}>
            {dayPnl != null ? fmtUsd(dayPnl) : '---'}
          </p>
        </div>
      </div>
      {/* Bayesian Win Tracker */}
      {data?.win_tracker && (
        <BayesianTrackerCompact tracker={data.win_tracker} color={meta.textActive} />
      )}
      {/* Sparkline: tiny intraday equity chart */}
      {sparkPoints.length > 1 && (
        <div className="h-10 mt-2 -mx-1">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkPoints} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`spark-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={meta.hexColor} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={meta.hexColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="equity"
                stroke={meta.hexColor}
                strokeWidth={1.5}
                fill={`url(#spark-${ticker})`}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

// ==============================================================================
// ENHANCEMENT: Drawdown chart
// ==============================================================================

function DrawdownChart({ points, isIntraday }: { points: any[]; isIntraday: boolean }) {
  if (!points || points.length < 2) return null
  const minDD = Math.min(...points.map(p => p.drawdown ?? 0))
  // No drawdown to show
  if (minDD >= -0.01) return null

  return (
    <div className="mt-3">
      <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
        <TrendingDown className="w-3 h-3" /> Drawdown
      </div>
      <div className="h-20">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 0, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="drawdownFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey={isIntraday ? 'time' : 'date'} hide />
            <YAxis
              tick={{ fill: '#6b7280', fontSize: 10 }}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
              width={45}
              domain={['dataMin', 0]}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: number) => [`${value.toFixed(2)}%`, 'Drawdown']}
            />
            <Area
              type="monotone"
              dataKey="drawdown"
              stroke="#ef4444"
              strokeWidth={1.5}
              fill="url(#drawdownFill)"
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ==============================================================================
// ENHANCEMENT: Daily P&L Heatmap
// ==============================================================================

function PnlHeatmap({ days }: { days: { date: string; pnl: number | null; trades: number }[] }) {
  if (!days || days.length < 2) return null

  // Find max abs P&L for intensity scaling
  const maxAbs = Math.max(
    ...days.filter(d => d.pnl != null).map(d => Math.abs(d.pnl!)),
    1, // prevent division by zero
  )

  function cellColor(pnl: number | null): string {
    if (pnl == null || pnl === 0) return 'bg-gray-800'
    const intensity = Math.min(Math.abs(pnl) / maxAbs, 1)
    if (pnl > 0) {
      if (intensity > 0.6) return 'bg-green-500'
      if (intensity > 0.3) return 'bg-green-600'
      return 'bg-green-800'
    }
    if (intensity > 0.6) return 'bg-red-500'
    if (intensity > 0.3) return 'bg-red-600'
    return 'bg-red-800'
  }

  return (
    <SectionCard
      title="Daily P&L Map"
      icon={<Calendar className="w-5 h-5 text-gray-400" />}
    >
      <div className="flex gap-[3px] flex-wrap">
        {days.map((d, i) => (
          <div
            key={i}
            title={`${d.date}: ${d.pnl != null ? fmtUsd(d.pnl) : 'No trades'}${d.trades ? ` (${d.trades} trade${d.trades > 1 ? 's' : ''})` : ''}`}
            className={`w-3.5 h-3.5 rounded-sm ${cellColor(d.pnl)} cursor-default transition-colors hover:ring-1 hover:ring-white/30`}
          />
        ))}
      </div>
      <div className="flex items-center gap-3 mt-2 text-[10px] text-gray-500">
        <div className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded-sm bg-gray-800" /> No trades</div>
        <div className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded-sm bg-red-800" /> Loss</div>
        <div className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded-sm bg-red-500" /> Big loss</div>
        <div className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded-sm bg-green-800" /> Win</div>
        <div className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded-sm bg-green-500" /> Big win</div>
      </div>
    </SectionCard>
  )
}

// ==============================================================================
// SHARED UI PRIMITIVES (kept at bottom)
// ==============================================================================

function EmptyBox({ message }: { message: string }) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
      <Eye className="w-10 h-10 text-gray-700 mx-auto mb-3" />
      <p className="text-gray-500 text-sm">{message}</p>
    </div>
  )
}
