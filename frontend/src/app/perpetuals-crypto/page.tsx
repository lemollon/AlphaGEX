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
  Zap,
  Globe,
  DollarSign,
  Shield,
  Target,
  ArrowUpDown,
  Settings,
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'

// ==============================================================================
// TYPES
// ==============================================================================

type CoinId = 'ALL' | 'ETH' | 'BTC' | 'XRP' | 'DOGE' | 'SHIB'

// ==============================================================================
// CONSTANTS
// ==============================================================================

const API = process.env.NEXT_PUBLIC_API_URL || ''

const COINS: CoinId[] = ['ALL', 'ETH', 'BTC', 'XRP', 'DOGE', 'SHIB']

const COIN_META: Record<CoinId, {
  symbol: string; label: string; instrument: string; hexColor: string;
  bgActive: string; borderActive: string; textActive: string;
  bgCard: string; borderCard: string;
  apiPrefix: string; priceKey: string; priceField: string; priceDecimals: number;
  quantityLabel: string; startingCapital: number;
}> = {
  'ALL': {
    symbol: 'ALL', label: 'All Perpetuals', instrument: '', hexColor: '#06B6D4',
    bgActive: 'bg-cyan-600', borderActive: 'border-cyan-500', textActive: 'text-cyan-400',
    bgCard: 'bg-cyan-950/30', borderCard: 'border-cyan-700/40',
    apiPrefix: '', priceKey: '', priceField: '', priceDecimals: 2,
    quantityLabel: '', startingCapital: 50000,
  },
  'ETH': {
    symbol: 'ETH', label: 'Ethereum', instrument: 'ETH-PERP', hexColor: '#D946EF',
    bgActive: 'bg-fuchsia-600', borderActive: 'border-fuchsia-500', textActive: 'text-fuchsia-400',
    bgCard: 'bg-fuchsia-950/30', borderCard: 'border-fuchsia-700/40',
    apiPrefix: '/api/agape-eth-perp', priceKey: 'current_eth_price', priceField: 'eth_price', priceDecimals: 2,
    quantityLabel: 'ETH', startingCapital: 12500,
  },
  'BTC': {
    symbol: 'BTC', label: 'Bitcoin', instrument: 'BTC-PERP', hexColor: '#F97316',
    bgActive: 'bg-orange-600', borderActive: 'border-orange-500', textActive: 'text-orange-400',
    bgCard: 'bg-orange-950/30', borderCard: 'border-orange-700/40',
    apiPrefix: '/api/agape-btc-perp', priceKey: 'current_btc_price', priceField: 'btc_price', priceDecimals: 2,
    quantityLabel: 'BTC', startingCapital: 25000,
  },
  'XRP': {
    symbol: 'XRP', label: 'Ripple', instrument: 'XRP-PERP', hexColor: '#0EA5E9',
    bgActive: 'bg-sky-600', borderActive: 'border-sky-500', textActive: 'text-sky-400',
    bgCard: 'bg-sky-950/30', borderCard: 'border-sky-700/40',
    apiPrefix: '/api/agape-xrp-perp', priceKey: 'current_xrp_price', priceField: 'xrp_price', priceDecimals: 4,
    quantityLabel: 'XRP', startingCapital: 9000,
  },
  'DOGE': {
    symbol: 'DOGE', label: 'Dogecoin', instrument: 'DOGE-PERP', hexColor: '#FACC15',
    bgActive: 'bg-yellow-600', borderActive: 'border-yellow-500', textActive: 'text-yellow-400',
    bgCard: 'bg-yellow-950/30', borderCard: 'border-yellow-700/40',
    apiPrefix: '/api/agape-doge-perp', priceKey: 'current_doge_price', priceField: 'doge_price', priceDecimals: 6,
    quantityLabel: 'DOGE', startingCapital: 2500,
  },
  'SHIB': {
    symbol: 'SHIB', label: 'Shiba Inu', instrument: 'SHIB-PERP', hexColor: '#FB7185',
    bgActive: 'bg-rose-600', borderActive: 'border-rose-500', textActive: 'text-rose-400',
    bgCard: 'bg-rose-950/30', borderCard: 'border-rose-700/40',
    apiPrefix: '/api/agape-shib-perp', priceKey: 'current_shib_price', priceField: 'shib_price', priceDecimals: 8,
    quantityLabel: 'SHIB', startingCapital: 1000,
  },
}

const ACTIVE_COINS = ['ETH', 'BTC', 'XRP', 'DOGE', 'SHIB'] as const
type ActiveCoinId = typeof ACTIVE_COINS[number]

const SECTION_TABS = [
  { id: 'overview' as const,    label: 'Overview',      icon: Layers },
  { id: 'positions' as const,   label: 'Positions',     icon: Wallet },
  { id: 'performance' as const, label: 'Performance',   icon: BarChart3 },
  { id: 'equity' as const,      label: 'Equity Curve',  icon: TrendingUp },
  { id: 'activity' as const,    label: 'Activity',      icon: Activity },
  { id: 'history' as const,     label: 'History',       icon: History },
]
type SectionTabId = typeof SECTION_TABS[number]['id']

