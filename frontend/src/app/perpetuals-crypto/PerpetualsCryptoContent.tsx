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
  LineChart,
  Brain,
} from 'lucide-react'
import PerpMarketCharts from '@/components/charts/PerpMarketCharts'
import SignalBriefCard from '@/components/trader/SignalBriefCard'
import Navigation from '@/components/Navigation'
import { TradeHistoryTable } from '@/components/perpetuals/TradeHistoryTable'
import { MultiBotPerpEquityChart, type ChartBot } from '@/components/perpetuals/MultiBotPerpEquityChart'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'

// ==============================================================================
// TYPES
// ==============================================================================

type CoinId = 'ALL' | 'ETH' | 'SOL' | 'AVAX' | 'BTC' | 'XRP' | 'DOGE' | 'SHIB' | 'LINK' | 'LTC' | 'BCH'

// ==============================================================================
// CONSTANTS
// ==============================================================================

const API = process.env.NEXT_PUBLIC_API_URL || ''

// Fixed top 3 by user pref: ETH, BTC, XRP. Remaining ordered by market cap / name recognition.
const COINS: CoinId[] = ['ALL', 'ETH', 'BTC', 'XRP', 'SOL', 'DOGE', 'AVAX', 'LINK', 'LTC', 'BCH', 'SHIB']

// productType marks each bot as a perpetual ("PERP") or dated futures ("FUTURE").
// PERP = Coinbase International (1000SHIB-PERP-INTX, geo-blocked from US) OR
//        Coinbase Derivatives 5-year-dated "perpetual-style" (e.g., BIP-20DEC30-CDE).
// FUTURE = Coinbase Derivatives monthly dated futures (e.g., SHB-29MAY26-CDE),
//          traded via FCM (Tastytrade/NinjaTrader/IBKR) with monthly contract rolls.
type ProductType = 'PERP' | 'FUTURE'