const TOTAL_CAPITAL = 50000

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
// SWR HOOKS (per-coin, using each bot's API)
// ==============================================================================

function usePerpStatus(coin: CoinId) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/status` : null, fetcher, { refreshInterval: 10_000 })
}

function usePerpPerformance(coin: CoinId) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/performance` : null, fetcher, { refreshInterval: 30_000 })
}

function usePerpPositions(coin: CoinId) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/positions` : null, fetcher, { refreshInterval: 10_000 })
}

function usePerpEquityCurve(coin: CoinId, days: number = 30) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/equity-curve?days=${days}` : null, fetcher, { refreshInterval: 30_000 })
}

function usePerpIntradayEquity(coin: CoinId) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/equity-curve/intraday` : null, fetcher, { refreshInterval: 15_000 })
}

function usePerpClosedTrades(coin: CoinId, limit: number = 50) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/closed-trades?limit=${limit}` : null, fetcher, { refreshInterval: 60_000 })
}

function usePerpScanActivity(coin: CoinId, limit: number = 30) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/scan-activity?limit=${limit}` : null, fetcher, { refreshInterval: 15_000 })
}

function usePerpSnapshot(coin: CoinId) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/snapshot` : null, fetcher, { refreshInterval: 15_000 })
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

function fmtPrice(val: number | null | undefined, decimals: number = 2): string {
  if (val == null) return '---'
  return `$${val.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}

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

export default function PerpetualsCryptoPage() {
  const [selectedCoin, setSelectedCoin] = useState<CoinId>('ALL')
  const [activeTab, setActiveTab] = useState<SectionTabId>('overview')
  const sidebarPadding = useSidebarPadding()

  // Fetch all 5 bots status for the combined view and price ticker
  const { data: ethStatusData, isLoading: ethLoading, mutate: refreshEth } = useSWR('/api/agape-eth-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: btcStatusData, isLoading: btcLoading, mutate: refreshBtc } = useSWR('/api/agape-btc-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: xrpStatusData, isLoading: xrpLoading, mutate: refreshXrp } = useSWR('/api/agape-xrp-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: dogeStatusData, isLoading: dogeLoading, mutate: refreshDoge } = useSWR('/api/agape-doge-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: shibStatusData, isLoading: shibLoading, mutate: refreshShib } = useSWR('/api/agape-shib-perp/status', fetcher, { refreshInterval: 10_000 })

  // Fetch all 5 performance for combined stats
  const { data: ethPerfData } = useSWR('/api/agape-eth-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: btcPerfData } = useSWR('/api/agape-btc-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: xrpPerfData } = useSWR('/api/agape-xrp-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: dogePerfData } = useSWR('/api/agape-doge-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: shibPerfData } = useSWR('/api/agape-shib-perp/performance', fetcher, { refreshInterval: 30_000 })

  const isAllView = selectedCoin === 'ALL'
  const allLoading = ethLoading && btcLoading && xrpLoading && dogeLoading && shibLoading

  const refreshAll = () => { refreshEth(); refreshBtc(); refreshXrp(); refreshDoge(); refreshShib() }

  // Build per-coin summary data for the combined view
  const coinSummaries = useMemo(() => {
    const build = (statusData: any, perfData: any, coin: CoinId) => {
      const status = statusData?.data
      const perf = perfData?.data
      const pa = status?.paper_account
      const meta = COIN_META[coin]
      return {
        coin,
        price: status?.[meta.priceKey] ?? null,
        openPositions: status?.open_positions ?? 0,
        unrealizedPnl: status?.total_unrealized_pnl ?? 0,
        totalPnl: perf?.total_pnl ?? pa?.cumulative_pnl ?? 0,
        returnPct: perf?.return_pct ?? pa?.return_pct ?? 0,
        winRate: perf?.win_rate ?? pa?.win_rate ?? null,
        totalTrades: perf?.total_trades ?? pa?.total_trades ?? 0,
        startingCapital: pa?.starting_capital ?? status?.starting_capital ?? meta.startingCapital,
        currentBalance: pa?.current_balance ?? meta.startingCapital,
        isActive: status?.status === 'ACTIVE',
        mode: status?.mode ?? 'paper',
      }
    }
    return {
      ETH: build(ethStatusData, ethPerfData, 'ETH'),
      BTC: build(btcStatusData, btcPerfData, 'BTC'),
      XRP: build(xrpStatusData, xrpPerfData, 'XRP'),
      DOGE: build(dogeStatusData, dogePerfData, 'DOGE'),
      SHIB: build(shibStatusData, shibPerfData, 'SHIB'),
    }
  }, [ethStatusData, btcStatusData, xrpStatusData, dogeStatusData, shibStatusData, ethPerfData, btcPerfData, xrpPerfData, dogePerfData, shibPerfData])

  // Loading state
  if (allLoading && !ethStatusData && !btcStatusData && !xrpStatusData && !dogeStatusData && !shibStatusData) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen bg-gray-950">
          <div className="text-center space-y-3">
            <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin mx-auto" />
            <p className="text-gray-400 text-sm">Loading Perpetuals Crypto...</p>
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

          {/* PAGE HEADER */}
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl md:text-3xl font-bold text-white">
                  AGAPE <span className="text-cyan-400">Perpetual</span>
                </h1>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-green-900/40 border border-green-500/40 rounded-full text-xs font-semibold text-green-400">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  24/7 PERPETUAL - ALWAYS OPEN
                </span>
              </div>
              <p className="text-gray-500 text-sm mt-1">
                24/7 Perpetual Contract Trading: ETH, BTC, XRP, DOGE, SHIB
              </p>
            </div>
            <button
              onClick={refreshAll}
              disabled={allLoading}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
              title="Refresh All"
            >
              <RefreshCw className={`w-4 h-4 ${allLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* LIVE PRICE TICKER STRIP */}
          <PriceTickerStrip summaries={coinSummaries} />

          {/* COIN SELECTOR */}
          <div className="flex gap-2 overflow-x-auto pb-1">
            {COINS.map((coin) => {
              const meta = COIN_META[coin]
              const isActive = selectedCoin === coin
              const summary = coin !== 'ALL' ? coinSummaries[coin as ActiveCoinId] : null
              return (
                <button
                  key={coin}
                  onClick={() => { setSelectedCoin(coin); setActiveTab('overview') }}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-all whitespace-nowrap ${
                    isActive
                      ? `${meta.bgActive} border-transparent text-white shadow-lg`
                      : 'bg-gray-900 border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white hover:border-gray-600'
                  }`}
                >
                  <span className="font-bold">{meta.symbol}</span>
                  {coin !== 'ALL' && summary?.price != null && (
                    <span className={`text-xs font-mono ${isActive ? 'text-white/80' : 'text-gray-500'}`}>
                      {fmtPrice(summary.price, meta.priceDecimals)}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* ALL VIEW - Combined Summary */}
          {isAllView && <AllCoinsDashboard summaries={coinSummaries} />}

          {/* SINGLE COIN VIEW */}
          {!isAllView && (
            <>
              {/* Coin header stats */}
              <SingleCoinHeader coin={selectedCoin} summaries={coinSummaries} />

              {/* Section Tabs */}
              <div className="flex gap-1.5 border-b border-gray-800 pb-2 overflow-x-auto">
                {SECTION_TABS.map((tab) => {
                  const isActive = activeTab === tab.id
                  const meta = COIN_META[selectedCoin]
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
                {activeTab === 'overview' && <OverviewTab coin={selectedCoin} />}
                {activeTab === 'positions' && <PositionsTab coin={selectedCoin} />}
                {activeTab === 'performance' && <PerformanceTab coin={selectedCoin} />}
                {activeTab === 'equity' && <EquityCurveTab coin={selectedCoin} />}
                {activeTab === 'activity' && <ActivityTab coin={selectedCoin} />}
                {activeTab === 'history' && <HistoryTab coin={selectedCoin} />}
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

function AllCoinsDashboard({ summaries }: { summaries: Record<ActiveCoinId, any> }) {
  // Aggregate totals
  const totalPnl = ACTIVE_COINS.reduce((s, c) => s + (summaries[c]?.totalPnl ?? 0), 0)
  const totalReturn = TOTAL_CAPITAL > 0 ? (totalPnl / TOTAL_CAPITAL) * 100 : 0
  const totalUnrealized = ACTIVE_COINS.reduce((s, c) => s + (summaries[c]?.unrealizedPnl ?? 0), 0)
  const totalTrades = ACTIVE_COINS.reduce((s, c) => s + (summaries[c]?.totalTrades ?? 0), 0)
  const totalPositions = ACTIVE_COINS.reduce((s, c) => s + (summaries[c]?.openPositions ?? 0), 0)

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

      {/* Per-coin summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {ACTIVE_COINS.map((coin) => (
          <CoinCard key={coin} coin={coin} data={summaries[coin]} />
        ))}
      </div>

      {/* Recent activity across all coins */}
      <AllCoinsRecentTrades />
    </div>
  )
}

function AllCoinsRecentTrades() {
  const { data: ethClosed } = useSWR('/api/agape-eth-perp/closed-trades?limit=10', fetcher, { refreshInterval: 60_000 })
  const { data: btcClosed } = useSWR('/api/agape-btc-perp/closed-trades?limit=10', fetcher, { refreshInterval: 60_000 })
  const { data: xrpClosed } = useSWR('/api/agape-xrp-perp/closed-trades?limit=10', fetcher, { refreshInterval: 60_000 })
  const { data: dogeClosed } = useSWR('/api/agape-doge-perp/closed-trades?limit=10', fetcher, { refreshInterval: 60_000 })
  const { data: shibClosed } = useSWR('/api/agape-shib-perp/closed-trades?limit=10', fetcher, { refreshInterval: 60_000 })

  const allTrades = useMemo(() => {
    const tagged = (data: any, coin: CoinId) =>
      (data?.data || []).map((t: any) => ({ ...t, _coin: coin }))
    const combined = [
      ...tagged(ethClosed, 'ETH'),
      ...tagged(btcClosed, 'BTC'),
      ...tagged(xrpClosed, 'XRP'),
      ...tagged(dogeClosed, 'DOGE'),
      ...tagged(shibClosed, 'SHIB'),
    ]
    combined.sort((a, b) => {
      const ta = a.close_time ? new Date(a.close_time).getTime() : 0
      const tb = b.close_time ? new Date(b.close_time).getTime() : 0
      return tb - ta
    })
    return combined.slice(0, 25)
  }, [ethClosed, btcClosed, xrpClosed, dogeClosed, shibClosed])

  if (allTrades.length === 0) return null

  return (
    <SectionCard title="Recent Closed Trades (All Coins)" icon={<History className="w-5 h-5 text-gray-400" />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Time</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Coin</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Side</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Quantity</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Entry</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Exit</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">P&L</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {allTrades.map((t: any, i: number) => {
              const meta = COIN_META[t._coin as CoinId]
              const dec = meta.priceDecimals
              return (
                <tr key={i} className="hover:bg-gray-800/30">
                  <td className="px-3 py-2 text-gray-500 font-mono text-xs">
                    {t.close_time ? new Date(t.close_time).toLocaleString() : '---'}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`font-bold text-xs ${meta.textActive}`}>{meta.symbol}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs font-bold ${t.side === 'long' ? 'text-green-400' : 'text-red-400'}`}>
                      {t.side?.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-white font-mono text-xs">
                    {t.quantity ?? t.contracts ?? '---'} {meta.quantityLabel}-PERP
                  </td>
                  <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(t.entry_price, dec)}</td>
                  <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(t.close_price, dec)}</td>
                  <td className="px-3 py-2 text-right">
                    <span className={`font-mono font-semibold text-xs ${pnlColor(t.realized_pnl ?? 0)}`}>
                      {fmtUsd(t.realized_pnl)}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      t.close_reason?.includes('SAR') ? 'bg-violet-900/30 text-violet-300' :
                      t.close_reason?.includes('TRAIL') ? 'bg-cyan-900/30 text-cyan-300' :
                      t.close_reason?.includes('PROFIT') ? 'bg-green-900/30 text-green-300' :
                      t.close_reason?.includes('STOP') ? 'bg-red-900/30 text-red-300' :
                      t.close_reason?.includes('LIQUIDAT') ? 'bg-red-900/30 text-red-300' :
                      'text-gray-400'
                    }`}>
                      {t.close_reason || '---'}
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

function SingleCoinHeader({ coin, summaries }: { coin: CoinId; summaries: Record<string, any> }) {
  const meta = COIN_META[coin]
  const summary = summaries[coin]

  return (
    <div className={`rounded-xl border p-4 ${meta.bgCard} ${meta.borderCard}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className={`text-2xl font-bold ${meta.textActive}`}>{meta.symbol}</span>
          <span className="text-gray-400 text-sm">{meta.label}</span>
          <ArrowRight className="w-4 h-4 text-gray-600" />
          <span className="text-white font-mono text-lg">{fmtPrice(summary?.price, meta.priceDecimals)}</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="text-right">
            <span className="text-gray-500 text-xs block">Open</span>
            <span className="text-white font-mono">{summary?.openPositions ?? 0}</span>
          </div>
          <div className="text-right">
            <span className="text-gray-500 text-xs block">Unrealized</span>
            <span className={`font-mono ${pnlColor(summary?.unrealizedPnl ?? 0)}`}>{fmtUsd(summary?.unrealizedPnl)}</span>
          </div>
          <div className="text-right">
            <span className="text-gray-500 text-xs block">Mode</span>
            <span className={`font-mono text-xs ${summary?.mode === 'live' ? 'text-green-400' : 'text-yellow-400'}`}>
              {(summary?.mode || 'paper').toUpperCase()}
            </span>
          </div>
        </div>
      </div>
      <p className="text-gray-500 text-xs">
        Perpetual Contract: {meta.instrument} | Directional trading (Long & Short) | {fmtUsd(meta.startingCapital)} starting capital
      </p>
    </div>
  )
}