const COIN_META: Record<CoinId, {
  symbol: string; label: string; instrument: string; hexColor: string;
  bgActive: string; borderActive: string; textActive: string;
  bgCard: string; borderCard: string;
  apiPrefix: string; priceKey: string; priceField: string; priceDecimals: number;
  quantityLabel: string; startingCapital: number;
  productType: ProductType;        // PERP or FUTURE — drives UI badge
  productTypeNote?: string;        // optional sub-label (e.g., "US, no roll" / "monthly roll")
  liveAvailableUS: boolean;        // false = paper-only because no US-accessible market
}> = {
  'ALL': {
    symbol: 'ALL', label: 'All Derivatives', instrument: '', hexColor: '#06B6D4',
    bgActive: 'bg-cyan-600', borderActive: 'border-cyan-500', textActive: 'text-cyan-400',
    bgCard: 'bg-cyan-950/30', borderCard: 'border-cyan-700/40',
    apiPrefix: '', priceKey: '', priceField: '', priceDecimals: 2,
    quantityLabel: '', startingCapital: 50000,
    productType: 'PERP', liveAvailableUS: true,
  },
  'ETH': {
    symbol: 'ETH', label: 'Ethereum', instrument: 'ETH-PERP', hexColor: '#D946EF',
    bgActive: 'bg-fuchsia-600', borderActive: 'border-fuchsia-500', textActive: 'text-fuchsia-400',
    bgCard: 'bg-fuchsia-950/30', borderCard: 'border-fuchsia-700/40',
    apiPrefix: '/api/agape-eth-perp', priceKey: 'current_eth_price', priceField: 'eth_price', priceDecimals: 2,
    quantityLabel: 'ETH', startingCapital: 12500,
    productType: 'PERP', productTypeNote: 'Coinbase US (ETP-20DEC30-CDE)', liveAvailableUS: true,
  },
  'SOL': {
    symbol: 'SOL', label: 'Solana', instrument: 'SOL-PERP', hexColor: '#22D3EE',
    bgActive: 'bg-cyan-600', borderActive: 'border-cyan-500', textActive: 'text-cyan-400',
    bgCard: 'bg-cyan-950/30', borderCard: 'border-cyan-700/40',
    apiPrefix: '/api/agape-sol-perp', priceKey: 'current_sol_price', priceField: 'sol_price', priceDecimals: 2,
    quantityLabel: 'SOL', startingCapital: 5000,
    productType: 'PERP', productTypeNote: 'Coinbase US (SLP-20DEC30-CDE)', liveAvailableUS: true,
  },
  'AVAX': {
    symbol: 'AVAX', label: 'Avalanche', instrument: 'AVAX-PERP', hexColor: '#EF4444',
    bgActive: 'bg-red-600', borderActive: 'border-red-500', textActive: 'text-red-400',
    bgCard: 'bg-red-950/30', borderCard: 'border-red-700/40',
    apiPrefix: '/api/agape-avax-perp', priceKey: 'current_avax_price', priceField: 'avax_price', priceDecimals: 2,
    quantityLabel: 'AVAX', startingCapital: 2500,
    productType: 'PERP', productTypeNote: 'Coinbase US (AVP-20DEC30-CDE)', liveAvailableUS: true,
  },
  'BTC': {
    symbol: 'BTC', label: 'Bitcoin', instrument: 'BTC-PERP', hexColor: '#F97316',
    bgActive: 'bg-orange-600', borderActive: 'border-orange-500', textActive: 'text-orange-400',
    bgCard: 'bg-orange-950/30', borderCard: 'border-orange-700/40',
    apiPrefix: '/api/agape-btc-perp', priceKey: 'current_btc_price', priceField: 'btc_price', priceDecimals: 2,
    quantityLabel: 'BTC', startingCapital: 25000,
    productType: 'PERP', productTypeNote: 'Coinbase US (BIP-20DEC30-CDE)', liveAvailableUS: true,
  },
  'XRP': {
    symbol: 'XRP', label: 'Ripple', instrument: 'XRP-PERP', hexColor: '#0EA5E9',
    bgActive: 'bg-sky-600', borderActive: 'border-sky-500', textActive: 'text-sky-400',
    bgCard: 'bg-sky-950/30', borderCard: 'border-sky-700/40',
    apiPrefix: '/api/agape-xrp-perp', priceKey: 'current_xrp_price', priceField: 'xrp_price', priceDecimals: 4,
    quantityLabel: 'XRP', startingCapital: 9000,
    productType: 'PERP', productTypeNote: 'Coinbase US (XPP-20DEC30-CDE)', liveAvailableUS: true,
  },
  'DOGE': {
    symbol: 'DOGE', label: 'Dogecoin', instrument: 'DOGE-PERP', hexColor: '#FACC15',
    bgActive: 'bg-yellow-600', borderActive: 'border-yellow-500', textActive: 'text-yellow-400',
    bgCard: 'bg-yellow-950/30', borderCard: 'border-yellow-700/40',
    apiPrefix: '/api/agape-doge-perp', priceKey: 'current_doge_price', priceField: 'doge_price', priceDecimals: 6,
    quantityLabel: 'DOGE', startingCapital: 2500,
    productType: 'PERP', productTypeNote: 'Coinbase US (DOP-20DEC30-CDE)', liveAvailableUS: true,
  },
  'SHIB': {
    symbol: 'SHIB', label: 'Shiba Inu', instrument: '1000SHIB-FUT', hexColor: '#FB7185',
    bgActive: 'bg-rose-600', borderActive: 'border-rose-500', textActive: 'text-rose-400',
    bgCard: 'bg-rose-950/30', borderCard: 'border-rose-700/40',
    apiPrefix: '/api/agape-shib-futures', priceKey: 'current_shib_price', priceField: 'shib_price', priceDecimals: 8,
    quantityLabel: 'SHIB', startingCapital: 1000,
    // SHIB has no US-accessible perpetual (Coinbase International lists
    // 1000SHIB-PERP-INTX but it geo-blocks US persons). The US-accessible
    // SHIB exposure is the monthly 1000SHIB futures on Coinbase Derivatives
    // (SHB-29MAY26-CDE, SHB-26JUN26-CDE, etc.) traded via FCM (Tastytrade /
    // NinjaTrader / IBKR). Each contract = 10K units of "1000SHIB" = 10M SHIB.
    // The paper bot still uses the agape_shib_perp directory; live execution
    // via Tastytrade FCM with monthly contract rolls is a separate build.
    productType: 'FUTURE',
    productTypeNote: 'Coinbase US 1k SHIB futures (SHB-29MAY26-CDE, monthly roll, FCM)',
    liveAvailableUS: true,  // contract IS available; live integration pending
  },
  'LINK': {
    symbol: 'LINK', label: 'Chainlink', instrument: 'LINK-FUT', hexColor: '#3B82F6',
    bgActive: 'bg-blue-600', borderActive: 'border-blue-500', textActive: 'text-blue-400',
    bgCard: 'bg-blue-950/30', borderCard: 'border-blue-700/40',
    apiPrefix: '/api/agape-link-futures', priceKey: 'current_link_price', priceField: 'link_price', priceDecimals: 2,
    quantityLabel: 'LINK', startingCapital: 2500,
    productType: 'FUTURE',
    productTypeNote: 'Coinbase US LINK futures (LNK-29MAY26-CDE, 100 LINK/contract, monthly roll, FCM)',
    liveAvailableUS: true,
  },
  'LTC': {
    symbol: 'LTC', label: 'Litecoin', instrument: 'LTC-FUT', hexColor: '#94A3B8',
    bgActive: 'bg-slate-600', borderActive: 'border-slate-500', textActive: 'text-slate-300',
    bgCard: 'bg-slate-950/30', borderCard: 'border-slate-700/40',
    apiPrefix: '/api/agape-ltc-futures', priceKey: 'current_ltc_price', priceField: 'ltc_price', priceDecimals: 2,
    quantityLabel: 'LTC', startingCapital: 2500,
    productType: 'FUTURE',
    productTypeNote: 'Coinbase US LTC futures (LTC-29MAY26-CDE, 50 LTC/contract, monthly roll, FCM)',
    liveAvailableUS: true,
  },
  'BCH': {
    symbol: 'BCH', label: 'Bitcoin Cash', instrument: 'BCH-FUT', hexColor: '#22C55E',
    bgActive: 'bg-green-600', borderActive: 'border-green-500', textActive: 'text-green-400',
    bgCard: 'bg-green-950/30', borderCard: 'border-green-700/40',
    apiPrefix: '/api/agape-bch-futures', priceKey: 'current_bch_price', priceField: 'bch_price', priceDecimals: 2,
    quantityLabel: 'BCH', startingCapital: 2500,
    productType: 'FUTURE',
    productTypeNote: 'Coinbase US BCH futures (BCH-29MAY26-CDE, 25 BCH/contract, monthly roll, FCM)',
    liveAvailableUS: true,
  },
}

const ACTIVE_COINS = ['ETH', 'BTC', 'XRP', 'SOL', 'DOGE', 'AVAX', 'LINK', 'LTC', 'BCH', 'SHIB'] as const
type ActiveCoinId = typeof ACTIVE_COINS[number]

// Maps the all-page CoinId to the bot_id slug used by /api/agape-perpetuals/trades.
const COIN_TO_BOT_ID: Record<ActiveCoinId, string> = {
  ETH: 'eth', SOL: 'sol', AVAX: 'avax', BTC: 'btc', XRP: 'xrp',
  DOGE: 'doge', SHIB: 'shib_futures', LINK: 'link_futures',
  LTC: 'ltc_futures', BCH: 'bch_futures',
}

// Bot list passed to MultiBotPerpEquityChart. Built once at module scope so
// the chart's per-bot useSWR hook order is stable across renders.
const CHART_BOTS: ChartBot[] = ACTIVE_COINS.map(c => ({
  bot_id: COIN_TO_BOT_ID[c],
  label: COIN_META[c].instrument,
  color: COIN_META[c].hexColor,
  apiPrefix: COIN_META[c].apiPrefix,
}))

const SECTION_TABS = [
  { id: 'overview' as const,    label: 'Overview',      icon: Layers },
  { id: 'analytics' as const,   label: 'Analytics + AI',icon: Brain },
  { id: 'margin' as const,      label: 'Margin Risk',   icon: Shield },
  { id: 'positions' as const,   label: 'Positions',     icon: Wallet },
  { id: 'performance' as const, label: 'Performance',   icon: BarChart3 },
  { id: 'equity' as const,      label: 'Equity Curve',  icon: TrendingUp },
  { id: 'activity' as const,    label: 'Activity',      icon: Activity },
  { id: 'history' as const,     label: 'History',       icon: History },
]
type SectionTabId = typeof SECTION_TABS[number]['id']