// ==============================================================================
// OVERVIEW TAB (single coin)
// ==============================================================================

function OverviewTab({ coin }: { coin: CoinId }) {
  const { data: statusData } = usePerpStatus(coin)
  const { data: perfData } = usePerpPerformance(coin)
  const { data: snapshotData } = usePerpSnapshot(coin)

  const status = statusData?.data
  const perf = perfData?.data
  const meta = COIN_META[coin]
  const pa = status?.paper_account

  const startingCapital = pa?.starting_capital ?? status?.starting_capital ?? meta.startingCapital
  const currentBalance = pa?.current_balance ?? startingCapital
  const cumulativePnl = perf?.total_pnl ?? pa?.cumulative_pnl ?? 0
  const returnPct = perf?.return_pct ?? pa?.return_pct ?? 0
  const winRate = perf?.win_rate ?? pa?.win_rate
  const totalTrades = perf?.total_trades ?? pa?.total_trades ?? 0
  const aggressive = status?.aggressive_features || {}

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

      {/* Aggressive Features */}
      <SectionCard title="Aggressive Features" icon={<Zap className={`w-5 h-5 ${meta.textActive}`} />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div className="flex items-start gap-2">
            <Shield className={`w-4 h-4 ${meta.textActive} mt-0.5 flex-shrink-0`} />
            <div>
              <span className="text-gray-500">No-Loss Trailing</span>
              <p className={`font-mono font-semibold ${aggressive.use_no_loss_trailing ? 'text-green-400' : 'text-gray-500'}`}>
                {aggressive.use_no_loss_trailing ? 'ACTIVE' : 'OFF'}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <RefreshCw className={`w-4 h-4 ${meta.textActive} mt-0.5 flex-shrink-0`} />
            <div>
              <span className="text-gray-500">Stop-and-Reverse</span>
              <p className={`font-mono font-semibold ${aggressive.use_sar ? 'text-green-400' : 'text-gray-500'}`}>
                {aggressive.use_sar ? 'ACTIVE' : 'OFF'}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Target className={`w-4 h-4 ${meta.textActive} mt-0.5 flex-shrink-0`} />
            <div>
              <span className="text-gray-500">Consecutive Losses</span>
              <p className={`font-mono font-semibold ${(aggressive.consecutive_losses || 0) >= 3 ? 'text-red-400' : 'text-white'}`}>
                {aggressive.consecutive_losses || 0}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <ArrowUpDown className={`w-4 h-4 ${meta.textActive} mt-0.5 flex-shrink-0`} />
            <div>
              <span className="text-gray-500">Direction Tracker</span>
              <p className="text-white font-mono text-xs">
                L: {aggressive.direction_tracker?.long_win_rate != null ? `${(aggressive.direction_tracker.long_win_rate * 100).toFixed(0)}%` : '--'}
                {' '}S: {aggressive.direction_tracker?.short_win_rate != null ? `${(aggressive.direction_tracker.short_win_rate * 100).toFixed(0)}%` : '--'}
              </p>
            </div>
          </div>
        </div>
      </SectionCard>

      {/* Market Snapshot (if available) */}
      {snapshotData?.data && (
        <MarketSnapshotPanel data={snapshotData.data} coin={coin} />
      )}

      {/* Configuration */}
      <SectionCard title="Configuration" icon={<Settings className={`w-5 h-5 ${meta.textActive}`} />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Instrument</span>
            <p className={`font-mono ${meta.textActive}`}>{status?.instrument || meta.instrument}</p>
          </div>
          <div>
            <span className="text-gray-500">Direction</span>
            <p className="text-white font-mono">LONG & SHORT</p>
          </div>
          <div>
            <span className="text-gray-500">Risk Per Trade</span>
            <p className="text-white font-mono">{status?.risk_per_trade_pct ?? 5}%</p>
          </div>
          <div>
            <span className="text-gray-500">Max Quantity</span>
            <p className="text-white font-mono">{status?.max_contracts ?? status?.max_quantity ?? 10} {meta.quantityLabel}</p>
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
          <div>
            <span className="text-gray-500">Market</span>
            <p className="text-cyan-400 font-mono">Perpetual 24/7</p>
          </div>
        </div>
      </SectionCard>
    </div>
  )
}

// ==============================================================================
// MARKET SNAPSHOT PANEL (compact inline version for overview)
// ==============================================================================

function MarketSnapshotPanel({ data, coin }: { data: any; coin: CoinId }) {
  const meta = COIN_META[coin]
  const signalColor = (signal: string) => {
    if (['LONG', 'BULLISH'].some(s => signal?.includes(s))) return 'text-green-400'
    if (['SHORT', 'BEARISH'].some(s => signal?.includes(s))) return 'text-red-400'
    if (signal === 'RANGE_BOUND') return 'text-yellow-400'
    return 'text-gray-400'
  }

  return (
    <SectionCard
      title={`Market Structure (${meta.symbol})`}
      icon={<Globe className={`w-5 h-5 ${meta.textActive}`} />}
      headerRight={
        data.signals?.combined_signal && (
          <span className={`px-3 py-1 rounded-full font-semibold text-xs ${signalColor(data.signals.combined_signal)}`}>
            {data.signals.combined_signal} {data.signals.combined_confidence && `(${data.signals.combined_confidence})`}
          </span>
        )
      }
    >
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <span className="text-gray-500">Funding Regime</span>
          <p className={signalColor(data.funding?.regime)}>{data.funding?.regime || '---'}</p>
        </div>
        <div>
          <span className="text-gray-500">L/S Ratio</span>
          <p className="text-white font-mono">{data.long_short?.ratio?.toFixed(2) || '---'}</p>
        </div>
        <div>
          <span className="text-gray-500">Crypto GEX</span>
          <p className={signalColor(data.crypto_gex?.regime)}>{data.crypto_gex?.regime || '---'}</p>
        </div>
        <div>
          <span className="text-gray-500">Squeeze Risk</span>
          <p className={
            data.signals?.squeeze_risk === 'HIGH' ? 'text-red-400' :
            data.signals?.squeeze_risk === 'ELEVATED' ? 'text-orange-400' :
            'text-green-400'
          }>{data.signals?.squeeze_risk || '---'}</p>
        </div>
      </div>
    </SectionCard>
  )
}

// ==============================================================================
// POSITIONS TAB
// ==============================================================================

function PositionsTab({ coin }: { coin: CoinId }) {
  const { data: posData, isLoading } = usePerpPositions(coin)
  const positions = posData?.data || []
  const meta = COIN_META[coin]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    )
  }

  if (positions.length === 0) {
    return <EmptyBox message={`No open positions for ${meta.symbol}. The bot is scanning for opportunities.`} />
  }

  return (
    <div className="space-y-3">
      {positions.map((pos: any, idx: number) => (
        <div key={pos.position_id || idx} className={`rounded-xl border p-4 ${meta.bgCard} ${meta.borderCard}`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <span className={`px-2 py-1 rounded text-xs font-bold ${
                pos.side === 'long' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
              }`}>
                {pos.side?.toUpperCase()}
              </span>
              <span className="text-white font-mono font-semibold">
                {pos.quantity ?? pos.contracts} {meta.quantityLabel}-PERP @ {fmtPrice(pos.entry_price, meta.priceDecimals)}
              </span>
              {pos.trailing_active && (
                <span className={`px-2 py-0.5 ${meta.bgCard} ${meta.textActive} text-xs rounded font-mono`}>
                  TRAILING @ {fmtPrice(pos.current_stop, meta.priceDecimals)}
                </span>
              )}
            </div>
            <span className={`text-lg font-mono font-bold ${pnlColor(pos.unrealized_pnl ?? 0)}`}>
              {fmtUsd(pos.unrealized_pnl)}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
            <div>
              <span className="text-gray-500">Stop Loss</span>
              <p className="text-red-400 font-mono">{pos.stop_loss ? fmtPrice(pos.stop_loss, meta.priceDecimals) : 'Trailing'}</p>
            </div>
            <div>
              <span className="text-gray-500">Take Profit</span>
              <p className="text-green-400 font-mono">{pos.take_profit ? fmtPrice(pos.take_profit, meta.priceDecimals) : 'No-Loss Trail'}</p>
            </div>
            <div>
              <span className="text-gray-500">Funding Regime</span>
              <p className="text-gray-300">{pos.funding_regime_at_entry || '---'}</p>
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

function PerformanceTab({ coin }: { coin: CoinId }) {
  const { data: perfData, isLoading } = usePerpPerformance(coin)
  const perf = perfData?.data ?? perfData

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    )
  }

  if (!perf) {
    return <EmptyBox message={`No performance data available for ${COIN_META[coin].symbol}.`} />
  }

  const meta = COIN_META[coin]

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
      <ClosedTradesTable coin={coin} />
    </div>
  )
}

function ClosedTradesTable({ coin }: { coin: CoinId }) {
  const { data: closedData } = usePerpClosedTrades(coin, 50)
  const trades = closedData?.data || []
  const meta = COIN_META[coin]

  if (trades.length === 0) return null

  return (
    <SectionCard title={`Closed Trades (${trades.length})`} icon={<History className={`w-5 h-5 ${meta.textActive}`} />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Closed</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Side</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Quantity</th>
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
                  <span className={`text-xs font-bold ${trade.side === 'long' ? 'text-green-400' : 'text-red-400'}`}>
                    {trade.side?.toUpperCase()}
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-white font-mono text-xs">
                  {trade.quantity ?? trade.contracts ?? '---'} {meta.quantityLabel}-PERP
                </td>
                <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(trade.entry_price, meta.priceDecimals)}</td>
                <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(trade.close_price, meta.priceDecimals)}</td>
                <td className="px-3 py-2 text-right">
                  <span className={`font-mono font-semibold text-xs ${pnlColor(trade.realized_pnl ?? 0)}`}>
                    {fmtUsd(trade.realized_pnl)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    trade.close_reason?.includes('SAR') ? 'bg-violet-900/30 text-violet-300' :
                    trade.close_reason?.includes('TRAIL') ? 'bg-cyan-900/30 text-cyan-300' :
                    trade.close_reason?.includes('PROFIT') ? 'bg-green-900/30 text-green-300' :
                    trade.close_reason?.includes('STOP') || trade.close_reason?.includes('EMERGENCY') ? 'bg-red-900/30 text-red-300' :
                    trade.close_reason?.includes('LIQUIDAT') ? 'bg-red-900/30 text-red-300' :
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

function EquityCurveTab({ coin }: { coin: CoinId }) {
  const [eqTimeFrame, setEqTimeFrame] = useState<TimeFrameId>('today')
  const isIntraday = eqTimeFrame === 'today'
  const eqDays = TIME_FRAMES.find(tf => tf.id === eqTimeFrame)?.days ?? 30

  const { data: equityData, isLoading: histLoading } = usePerpEquityCurve(coin, eqDays)
  const { data: intradayData, isLoading: intradayLoading } = usePerpIntradayEquity(coin)
  const meta = COIN_META[coin]
  const points = isIntraday
    ? (intradayData?.data_points || [])
    : (equityData?.data?.equity_curve || [])
  const gradientId = `eqFill-perp-${coin}`
  const isLoading = isIntraday ? intradayLoading : histLoading

  const startCap = equityData?.data?.starting_capital ?? meta.startingCapital
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
          ? `No intraday snapshots for ${meta.symbol} yet. The bot saves equity every 5 minutes.`
          : `No equity data for ${meta.symbol} yet. Complete trades to populate this chart.`
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
                if (isIntraday) return v?.slice(0, 5) || v
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
      <DrawdownChart points={drawdownPoints} isIntraday={isIntraday} />
      {!isIntraday && heatmapDays.length > 1 && (
        <div className="mt-4">
          <PnlHeatmap days={heatmapDays} />
        </div>
      )}
    </SectionCard>
  )
}

// ==============================================================================
// ACTIVITY TAB (Scan Activity)
// ==============================================================================

function ActivityTab({ coin }: { coin: CoinId }) {
  const { data: scanData, isLoading } = usePerpScanActivity(coin, 40)
  const scans = scanData?.data || []
  const meta = COIN_META[coin]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    )
  }

  if (scans.length === 0) {
    return <EmptyBox message={`No scan activity for ${meta.symbol} yet.`} />
  }

  // Auto-detect price field using COIN_META
  const priceField = meta.priceField

  return (
    <SectionCard title={`Scan Activity (${scans.length})`} icon={<Activity className={`w-5 h-5 ${meta.textActive}`} />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Time</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Price</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Funding</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Signal</th>
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
                  {fmtPrice(scan[priceField] ?? scan.price ?? scan.current_price, meta.priceDecimals)}
                </td>
                <td className="px-3 py-2 text-xs text-gray-400">{scan.funding_regime || '---'}</td>
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
                <td className="px-3 py-2 text-xs text-gray-400">{scan.oracle_advice || '---'}</td>
                <td className="px-3 py-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    scan.outcome?.includes('TRADED') ? 'bg-cyan-900/50 text-cyan-300' :
                    scan.outcome?.includes('SAR') ? 'bg-violet-900/50 text-violet-300' :
                    scan.outcome?.includes('ERROR') ? 'bg-red-900/50 text-red-300' :
                    scan.outcome?.includes('LOSS_STREAK') ? 'bg-orange-900/50 text-orange-300' :
                    scan.outcome?.includes('LIQUIDAT') ? 'bg-red-900/50 text-red-300' :
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
// HISTORY TAB (Closed Trades)
// ==============================================================================

function HistoryTab({ coin }: { coin: CoinId }) {
  const { data: closedData, isLoading } = usePerpClosedTrades(coin, 50)
  const trades = closedData?.data || []
  const meta = COIN_META[coin]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    )
  }

  if (trades.length === 0) {
    return <EmptyBox message={`No closed trades for ${meta.symbol} yet.`} />
  }

  return (
    <SectionCard title={`Trade History (${trades.length})`} icon={<History className={`w-5 h-5 ${meta.textActive}`} />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Closed</th>
              <th className="text-left px-3 py-2 text-gray-500 font-medium">Side</th>
              <th className="text-right px-3 py-2 text-gray-500 font-medium">Quantity</th>
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
                  <span className={`text-xs font-bold ${trade.side === 'long' ? 'text-green-400' : 'text-red-400'}`}>
                    {trade.side?.toUpperCase()}
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-white font-mono text-xs">
                  {trade.quantity ?? trade.contracts ?? '---'} {meta.quantityLabel}-PERP
                </td>
                <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(trade.entry_price, meta.priceDecimals)}</td>
                <td className="px-3 py-2 text-white font-mono text-xs">{fmtPrice(trade.close_price, meta.priceDecimals)}</td>
                <td className="px-3 py-2 text-right">
                  <span className={`font-mono font-semibold text-xs ${pnlColor(trade.realized_pnl ?? 0)}`}>
                    {fmtUsd(trade.realized_pnl)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    trade.close_reason?.includes('SAR') ? 'bg-violet-900/30 text-violet-300' :
                    trade.close_reason?.includes('TRAIL') ? 'bg-cyan-900/30 text-cyan-300' :
                    trade.close_reason?.includes('PROFIT') ? 'bg-green-900/30 text-green-300' :
                    trade.close_reason?.includes('STOP') || trade.close_reason?.includes('EMERGENCY') ? 'bg-red-900/30 text-red-300' :
                    trade.close_reason?.includes('LIQUIDAT') ? 'bg-red-900/30 text-red-300' :
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
              ? 'bg-violet-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'
          }`}
        >
          {tf.label}
        </button>
      ))}
    </div>
  )
}

function EmptyBox({ message }: { message: string }) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
      <Eye className="w-10 h-10 text-gray-700 mx-auto mb-3" />
      <p className="text-gray-500 text-sm">{message}</p>
    </div>
  )
}

// ==============================================================================
// LIVE PRICE TICKER STRIP
// ==============================================================================

function PriceTickerStrip({ summaries }: { summaries: Record<string, any> }) {
  return (
    <div className="flex items-center gap-4 overflow-x-auto py-2 px-3 bg-gray-900/60 rounded-lg border border-gray-800/50">
      {ACTIVE_COINS.map((coin, idx) => {
        const meta = COIN_META[coin]
        const data = summaries[coin]
        if (!data) return null
        const ret = data.returnPct ?? 0
        return (
          <div key={coin} className="flex items-center gap-2 whitespace-nowrap">
            <span className={`text-xs font-bold ${meta.textActive}`}>{meta.symbol}</span>
            <span className="text-white font-mono text-sm">{fmtPrice(data.price, meta.priceDecimals)}</span>
            <span className={`text-xs font-mono ${pnlColor(ret)}`}>
              {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
            </span>
            <span className={`text-xs font-mono ${pnlColor(data.totalPnl)}`}>
              ({fmtUsd(data.totalPnl)})
            </span>
            {idx < ACTIVE_COINS.length - 1 && <span className="text-gray-700 mx-1">|</span>}
          </div>
        )
      })}
    </div>
  )
}

// ==============================================================================
// PER-COIN CARD (for ALL view)
// ==============================================================================

function CoinCard({ coin, data }: { coin: string; data: any }) {
  const meta = COIN_META[coin as CoinId]
  const pnl = data?.totalPnl ?? 0
  const returnPct = data?.returnPct ?? 0

  return (
    <div className={`rounded-xl border p-4 ${meta.bgCard} ${meta.borderCard} transition-colors`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`font-bold text-lg ${meta.textActive}`}>{meta.symbol}</span>
          <span className="text-gray-500 text-xs">{meta.label}</span>
        </div>
        <span className="text-white font-mono text-sm">{fmtPrice(data?.price, meta.priceDecimals)}</span>
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
          <p className="text-white font-mono">{data?.openPositions ?? 0}</p>
        </div>
        <div>
          <span className="text-gray-500 text-xs">Trades</span>
          <p className="text-white font-mono">{data?.totalTrades ?? 0}</p>
        </div>
        <div>
          <span className="text-gray-500 text-xs">Win Rate</span>
          <p className="text-white font-mono">
            {data?.winRate != null ? `${Number(data.winRate).toFixed(1)}%` : '---'}
          </p>
        </div>
        <div>
          <span className="text-gray-500 text-xs">Instrument</span>
          <p className={`font-mono text-xs ${meta.textActive}`}>{meta.instrument}</p>
        </div>
      </div>
      {/* Capital & Status */}
      <div className="mt-3 pt-2 border-t border-gray-700/50 flex items-center justify-between">
        <span className="text-gray-500 text-xs">Capital: {fmtUsd(meta.startingCapital)}</span>
        <span className={`text-xs font-mono px-2 py-0.5 rounded ${
          data?.isActive ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'
        }`}>
          {data?.isActive ? 'ACTIVE' : 'IDLE'}
        </span>
      </div>
    </div>
  )
}

// ==============================================================================
// DRAWDOWN CHART
// ==============================================================================

function DrawdownChart({ points, isIntraday }: { points: any[]; isIntraday: boolean }) {
  if (!points || points.length < 2) return null
  const minDD = Math.min(...points.map(p => p.drawdown ?? 0))
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
              <linearGradient id="drawdownFillPerp" x1="0" y1="0" x2="0" y2="1">
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
              fill="url(#drawdownFillPerp)"
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
// DAILY P&L HEATMAP
// ==============================================================================

function PnlHeatmap({ days }: { days: { date: string; pnl: number | null; trades: number }[] }) {
  if (!days || days.length < 2) return null

  const maxAbs = Math.max(
    ...days.filter(d => d.pnl != null).map(d => Math.abs(d.pnl!)),
    1,
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
    <div>
      <div className="text-xs text-gray-500 mb-2 flex items-center gap-1">
        <Calendar className="w-3 h-3" /> Daily P&L Map
      </div>
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
    </div>
  )
}