const TOTAL_CAPITAL = 65000  // ETH 12.5 + SOL 5 + AVAX 2.5 + BTC 25 + XRP 9 + DOGE 2.5 + SHIB 1 + LINK 2.5 + LTC 2.5 + BCH 2.5

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

  // Fetch all 7 bots status for the combined view and price ticker
  const { data: ethStatusData, isLoading: ethLoading, mutate: refreshEth } = useSWR('/api/agape-eth-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: solStatusData, isLoading: solLoading, mutate: refreshSol } = useSWR('/api/agape-sol-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: avaxStatusData, isLoading: avaxLoading, mutate: refreshAvax } = useSWR('/api/agape-avax-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: btcStatusData, isLoading: btcLoading, mutate: refreshBtc } = useSWR('/api/agape-btc-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: xrpStatusData, isLoading: xrpLoading, mutate: refreshXrp } = useSWR('/api/agape-xrp-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: dogeStatusData, isLoading: dogeLoading, mutate: refreshDoge } = useSWR('/api/agape-doge-perp/status', fetcher, { refreshInterval: 10_000 })
  const { data: shibStatusData, isLoading: shibLoading, mutate: refreshShib } = useSWR('/api/agape-shib-futures/status', fetcher, { refreshInterval: 10_000 })
  const { data: linkStatusData, isLoading: linkLoading, mutate: refreshLink } = useSWR('/api/agape-link-futures/status', fetcher, { refreshInterval: 10_000 })
  const { data: ltcStatusData, isLoading: ltcLoading, mutate: refreshLtc } = useSWR('/api/agape-ltc-futures/status', fetcher, { refreshInterval: 10_000 })
  const { data: bchStatusData, isLoading: bchLoading, mutate: refreshBch } = useSWR('/api/agape-bch-futures/status', fetcher, { refreshInterval: 10_000 })

  // Fetch all 10 performance for combined stats
  const { data: ethPerfData } = useSWR('/api/agape-eth-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: solPerfData } = useSWR('/api/agape-sol-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: avaxPerfData } = useSWR('/api/agape-avax-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: btcPerfData } = useSWR('/api/agape-btc-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: xrpPerfData } = useSWR('/api/agape-xrp-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: dogePerfData } = useSWR('/api/agape-doge-perp/performance', fetcher, { refreshInterval: 30_000 })
  const { data: shibPerfData } = useSWR('/api/agape-shib-futures/performance', fetcher, { refreshInterval: 30_000 })
  const { data: linkPerfData } = useSWR('/api/agape-link-futures/performance', fetcher, { refreshInterval: 30_000 })
  const { data: ltcPerfData } = useSWR('/api/agape-ltc-futures/performance', fetcher, { refreshInterval: 30_000 })
  const { data: bchPerfData } = useSWR('/api/agape-bch-futures/performance', fetcher, { refreshInterval: 30_000 })

  const isAllView = selectedCoin === 'ALL'
  const allLoading = ethLoading && solLoading && avaxLoading && btcLoading && xrpLoading && dogeLoading && shibLoading && linkLoading && ltcLoading && bchLoading

  const refreshAll = () => { refreshEth(); refreshSol(); refreshAvax(); refreshBtc(); refreshXrp(); refreshDoge(); refreshShib(); refreshLink(); refreshLtc(); refreshBch() }

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
      SOL: build(solStatusData, solPerfData, 'SOL'),
      AVAX: build(avaxStatusData, avaxPerfData, 'AVAX'),
      BTC: build(btcStatusData, btcPerfData, 'BTC'),
      XRP: build(xrpStatusData, xrpPerfData, 'XRP'),
      DOGE: build(dogeStatusData, dogePerfData, 'DOGE'),
      SHIB: build(shibStatusData, shibPerfData, 'SHIB'),
      LINK: build(linkStatusData, linkPerfData, 'LINK'),
      LTC: build(ltcStatusData, ltcPerfData, 'LTC'),
      BCH: build(bchStatusData, bchPerfData, 'BCH'),
    }
  }, [ethStatusData, solStatusData, avaxStatusData, btcStatusData, xrpStatusData, dogeStatusData, shibStatusData, linkStatusData, ltcStatusData, bchStatusData, ethPerfData, solPerfData, avaxPerfData, btcPerfData, xrpPerfData, dogePerfData, shibPerfData, linkPerfData, ltcPerfData, bchPerfData])

  // Loading state
  if (allLoading && !ethStatusData && !solStatusData && !avaxStatusData && !btcStatusData && !xrpStatusData && !dogeStatusData && !shibStatusData && !linkStatusData && !ltcStatusData && !bchStatusData) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen bg-gray-950">
          <div className="text-center space-y-3">
            <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin mx-auto" />
            <p className="text-gray-400 text-sm">Loading AGAPE Derivatives...</p>
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
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl md:text-3xl font-bold text-white">
                  AGAPE <span className="text-cyan-400">Derivatives</span>
                </h1>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-green-900/40 border border-green-500/40 rounded-full text-xs font-semibold text-green-400">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  24/7
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-900/40 border border-blue-500/30 rounded text-[11px] font-bold text-blue-300" title="Perpetual contracts — no expiration, no contract rolls">
                  PERP = Perpetual
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-900/40 border border-amber-500/30 rounded text-[11px] font-bold text-amber-300" title="Dated futures — monthly expiration, requires contract rolls (FCM-traded)">
                  FUTURE = Monthly Futures
                </span>
              </div>
              <p className="text-gray-500 text-sm mt-1">
                Perpetuals + monthly futures: ETH, BTC, XRP, SOL, DOGE, AVAX, LINK, LTC, BCH, SHIB
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
                  {coin !== 'ALL' && (
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide ${
                        meta.productType === 'PERP'
                          ? (isActive ? 'bg-white/25 text-white' : 'bg-blue-900/60 text-blue-300')
                          : (isActive ? 'bg-white/25 text-white' : 'bg-amber-900/60 text-amber-300')
                      }`}
                      title={meta.productTypeNote || meta.productType}
                    >
                      {meta.productType}
                    </span>
                  )}
                  {coin !== 'ALL' && !meta.liveAvailableUS && (
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        isActive ? 'bg-white/25 text-white' : 'bg-gray-700 text-gray-400'
                      }`}
                      title="Paper-only — no US-accessible market for this product"
                    >
                      PAPER
                    </span>
                  )}
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
                {activeTab === 'analytics' && <AnalyticsTab coin={selectedCoin} />}
                {activeTab === 'margin' && <MarginRiskTab coin={selectedCoin} />}
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

      {/* Normalized multi-bot performance comparison */}
      <MultiBotPerpEquityChart bots={CHART_BOTS} defaultMode="indexed" defaultWindow="30d" />

      {/* Recent activity across all coins */}
      <AllCoinsRecentTrades />
    </div>
  )
}

function AllCoinsRecentTrades() {
  const allBotIds = ACTIVE_COINS.map(c => COIN_TO_BOT_ID[c])
  return (
    <TradeHistoryTable
      bots={allBotIds}
      showBotColumn
      defaultRange="30d"
      title="Recent Trades — All Bots"
    />
  )
}

// ==============================================================================
// SINGLE COIN HEADER
// ==============================================================================

function SingleCoinHeader({ coin, summaries }: { coin: CoinId; summaries: Record<string, any> }) {
  const meta = COIN_META[coin]
  const summary = summaries[coin]

  const productLabel = meta.productType === 'PERP' ? 'Perpetual Contract' : 'Monthly Futures'
  return (
    <div className={`rounded-xl border p-4 ${meta.bgCard} ${meta.borderCard}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`text-2xl font-bold ${meta.textActive}`}>{meta.symbol}</span>
          <span className="text-gray-400 text-sm">{meta.label}</span>
          <span
            className={`px-2 py-0.5 rounded text-[11px] font-bold tracking-wide ${
              meta.productType === 'PERP'
                ? 'bg-blue-900/60 text-blue-300 border border-blue-700/50'
                : 'bg-amber-900/60 text-amber-300 border border-amber-700/50'
            }`}
            title={meta.productTypeNote || meta.productType}
          >
            {meta.productType}
          </span>
          {!meta.liveAvailableUS && (
            <span
              className="px-2 py-0.5 rounded text-[11px] font-bold bg-gray-700 text-gray-400 border border-gray-600"
              title="Paper-only — no US-accessible market for this product"
            >
              PAPER ONLY
            </span>
          )}
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
        {productLabel}: {meta.instrument} | Directional trading (Long & Short) | {fmtUsd(meta.startingCapital)} starting capital
        {meta.productTypeNote && <span className="text-gray-600"> | {meta.productTypeNote}</span>}
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
// ANALYTICS + AI TAB — charts and Claude commentary per coin
// ==============================================================================

function usePerpChartData(coin: ActiveCoinId) {
  const prefix = COIN_META[coin].apiPrefix
  return useSWR(`${prefix}/chart-data`, fetcher, { refreshInterval: 5 * 60_000 })
}

function usePerpBrief(coin: ActiveCoinId) {
  const prefix = COIN_META[coin].apiPrefix
  return useSWR(`${prefix}/brief`, fetcher, { refreshInterval: 5 * 60_000 })
}

function CoinAnalytics({ coin }: { coin: ActiveCoinId }) {
  const meta = COIN_META[coin]
  const { data: chartData, isLoading: chartLoading } = usePerpChartData(coin)
  const { data: briefData, isLoading: briefLoading } = usePerpBrief(coin)

  const chart = (chartData as any)?.data
  const brief = (briefData as any)?.data
  const briefReason = (briefData as any)?.reason

  return (
    <div className={`rounded-xl border ${meta.borderCard} ${meta.bgCard} p-4 space-y-4`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-1 rounded text-sm font-bold ${meta.bgActive}/30 ${meta.textActive}`}>
            {meta.symbol}
          </span>
          <span className="text-xs text-gray-500">
            {chart ? `${chart.lookback_days}d / ${chart.interval}` : '...'}
          </span>
        </div>
        {chart?.fetched_at && (
          <span className="text-xs text-gray-500">
            data: {new Date(chart.fetched_at).toLocaleTimeString()}
          </span>
        )}
      </div>
      <SignalBriefCard data={brief} loading={briefLoading} reason={briefReason} />
      <PerpMarketCharts data={chart || null} loading={chartLoading} />
    </div>
  )
}

function AnalyticsTab({ coin }: { coin: CoinId }) {
  const coinsToShow: ActiveCoinId[] = coin === 'ALL'
    ? (ACTIVE_COINS as readonly ActiveCoinId[]).slice() as ActiveCoinId[]
    : [coin as ActiveCoinId]

  return (
    <div className="space-y-5">
      <div className="bg-gradient-to-br from-purple-900/30 to-blue-900/30 border border-purple-700/40 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Brain className="w-5 h-5 text-purple-300 mt-0.5" />
          <div className="text-sm text-gray-200">
            <div className="text-purple-200 font-semibold mb-1">Per-Coin Analytics + Claude Commentary</div>
            <p className="text-gray-300">
              30-day h4 history of <span className="text-blue-300">price</span>, <span className="text-green-300">L/S ratio</span>,{' '}
              <span className="text-purple-300">open interest</span>, and <span className="text-orange-300">funding rate</span> from CoinGlass.
              Claude reads the live market data and writes a plain-English brief on what the bot is seeing and what it likely means for the next move.
              Switch coins above to drill into one, or pick "ALL" to see all 5 stacked.
            </p>
          </div>
        </div>
      </div>

      {coinsToShow.map(c => <CoinAnalytics key={c} coin={c} />)}
    </div>
  )
}


// ==============================================================================
// MARGIN RISK TAB
// ==============================================================================

function usePerpMargin(coin: ActiveCoinId) {
  const prefix = COIN_META[coin].apiPrefix
  return useSWR(`${prefix}/margin`, fetcher, { refreshInterval: 15_000 })
}

function marginHealthClass(health: string | undefined): { text: string; bg: string; border: string } {
  switch ((health || '').toUpperCase()) {
    case 'HEALTHY':  return { text: 'text-green-400',   bg: 'bg-green-500/20',   border: 'border-green-700/40' }
    case 'WARNING':  return { text: 'text-yellow-400',  bg: 'bg-yellow-500/20',  border: 'border-yellow-700/40' }
    case 'DANGER':   return { text: 'text-orange-400',  bg: 'bg-orange-500/20',  border: 'border-orange-700/40' }
    case 'CRITICAL': return { text: 'text-red-400',     bg: 'bg-red-500/20',     border: 'border-red-700/40' }
    default:         return { text: 'text-slate-400',   bg: 'bg-slate-500/20',   border: 'border-slate-700/40' }
  }
}

function usagePctClass(pct: number | undefined): string {
  if (pct == null) return 'bg-slate-500'
  if (pct >= 100) return 'bg-red-600'
  if (pct >= 80)  return 'bg-orange-500'
  if (pct >= 60)  return 'bg-yellow-500'
  return 'bg-green-500'
}

function MarginRow({ coin }: { coin: ActiveCoinId }) {
  const { data, error, isLoading } = usePerpMargin(coin)
  const meta = COIN_META[coin]
  const m = data?.data
  const health = m?.margin_health
  const cls = marginHealthClass(health)
  const usage = m?.margin_usage_pct ?? 0

  return (
    <tr className="border-t border-gray-800 hover:bg-gray-800/40 transition">
      <td className="py-3 px-4">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${cls.bg}`} />
          <span className={`font-bold ${meta.textActive}`}>{coin}-PERP</span>
        </div>
      </td>
      <td className="py-3 px-4 text-right">
        {isLoading ? '—' : error ? <span className="text-red-400">err</span> : fmtUsd(m?.account_equity)}
      </td>
      <td className="py-3 px-4 text-right">{isLoading ? '—' : fmtUsd(m?.margin_used)}</td>
      <td className="py-3 px-4 text-right">{isLoading ? '—' : fmtUsd(m?.available_margin)}</td>
      <td className="py-3 px-4">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 bg-gray-800 rounded overflow-hidden">
            <div
              className={`h-full ${usagePctClass(usage)}`}
              style={{ width: `${Math.min(100, usage)}%` }}
            />
          </div>
          <span className={`w-14 text-right font-mono text-xs ${usage >= 100 ? 'text-red-400 font-bold' : usage >= 80 ? 'text-orange-400' : 'text-gray-300'}`}>
            {isLoading ? '—' : `${usage.toFixed(1)}%`}
          </span>
        </div>
      </td>
      <td className="py-3 px-4 text-right">
        {isLoading ? '—' : (m?.position_count ?? 0)}
      </td>
      <td className="py-3 px-4 text-right">
        {isLoading ? '—' : `${(m?.effective_leverage ?? 0).toFixed(2)}x`}
      </td>
      <td className="py-3 px-4 text-right">
        <span className={pnlColor(m?.total_unrealized_pnl ?? 0)}>
          {isLoading ? '—' : fmtUsd(m?.total_unrealized_pnl)}
        </span>
      </td>
      <td className="py-3 px-4">
        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${cls.bg} ${cls.text}`}>
          {isLoading ? '...' : (health || 'UNKNOWN')}
        </span>
      </td>
    </tr>
  )
}

function MarginRiskTab({ coin }: { coin: CoinId }) {
  const coinsToShow: ActiveCoinId[] = coin === 'ALL'
    ? (ACTIVE_COINS as readonly ActiveCoinId[]).slice() as ActiveCoinId[]
    : [coin as ActiveCoinId]

  return (
    <div className="space-y-5">
      <div className="bg-gradient-to-br from-blue-950/40 to-cyan-950/30 border border-blue-700/40 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Shield className="w-5 h-5 text-blue-400 mt-0.5" />
          <div className="text-sm text-gray-300">
            <div className="text-blue-300 font-semibold mb-1">Margin Risk Manager</div>
            <p>
              Position-count cap was removed — every qualifying signal opens a position. Margin engine is the backstop.
              Watch the usage bar: <span className="text-yellow-400">≥60% caution</span>,{' '}
              <span className="text-orange-400">≥80% danger</span>,{' '}
              <span className="text-red-400 font-semibold">≥100% over-leveraged</span>.
            </p>
          </div>
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/60 text-xs uppercase tracking-wide text-gray-400">
            <tr>
              <th className="py-3 px-4 text-left">Bot</th>
              <th className="py-3 px-4 text-right">Equity</th>
              <th className="py-3 px-4 text-right">Margin Used</th>
              <th className="py-3 px-4 text-right">Available</th>
              <th className="py-3 px-4 text-left min-w-[180px]">Usage</th>
              <th className="py-3 px-4 text-right">Pos</th>
              <th className="py-3 px-4 text-right">Lev</th>
              <th className="py-3 px-4 text-right">uPnL</th>
              <th className="py-3 px-4 text-left">Health</th>
            </tr>
          </thead>
          <tbody>
            {coinsToShow.map(c => <MarginRow key={c} coin={c} />)}
          </tbody>
        </table>
      </div>

      <TradeEconomicsTable coinsToShow={coinsToShow} />

      {coin !== 'ALL' && <PerCoinPositionMargin coin={coin as ActiveCoinId} />}
    </div>
  )
}

// ==============================================================================
// TRADE ECONOMICS — what each trade actually costs and how to fund the account
// ==============================================================================

const PER_POSITION_MARGIN_PCT = 7.0   // matches signals.py cap
const MARGIN_GATE_PCT = 70.0          // matches trader entry gate
const TYPICAL_TRADES_TARGET = 10      // funding sized for this many concurrent trades

function TradeEconomicsRow({ coin }: { coin: ActiveCoinId }) {
  const meta = COIN_META[coin]
  const { data: marginData } = usePerpMargin(coin)
  const { data: statusData } = usePerpStatus(coin)
  const m = (marginData as any)?.data
  const s = (statusData as any)?.data

  const equity = m?.account_equity ?? s?.starting_capital ?? 0
  const startingCapital = s?.starting_capital ?? 0
  const leverage = m?.spec?.default_leverage ?? m?.effective_leverage ?? 0
  const spot = s?.[meta.priceKey] ?? 0
  const riskPct = s?.risk_per_trade_pct ?? 5

  // What ONE new position will cost, given the live 7%-of-equity sizer
  const marginPerTrade = equity * (PER_POSITION_MARGIN_PCT / 100)
  const notionalPerTrade = marginPerTrade * leverage
  const qtyPerTrade = spot > 0 ? notionalPerTrade / spot : 0
  const riskPerTrade = startingCapital * (riskPct / 100)
  const slotsBeforeGate = marginPerTrade > 0 ? Math.floor((equity * MARGIN_GATE_PCT / 100) / marginPerTrade) : 0

  // Real cash needed for N trades sized at target margin pct
  const fundForN = (n: number) => (n * marginPerTrade) / (MARGIN_GATE_PCT / 100)

  return (
    <tr className="border-t border-gray-800 hover:bg-gray-800/40">
      <td className="py-3 px-3"><span className={`font-bold ${meta.textActive}`}>{coin}</span></td>
      <td className="py-3 px-3 text-right text-white font-mono text-xs">{spot ? fmtPrice(spot, meta.priceDecimals) : '—'}</td>
      <td className="py-3 px-3 text-right text-gray-300 text-xs">{leverage ? `${leverage}x` : '—'}</td>
      <td className="py-3 px-3 text-right text-white font-mono text-xs">{fmtUsd(equity, 0)}</td>
      <td className="py-3 px-3 text-right text-blue-300 font-mono">{fmtUsd(marginPerTrade, 0)}</td>
      <td className="py-3 px-3 text-right text-purple-300 font-mono">{fmtUsd(notionalPerTrade, 0)}</td>
      <td className="py-3 px-3 text-right text-gray-300 font-mono text-xs">{qtyPerTrade > 0 ? qtyPerTrade.toLocaleString(undefined, { maximumFractionDigits: meta.priceDecimals }) : '—'} {meta.quantityLabel}</td>
      <td className="py-3 px-3 text-right text-orange-400 font-mono">{fmtUsd(riskPerTrade, 0)}</td>
      <td className="py-3 px-3 text-right text-gray-300 font-mono text-xs">{slotsBeforeGate}</td>
      <td className="py-3 px-3 text-right text-green-300 font-mono">{fmtUsd(fundForN(TYPICAL_TRADES_TARGET), 0)}</td>
    </tr>
  )
}

function TradeEconomicsTable({ coinsToShow }: { coinsToShow: ActiveCoinId[] }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-start gap-3">
        <DollarSign className="w-5 h-5 text-green-400 mt-0.5" />
        <div className="text-sm">
          <div className="text-green-300 font-semibold">Trade Economics — what each position costs</div>
          <div className="text-xs text-gray-400 mt-0.5">
            Sizer caps each new position at <span className="text-blue-300">{PER_POSITION_MARGIN_PCT}% of equity in margin</span>;
            entry gate refuses opens above <span className="text-yellow-400">{MARGIN_GATE_PCT}%</span>.
            "Fund for {TYPICAL_TRADES_TARGET} trades" is the real cash needed to comfortably run that many concurrent positions before the gate trips.
          </div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/60 text-xs uppercase tracking-wide text-gray-400">
            <tr>
              <th className="py-3 px-3 text-left">Coin</th>
              <th className="py-3 px-3 text-right">Spot</th>
              <th className="py-3 px-3 text-right">Lev</th>
              <th className="py-3 px-3 text-right">Equity Now</th>
              <th className="py-3 px-3 text-right">Cost / Trade</th>
              <th className="py-3 px-3 text-right">Notional / Trade</th>
              <th className="py-3 px-3 text-right">Size / Trade</th>
              <th className="py-3 px-3 text-right">Max Loss / Trade</th>
              <th className="py-3 px-3 text-right">Slots</th>
              <th className="py-3 px-3 text-right">Fund for {TYPICAL_TRADES_TARGET}</th>
            </tr>
          </thead>
          <tbody>
            {coinsToShow.map(c => <TradeEconomicsRow key={c} coin={c} />)}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function PerCoinPositionMargin({ coin }: { coin: ActiveCoinId }) {
  const { data, isLoading } = usePerpMargin(coin)
  const positions = data?.data?.positions || []
  const meta = COIN_META[coin]

  if (isLoading) return null
  if (positions.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 text-center text-gray-500 text-sm">
        No open positions for {coin}-PERP.
      </div>
    )
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold text-gray-200">
        Per-Position Breakdown · {coin}-PERP
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-800/60 text-xs uppercase tracking-wide text-gray-400">
          <tr>
            <th className="py-3 px-4 text-left">Position</th>
            <th className="py-3 px-4 text-left">Side</th>
            <th className="py-3 px-4 text-right">Qty</th>
            <th className="py-3 px-4 text-right">Entry</th>
            <th className="py-3 px-4 text-right">Current</th>
            <th className="py-3 px-4 text-right">Notional</th>
            <th className="py-3 px-4 text-right">Margin</th>
            <th className="py-3 px-4 text-right">Liq Price</th>
            <th className="py-3 px-4 text-right">uPnL</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p: any, i: number) => (
            <tr key={p.position_id || i} className="border-t border-gray-800">
              <td className="py-2 px-4 font-mono text-xs text-gray-400">{(p.position_id || '').slice(-8)}</td>
              <td className="py-2 px-4">
                <span className={p.side === 'long' ? 'text-green-400' : 'text-red-400'}>{(p.side || '').toUpperCase()}</span>
              </td>
              <td className="py-2 px-4 text-right">{(p.quantity ?? 0).toLocaleString()}</td>
              <td className="py-2 px-4 text-right">{fmtPrice(p.entry_price, meta.priceDecimals)}</td>
              <td className="py-2 px-4 text-right">{fmtPrice(p.current_price, meta.priceDecimals)}</td>
              <td className="py-2 px-4 text-right">{fmtUsd(p.notional_value, 0)}</td>
              <td className="py-2 px-4 text-right">{fmtUsd(p.initial_margin_required, 0)}</td>
              <td className="py-2 px-4 text-right text-orange-300">{fmtPrice(p.liquidation_price, meta.priceDecimals)}</td>
              <td className={`py-2 px-4 text-right ${pnlColor(p.unrealized_pnl ?? 0)}`}>{fmtUsd(p.unrealized_pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


// ==============================================================================
// POSITIONS TAB
// ==============================================================================

function PositionsTab({ coin }: { coin: CoinId }) {
  const { data: posData, isLoading } = usePerpPositions(coin)
  const marginPrefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  const { data: marginData } = useSWR(
    marginPrefix ? `${marginPrefix}/margin` : null,
    fetcher,
    { refreshInterval: 15_000 }
  )
  const positions = posData?.data || []
  const meta = COIN_META[coin]

  // Build a lookup of margin/notional per position_id from the /margin endpoint
  const marginByPosId: Record<string, any> = {}
  for (const p of ((marginData as any)?.data?.positions || [])) {
    if (p?.position_id) marginByPosId[p.position_id] = p
  }

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
      {positions.map((pos: any, idx: number) => {
        const m = marginByPosId[pos.position_id] || {}
        return (
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
            <div className="flex items-baseline gap-4">
              <div className="text-right">
                <div className="text-xs text-gray-500">Cost (Margin)</div>
                <span className="text-base font-mono font-semibold text-blue-300">
                  {m.initial_margin_required != null ? fmtUsd(m.initial_margin_required, 0) : '---'}
                </span>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500">Notional</div>
                <span className="text-base font-mono font-semibold text-purple-300">
                  {m.notional_value != null ? fmtUsd(m.notional_value, 0) : '---'}
                </span>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500">At Risk</div>
                <span className="text-base font-mono font-semibold text-orange-400">
                  {pos.max_risk_usd != null ? fmtUsd(pos.max_risk_usd) : '---'}
                </span>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500">P&L</div>
                <span className={`text-lg font-mono font-bold ${pnlColor(pos.unrealized_pnl ?? 0)}`}>
                  {fmtUsd(pos.unrealized_pnl)}
                </span>
              </div>
            </div>
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
              <span className="text-gray-500">Liq Price</span>
              <p className="text-orange-300 font-mono">{m.liquidation_price != null ? fmtPrice(m.liquidation_price, meta.priceDecimals) : '---'}</p>
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
        )
      })}
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
  if (coin === 'ALL') return null
  const meta = COIN_META[coin]
  const botId = COIN_TO_BOT_ID[coin as ActiveCoinId]
  return (
    <TradeHistoryTable
      bots={[botId]}
      showBotColumn={false}
      defaultRange="30d"
      title={`${meta.symbol} Closed Trades`}
    />
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
  if (coin === 'ALL') return null
  const meta = COIN_META[coin]
  const botId = COIN_TO_BOT_ID[coin as ActiveCoinId]
  return (
    <TradeHistoryTable
      bots={[botId]}
      showBotColumn={false}
      defaultRange="30d"
      title={`${meta.symbol} Trade History`}
    />
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
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`font-bold text-lg ${meta.textActive}`}>{meta.symbol}</span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide ${
              meta.productType === 'PERP'
                ? 'bg-blue-900/60 text-blue-300'
                : 'bg-amber-900/60 text-amber-300'
            }`}
            title={meta.productTypeNote || meta.productType}
          >
            {meta.productType}
          </span>
          {!meta.liveAvailableUS && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-700 text-gray-400" title="Paper-only">
              PAPER
            </span>
          )}
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
