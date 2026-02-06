'use client'

import { useState } from 'react'
import useSWR from 'swr'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { DollarSign, TrendingUp, Banknote, Receipt, Target } from 'lucide-react'
import {
  BotPageHeader,
  StatCard,
} from '@/components/trader'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

// ==============================================================================
// EQUITY TIMEFRAME OPTIONS (matching HERACLES)
// ==============================================================================
const EQUITY_TIMEFRAMES = [
  { id: 'intraday', label: 'Today', days: 0 },
  { id: '7d', label: '7D', days: 7 },
  { id: '14d', label: '14D', days: 14 },
  { id: '30d', label: '30D', days: 30 },
  { id: '90d', label: '90D', days: 90 },
]

// Alias for IC trading (same options)
const IC_EQUITY_TIMEFRAMES = EQUITY_TIMEFRAMES

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

const fetcher = (url: string) => fetch(`${API_URL}${url}`).then(res => {
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
})

interface Position {
  position_id: string
  ticker: string
  lower_strike: number
  upper_strike: number
  strike_width: number
  expiration: string
  open_time: string              // When position was opened
  dte_at_entry: number           // Original DTE at entry
  current_dte: number            // Days remaining now
  contracts: number
  entry_credit: number           // Per contract credit
  total_credit_received: number  // Total credit received
  theoretical_value: number      // What box is worth at expiration (strike_width * 100)
  total_owed_at_expiration: number  // Total owed back
  borrowing_cost: number         // Total interest cost
  cost_accrued_to_date: number   // How much interest has accrued so far
  daily_cost: number             // Daily interest accrual
  implied_annual_rate: number    // Annualized borrowing rate
  // Capital deployment
  cash_deployed_to_ares: number
  cash_deployed_to_titan: number
  cash_deployed_to_pegasus: number
  cash_held_in_reserve: number
  total_cash_deployed: number
  // Returns tracking
  returns_from_ares: number
  returns_from_titan: number
  returns_from_pegasus: number
  total_ic_returns: number
  net_profit: number
  // Context at entry
  spot_at_entry: number
  vix_at_entry: number
  fed_funds_at_entry: number
  margin_rate_at_entry: number
  savings_vs_margin: number
  // Status
  status: string
  early_assignment_risk: string
  current_margin_used: number
  margin_cushion: number
}

export default function PrometheusBoxDashboard() {
  const sidebarPadding = useSidebarPadding()
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'ic-trading' | 'analytics' | 'education' | 'howItWorks'>('overview')
  const [boxEquityTimeframe, setBoxEquityTimeframe] = useState('intraday')
  const [icEquityTimeframe, setIcEquityTimeframe] = useState('intraday')
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Get selected Box Spread equity timeframe config
  const selectedBoxTimeframe = EQUITY_TIMEFRAMES.find(t => t.id === boxEquityTimeframe) || EQUITY_TIMEFRAMES[0]
  const isBoxIntraday = boxEquityTimeframe === 'intraday'

  // Get selected IC equity timeframe config
  const selectedIcTimeframe = IC_EQUITY_TIMEFRAMES.find(t => t.id === icEquityTimeframe) || IC_EQUITY_TIMEFRAMES[0]
  const isIcIntraday = icEquityTimeframe === 'intraday'

  // Data fetching - Box Spread
  const { data: status, error: statusError } = useSWR('/api/prometheus-box/status', fetcher, { refreshInterval: 30000 })
  const { data: positions } = useSWR('/api/prometheus-box/positions', fetcher, { refreshInterval: 30000 })
  const { data: rateAnalysis } = useSWR('/api/prometheus-box/analytics/rates', fetcher, { refreshInterval: 60000 })
  const { data: capitalFlow } = useSWR('/api/prometheus-box/analytics/capital-flow', fetcher, { refreshInterval: 30000 })
  // Box Spread Equity Curve - fetch based on selected timeframe (matching HERACLES pattern)
  const boxEquityCurveUrl = `/api/prometheus-box/equity-curve?days=${selectedBoxTimeframe.days}`
  const { data: equityCurve, isLoading: boxEquityCurveLoading } = useSWR(
    isBoxIntraday ? null : boxEquityCurveUrl, // Don't fetch historical for intraday
    fetcher,
    { refreshInterval: 30000 }
  )
  const { data: intradayEquity, isLoading: boxIntradayLoading } = useSWR(
    '/api/prometheus-box/equity-curve/intraday',
    fetcher,
    { refreshInterval: 15000 }  // Faster refresh for intraday
  )
  const { data: interestRates } = useSWR('/api/prometheus-box/analytics/interest-rates', fetcher, { refreshInterval: 300000 })

  // IC Trading data - All required endpoints per STANDARDS.md
  const { data: icStatus } = useSWR('/api/prometheus-box/ic/status', fetcher, { refreshInterval: 30000 })
  const { data: icPositions } = useSWR('/api/prometheus-box/ic/positions', fetcher, { refreshInterval: 15000 })
  const { data: icPerformance } = useSWR('/api/prometheus-box/ic/performance', fetcher, { refreshInterval: 30000 })
  const { data: icClosedTrades } = useSWR('/api/prometheus-box/ic/closed-trades?limit=20', fetcher, { refreshInterval: 60000 })
  // IC Equity Curve - fetch based on selected timeframe
  // For "Today", use intraday snapshots endpoint; otherwise use historical with days parameter
  const icEquityCurveUrl = `/api/prometheus-box/ic/equity-curve?days=${selectedIcTimeframe.days}`
  const { data: icEquityCurve, isLoading: icEquityCurveLoading } = useSWR(
    isIcIntraday ? null : icEquityCurveUrl, // Don't fetch historical for intraday
    fetcher,
    { refreshInterval: 30000 }
  )
  const { data: icIntradayEquity, isLoading: icIntradayLoading } = useSWR(
    '/api/prometheus-box/ic/equity-curve/intraday',
    fetcher,
    { refreshInterval: 15000 }  // Faster refresh for intraday
  )
  const { data: icLogs } = useSWR('/api/prometheus-box/ic/logs?limit=50', fetcher, { refreshInterval: 30000 })
  const { data: icSignals } = useSWR('/api/prometheus-box/ic/signals/recent?limit=20', fetcher, { refreshInterval: 30000 })
  const { data: combinedPerformance } = useSWR('/api/prometheus-box/combined/performance', fetcher, { refreshInterval: 60000 })

  // Full Reconciliation - server-calculated, all values from API
  const { data: reconciliation } = useSWR('/api/prometheus-box/reconciliation', fetcher, { refreshInterval: 30000 })

  // Daily P&L breakdown - IC earnings vs borrowing costs
  const { data: dailyPnl } = useSWR('/api/prometheus-box/daily-pnl?days=14', fetcher, { refreshInterval: 60000 })

  // IC Bot positions for capital deployment tracking (legacy - to be removed)
  const { data: aresPositions } = useSWR('/api/ares/positions', fetcher, { refreshInterval: 30000 })
  const { data: titanPositions } = useSWR('/api/titan/positions', fetcher, { refreshInterval: 30000 })
  const { data: pegasusPositions } = useSWR('/api/pegasus/positions', fetcher, { refreshInterval: 30000 })

  const isLoading = !status
  const isError = statusError

  const formatCurrency = (value: number) => {
    if (value === undefined || value === null) return '$0.00'
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(value)
  }

  const formatPct = (value: number, decimals = 2) => {
    if (value === undefined || value === null) return '0.00%'
    return `${value.toFixed(decimals)}%`
  }

  // ============================================================================
  // SINGLE SOURCE OF TRUTH: Use reconciliation endpoint for all key metrics
  // ============================================================================
  // The reconciliation endpoint calculates ALL values server-side to ensure consistency.
  // Frontend ONLY displays - no client-side math that could create mismatches.

  // Box Spread metrics (from reconciliation)
  const totalBorrowed = reconciliation?.box_spreads?.totals?.total_borrowed || status?.total_borrowed || 0
  const totalBorrowingCostLife = reconciliation?.box_spreads?.totals?.total_borrowing_cost || 0  // Total cost over life of all boxes
  const totalCostAccrued = reconciliation?.box_spreads?.totals?.cost_accrued_to_date || status?.total_borrowing_costs || 0  // Cost accrued so far
  const totalCostRemaining = reconciliation?.box_spreads?.totals?.cost_remaining || 0

  // IC Trading metrics (from reconciliation)
  const icRealizedPnL = reconciliation?.net_profit_reconciliation?.income?.ic_realized_pnl || 0
  const icUnrealizedPnL = reconciliation?.net_profit_reconciliation?.income?.ic_unrealized_pnl || 0
  const totalICReturns = reconciliation?.net_profit_reconciliation?.income?.total_ic_returns || icRealizedPnL + icUnrealizedPnL

  // THE KEY FORMULA: Net Profit = Total IC Returns - Borrowing Cost Accrued
  const netPnL = reconciliation?.net_profit_reconciliation?.net_profit || (totalICReturns - totalCostAccrued)

  // Cost Efficiency = Total IC Returns / Borrowing Cost Accrued
  // If > 1, you're making more from ICs than you're paying in borrowing costs
  const costEfficiency = reconciliation?.net_profit_reconciliation?.cost_efficiency || (totalCostAccrued > 0 ? (totalICReturns / totalCostAccrued) : 0)

  // Capital deployment (from reconciliation)
  const reservedCapital = reconciliation?.capital_deployment?.reserved || 0
  const capitalInICTrades = reconciliation?.capital_deployment?.in_ic_trades || 0
  const availableToTrade = reconciliation?.capital_deployment?.available_to_trade || 0

  // Legacy metric for backwards compatibility
  const returnOnBorrowed = totalBorrowed > 0 ? (netPnL / totalBorrowed) * 100 : 0

  // Handle refresh
  const handleRefresh = () => {
    setIsRefreshing(true)
    // SWR will automatically revalidate, just show spinner briefly
    setTimeout(() => setIsRefreshing(false), 1000)
  }

  return (
    <>
      <Navigation />
      <main className={`min-h-screen bg-black text-white px-4 pb-4 md:px-6 md:pb-6 pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-7xl mx-auto space-y-6">

          {/* Header - Branded */}
          <BotPageHeader
            botName="PROMETHEUS"
            isActive={status?.system_status === 'active'}
            lastHeartbeat={status?.last_update || undefined}
            onRefresh={handleRefresh}
            isRefreshing={isRefreshing}
            scanIntervalMinutes={5}
          />

          {/* ═══════════════════════════════════════════════════════════════════════
              P&L SUMMARY - Single source of truth, always visible above tabs
              ═══════════════════════════════════════════════════════════════════════ */}
          <div className="bg-[#0a0a0a] rounded-xl border border-emerald-500/30 p-4">
            {/* Header row with status badge */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-medium text-white">PROMETHEUS P&L Summary</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  IC Trading Profit − Borrowing Cost = Net Profit
                  <span className="ml-2 text-gray-600">• All-time since inception</span>
                </p>
              </div>
              {/* Cost Efficiency Badge with explanation */}
              <div
                className={`px-3 py-1.5 rounded-full text-xs font-medium cursor-help ${
                  costEfficiency >= 1.5 ? 'bg-green-900/50 text-green-400 border border-green-600/50' :
                  costEfficiency >= 1 ? 'bg-green-900/30 text-green-400 border border-green-700/50' :
                  costEfficiency >= 0.8 ? 'bg-yellow-900/30 text-yellow-400 border border-yellow-700/50' :
                  'bg-red-900/30 text-red-400 border border-red-700/50'
                }`}
                title={`Cost Efficiency = IC Profit ÷ Borrowing Cost\n\n${formatCurrency(totalICReturns)} ÷ ${formatCurrency(totalCostAccrued)} = ${costEfficiency.toFixed(2)}x\n\n1.0x = break-even (IC profit equals borrowing cost)\nAbove 1.0x = profitable\nBelow 1.0x = losing money`}
              >
                {!reconciliation ? <span className="animate-pulse">---</span> : (
                  <>
                    {costEfficiency.toFixed(1)}x efficiency
                    <span className="ml-1 opacity-75">
                      {costEfficiency >= 1.5 ? '• Highly Profitable' :
                       costEfficiency >= 1 ? '• Covering Costs' :
                       costEfficiency >= 0.8 ? '• Near Break-Even' :
                       '• Below Break-Even'}
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Main metrics - clear labels with explanatory subtitles */}
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              {/* 1: Capital Borrowed */}
              <div className="bg-blue-900/20 rounded-lg p-3 border border-blue-700/30">
                <div className="text-xs text-blue-400/70 mb-1">Capital Borrowed <span className="text-gray-600">(Active)</span></div>
                <div className="text-lg font-bold text-blue-400">
                  {!reconciliation && !status ? <span className="animate-pulse">---</span> : formatCurrency(totalBorrowed)}
                </div>
                <div className="text-xs text-gray-500">{positions?.positions?.length || 0} active box spread{(positions?.positions?.length || 0) !== 1 ? 's' : ''}</div>
              </div>

              {/* 2: Closed IC Trades - renamed from "IC Realized" */}
              <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
                <div className="text-xs text-gray-400 mb-1">Closed IC Trades <span className="text-gray-600">(All-time)</span></div>
                <div className={`text-lg font-bold ${icRealizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {!reconciliation && !icPerformance ? <span className="animate-pulse text-gray-500">---</span> : (
                    <>{icRealizedPnL >= 0 ? '+' : ''}{formatCurrency(icRealizedPnL)}</>
                  )}
                </div>
                <div className="text-xs text-gray-500">{icPerformance?.performance?.closed_trades?.total || 0} trade{(icPerformance?.performance?.closed_trades?.total || 0) !== 1 ? 's' : ''} completed</div>
              </div>

              {/* 3: Open IC Positions - renamed from "IC Unrealized" */}
              <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
                <div className="text-xs text-gray-400 mb-1">Open IC Positions <span className="text-gray-600">(Current)</span></div>
                <div className={`text-lg font-bold ${icUnrealizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {!reconciliation && !icPositions ? <span className="animate-pulse text-gray-500">---</span> : (
                    <>{icUnrealizedPnL >= 0 ? '+' : ''}{formatCurrency(icUnrealizedPnL)}</>
                  )}
                </div>
                <div className="text-xs text-gray-500">{icPositions?.count || 0} position{(icPositions?.count || 0) !== 1 ? 's' : ''} open now</div>
              </div>

              {/* 4: Total IC Profit - sum of closed + open */}
              <div className="bg-emerald-900/20 rounded-lg p-3 border border-emerald-600/30">
                <div className="text-xs text-emerald-400/70 mb-1">Total IC Profit <span className="text-gray-500">(All-time)</span></div>
                <div className={`text-lg font-bold ${totalICReturns >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {!reconciliation ? <span className="animate-pulse text-gray-500">---</span> : (
                    <>{totalICReturns >= 0 ? '+' : ''}{formatCurrency(totalICReturns)}</>
                  )}
                </div>
                <div className="text-xs text-gray-500">= closed + open combined</div>
              </div>

              {/* 5: Borrowing Cost Accrued - clearer name */}
              <div className="bg-red-900/20 rounded-lg p-3 border border-red-700/30">
                <div className="text-xs text-red-400/70 mb-1">Borrowing Cost <span className="text-gray-500">(To Date)</span></div>
                <div className="text-lg font-bold text-red-400">
                  {!reconciliation && !status ? <span className="animate-pulse text-gray-500">---</span> : (
                    <>−{formatCurrency(totalCostAccrued)}</>
                  )}
                </div>
                <div className="text-xs text-gray-500">interest accrued so far</div>
              </div>

              {/* 6: NET PROFIT - the bottom line */}
              <div className={`rounded-lg p-3 border-2 ${netPnL >= 0 ? 'bg-green-900/30 border-green-500/50' : 'bg-red-900/30 border-red-500/50'}`}>
                <div className="text-xs text-gray-300 mb-1 font-medium">NET PROFIT <span className="font-normal text-gray-500">(All-time)</span></div>
                <div className={`text-xl font-bold ${netPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {!reconciliation ? <span className="animate-pulse text-gray-500">---</span> : (
                    <>{netPnL >= 0 ? '+' : ''}{formatCurrency(netPnL)}</>
                  )}
                </div>
                <div className="text-xs text-gray-400">
                  {!reconciliation ? 'Loading...' : netPnL >= 0 ? 'IC profit exceeds borrowing cost' : 'IC profit below borrowing cost'}
                </div>
              </div>
            </div>

            {/* Visual equation showing how the numbers add up */}
            <div className="mt-4 pt-3 border-t border-gray-700/50">
              <div className="flex items-center justify-center gap-3 text-sm flex-wrap">
                <div className="flex items-center gap-1 bg-gray-800/50 px-2 py-1 rounded">
                  <span className="text-gray-500 text-xs">IC Profit:</span>
                  <span className={`font-mono font-bold ${totalICReturns >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {formatCurrency(totalICReturns)}
                  </span>
                </div>
                <span className="text-gray-500 text-lg font-bold">−</span>
                <div className="flex items-center gap-1 bg-gray-800/50 px-2 py-1 rounded">
                  <span className="text-gray-500 text-xs">Cost:</span>
                  <span className="font-mono font-bold text-red-400">{formatCurrency(totalCostAccrued)}</span>
                </div>
                <span className="text-gray-500 text-lg font-bold">=</span>
                <div className={`flex items-center gap-1 px-3 py-1 rounded font-bold ${netPnL >= 0 ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
                  <span className="text-xs opacity-75">Net:</span>
                  <span className="font-mono text-lg">{netPnL >= 0 ? '+' : ''}{formatCurrency(netPnL)}</span>
                </div>
              </div>
              {/* Data freshness indicator */}
              <div className="mt-3 text-center text-xs text-gray-600">
                Data refreshes every 30 seconds • {reconciliation ?
                  <span className="text-gray-500">Last updated: {new Date().toLocaleTimeString()}</span> :
                  <span className="animate-pulse">Loading...</span>
                }
              </div>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden">
            <div className="flex gap-1 p-1 bg-gray-900/50 border-b border-gray-800 overflow-x-auto">
              {[
                { key: 'overview', label: '📋 Overview' },
                { key: 'positions', label: '🏦 Box Spreads (Long-Term Borrowing)' },
                { key: 'ic-trading', label: '⚡ Iron Condors (Daily Income)' },
                { key: 'analytics', label: '📊 Performance' },
                { key: 'education', label: '📚 Education' },
                { key: 'howItWorks', label: '❓ How It Works' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key as any)}
                  className={`px-6 py-3 font-medium rounded-lg transition-colors ${
                    activeTab === tab.key ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            <div className="p-6">
              {isLoading && (
          <div className="text-center py-12">
            <div className="animate-spin text-4xl mb-4">🔥</div>
            <p className="text-gray-400">Loading PROMETHEUS data...</p>
          </div>
        )}

        {isError && (
          <div className="bg-red-900/50 border border-red-700 rounded-lg p-6 text-center">
            <p className="text-red-300">Failed to load PROMETHEUS data</p>
          </div>
        )}

        {!isLoading && !isError && (
          <>
            {/* Overview Tab */}
            {activeTab === 'overview' && (
              <div className="space-y-6">
                {/* Quick Explainer for Newcomers - Always visible, collapsible for returning users */}
                <div className="bg-emerald-900/20 rounded-lg p-4 border border-emerald-600/30">
                  <details className="group" open>
                    <summary className="flex items-center justify-between cursor-pointer text-emerald-400 font-medium">
                      <span>How PROMETHEUS Makes Money</span>
                      <span className="text-xs text-gray-500">(click to collapse)</span>
                    </summary>
                    <div className="mt-3 pt-3 border-t border-emerald-700/30 text-sm text-gray-300">
                      {/* Simple 3-step explanation */}
                      <div className="grid md:grid-cols-3 gap-4 mb-4">
                        <div className="bg-black/30 rounded-lg p-3">
                          <div className="text-blue-400 font-bold text-xs mb-1">1. BORROW CHEAP</div>
                          <p className="text-xs text-gray-400">Sell box spreads to borrow cash at ~4-5% interest (cheaper than margin loans at 8-12%)</p>
                        </div>
                        <div className="bg-black/30 rounded-lg p-3">
                          <div className="text-emerald-400 font-bold text-xs mb-1">2. TRADE ICs</div>
                          <p className="text-xs text-gray-400">Use borrowed capital to trade Iron Condors, which generate premium income when markets stay within a range</p>
                        </div>
                        <div className="bg-black/30 rounded-lg p-3">
                          <div className="text-green-400 font-bold text-xs mb-1">3. PROFIT IF IC &gt; COST</div>
                          <p className="text-xs text-gray-400">If IC trading profit exceeds borrowing cost, you keep the difference. Goal: earn more than you pay.</p>
                        </div>
                      </div>

                      {/* Terminology guide */}
                      <div className="text-xs text-gray-400 space-y-1">
                        <p className="font-medium text-gray-300 mb-2">What the numbers mean:</p>
                        <div className="grid md:grid-cols-2 gap-x-6 gap-y-1">
                          <p><span className="text-blue-400 font-medium">Capital Borrowed</span> = Cash from box spreads (your &quot;loan&quot;)</p>
                          <p><span className="text-gray-300 font-medium">Closed IC Trades</span> = Profit from ICs that have finished</p>
                          <p><span className="text-gray-300 font-medium">Open IC Positions</span> = Current value of ICs still running</p>
                          <p><span className="text-emerald-400 font-medium">Total IC Profit</span> = Closed + Open (all IC earnings)</p>
                          <p><span className="text-red-400 font-medium">Borrowing Cost</span> = Interest accrued so far</p>
                          <p><span className="text-yellow-400 font-medium">Efficiency 1.0x</span> = Break-even. Above = profit, below = loss</p>
                        </div>
                      </div>
                    </div>
                  </details>
                </div>

                {/* THE MONEY FLOW - With REAL Numbers */}
                <div className="bg-gradient-to-r from-gray-800 via-gray-800 to-gray-800 rounded-lg p-6 border border-orange-500/30">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    <span className="text-2xl">💸</span> Your Money Flow
                    <span className="text-sm font-normal text-gray-400">- How capital moves through PROMETHEUS</span>
                  </h2>
                  <div className="grid md:grid-cols-4 gap-4">
                    {/* Step 1: Borrow */}
                    <div className="relative">
                      <div className="bg-blue-900/40 rounded-lg p-4 border border-blue-600/50 h-full">
                        <div className="text-xs text-gray-400 mb-1">STEP 1: BORROW</div>
                        <div className="text-2xl font-bold text-blue-400">{formatCurrency(totalBorrowed)}</div>
                        <div className="text-xs text-gray-300 mt-2">
                          via <span className="text-white font-medium">{positions?.positions?.length || 0}</span> box spread{(positions?.positions?.length || 0) !== 1 ? 's' : ''}
                        </div>
                        <div className="mt-2 text-xs text-gray-400">
                          at <span className="text-yellow-400 font-medium">{(status?.performance?.avg_implied_rate || rateAnalysis?.box_implied_rate || 0).toFixed(2)}%</span> annual rate
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          Daily cost: <span className="text-red-400">{formatCurrency((totalBorrowed * (rateAnalysis?.box_implied_rate || 4.0) / 100) / 365)}</span>
                        </div>
                      </div>
                      <div className="hidden md:block absolute -right-2 top-1/2 text-2xl z-10 text-gray-500">→</div>
                    </div>
                    {/* Step 2: Reserve */}
                    <div className="relative">
                      <div className="bg-yellow-900/40 rounded-lg p-4 border border-yellow-600/50 h-full">
                        <div className="text-xs text-gray-400 mb-1">STEP 2: RESERVE</div>
                        <div className="text-2xl font-bold text-yellow-400">{formatCurrency(reconciliation?.capital_deployment?.reserved || totalBorrowed * (reconciliation?.config?.reserve_pct || 10) / 100)}</div>
                        <div className="text-xs text-gray-300 mt-2">
                          held as margin buffer
                        </div>
                        <div className="mt-2 text-xs text-gray-400">
                          {reconciliation?.config?.reserve_pct || 10}% reserved for safety
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          Protects against IC losses
                        </div>
                      </div>
                      <div className="hidden md:block absolute -right-2 top-1/2 text-2xl z-10 text-gray-500">→</div>
                    </div>
                    {/* Step 3: Deploy to IC */}
                    <div className="relative">
                      <div className="bg-orange-900/40 rounded-lg p-4 border border-orange-600/50 h-full">
                        <div className="text-xs text-gray-400 mb-1">STEP 3: DEPLOY</div>
                        <div className="text-2xl font-bold text-orange-400">{formatCurrency(reconciliation?.capital_deployment?.available_to_trade || icStatus?.status?.available_capital || 0)}</div>
                        <div className="text-xs text-gray-300 mt-2">
                          available for IC trading
                        </div>
                        <div className="mt-2 text-xs text-gray-400">
                          <span className="text-white font-medium">{icStatus?.status?.open_positions || 0}</span> positions using <span className="text-white font-medium">{formatCurrency(reconciliation?.capital_deployment?.in_ic_trades || (icStatus?.status?.open_positions || 0) * (reconciliation?.config?.min_capital_per_trade || 5000))}</span>
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          {icStatus?.status?.daily_trades || 0} trades today
                        </div>
                      </div>
                      <div className="hidden md:block absolute -right-2 top-1/2 text-2xl z-10 text-gray-500">→</div>
                    </div>
                    {/* Step 4: Returns */}
                    <div>
                      <div className={`rounded-lg p-4 h-full ${netPnL >= 0 ? 'bg-green-900/40 border border-green-600/50' : 'bg-red-900/40 border border-red-600/50'}`}>
                        <div className="text-xs text-gray-400 mb-1">STEP 4: RETURNS</div>
                        <div className={`text-2xl font-bold ${netPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {formatCurrency(netPnL)}
                        </div>
                        <div className="text-xs text-gray-300 mt-2">
                          net profit (IC returns - costs)
                        </div>
                        <div className="mt-2 text-xs text-gray-400">
                          IC: <span className={totalICReturns >= 0 ? 'text-green-400' : 'text-red-400'}>{totalICReturns >= 0 ? '+' : ''}{formatCurrency(totalICReturns)}</span>
                        </div>
                        <div className="text-xs text-gray-500">
                          Cost: <span className="text-red-400">−{formatCurrency(totalCostAccrued)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  {totalBorrowed > 0 ? (
                    <div className={`mt-4 p-3 rounded-lg text-sm ${costEfficiency > 1 ? 'bg-green-900/30 border border-green-600/30' : 'bg-yellow-900/30 border border-yellow-600/30'}`}>
                      <strong className={costEfficiency > 1 ? 'text-green-400' : 'text-yellow-400'}>
                        {costEfficiency > 1 ? '✅ PROFITABLE:' : '⚠️ BELOW BREAK-EVEN:'}
                      </strong>
                      <span className="text-gray-300 ml-2">
                        IC returns are <span className="font-bold">{costEfficiency.toFixed(1)}x</span> borrowing costs.
                        {costEfficiency > 1
                          ? ` You're earning ${formatCurrency(netPnL)} more than your borrowing costs.`
                          : ` You need to earn ${formatCurrency(-netPnL)} more to break even.`}
                      </span>
                    </div>
                  ) : (
                    <div className="mt-4 p-3 bg-yellow-900/30 border border-yellow-600/30 rounded-lg text-sm">
                      <strong className="text-yellow-400">⚠️ NO CAPITAL DEPLOYED:</strong>
                      <span className="text-gray-300 ml-2">
                        Open box spreads first to borrow capital for IC trading.
                      </span>
                    </div>
                  )}
                </div>

                {/* MARGIN & COLLATERAL REQUIRED */}
                <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    <span className="text-2xl">🏦</span> Margin & Collateral
                  </h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Box Spread Collateral</div>
                      <div className="text-2xl font-bold text-yellow-400">
                        {positions?.positions?.length > 0
                          ? formatCurrency(positions.positions.reduce((sum: number, p: Position) => sum + (p.strike_width * 100 * p.contracts), 0))
                          : formatCurrency((status?.config?.strike_width || 50) * 100 * 10)}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        = Strike width × $100 × contracts
                      </div>
                      <div className="mt-2 text-xs text-gray-400">
                        This is the face value owed at expiration - your broker holds this as collateral
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">IC Trading Margin</div>
                      <div className="text-2xl font-bold text-blue-400">
                        {formatCurrency(icStatus?.status?.available_capital || 0)}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Available for Iron Condor trades
                      </div>
                      <div className="mt-2 text-xs text-gray-400">
                        PROMETHEUS uses borrowed capital to fund IC margin requirements
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Tradier Requirements</div>
                      <div className="text-lg font-bold text-gray-300">PM Account Required</div>
                      <div className="text-xs text-gray-500 mt-1">
                        Portfolio Margin for best rates
                      </div>
                      <div className="mt-2 text-xs text-gray-400">
                        SPX options = European style (no early assignment risk)
                      </div>
                    </div>
                  </div>
                  {positions?.positions?.length > 0 && (
                    <div className="mt-4 grid md:grid-cols-2 gap-4 text-sm">
                      <div className="bg-black/30 rounded p-3">
                        <span className="text-gray-400">Cash Received: </span>
                        <span className="text-green-400 font-bold">{formatCurrency(totalBorrowed)}</span>
                        <span className="text-gray-500"> (what you have to deploy)</span>
                      </div>
                      <div className="bg-black/30 rounded p-3">
                        <span className="text-gray-400">Face Value Owed: </span>
                        <span className="text-red-400 font-bold">
                          {formatCurrency(positions.positions.reduce((sum: number, p: Position) => sum + (p.strike_width * 100 * p.contracts), 0))}
                        </span>
                        <span className="text-gray-500"> (at expiration)</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* TODAY'S ACTIVITY */}
                <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    <span className="text-2xl">📊</span> Today&apos;s Activity
                    <span className="text-sm font-normal text-gray-500 ml-2">
                      ({new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })})
                    </span>
                  </h2>
                  <div className="grid md:grid-cols-4 gap-4">
                    <div className="bg-gradient-to-br from-green-900/30 to-gray-800 rounded-lg p-4 border border-green-700/30">
                      <div className="text-xs text-gray-400 mb-1">Today&apos;s IC P&L</div>
                      <div className={`text-2xl font-bold ${(icPerformance?.performance?.today?.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {!icPerformance ? <span className="animate-pulse text-gray-500">---</span> : (
                          <>{(icPerformance?.performance?.today?.pnl || 0) >= 0 ? '+' : ''}{formatCurrency(icPerformance?.performance?.today?.pnl || 0)}</>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {icPerformance?.performance?.today?.trades || 0} trade{(icPerformance?.performance?.today?.trades || 0) !== 1 ? 's' : ''} closed today
                      </div>
                    </div>
                    <div className="bg-gradient-to-br from-orange-900/30 to-gray-800 rounded-lg p-4 border border-orange-700/30">
                      <div className="text-xs text-gray-400 mb-1">IC Positions Open <span className="text-gray-600">(Now)</span></div>
                      <div className="text-2xl font-bold text-orange-400">
                        {!icStatus ? <span className="animate-pulse text-gray-500">---</span> : icStatus?.status?.open_positions || 0}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Unrealized: <span className={(icStatus?.status?.total_unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                          {(icStatus?.status?.total_unrealized_pnl || 0) >= 0 ? '+' : ''}{formatCurrency(icStatus?.status?.total_unrealized_pnl || 0)}
                        </span>
                      </div>
                    </div>
                    <div className="bg-gradient-to-br from-blue-900/30 to-gray-800 rounded-lg p-4 border border-blue-700/30">
                      <div className="text-xs text-gray-400 mb-1">Daily Trade Count</div>
                      <div className="text-2xl font-bold text-blue-400">
                        {!icStatus ? <span className="animate-pulse text-gray-500">---</span> : (
                          <>{icStatus?.status?.daily_trades || 0} / {icStatus?.status?.max_daily_trades || 5}</>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Trades opened today / max
                      </div>
                    </div>
                    <div className="bg-gradient-to-br from-purple-900/30 to-gray-800 rounded-lg p-4 border border-purple-700/30">
                      <div className="text-xs text-gray-400 mb-1">Daily Borrowing Cost</div>
                      <div className="text-2xl font-bold text-purple-400">
                        {!positions ? <span className="animate-pulse text-gray-500">---</span> : (
                          positions?.positions?.length > 0
                            ? <>−{formatCurrency(positions.positions.reduce((sum: number, p: Position) => sum + (p.daily_cost || 0), 0))}</>
                            : <span className="text-gray-500">$0.00</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {positions?.positions?.length > 0 ? 'Interest accruing daily' : 'No active box spreads'}
                      </div>
                    </div>
                  </div>

                  {/* Recent Activity Feed */}
                  {icLogs?.logs?.length > 0 && (
                    <div className="mt-4">
                      <div className="text-sm font-medium text-gray-400 mb-2">Recent Activity</div>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {icLogs.logs.slice(0, 5).map((log: any, idx: number) => (
                          <div key={idx} className="text-xs bg-black/30 rounded p-2 flex justify-between">
                            <span className="text-gray-300">{log.action}: {log.message?.substring(0, 60)}...</span>
                            <span className="text-gray-500">{new Date(log.log_time).toLocaleTimeString()}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* CAPITAL DEPLOYMENT - Using capitalFlow data */}
                {capitalFlow && (
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                      <span className="text-2xl">💰</span> Capital Deployment
                    </h2>
                    <div className="grid md:grid-cols-2 gap-6">
                      {/* Left: Where the money goes */}
                      <div>
                        <div className="text-sm font-medium text-gray-400 mb-3">Where Your Borrowed Capital Goes</div>
                        <div className="space-y-3">
                          <div className="bg-black/30 rounded-lg p-3">
                            <div className="flex justify-between items-center">
                              <span className="text-orange-400 font-medium">🔥 PROMETHEUS IC Trading</span>
                              <span className="font-bold">{formatCurrency(icStatus?.status?.available_capital || 0)}</span>
                            </div>
                            <div className="mt-1 text-xs text-gray-500">
                              SPX 0DTE Iron Condors - Primary return generator
                            </div>
                          </div>
                          <div className="bg-black/30 rounded-lg p-3">
                            <div className="flex justify-between items-center">
                              <span className="text-gray-400 font-medium">💵 Reserve</span>
                              <span className="font-bold">{formatCurrency(capitalFlow?.deployment_summary?.reserve?.amount || 0)}</span>
                            </div>
                            <div className="mt-1 text-xs text-gray-500">
                              Buffer for IC margin and adjustments
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Right: Returns breakdown */}
                      <div>
                        <div className="text-sm font-medium text-gray-400 mb-3">Returns Generated</div>
                        <div className="bg-black/30 rounded-lg p-4">
                          <div className="flex justify-between items-center mb-3">
                            <span className="text-gray-400">Total IC Returns</span>
                            <span className="text-green-400 font-bold text-xl">{formatCurrency(totalICReturns)}</span>
                          </div>
                          <div className="flex justify-between items-center mb-3">
                            <span className="text-gray-400">Borrowing Costs Paid</span>
                            <span className="text-red-400 font-bold text-xl">-{formatCurrency(totalCostAccrued)}</span>
                          </div>
                          <div className="border-t border-gray-600 pt-3 flex justify-between items-center">
                            <span className="text-white font-medium">Net Profit</span>
                            <span className={`font-bold text-2xl ${netPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {formatCurrency(netPnL)}
                            </span>
                          </div>
                        </div>
                        {totalBorrowed > 0 && (
                          <div className="mt-3 text-center p-2 bg-gray-700/50 rounded">
                            <span className="text-gray-400">ROI on Borrowed Capital: </span>
                            <span className={`font-bold ${returnOnBorrowed >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {formatPct(returnOnBorrowed)}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Active Position Details - Show when positions exist */}
                {positions?.positions?.length > 0 && (
                  <div className="bg-gradient-to-br from-orange-900/30 to-gray-800 rounded-lg p-6 border border-orange-500/50">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-2xl font-bold">Active Box Spread Position</h2>
                      <span className="px-3 py-1 bg-green-600 text-white rounded-full text-sm font-medium">LIVE</span>
                    </div>

                    {positions.positions.map((pos: Position) => {
                      // Calculate derived metrics using actual backend data
                      const faceValue = pos.strike_width * 100 * pos.contracts
                      const creditReceived = pos.total_credit_received
                      const owedAtExpiration = pos.total_owed_at_expiration || faceValue
                      // Use actual dte_at_entry from backend, not hardcoded assumption
                      const totalDays = pos.dte_at_entry || 180  // Backend provides original DTE
                      const daysElapsed = totalDays - pos.current_dte
                      const progressPct = Math.min(100, Math.max(0, (daysElapsed / totalDays) * 100))
                      // Use actual daily_cost from backend, fall back to calculated if not available
                      const dailyAccrual = pos.daily_cost || (pos.borrowing_cost / Math.max(1, daysElapsed))
                      const projectedTotalCost = dailyAccrual * totalDays
                      const costAccruedSoFar = pos.cost_accrued_to_date || pos.borrowing_cost
                      const breakEvenICReturn = projectedTotalCost  // Need to earn at least the total borrowing cost
                      const isAboveBreakEven = pos.total_ic_returns >= costAccruedSoFar
                      const netROI = creditReceived > 0 ? (pos.net_profit / creditReceived) * 100 : 0
                      // Format open_time for display
                      const openDate = pos.open_time ? new Date(pos.open_time).toLocaleDateString() : 'N/A'

                      return (
                        <div key={pos.position_id} className="space-y-6">
                          {/* Position Structure */}
                          <div className="grid md:grid-cols-2 gap-6">
                            {/* Left: Position Details */}
                            <div className="space-y-4">
                              <div className="bg-black/40 rounded-lg p-4">
                                <h3 className="text-sm font-medium text-gray-400 mb-3">POSITION STRUCTURE</h3>
                                <div className="grid grid-cols-2 gap-4">
                                  <div>
                                    <div className="text-xs text-gray-500">Ticker</div>
                                    <div className="text-xl font-bold text-white">{pos.ticker}</div>
                                  </div>
                                  <div>
                                    <div className="text-xs text-gray-500">Contracts</div>
                                    <div className="text-xl font-bold text-white">{pos.contracts}</div>
                                  </div>
                                </div>
                                {/* Box Spread = 4 Legs (Synthetic Loan) */}
                                <div className="mt-4 pt-4 border-t border-gray-700">
                                  <div className="text-xs text-gray-500 mb-2">Box Spread Structure (4 Legs)</div>
                                  <div className="grid grid-cols-2 gap-2 text-sm">
                                    {/* Call Spread (Bull Call) */}
                                    <div className="bg-green-900/20 rounded p-2 border border-green-700/30">
                                      <div className="text-xs text-green-400 font-medium mb-1">CALL SPREAD</div>
                                      <div className="flex justify-between">
                                        <span className="text-green-400">+LONG {pos.lower_strike}C</span>
                                      </div>
                                      <div className="flex justify-between">
                                        <span className="text-red-400">−SHORT {pos.upper_strike}C</span>
                                      </div>
                                    </div>
                                    {/* Put Spread (Bull Put) */}
                                    <div className="bg-purple-900/20 rounded p-2 border border-purple-700/30">
                                      <div className="text-xs text-purple-400 font-medium mb-1">PUT SPREAD</div>
                                      <div className="flex justify-between">
                                        <span className="text-red-400">−SHORT {pos.lower_strike}P</span>
                                      </div>
                                      <div className="flex justify-between">
                                        <span className="text-green-400">+LONG {pos.upper_strike}P</span>
                                      </div>
                                    </div>
                                  </div>
                                  <div className="mt-2 text-center text-xs text-gray-500">
                                    {pos.ticker} {pos.lower_strike}/{pos.upper_strike} • {pos.strike_width}pt width • {pos.contracts} contracts
                                  </div>
                                </div>
                              </div>

                              {/* Expiration & Timeline */}
                              <div className="bg-black/40 rounded-lg p-4">
                                <h3 className="text-sm font-medium text-gray-400 mb-3">EXPIRATION TIMELINE</h3>
                                <div className="flex justify-between items-center mb-2">
                                  <div className="text-left">
                                    <div className="text-gray-500 text-xs">Opened</div>
                                    <div className="text-sm font-medium">{openDate}</div>
                                  </div>
                                  <div className="text-center px-4">
                                    <div className="text-gray-500 text-xs">Original DTE</div>
                                    <div className="text-sm font-medium text-blue-400">{pos.dte_at_entry || totalDays} days</div>
                                  </div>
                                  <div className="text-right">
                                    <div className="text-gray-500 text-xs">Expires</div>
                                    <div className="text-sm font-medium">{pos.expiration}</div>
                                  </div>
                                </div>
                                {/* Progress Bar */}
                                <div className="relative h-4 bg-gray-700 rounded-full overflow-hidden mb-2">
                                  <div
                                    className="absolute left-0 top-0 h-full bg-gradient-to-r from-orange-600 to-orange-400 transition-all"
                                    style={{ width: `${progressPct}%` }}
                                  />
                                  <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white">
                                    {Math.round(progressPct)}% elapsed
                                  </div>
                                </div>
                                <div className="flex justify-between text-sm">
                                  <span className="text-gray-400">{daysElapsed > 0 ? daysElapsed : 0} days elapsed</span>
                                  <span className={`font-bold ${pos.current_dte <= 30 ? 'text-yellow-400' : 'text-white'}`}>
                                    {pos.current_dte} DTE remaining
                                  </span>
                                </div>
                                {pos.current_dte <= 30 && (
                                  <div className="mt-2 px-3 py-2 bg-yellow-900/50 border border-yellow-600/50 rounded text-sm text-yellow-400">
                                    ⚠️ Position approaching roll threshold (30 DTE)
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Right: Financial Summary */}
                            <div className="space-y-4">
                              <div className="bg-black/40 rounded-lg p-4">
                                <h3 className="text-sm font-medium text-gray-400 mb-3">FINANCIAL SUMMARY</h3>
                                <div className="space-y-3">
                                  <div className="flex justify-between items-center">
                                    <span className="text-gray-400">Credit Received</span>
                                    <span className="text-xl font-bold text-green-400">{formatCurrency(creditReceived)}</span>
                                  </div>
                                  <div className="flex justify-between items-center">
                                    <span className="text-gray-400">Face Value (owed at exp)</span>
                                    <span className="text-xl font-bold text-red-400">{formatCurrency(owedAtExpiration)}</span>
                                  </div>
                                  <div className="border-t border-gray-700 pt-3 flex justify-between items-center">
                                    <span className="text-gray-400">Implied Annual Rate</span>
                                    <span className="text-xl font-bold text-blue-400">{formatPct(pos.implied_annual_rate)}</span>
                                  </div>
                                </div>
                              </div>

                              <div className="bg-black/40 rounded-lg p-4">
                                <h3 className="text-sm font-medium text-gray-400 mb-3">BORROWING COST ACCRUAL</h3>
                                <div className="space-y-3">
                                  <div className="flex justify-between items-center">
                                    <span className="text-gray-400">Accrued to Date</span>
                                    <span className="text-lg font-bold text-red-400">{formatCurrency(costAccruedSoFar)}</span>
                                  </div>
                                  <div className="flex justify-between items-center text-sm">
                                    <span className="text-gray-500">Daily Accrual Rate</span>
                                    <span className="text-gray-300">~{formatCurrency(dailyAccrual)}/day</span>
                                  </div>
                                  <div className="flex justify-between items-center text-sm">
                                    <span className="text-gray-500">Projected Total Cost</span>
                                    <span className="text-gray-300">{formatCurrency(projectedTotalCost)}</span>
                                  </div>
                                  {/* Accrual Progress Bar */}
                                  <div className="pt-2">
                                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                                      <span>0%</span>
                                      <span>Cost Progress</span>
                                      <span>100%</span>
                                    </div>
                                    <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                                      <div
                                        className="h-full bg-gradient-to-r from-red-700 to-red-500 transition-all"
                                        style={{ width: `${Math.min(100, (costAccruedSoFar / projectedTotalCost) * 100)}%` }}
                                      />
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Break-Even Analysis */}
                          <div className="bg-black/40 rounded-lg p-4">
                            <h3 className="text-sm font-medium text-gray-400 mb-3">BREAK-EVEN ANALYSIS</h3>
                            <div className="grid md:grid-cols-4 gap-4">
                              <div className={`rounded-lg p-4 text-center ${isAboveBreakEven ? 'bg-green-900/30 border border-green-600/50' : 'bg-red-900/30 border border-red-600/50'}`}>
                                <div className="text-xs text-gray-400 mb-1">Status</div>
                                <div className={`text-2xl font-bold ${isAboveBreakEven ? 'text-green-400' : 'text-red-400'}`}>
                                  {isAboveBreakEven ? 'PROFITABLE' : 'BELOW B/E'}
                                </div>
                              </div>
                              <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                                <div className="text-xs text-gray-400 mb-1">Costs Accrued</div>
                                <div className="text-xl font-bold text-yellow-400">{formatCurrency(costAccruedSoFar)}</div>
                                <div className="text-xs text-gray-500">so far ({formatCurrency(breakEvenICReturn)} total)</div>
                              </div>
                              <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                                <div className="text-xs text-gray-400 mb-1">Actual IC Returns</div>
                                <div className="text-xl font-bold text-green-400">{formatCurrency(pos.total_ic_returns)}</div>
                                <div className="text-xs text-gray-500">earned so far</div>
                              </div>
                              <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                                <div className="text-xs text-gray-400 mb-1">Net ROI</div>
                                <div className={`text-xl font-bold ${netROI >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatPct(netROI)}
                                </div>
                                <div className="text-xs text-gray-500">on credit received</div>
                              </div>
                            </div>

                            {/* Visual Break-Even Bar - Returns vs Accrued Costs */}
                            <div className="mt-4">
                              <div className="flex justify-between text-xs text-gray-400 mb-1">
                                <span>$0</span>
                                <span>Accrued Cost: {formatCurrency(costAccruedSoFar)}</span>
                                <span>{formatCurrency(costAccruedSoFar * 2)}</span>
                              </div>
                              <div className="relative h-6 bg-gray-700 rounded-full overflow-hidden">
                                {/* Break-even marker at 50% (where returns = costs) */}
                                <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-yellow-400 z-10" />
                                {/* Actual returns bar */}
                                <div
                                  className={`absolute left-0 top-0 h-full transition-all ${isAboveBreakEven ? 'bg-gradient-to-r from-green-600 to-green-400' : 'bg-gradient-to-r from-red-600 to-red-400'}`}
                                  style={{ width: `${Math.min(100, (pos.total_ic_returns / (costAccruedSoFar * 2 || 1)) * 100)}%` }}
                                />
                              </div>
                              <div className="text-center mt-2 text-sm">
                                <span className="text-gray-400">IC Returns: </span>
                                <span className={isAboveBreakEven ? 'text-green-400' : 'text-red-400'}>
                                  {formatCurrency(pos.total_ic_returns)}
                                </span>
                                <span className="text-gray-400"> | Net vs Accrued: </span>
                                <span className={pos.total_ic_returns - costAccruedSoFar >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  {formatCurrency(pos.total_ic_returns - costAccruedSoFar)}
                                </span>
                              </div>
                            </div>
                          </div>

                          {/* Assignment Risk */}
                          <div className="flex items-center justify-between bg-gray-700/30 rounded-lg p-4">
                            <div className="flex items-center gap-3">
                              <span className="text-gray-400">Early Assignment Risk:</span>
                              <span className={`px-3 py-1 rounded font-medium ${
                                pos.early_assignment_risk === 'LOW' ? 'bg-green-900/50 text-green-400' :
                                pos.early_assignment_risk === 'MEDIUM' ? 'bg-yellow-900/50 text-yellow-400' :
                                'bg-red-900/50 text-red-400'
                              }`}>
                                {pos.early_assignment_risk}
                              </span>
                            </div>
                            <div className="text-sm text-gray-400">
                              SPX = European-style (no early exercise)
                            </div>
                          </div>

                          {/* PROMETHEUS IC Trading Summary */}
                          <div className="bg-black/40 rounded-lg p-4">
                            <h3 className="text-sm font-medium text-gray-400 mb-3">IC TRADING WITH BORROWED CAPITAL</h3>
                            <div className="grid grid-cols-3 gap-3">
                              <div className="text-center">
                                <div className="text-xs text-gray-500">Capital Available</div>
                                <div className="text-lg font-bold text-orange-400">{formatCurrency(pos.total_cash_deployed)}</div>
                                <div className="text-xs text-gray-400">from box spread</div>
                              </div>
                              <div className="text-center">
                                <div className="text-xs text-gray-500">IC Returns</div>
                                <div className={`text-lg font-bold ${pos.total_ic_returns >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatCurrency(pos.total_ic_returns)}
                                </div>
                                <div className="text-xs text-gray-400">realized + unrealized</div>
                              </div>
                              <div className="text-center">
                                <div className="text-xs text-gray-500">Borrowing Cost</div>
                                <div className="text-lg font-bold text-red-400">{formatCurrency(pos.cost_accrued_to_date)}</div>
                                <div className="text-xs text-gray-400">accrued to date</div>
                              </div>
                            </div>
                          </div>

                          {/* Net P&L Summary */}
                          <div className={`rounded-lg p-4 ${pos.net_profit >= 0 ? 'bg-green-900/20 border border-green-600/30' : 'bg-red-900/20 border border-red-600/30'}`}>
                            <div className="flex justify-between items-center">
                              <div>
                                <div className="text-sm text-gray-400">Net Profit (IC Returns - Borrowing Cost)</div>
                                <div className={`text-3xl font-bold ${pos.net_profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatCurrency(pos.net_profit)}
                                </div>
                              </div>
                              <div className="text-right">
                                <div className="text-sm text-gray-400">ROI on Borrowed Capital</div>
                                <div className={`text-2xl font-bold ${netROI >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatPct(netROI)}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* No Position State - Show System Configuration */}
                {(!positions?.positions || positions.positions.length === 0) && (
                  <div className="space-y-6">
                    {/* System Ready Banner */}
                    <div className="bg-gradient-to-br from-orange-900/30 to-gray-800 rounded-lg p-6 border border-orange-500/50">
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="text-2xl font-bold">PROMETHEUS Ready</h2>
                        <span className="px-3 py-1 bg-yellow-600 text-white rounded-full text-sm font-medium">STANDBY</span>
                      </div>
                      <p className="text-gray-400 mb-4">
                        No active box spread position. System scans for favorable opportunities at market open (8:30 AM CT) and throughout the trading day.
                      </p>
                      {rateAnalysis && (
                        <div className="space-y-2">
                          <div className={`inline-block px-4 py-2 rounded-lg ${rateAnalysis.is_favorable ? 'bg-green-900/50 text-green-400 border border-green-600' : 'bg-yellow-900/50 text-yellow-400 border border-yellow-600'}`}>
                            Current rates are <strong>{rateAnalysis.is_favorable ? 'FAVORABLE' : 'UNFAVORABLE'}</strong> for new positions
                            <span className="ml-2 text-xs opacity-75">
                              (Fed Funds: {rateAnalysis.fed_funds_rate?.toFixed(2)}% | Box Rate: {rateAnalysis.box_implied_rate?.toFixed(2)}%)
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-gray-500">
                            <span className={`w-2 h-2 rounded-full ${
                              rateAnalysis.rates_source === 'live' ? 'bg-green-500' :
                              rateAnalysis.rates_source === 'mixed' ? 'bg-green-400' :
                              rateAnalysis.rates_source === 'cached' ? 'bg-yellow-500' :
                              rateAnalysis.rates_source === 'fomc_based' ? 'bg-blue-500' :
                              rateAnalysis.rates_source === 'treasury_direct' ? 'bg-blue-400' : 'bg-red-500'
                            }`}></span>
                            <span>Rates: {
                              rateAnalysis.rates_source === 'live' ? 'LIVE (FRED API)' :
                              rateAnalysis.rates_source === 'mixed' ? 'PARTIAL LIVE' :
                              rateAnalysis.rates_source === 'cached' ? 'CACHED' :
                              rateAnalysis.rates_source === 'fomc_based' ? 'FOMC TARGET (4.25-4.50%)' :
                              rateAnalysis.rates_source === 'treasury_direct' ? 'TREASURY.GOV' : 'FALLBACK'
                            }</span>
                            {rateAnalysis.rates_last_updated && (
                              <span className="text-gray-600">| Updated: {new Date(rateAnalysis.rates_last_updated).toLocaleTimeString()}</span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* System Configuration - Always show this */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h2 className="text-xl font-bold mb-4">System Configuration</h2>
                      <p className="text-sm text-gray-400 mb-4">
                        When a position opens, these settings determine how capital is borrowed and deployed.
                      </p>

                      <div className="grid md:grid-cols-2 gap-6">
                        {/* Capital & Sizing */}
                        <div className="bg-black/30 rounded-lg p-4">
                          <h3 className="text-sm font-medium text-gray-400 mb-3">CAPITAL SETTINGS</h3>
                          <div className="space-y-3">
                            <div className="flex justify-between items-center">
                              <span className="text-gray-400">Total Capital</span>
                              <span className="text-xl font-bold text-green-400">{formatCurrency(status?.capital || 500000)}</span>
                            </div>
                            <div className="flex justify-between items-center text-sm">
                              <span className="text-gray-500">Max Position Size</span>
                              <span className="text-gray-300">{formatCurrency(status?.config?.max_position_size || 250000)}</span>
                            </div>
                            <div className="flex justify-between items-center text-sm">
                              <span className="text-gray-500">Max Positions</span>
                              <span className="text-gray-300">{status?.config?.max_positions || 5}</span>
                            </div>
                          </div>
                        </div>

                        {/* Box Spread Settings */}
                        <div className="bg-black/30 rounded-lg p-4">
                          <h3 className="text-sm font-medium text-gray-400 mb-3">BOX SPREAD SETTINGS</h3>
                          <div className="space-y-3">
                            <div className="flex justify-between items-center">
                              <span className="text-gray-400">Ticker</span>
                              <span className="text-xl font-bold text-blue-400">{status?.ticker || 'SPX'}</span>
                            </div>
                            <div className="flex justify-between items-center text-sm">
                              <span className="text-gray-500">Strike Width</span>
                              <span className="text-gray-300">{status?.config?.strike_width || 50} points (${((status?.config?.strike_width || 50) * 100).toLocaleString()}/contract)</span>
                            </div>
                            <div className="flex justify-between items-center text-sm">
                              <span className="text-gray-500">Target DTE</span>
                              <span className="text-gray-300">{status?.config?.target_dte_min || 180} - {status?.config?.target_dte_max || 365} days</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* PROMETHEUS IC Trading Settings */}
                      <div className="mt-6 bg-black/30 rounded-lg p-4">
                        <h3 className="text-sm font-medium text-gray-400 mb-3">IC TRADING CONFIGURATION</h3>
                        <p className="text-xs text-gray-500 mb-3">
                          PROMETHEUS uses borrowed capital to trade its own Iron Condors on SPX.
                        </p>
                        <div className="grid grid-cols-4 gap-2">
                          <div className="bg-orange-900/30 rounded p-3 text-center">
                            <div className="text-xs text-gray-500">Ticker</div>
                            <div className="text-lg font-bold text-orange-400">SPX</div>
                          </div>
                          <div className="bg-orange-900/30 rounded p-3 text-center">
                            <div className="text-xs text-gray-500">Strategy</div>
                            <div className="text-lg font-bold text-orange-400">0DTE IC</div>
                          </div>
                          <div className="bg-orange-900/30 rounded p-3 text-center">
                            <div className="text-xs text-gray-500">Max Positions</div>
                            <div className="text-lg font-bold text-orange-400">3</div>
                          </div>
                          <div className="bg-orange-900/30 rounded p-3 text-center">
                            <div className="text-xs text-gray-500">Cycle</div>
                            <div className="text-lg font-bold text-orange-400">10 min</div>
                          </div>
                        </div>
                      </div>

                      {/* Example Position Preview */}
                      <div className="mt-6 bg-black/30 rounded-lg p-4">
                        <h3 className="text-sm font-medium text-gray-400 mb-3">EXAMPLE: WHAT A POSITION LOOKS LIKE</h3>
                        <p className="text-xs text-gray-500 mb-3">
                          Based on current settings, a typical position would be:
                        </p>
                        <div className="grid md:grid-cols-3 gap-4 text-sm">
                          <div>
                            <span className="text-gray-500">Structure:</span>
                            <span className="ml-2 text-gray-200">SPX {status?.config?.strike_width || 50}-point box spread</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Face Value:</span>
                            <span className="ml-2 text-gray-200">${((status?.config?.strike_width || 50) * 100).toLocaleString()} per contract</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Expiration:</span>
                            <span className="ml-2 text-gray-200">{status?.config?.target_dte_min || 180}+ days out</span>
                          </div>
                        </div>
                        <div className="mt-3 text-xs text-gray-500 border-t border-gray-700 pt-3">
                          <strong>The Goal:</strong> Borrow at ~4-5% via box spread, trade SPX Iron Condors earning ~20-40%/year, profit the difference.
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Rate Analysis */}
                {rateAnalysis && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4">Current Rate Environment</h2>
                    <div className="grid md:grid-cols-4 gap-4 mb-4">
                      <div className="bg-blue-900/30 rounded-lg p-4 text-center">
                        <div className="text-xs text-gray-400 mb-1">Box Spread Rate</div>
                        <div className="text-2xl font-bold text-blue-400">{formatPct(rateAnalysis.box_implied_rate)}</div>
                        <div className="text-xs text-gray-500">Your borrowing cost</div>
                      </div>
                      <div className="bg-red-900/30 rounded-lg p-4 text-center">
                        <div className="text-xs text-gray-400 mb-1">Margin Rate</div>
                        <div className="text-2xl font-bold text-red-400">{formatPct(rateAnalysis.broker_margin_rate)}</div>
                        <div className="text-xs text-gray-500">Traditional cost</div>
                      </div>
                      <div className="bg-green-900/30 rounded-lg p-4 text-center">
                        <div className="text-xs text-gray-400 mb-1">You Save</div>
                        <div className="text-2xl font-bold text-green-400">{formatPct(Math.abs(rateAnalysis.spread_to_margin))}</div>
                        <div className="text-xs text-gray-500">Per year</div>
                      </div>
                      <div className="bg-purple-900/30 rounded-lg p-4 text-center">
                        <div className="text-xs text-gray-400 mb-1">Break-Even</div>
                        <div className="text-2xl font-bold text-purple-400">{formatPct(rateAnalysis.box_implied_rate / 12)}</div>
                        <div className="text-xs text-gray-500">Monthly IC return</div>
                      </div>
                    </div>
                    <div className={`p-4 rounded-lg ${rateAnalysis.is_favorable ? 'bg-green-900/30 border border-green-700/50' : 'bg-yellow-900/30 border border-yellow-700/50'}`}>
                      <div className={`font-medium ${rateAnalysis.is_favorable ? 'text-green-400' : 'text-yellow-400'}`}>
                        {rateAnalysis.is_favorable ? '✅' : '⚠️'} {rateAnalysis.recommendation}
                      </div>
                      <p className="text-sm text-gray-300 mt-2">{rateAnalysis.reasoning}</p>
                    </div>
                  </div>
                )}

                {/* PROMETHEUS IC Trading Status */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold">PROMETHEUS IC Trading</h2>
                    <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                      icStatus?.status?.trading_active ? 'bg-green-500/20 text-green-400' :
                      icStatus?.status?.enabled ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-red-500/20 text-red-400'
                    }`}>
                      {icStatus?.status?.trading_active ? 'TRADING' :
                       icStatus?.status?.enabled ? 'STANDBY' : 'DISABLED'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-400 mb-4">
                    Trades SPX 0DTE Iron Condors using capital from box spread borrowing.
                    {icStatus?.status?.inactive_reason && (
                      <span className="block mt-1 text-yellow-400">
                        ⚠️ {icStatus.status.inactive_reason}
                      </span>
                    )}
                  </p>
                  <div className="grid md:grid-cols-4 gap-4">
                    <div className="bg-orange-900/30 rounded-lg p-4 text-center">
                      <div className="text-xs text-gray-400 mb-1">Open Positions</div>
                      <div className="text-2xl font-bold text-orange-400">{icStatus?.status?.open_positions || 0}</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                      <div className="text-xs text-gray-400 mb-1">Today&apos;s Trades</div>
                      <div className="text-2xl font-bold">{icStatus?.status?.daily_trades || 0} / {icStatus?.status?.max_daily_trades || 5}</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                      <div className="text-xs text-gray-400 mb-1">Unrealized P&L</div>
                      <div className={`text-2xl font-bold ${(icStatus?.status?.total_unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(icStatus?.status?.total_unrealized_pnl || 0)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                      <div className="text-xs text-gray-400 mb-1">Available Capital</div>
                      <div className="text-2xl font-bold text-blue-400">{formatCurrency(icStatus?.status?.available_capital || 0)}</div>
                    </div>
                  </div>
                  <div className="mt-4 text-sm text-gray-400 bg-gray-700/30 rounded-lg p-3">
                    IC trading runs every 10 minutes when Oracle approves. See the <strong>IC Trading</strong> tab for details.
                  </div>
                </div>

                {/* ================================================================ */}
                {/* FULL RECONCILIATION SECTION - All values from API               */}
                {/* ================================================================ */}
                {reconciliation?.available && (
                  <div className="bg-gray-800 rounded-lg p-6 border-2 border-orange-500/50">
                    <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                      <span className="text-3xl">📋</span>
                      Full Reconciliation
                      <span className="text-sm font-normal text-gray-400 ml-2">
                        All calculations verified server-side
                      </span>
                      {reconciliation.net_profit_reconciliation?.reconciles && (
                        <span className="ml-auto px-3 py-1 bg-green-500/20 text-green-400 rounded-full text-sm font-medium">
                          ✓ RECONCILES
                        </span>
                      )}
                    </h2>

                    {/* SECTION 1: Per-Position Box Spread Reconciliation */}
                    {reconciliation.box_spreads?.positions?.length > 0 && (
                      <div className="mb-8">
                        <h3 className="text-lg font-bold mb-4 text-blue-400 flex items-center gap-2">
                          📦 Box Spread Capital Reconciliation
                          <span className="text-sm font-normal text-gray-400">
                            ({reconciliation.box_spreads.count} position{reconciliation.box_spreads.count !== 1 ? 's' : ''})
                          </span>
                        </h3>

                        {reconciliation.box_spreads.positions.map((pos: any) => (
                          <div key={pos.position_id} className="bg-black/40 rounded-lg p-5 mb-4 border border-blue-700/30">
                            {/* Position Header with 4-Leg Display */}
                            <div className="flex justify-between items-start mb-4 pb-3 border-b border-gray-700">
                              <div>
                                <div className="text-lg font-bold text-white mb-2">
                                  {pos.ticker} Box Spread
                                  <span className="text-gray-400 font-normal ml-2">(${pos.strike_width} width)</span>
                                </div>
                                {/* 4 Legs of Box Spread */}
                                <div className="flex gap-4 text-xs mb-2">
                                  <div className="bg-green-900/20 px-2 py-1 rounded border border-green-700/30">
                                    <span className="text-green-400">+LONG {pos.lower_strike}C</span>
                                    <span className="text-red-400 ml-2">−SHORT {pos.upper_strike}C</span>
                                  </div>
                                  <div className="bg-purple-900/20 px-2 py-1 rounded border border-purple-700/30">
                                    <span className="text-red-400">−SHORT {pos.lower_strike}P</span>
                                    <span className="text-green-400 ml-2">+LONG {pos.upper_strike}P</span>
                                  </div>
                                </div>
                                <div className="text-sm text-gray-400">
                                  Expiration: {pos.expiration} ({pos.current_dte} DTE remaining)
                                </div>
                                <div className="text-xs text-gray-500">
                                  Opened: {pos.open_time ? new Date(pos.open_time).toLocaleDateString() : 'N/A'} • Held {pos.days_held} days
                                </div>
                              </div>
                              <div className="text-right">
                                <div className="text-sm text-gray-400">Contracts</div>
                                <div className="text-2xl font-bold">{pos.contracts}</div>
                              </div>
                            </div>

                            {/* Capital Math */}
                            <div className="grid md:grid-cols-2 gap-6">
                              <div>
                                <div className="text-sm font-medium text-gray-400 mb-3">CAPITAL MATH</div>
                                <div className="space-y-2 text-sm font-mono">
                                  <div className="flex justify-between">
                                    <span className="text-gray-400">Face Value (owed at exp):</span>
                                    <span className="text-red-400">${pos.strike_width} × 100 × {pos.contracts} = {formatCurrency(pos.face_value)}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-400">Credit Received (borrowed):</span>
                                    <span className="text-green-400">{formatCurrency(pos.credit_received)}</span>
                                  </div>
                                  <div className="flex justify-between border-t border-gray-700 pt-2">
                                    <span className="text-gray-400">Total Borrowing Cost:</span>
                                    <span className="text-yellow-400">{formatCurrency(pos.total_borrowing_cost)}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-400">Implied Annual Rate:</span>
                                    <span className="text-yellow-400">{pos.implied_annual_rate?.toFixed(2)}%</span>
                                  </div>
                                </div>
                              </div>

                              {/* Cost Accrual */}
                              <div>
                                <div className="text-sm font-medium text-gray-400 mb-3">COST ACCRUAL</div>
                                <div className="space-y-2 text-sm">
                                  <div className="flex justify-between">
                                    <span className="text-gray-400">Daily Cost:</span>
                                    <span>{formatCurrency(pos.daily_cost)}/day</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-400">Cost Accrued ({pos.days_held} days):</span>
                                    <span className="text-red-400">{formatCurrency(pos.cost_accrued_to_date)}</span>
                                  </div>
                                  <div className="flex justify-between font-bold">
                                    <span className="text-yellow-400">Cost Remaining:</span>
                                    <span className="text-yellow-400">{formatCurrency(pos.cost_remaining)}</span>
                                  </div>
                                  {/* Accrual Progress Bar */}
                                  <div className="pt-2">
                                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                                      <span>Accrued</span>
                                      <span>{pos.accrual_pct?.toFixed(1)}%</span>
                                      <span>Remaining</span>
                                    </div>
                                    <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
                                      <div
                                        className="h-full bg-gradient-to-r from-red-600 to-red-400 transition-all"
                                        style={{ width: `${pos.accrual_pct || 0}%` }}
                                      />
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* PER-POSITION CAPITAL DEPLOYMENT - Where the borrowed cash sits */}
                            {pos.capital_deployment && (
                              <div className="mt-4 bg-purple-900/20 rounded-lg p-4 border border-purple-600/30">
                                <div className="text-sm font-medium text-purple-400 mb-3">
                                  WHERE THE {formatCurrency(pos.credit_received)} SITS NOW
                                  {pos.capital_deployment.reconciles && (
                                    <span className="ml-2 px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-xs">✓ TIES</span>
                                  )}
                                </div>
                                <div className="grid grid-cols-4 gap-2 text-center">
                                  <div className="bg-yellow-900/30 rounded p-2">
                                    <div className="text-xs text-gray-400">Reserved ({pos.capital_deployment.reserved_pct}%)</div>
                                    <div className="text-lg font-bold text-yellow-400">{formatCurrency(pos.capital_deployment.reserved)}</div>
                                  </div>
                                  <div className="bg-orange-900/30 rounded p-2">
                                    <div className="text-xs text-gray-400">In ICs ({pos.capital_deployment.ic_count})</div>
                                    <div className="text-lg font-bold text-orange-400">{formatCurrency(pos.capital_deployment.in_ic_trades)}</div>
                                  </div>
                                  <div className="bg-green-900/30 rounded p-2">
                                    <div className="text-xs text-gray-400">Available</div>
                                    <div className="text-lg font-bold text-green-400">{formatCurrency(pos.capital_deployment.available)}</div>
                                  </div>
                                  <div className="bg-blue-900/30 rounded p-2">
                                    <div className="text-xs text-gray-400">TOTAL</div>
                                    <div className="text-lg font-bold text-blue-400">{formatCurrency(pos.capital_deployment.total_borrowed)}</div>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* ROLL INFO - When this position needs to roll */}
                            {pos.roll_info && (
                              <div className={`mt-4 p-3 rounded-lg border ${
                                pos.roll_info.urgency === 'CRITICAL' ? 'bg-red-900/30 border-red-600/50' :
                                pos.roll_info.urgency === 'WARNING' ? 'bg-yellow-900/30 border-yellow-600/50' :
                                pos.roll_info.urgency === 'SOON' ? 'bg-orange-900/30 border-orange-600/30' :
                                'bg-gray-900/30 border-gray-600/30'
                              }`}>
                                <div className="flex justify-between items-center">
                                  <span className="text-gray-300">Roll Threshold:</span>
                                  <span className="text-gray-400">DTE &lt; {pos.roll_info.roll_threshold_dte} days</span>
                                </div>
                                <div className="flex justify-between items-center mt-1">
                                  <span className="text-gray-300">Days Until Roll:</span>
                                  <span className={`font-bold ${
                                    pos.roll_info.urgency === 'CRITICAL' ? 'text-red-400' :
                                    pos.roll_info.urgency === 'WARNING' ? 'text-yellow-400' :
                                    pos.roll_info.urgency === 'SOON' ? 'text-orange-400' :
                                    'text-green-400'
                                  }`}>
                                    {pos.roll_info.days_until_roll} days
                                    {pos.roll_info.urgency !== 'OK' && (
                                      <span className="ml-2 text-xs">
                                        {pos.roll_info.urgency === 'CRITICAL' ? '⚠️ ROLL NOW' :
                                         pos.roll_info.urgency === 'WARNING' ? '⚠️ ROLL SOON' :
                                         '📅 Schedule Roll'}
                                      </span>
                                    )}
                                  </span>
                                </div>
                              </div>
                            )}

                            {/* Net Profit for this position */}
                            <div className={`mt-4 p-3 rounded-lg ${pos.net_profit >= 0 ? 'bg-green-900/30 border border-green-600/30' : 'bg-red-900/30 border border-red-600/30'}`}>
                              <div className="flex justify-between items-center">
                                <span className="text-gray-300">IC Returns from this capital:</span>
                                <span className="text-green-400 font-bold">{formatCurrency(pos.total_ic_returns)}</span>
                              </div>
                              <div className="flex justify-between items-center mt-1">
                                <span className="text-gray-300">Net Profit (Returns - Accrued Cost):</span>
                                <span className={`text-xl font-bold ${pos.net_profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatCurrency(pos.net_profit)}
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}

                        {/* Box Spread Totals */}
                        <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-600/30">
                          <div className="text-sm font-medium text-blue-400 mb-3">BOX SPREAD TOTALS</div>
                          <div className="grid grid-cols-5 gap-4 text-center">
                            <div>
                              <div className="text-xs text-gray-400">Total Borrowed</div>
                              <div className="text-lg font-bold text-blue-400">{formatCurrency(reconciliation.box_spreads.totals.total_borrowed)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-400">Face Value Owed</div>
                              <div className="text-lg font-bold text-red-400">{formatCurrency(reconciliation.box_spreads.totals.total_face_value)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-400">Total Interest</div>
                              <div className="text-lg font-bold text-yellow-400">{formatCurrency(reconciliation.box_spreads.totals.total_borrowing_cost)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-400">Cost Accrued</div>
                              <div className="text-lg font-bold text-red-400">{formatCurrency(reconciliation.box_spreads.totals.cost_accrued_to_date)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-400">Cost Remaining</div>
                              <div className="text-lg font-bold text-yellow-400">{formatCurrency(reconciliation.box_spreads.totals.cost_remaining)}</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* SECTION 2: Capital Deployment Reconciliation */}
                    <div className="mb-8">
                      <h3 className="text-lg font-bold mb-4 text-yellow-400 flex items-center gap-2">
                        💰 Capital Deployment Reconciliation
                        {reconciliation.capital_deployment?.reconciles && (
                          <span className="ml-2 px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-xs">✓ TIES</span>
                        )}
                      </h3>
                      <div className="bg-black/40 rounded-lg p-5 border border-yellow-700/30">
                        <div className="grid md:grid-cols-5 gap-4 text-center items-center">
                          <div className="bg-blue-900/30 rounded-lg p-3 border border-blue-600/30">
                            <div className="text-xs text-gray-400">From Box Spreads</div>
                            <div className="text-xl font-bold text-blue-400">{formatCurrency(reconciliation.capital_deployment?.total_borrowed || 0)}</div>
                          </div>
                          <div className="text-2xl text-gray-500">−</div>
                          <div className="bg-yellow-900/30 rounded-lg p-3 border border-yellow-600/30">
                            <div className="text-xs text-gray-400">Reserved ({reconciliation.capital_deployment?.reserved_pct || 15}%)</div>
                            <div className="text-xl font-bold text-yellow-400">{formatCurrency(reconciliation.capital_deployment?.reserved || 0)}</div>
                          </div>
                          <div className="text-2xl text-gray-500">−</div>
                          <div className="bg-orange-900/30 rounded-lg p-3 border border-orange-600/30">
                            <div className="text-xs text-gray-400">In IC Trades ({reconciliation.capital_deployment?.ic_positions_count || 0})</div>
                            <div className="text-xl font-bold text-orange-400">{formatCurrency(reconciliation.capital_deployment?.in_ic_trades || 0)}</div>
                          </div>
                        </div>
                        <div className="mt-4 pt-4 border-t border-gray-700 flex justify-between items-center">
                          <span className="text-lg text-gray-300">= AVAILABLE TO TRADE:</span>
                          <span className="text-2xl font-bold text-green-400">{formatCurrency(reconciliation.capital_deployment?.available_to_trade || 0)}</span>
                        </div>
                      </div>
                    </div>

                    {/* SECTION 3: IC Trading Reconciliation with Oracle */}
                    {reconciliation.ic_trading?.positions?.length > 0 && (
                      <div className="mb-8">
                        <h3 className="text-lg font-bold mb-4 text-orange-400 flex items-center gap-2">
                          📊 IC Trading Reconciliation
                          <span className="text-sm font-normal text-gray-400">
                            ({reconciliation.ic_trading.count} open position{reconciliation.ic_trading.count !== 1 ? 's' : ''})
                          </span>
                        </h3>

                        {/* Open IC Positions */}
                        <div className="space-y-3 mb-4">
                          {reconciliation.ic_trading.positions.map((pos: any) => (
                            <div key={pos.position_id} className="bg-black/40 rounded-lg p-4 border border-orange-700/30">
                              <div className="flex justify-between items-start mb-3">
                                <div>
                                  <div className="text-lg font-bold text-white">
                                    {pos.ticker} {pos.put_long_strike}/{pos.put_short_strike}P | {pos.call_short_strike}/{pos.call_long_strike}C
                                  </div>
                                  <div className="text-sm text-gray-400">
                                    Exp: {pos.expiration} ({pos.dte} DTE) • {pos.contracts} contract{pos.contracts !== 1 ? 's' : ''}
                                  </div>
                                </div>
                                <div className="text-right">
                                  <div className={`text-xl font-bold ${pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatCurrency(pos.unrealized_pnl)}
                                  </div>
                                  <div className="text-xs text-gray-500">{pos.pnl_pct?.toFixed(1)}% of credit</div>
                                </div>
                              </div>

                              {/* P&L Details */}
                              <div className="grid grid-cols-3 gap-4 mb-3 text-sm">
                                <div>
                                  <span className="text-gray-400">Entry Credit: </span>
                                  <span className="text-green-400 font-medium">{formatCurrency(pos.total_credit_received)}</span>
                                </div>
                                <div>
                                  <span className="text-gray-400">Current Value: </span>
                                  <span className="font-medium">{formatCurrency(pos.current_value)}</span>
                                </div>
                                <div>
                                  <span className="text-gray-400">Max Loss: </span>
                                  <span className="text-red-400 font-medium">{formatCurrency(pos.max_loss)}</span>
                                </div>
                              </div>

                              {/* Oracle Reasoning - FULL transparency */}
                              <div className="bg-purple-900/20 rounded-lg p-3 border border-purple-600/30">
                                <div className="flex items-center gap-2 mb-2">
                                  <span className="text-purple-400 font-medium">🔮 Oracle Decision</span>
                                  <span className={`px-2 py-0.5 rounded text-xs ${
                                    pos.oracle_confidence >= 0.7 ? 'bg-green-500/20 text-green-400' :
                                    pos.oracle_confidence >= 0.5 ? 'bg-yellow-500/20 text-yellow-400' :
                                    'bg-red-500/20 text-red-400'
                                  }`}>
                                    {(pos.oracle_confidence * 100).toFixed(0)}% confidence
                                  </span>
                                </div>
                                <div className="text-sm text-gray-300">
                                  {pos.oracle_reasoning || 'No reasoning recorded'}
                                </div>
                                <div className="mt-2 text-xs text-gray-500">
                                  Entry: SPX @ {formatCurrency(pos.spot_at_entry)} • VIX: {pos.vix_at_entry?.toFixed(1)} • Regime: {pos.gamma_regime_at_entry || 'N/A'}
                                </div>
                              </div>

                              {/* Risk Rules */}
                              <div className="mt-2 flex gap-4 text-xs text-gray-500">
                                <span>Stop Loss: {pos.stop_loss_pct}%</span>
                                <span>Profit Target: {pos.profit_target_pct}%</span>
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* IC Totals */}
                        <div className="bg-orange-900/20 rounded-lg p-4 border border-orange-600/30">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div>
                              <div className="text-sm font-medium text-gray-400 mb-2">OPEN POSITIONS</div>
                              <div className="flex justify-between text-sm">
                                <span className="text-gray-400">Total Credit:</span>
                                <span className="text-green-400 font-bold">{formatCurrency(reconciliation.ic_trading.totals.total_credit_received)}</span>
                              </div>
                              <div className="flex justify-between text-sm">
                                <span className="text-gray-400">Current Value:</span>
                                <span>{formatCurrency(reconciliation.ic_trading.totals.total_current_value)}</span>
                              </div>
                              <div className="flex justify-between text-sm font-bold border-t border-gray-700 pt-1 mt-1">
                                <span className="text-gray-300">Unrealized P&L:</span>
                                <span className={reconciliation.ic_trading.totals.total_unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  {formatCurrency(reconciliation.ic_trading.totals.total_unrealized_pnl)}
                                </span>
                              </div>
                            </div>
                            <div>
                              <div className="text-sm font-medium text-gray-400 mb-2">CLOSED TRADES</div>
                              <div className="flex justify-between text-sm">
                                <span className="text-gray-400">Wins / Losses:</span>
                                <span>{reconciliation.ic_trading.closed_trades.wins} / {reconciliation.ic_trading.closed_trades.losses}</span>
                              </div>
                              <div className="flex justify-between text-sm">
                                <span className="text-gray-400">Win Rate:</span>
                                <span className={reconciliation.ic_trading.closed_trades.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}>
                                  {(reconciliation.ic_trading.closed_trades.win_rate * 100).toFixed(1)}%
                                </span>
                              </div>
                              <div className="flex justify-between text-sm font-bold border-t border-gray-700 pt-1 mt-1">
                                <span className="text-gray-300">Realized P&L:</span>
                                <span className={reconciliation.ic_trading.closed_trades.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  {formatCurrency(reconciliation.ic_trading.closed_trades.realized_pnl)}
                                </span>
                              </div>
                            </div>
                            <div className="md:col-span-2 bg-black/30 rounded-lg p-3">
                              <div className="text-sm font-medium text-gray-400 mb-2">TOTAL IC RETURNS</div>
                              <div className="grid grid-cols-3 gap-2 text-center">
                                <div>
                                  <div className="text-xs text-gray-500">Realized</div>
                                  <div className="text-lg font-bold text-green-400">{formatCurrency(reconciliation.ic_trading.closed_trades.realized_pnl)}</div>
                                </div>
                                <div className="text-2xl text-gray-500">+</div>
                                <div>
                                  <div className="text-xs text-gray-500">Unrealized</div>
                                  <div className="text-lg font-bold text-blue-400">{formatCurrency(reconciliation.ic_trading.totals.total_unrealized_pnl)}</div>
                                </div>
                              </div>
                              <div className="mt-2 pt-2 border-t border-gray-700 text-center">
                                <div className="text-xs text-gray-500">= Total IC Returns</div>
                                <div className="text-2xl font-bold text-green-400">{formatCurrency(reconciliation.net_profit_reconciliation?.income?.total_ic_returns || 0)}</div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* SECTION 4: Net Profit Reconciliation - THE BOTTOM LINE */}
                    <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-lg p-6 border-2 border-green-500/30">
                      <h3 className="text-xl font-bold mb-4 text-white flex items-center gap-2">
                        🎯 Net Profit Reconciliation
                        <span className="text-sm font-normal text-gray-400">— The Bottom Line</span>
                        {reconciliation.net_profit_reconciliation?.reconciles && (
                          <span className="ml-auto px-3 py-1 bg-green-500/20 text-green-400 rounded-full text-sm">✓ VERIFIED</span>
                        )}
                      </h3>

                      <div className="grid md:grid-cols-2 gap-6">
                        {/* INCOME */}
                        <div className="bg-green-900/20 rounded-lg p-4 border border-green-600/30">
                          <div className="text-sm font-bold text-green-400 mb-3">INCOME (What You&apos;ve Earned)</div>
                          <div className="space-y-2 text-sm font-mono">
                            <div className="flex justify-between">
                              <span className="text-gray-400">IC Realized P&L:</span>
                              <span className="text-green-400">+{formatCurrency(reconciliation.net_profit_reconciliation?.income?.ic_realized_pnl || 0)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-gray-400">IC Unrealized P&L:</span>
                              <span className="text-blue-400">+{formatCurrency(reconciliation.net_profit_reconciliation?.income?.ic_unrealized_pnl || 0)}</span>
                            </div>
                            <div className="flex justify-between border-t border-green-700/50 pt-2 font-bold">
                              <span className="text-green-300">TOTAL IC RETURNS:</span>
                              <span className="text-green-400 text-lg">+{formatCurrency(reconciliation.net_profit_reconciliation?.income?.total_ic_returns || 0)}</span>
                            </div>
                          </div>
                        </div>

                        {/* COSTS */}
                        <div className="bg-red-900/20 rounded-lg p-4 border border-red-600/30">
                          <div className="text-sm font-bold text-red-400 mb-3">COSTS (What You&apos;re Paying)</div>
                          <div className="space-y-2 text-sm font-mono">
                            <div className="flex justify-between">
                              <span className="text-gray-400">Borrowing Cost Accrued:</span>
                              <span className="text-red-400">-{formatCurrency(reconciliation.net_profit_reconciliation?.costs?.borrowing_cost_accrued || 0)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-yellow-400">Cost Remaining (future):</span>
                              <span className="text-yellow-400">-{formatCurrency(reconciliation.net_profit_reconciliation?.costs?.borrowing_cost_remaining || 0)}</span>
                            </div>
                            <div className="flex justify-between border-t border-red-700/50 pt-2 font-bold">
                              <span className="text-red-300">COSTS TO DATE:</span>
                              <span className="text-red-400 text-lg">-{formatCurrency(reconciliation.net_profit_reconciliation?.costs?.borrowing_cost_accrued || 0)}</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* THE ANSWER */}
                      <div className={`mt-6 p-6 rounded-lg text-center ${
                        reconciliation.net_profit_reconciliation?.is_profitable
                          ? 'bg-green-900/30 border-2 border-green-500/50'
                          : 'bg-red-900/30 border-2 border-red-500/50'
                      }`}>
                        <div className="text-sm text-gray-400 mb-2">NET PROFIT = IC Returns − Borrowing Costs</div>
                        <div className={`text-4xl font-bold ${
                          reconciliation.net_profit_reconciliation?.is_profitable ? 'text-green-400' : 'text-red-400'
                        }`}>
                          {formatCurrency(reconciliation.net_profit_reconciliation?.net_profit || 0)}
                        </div>
                        <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                          <div className="bg-black/30 rounded-lg p-3">
                            <div className="text-gray-400">Cost Efficiency</div>
                            <div className={`text-xl font-bold ${
                              (reconciliation.net_profit_reconciliation?.cost_efficiency || 0) >= 1 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {(reconciliation.net_profit_reconciliation?.cost_efficiency || 0).toFixed(1)}x
                            </div>
                            <div className="text-xs text-gray-500">IC returns vs borrowing cost</div>
                          </div>
                          <div className="bg-black/30 rounded-lg p-3">
                            <div className="text-gray-400">ROI on Borrowed</div>
                            <div className={`text-xl font-bold ${
                              (reconciliation.net_profit_reconciliation?.roi_on_borrowed || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {(reconciliation.net_profit_reconciliation?.roi_on_borrowed || 0).toFixed(2)}%
                            </div>
                            <div className="text-xs text-gray-500">Net profit ÷ borrowed capital</div>
                          </div>
                        </div>
                        {reconciliation.net_profit_reconciliation?.is_profitable ? (
                          <div className="mt-4 text-green-400 font-medium">
                            ✅ STRATEGY WORKING: IC returns exceed borrowing costs by {(reconciliation.net_profit_reconciliation?.cost_efficiency || 0).toFixed(1)}x
                          </div>
                        ) : (
                          <div className="mt-4 text-yellow-400 font-medium">
                            ⚠️ BELOW BREAK-EVEN: Need {formatCurrency(Math.abs(reconciliation.net_profit_reconciliation?.net_profit || 0))} more in IC returns
                          </div>
                        )}
                      </div>

                      {/* RISK ALERTS SECTION */}
                      {reconciliation.risk_alerts?.alerts?.length > 0 && (
                        <div className={`mt-6 rounded-lg p-4 border ${
                          reconciliation.risk_alerts.has_critical ? 'bg-red-900/30 border-red-600/50' :
                          reconciliation.risk_alerts.has_warnings ? 'bg-yellow-900/30 border-yellow-600/50' :
                          'bg-blue-900/30 border-blue-600/30'
                        }`}>
                          <div className="text-sm font-medium mb-3 flex items-center gap-2">
                            {reconciliation.risk_alerts.has_critical ? '🚨' : reconciliation.risk_alerts.has_warnings ? '⚠️' : 'ℹ️'}
                            <span className={
                              reconciliation.risk_alerts.has_critical ? 'text-red-400' :
                              reconciliation.risk_alerts.has_warnings ? 'text-yellow-400' :
                              'text-blue-400'
                            }>
                              Risk Alerts ({reconciliation.risk_alerts.count})
                            </span>
                          </div>
                          <div className="space-y-2">
                            {reconciliation.risk_alerts.alerts.map((alert: any, idx: number) => (
                              <div key={idx} className={`p-2 rounded text-sm flex items-center gap-2 ${
                                alert.severity === 'HIGH' ? 'bg-red-900/50 text-red-300' :
                                alert.severity === 'MEDIUM' ? 'bg-yellow-900/50 text-yellow-300' :
                                'bg-blue-900/50 text-blue-300'
                              }`}>
                                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                                  alert.severity === 'HIGH' ? 'bg-red-600 text-white' :
                                  alert.severity === 'MEDIUM' ? 'bg-yellow-600 text-black' :
                                  'bg-blue-600 text-white'
                                }`}>
                                  {alert.severity}
                                </span>
                                <span>{alert.message}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* ROLL SCHEDULE TIMELINE */}
                      {reconciliation.roll_schedule?.length > 0 && (
                        <div className="mt-6 bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                          <div className="text-sm font-medium text-gray-400 mb-3">📅 Roll Schedule Timeline</div>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-left text-gray-500 border-b border-gray-700">
                                  <th className="pb-2">Position</th>
                                  <th className="pb-2">Expiration</th>
                                  <th className="pb-2">Current DTE</th>
                                  <th className="pb-2">Roll Threshold</th>
                                  <th className="pb-2">Days Until Roll</th>
                                  <th className="pb-2">Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {reconciliation.roll_schedule.map((item: any) => (
                                  <tr key={item.position_id} className="border-b border-gray-800">
                                    <td className="py-2 font-mono text-blue-400">{item.ticker} {item.strikes}</td>
                                    <td className="py-2">{item.expiration}</td>
                                    <td className="py-2">{item.current_dte} days</td>
                                    <td className="py-2 text-gray-400">&lt; {item.roll_threshold_dte} days</td>
                                    <td className={`py-2 font-bold ${
                                      item.urgency === 'CRITICAL' ? 'text-red-400' :
                                      item.urgency === 'WARNING' ? 'text-yellow-400' :
                                      item.urgency === 'SOON' ? 'text-orange-400' :
                                      'text-green-400'
                                    }`}>
                                      {item.days_until_roll} days
                                    </td>
                                    <td className="py-2">
                                      <span className={`px-2 py-1 rounded text-xs ${
                                        item.urgency === 'CRITICAL' ? 'bg-red-500/20 text-red-400' :
                                        item.urgency === 'WARNING' ? 'bg-yellow-500/20 text-yellow-400' :
                                        item.urgency === 'SOON' ? 'bg-orange-500/20 text-orange-400' :
                                        'bg-green-500/20 text-green-400'
                                      }`}>
                                        {item.urgency === 'CRITICAL' ? '🚨 ROLL NOW' :
                                         item.urgency === 'WARNING' ? '⚠️ ROLL SOON' :
                                         item.urgency === 'SOON' ? '📅 UPCOMING' :
                                         '✓ OK'}
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {/* BREAK-EVEN PROGRESS BAR */}
                      {reconciliation.break_even_progress && (
                        <div className="mt-6 bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                          <div className="text-sm font-medium text-gray-400 mb-3">📊 Break-Even Progress</div>
                          <div className="relative">
                            {/* Progress bar background */}
                            <div className="h-8 bg-gray-800 rounded-lg overflow-hidden relative">
                              {/* Break-even marker at center */}
                              <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-white z-10" style={{ transform: 'translateX(-50%)' }} />
                              <div className="absolute left-1/2 -top-5 text-xs text-gray-400 transform -translate-x-1/2">Break-Even</div>

                              {/* Progress fill */}
                              <div
                                className={`h-full transition-all duration-500 ${
                                  reconciliation.break_even_progress.is_above_break_even ? 'bg-gradient-to-r from-green-600 to-green-400' : 'bg-gradient-to-r from-red-600 to-red-400'
                                }`}
                                style={{
                                  width: `${Math.min(100, Math.max(0, reconciliation.break_even_progress.break_even_pct / 2))}%`
                                }}
                              />
                            </div>

                            {/* Labels */}
                            <div className="flex justify-between mt-2 text-sm">
                              <div>
                                <span className="text-gray-400">IC Returns: </span>
                                <span className="text-green-400 font-bold">{formatCurrency(reconciliation.break_even_progress.ic_returns)}</span>
                              </div>
                              <div className={`text-center font-bold ${reconciliation.break_even_progress.is_above_break_even ? 'text-green-400' : 'text-red-400'}`}>
                                {reconciliation.break_even_progress.is_above_break_even ? '+' : ''}{formatCurrency(reconciliation.break_even_progress.excess_over_break_even)}
                              </div>
                              <div>
                                <span className="text-gray-400">Borrowing Costs: </span>
                                <span className="text-red-400 font-bold">{formatCurrency(reconciliation.break_even_progress.borrowing_costs)}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Trading Rules Summary */}
                      <div className="mt-6 bg-black/30 rounded-lg p-4">
                        <div className="text-sm font-medium text-gray-400 mb-3">📜 Trading Rules (from config)</div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                          <div>
                            <span className="text-gray-500">Box DTE Target:</span>
                            <span className="ml-2">{reconciliation.config?.box_target_dte_min}-{reconciliation.config?.box_target_dte_max} days</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Roll When:</span>
                            <span className="ml-2">DTE &lt; {reconciliation.config?.box_min_dte_to_hold} days</span>
                          </div>
                          <div>
                            <span className="text-gray-500">IC Profit Target:</span>
                            <span className="ml-2 text-green-400">{reconciliation.config?.ic_profit_target_pct}%</span>
                          </div>
                          <div>
                            <span className="text-gray-500">IC Stop Loss:</span>
                            <span className="ml-2 text-red-400">{reconciliation.config?.ic_stop_loss_pct}%</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Oracle Required:</span>
                            <span className="ml-2">{reconciliation.config?.require_oracle_approval ? 'Yes' : 'No'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Min Confidence:</span>
                            <span className="ml-2">{(reconciliation.config?.min_oracle_confidence || 0.6) * 100}%</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Max IC Positions:</span>
                            <span className="ml-2">{reconciliation.config?.ic_max_positions}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Max Daily Trades:</span>
                            <span className="ml-2">{reconciliation.config?.ic_max_daily_trades}</span>
                          </div>
                        </div>
                      </div>

                      {/* DAILY P&L BREAKDOWN TABLE */}
                      {dailyPnl?.available && dailyPnl.daily_pnl?.length > 0 && (
                        <div className="mt-6 bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                          <div className="text-sm font-medium text-gray-400 mb-3 flex items-center justify-between">
                            <span>📈 Daily P&L Breakdown (Last 14 Days)</span>
                            <span className="text-xs text-gray-500">
                              Daily borrowing cost: <span className="text-red-400">{formatCurrency(dailyPnl.total_daily_borrowing_cost)}</span>/day
                            </span>
                          </div>
                          <div className="overflow-x-auto max-h-80">
                            <table className="w-full text-sm">
                              <thead className="sticky top-0 bg-gray-900">
                                <tr className="text-left text-gray-500 border-b border-gray-700">
                                  <th className="pb-2 pr-4">Date</th>
                                  <th className="pb-2 pr-4 text-right">IC Earned</th>
                                  <th className="pb-2 pr-4 text-right">Box Cost</th>
                                  <th className="pb-2 pr-4 text-right">Net</th>
                                  <th className="pb-2 pr-4 text-right">Cumulative</th>
                                  <th className="pb-2 text-center">Trades</th>
                                </tr>
                              </thead>
                              <tbody>
                                {dailyPnl.daily_pnl.slice(-14).map((day: any) => (
                                  <tr key={day.date} className="border-b border-gray-800">
                                    <td className="py-2 pr-4 font-mono text-gray-300">{day.date}</td>
                                    <td className="py-2 pr-4 text-right text-green-400">{formatCurrency(day.ic_earned)}</td>
                                    <td className="py-2 pr-4 text-right text-red-400">-{formatCurrency(day.box_cost)}</td>
                                    <td className={`py-2 pr-4 text-right font-bold ${day.net >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                      {day.net >= 0 ? '+' : ''}{formatCurrency(day.net)}
                                    </td>
                                    <td className={`py-2 pr-4 text-right ${day.cumulative >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                      {formatCurrency(day.cumulative)}
                                    </td>
                                    <td className="py-2 text-center text-gray-400">{day.trades}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          {/* Summary row */}
                          <div className="mt-3 pt-3 border-t border-gray-700 grid grid-cols-4 gap-4 text-center text-sm">
                            <div>
                              <div className="text-xs text-gray-500">Total IC Earned</div>
                              <div className="font-bold text-green-400">{formatCurrency(dailyPnl.summary?.total_ic_earned || 0)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500">Total Box Cost</div>
                              <div className="font-bold text-red-400">-{formatCurrency(dailyPnl.summary?.total_box_cost || 0)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500">Total Net</div>
                              <div className={`font-bold ${(dailyPnl.summary?.total_net || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {formatCurrency(dailyPnl.summary?.total_net || 0)}
                              </div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500">Avg Daily Net</div>
                              <div className={`font-bold ${(dailyPnl.summary?.avg_daily_net || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {formatCurrency(dailyPnl.summary?.avg_daily_net || 0)}/day
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* ORACLE SCAN ACTIVITY */}
                      {icSignals?.available && icSignals.signals?.length > 0 && (
                        <div className="mt-6 bg-gray-900/50 rounded-lg p-4 border border-purple-700/30">
                          <div className="text-sm font-medium text-purple-400 mb-3">
                            🔮 Oracle Scan Activity (Recent IC Signals)
                          </div>
                          <div className="space-y-2 max-h-80 overflow-y-auto">
                            {icSignals.signals.slice(0, 10).map((signal: any) => (
                              <div
                                key={signal.signal_id}
                                className={`p-3 rounded-lg border ${
                                  signal.oracle_approved
                                    ? signal.was_executed
                                      ? 'bg-green-900/20 border-green-600/30'
                                      : 'bg-blue-900/20 border-blue-600/30'
                                    : 'bg-red-900/20 border-red-600/30'
                                }`}
                              >
                                <div className="flex justify-between items-start mb-2">
                                  <div>
                                    <span className="font-mono text-sm text-white">
                                      {signal.ticker} {signal.put_short_strike}/{signal.put_long_strike}P | {signal.call_short_strike}/{signal.call_long_strike}C
                                    </span>
                                    <span className="ml-2 text-xs text-gray-400">{signal.dte || 0} DTE</span>
                                  </div>
                                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                                    signal.oracle_approved
                                      ? signal.was_executed
                                        ? 'bg-green-500/20 text-green-400'
                                        : 'bg-blue-500/20 text-blue-400'
                                      : 'bg-red-500/20 text-red-400'
                                  }`}>
                                    {signal.oracle_approved
                                      ? signal.was_executed ? '✓ EXECUTED' : '✓ APPROVED'
                                      : '✗ REJECTED'}
                                  </span>
                                </div>
                                <div className="text-xs text-gray-400 mb-1">
                                  {signal.signal_time ? new Date(signal.signal_time).toLocaleString() : 'N/A'}
                                </div>
                                {/* Oracle reasoning */}
                                {signal.oracle_reasoning && (
                                  <div className="mt-2 p-2 bg-purple-900/30 rounded text-sm text-purple-300">
                                    <span className="text-purple-400 font-medium">Oracle ({(signal.oracle_confidence * 100 || 0).toFixed(0)}%): </span>
                                    {signal.oracle_reasoning}
                                  </div>
                                )}
                                {/* Skip reason for rejected signals */}
                                {!signal.oracle_approved && signal.skip_reason && (
                                  <div className="mt-2 p-2 bg-red-900/30 rounded text-sm text-red-300">
                                    <span className="text-red-400 font-medium">Skip Reason: </span>
                                    {signal.skip_reason}
                                  </div>
                                )}
                                {/* Pricing info */}
                                <div className="mt-2 flex gap-4 text-xs text-gray-400">
                                  <span>Credit: <span className="text-green-400">{formatCurrency(signal.total_credit || 0)}</span></span>
                                  <span>Max Loss: <span className="text-red-400">{formatCurrency(signal.max_loss || 0)}</span></span>
                                  <span>PoP: <span className="text-blue-400">{((signal.probability_of_profit || 0) * 100).toFixed(0)}%</span></span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* No reconciliation data message */}
                {!reconciliation?.available && reconciliation !== undefined && (
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 text-center">
                    <div className="text-4xl mb-4">📋</div>
                    <p className="text-gray-400">Reconciliation data not available</p>
                    <p className="text-sm text-gray-500 mt-2">Open box spreads to see full reconciliation</p>
                  </div>
                )}
              </div>
            )}

            {/* Positions Tab - Box Spreads (Borrowing Side) */}
            {activeTab === 'positions' && (
              <div className="space-y-6">
                {/* Borrowing Summary */}
                <div className="bg-gradient-to-br from-blue-900/30 to-gray-800 rounded-lg p-6 border border-blue-500/50">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    <span className="text-2xl">📦</span> Box Spread Borrowing
                    <span className="text-sm font-normal text-gray-400">- Your synthetic loan positions</span>
                  </h2>
                  <div className="grid md:grid-cols-5 gap-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Total Borrowed</div>
                      <div className="text-2xl font-bold text-blue-400">{formatCurrency(totalBorrowed)}</div>
                      <div className="text-xs text-gray-500">{positions?.positions?.length || 0} position{(positions?.positions?.length || 0) !== 1 ? 's' : ''}</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Face Value Owed</div>
                      <div className="text-2xl font-bold text-red-400">
                        {formatCurrency(positions?.positions?.reduce((sum: number, p: Position) => sum + (p.strike_width * 100 * p.contracts), 0) || 0)}
                      </div>
                      <div className="text-xs text-gray-500">at expiration</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Avg Implied Rate</div>
                      <div className="text-2xl font-bold text-yellow-400">
                        {(status?.performance?.avg_implied_rate || rateAnalysis?.box_implied_rate || 0).toFixed(2)}%
                      </div>
                      <div className="text-xs text-gray-500">annual cost</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Daily Cost</div>
                      <div className="text-2xl font-bold text-red-400">
                        {formatCurrency((totalBorrowed * (rateAnalysis?.box_implied_rate || 4.0) / 100) / 365)}
                      </div>
                      <div className="text-xs text-gray-500">interest accrual</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Total Costs Paid</div>
                      <div className="text-2xl font-bold text-red-400">
                        {formatCurrency(totalCostAccrued)}
                      </div>
                      <div className="text-xs text-gray-500">since inception</div>
                    </div>
                  </div>
                  {totalBorrowed > 0 && (
                    <div className="mt-4 p-3 bg-black/30 rounded-lg text-sm">
                      <span className="text-gray-400">Margin saved vs broker margin: </span>
                      <span className="text-green-400 font-bold">
                        {formatCurrency(totalBorrowed * ((8.5 - (rateAnalysis?.box_implied_rate || 4.0)) / 100))}
                      </span>
                      <span className="text-gray-500"> /year (vs 8.5% margin rate)</span>
                    </div>
                  )}
                </div>

                {/* Position Details */}
                <div className="bg-gray-800 rounded-lg overflow-hidden">
                  <div className="p-4 border-b border-gray-700">
                    <h2 className="text-lg font-bold">Position Details</h2>
                  </div>

                  {positions?.positions?.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="bg-gray-700/50">
                          <tr>
                            <th className="px-4 py-3 text-left text-sm">Position</th>
                            <th className="px-4 py-3 text-left text-sm">Strikes</th>
                            <th className="px-4 py-3 text-left text-sm">Expiration</th>
                            <th className="px-4 py-3 text-right text-sm">Credit</th>
                            <th className="px-4 py-3 text-right text-sm">Cost</th>
                            <th className="px-4 py-3 text-right text-sm">IC Returns</th>
                            <th className="px-4 py-3 text-right text-sm">Net P&L</th>
                            <th className="px-4 py-3 text-center text-sm">Risk</th>
                          </tr>
                        </thead>
                        <tbody>
                          {positions.positions.map((pos: Position) => (
                            <tr key={pos.position_id} className="border-t border-gray-700 hover:bg-gray-700/30">
                              <td className="px-4 py-3">
                                <div className="font-medium">{pos.position_id}</div>
                                <div className="text-xs text-gray-400">{pos.contracts} contracts</div>
                              </td>
                              <td className="px-4 py-3">
                                <div className="font-medium">{pos.ticker} Box</div>
                                <div className="text-xs text-gray-400">
                                  <span className="text-green-400">+{pos.lower_strike}C</span>
                                  <span className="text-red-400 ml-1">−{pos.upper_strike}C</span>
                                </div>
                                <div className="text-xs text-gray-400">
                                  <span className="text-red-400">−{pos.lower_strike}P</span>
                                  <span className="text-green-400 ml-1">+{pos.upper_strike}P</span>
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <div>{pos.expiration}</div>
                                <div className="text-sm text-gray-400">{pos.current_dte} DTE</div>
                              </td>
                              <td className="px-4 py-3 text-right">
                                <div>{formatCurrency(pos.total_credit_received)}</div>
                                <div className="text-xs text-gray-400">@ {formatPct(pos.implied_annual_rate)}</div>
                              </td>
                              <td className="px-4 py-3 text-right text-red-400">{formatCurrency(pos.borrowing_cost)}</td>
                              <td className="px-4 py-3 text-right text-green-400">{formatCurrency(pos.total_ic_returns)}</td>
                              <td className={`px-4 py-3 text-right font-medium ${pos.net_profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {formatCurrency(pos.net_profit)}
                              </td>
                              <td className="px-4 py-3 text-center">
                                <span className={`px-2 py-1 rounded text-xs ${
                                  pos.early_assignment_risk === 'LOW' ? 'bg-green-900/50 text-green-400' :
                                  pos.early_assignment_risk === 'MEDIUM' ? 'bg-yellow-900/50 text-yellow-400' :
                                  'bg-red-900/50 text-red-400'
                                }`}>
                                  {pos.early_assignment_risk}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-8 text-center text-gray-400">
                      <div className="text-4xl mb-4">📦</div>
                      <p className="text-lg">No Open Positions</p>
                      <p className="text-sm mt-2">PROMETHEUS scans for opportunities starting at market open (8:30 AM CT)</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* IC Trading Tab */}
            {activeTab === 'ic-trading' && (
              <div className="space-y-6">
                {/* IC Status Header - NOW WITH SPECIFIC AMOUNTS */}
                <div className="bg-gradient-to-br from-orange-900/30 to-gray-800 rounded-lg p-6 border border-orange-500/50">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="text-3xl">📊</div>
                      <div>
                        <h2 className="text-xl font-bold">Iron Condor Trading</h2>
                        {totalBorrowed > 0 ? (
                          <p className="text-sm text-gray-400">
                            Trading with <span className="text-blue-400 font-bold">{formatCurrency(totalBorrowed)}</span> borrowed from{' '}
                            <span className="text-orange-400 font-bold">{positions?.positions?.length || 0} box spread{(positions?.positions?.length || 0) !== 1 ? 's' : ''}</span>{' '}
                            at <span className="text-yellow-400">{(status?.performance?.avg_implied_rate || rateAnalysis?.box_implied_rate || 0).toFixed(2)}%</span> avg rate
                          </p>
                        ) : (
                          <p className="text-sm text-yellow-400">
                            ⚠️ No capital borrowed yet - Open box spreads first to fund IC trading
                          </p>
                        )}
                      </div>
                    </div>
                    <div className={`px-3 py-1 rounded-full text-sm font-medium ${
                      icStatus?.status?.enabled ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      {icStatus?.status?.enabled ? 'ENABLED' : 'DISABLED'}
                    </div>
                  </div>

                  {/* CAPITAL SOURCE - WHERE THE MONEY COMES FROM */}
                  <div className="bg-black/40 rounded-lg p-4 mb-4 border border-gray-600">
                    <h3 className="text-sm font-bold text-gray-300 mb-3 flex items-center gap-2">
                      💰 YOUR CAPITAL SOURCE
                      <span className="text-xs font-normal text-gray-500">(Where the money comes from)</span>
                    </h3>
                    <div className="grid md:grid-cols-5 gap-3 text-sm">
                      <div className="bg-blue-900/30 rounded p-3 border border-blue-700/50">
                        <div className="text-xs text-gray-400">From Box Spreads</div>
                        <div className="text-lg font-bold text-blue-400">{formatCurrency(totalBorrowed)}</div>
                        <div className="text-xs text-gray-500">{positions?.positions?.length || 0} positions</div>
                      </div>
                      <div className="flex items-center justify-center text-gray-500">−</div>
                      <div className="bg-yellow-900/30 rounded p-3 border border-yellow-700/50">
                        <div className="text-xs text-gray-400">Reserved ({reconciliation?.config?.reserve_pct || 10}%)</div>
                        <div className="text-lg font-bold text-yellow-400">{formatCurrency(reconciliation?.capital_deployment?.reserved || totalBorrowed * (reconciliation?.config?.reserve_pct || 10) / 100)}</div>
                        <div className="text-xs text-gray-500">Margin buffer</div>
                      </div>
                      <div className="flex items-center justify-center text-gray-500">−</div>
                      <div className="bg-orange-900/30 rounded p-3 border border-orange-700/50">
                        <div className="text-xs text-gray-400">In IC Trades</div>
                        <div className="text-lg font-bold text-orange-400">
                          {formatCurrency(reconciliation?.capital_deployment?.in_ic_trades || (icStatus?.status?.open_positions || 0) * (reconciliation?.config?.min_capital_per_trade || 5000))}
                        </div>
                        <div className="text-xs text-gray-500">{icStatus?.status?.open_positions || 0} × {formatCurrency(reconciliation?.config?.min_capital_per_trade || 5000)}/trade</div>
                      </div>
                    </div>
                    <div className="mt-3 pt-3 border-t border-gray-600 flex justify-between items-center">
                      <span className="text-gray-400">AVAILABLE TO TRADE:</span>
                      <span className="text-2xl font-bold text-green-400">{formatCurrency(icStatus?.status?.available_capital || 0)}</span>
                    </div>
                    {totalBorrowed > 0 && (
                      <div className="mt-2 text-xs text-gray-500">
                        Daily borrowing cost: <span className="text-red-400">{formatCurrency((totalBorrowed * (rateAnalysis?.box_implied_rate || 4.0) / 100) / 365)}</span>/day
                        {' '}| Must earn at least: <span className="text-yellow-400">{formatCurrency((totalBorrowed * (rateAnalysis?.box_implied_rate || 4.0) / 100) / 12)}</span>/month to break even
                      </div>
                    )}
                  </div>

                  {/* TRADING STATUS - WHY CAN/CAN'T TRADE */}
                  <div className="bg-black/40 rounded-lg p-4 border border-gray-600">
                    <h3 className="text-sm font-bold text-gray-300 mb-3 flex items-center gap-2">
                      🎯 TRADING STATUS
                      <span className={`ml-auto px-2 py-1 rounded text-xs font-bold ${icStatus?.status?.can_trade ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                        {icStatus?.status?.can_trade ? '✓ CAN TRADE' : '✗ CANNOT TRADE'}
                      </span>
                    </h3>
                    <div className="grid md:grid-cols-2 gap-4 text-sm">
                      <div className="space-y-2">
                        <div className={`flex items-center gap-2 ${(icStatus?.status?.available_capital || 0) >= (reconciliation?.config?.min_capital_per_trade || 5000) ? 'text-green-400' : 'text-red-400'}`}>
                          {(icStatus?.status?.available_capital || 0) >= (reconciliation?.config?.min_capital_per_trade || 5000) ? '✓' : '✗'} Capital: {formatCurrency(icStatus?.status?.available_capital || 0)}
                          {(icStatus?.status?.available_capital || 0) < (reconciliation?.config?.min_capital_per_trade || 5000) && <span className="text-xs text-gray-500">(need {formatCurrency(reconciliation?.config?.min_capital_per_trade || 5000)} min)</span>}
                        </div>
                        <div className={`flex items-center gap-2 ${(icStatus?.status?.open_positions || 0) < (reconciliation?.config?.ic_max_positions || 3) ? 'text-green-400' : 'text-red-400'}`}>
                          {(icStatus?.status?.open_positions || 0) < (reconciliation?.config?.ic_max_positions || 3) ? '✓' : '✗'} Positions: {icStatus?.status?.open_positions || 0} / {reconciliation?.config?.ic_max_positions || 3} max
                        </div>
                        <div className={`flex items-center gap-2 ${(icStatus?.status?.daily_trades || 0) < (icStatus?.status?.max_daily_trades || 5) ? 'text-green-400' : 'text-red-400'}`}>
                          {(icStatus?.status?.daily_trades || 0) < (icStatus?.status?.max_daily_trades || 5) ? '✓' : '✗'} Daily trades: {icStatus?.status?.daily_trades || 0} / {icStatus?.status?.max_daily_trades || 5}
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className={`flex items-center gap-2 ${icStatus?.status?.in_trading_window ? 'text-green-400' : 'text-yellow-400'}`}>
                          {icStatus?.status?.in_trading_window ? '✓' : '○'} Trading window: {icStatus?.status?.in_trading_window ? 'OPEN' : 'CLOSED'}
                          <span className="text-xs text-gray-500">(8:35 AM - 2:30 PM CT)</span>
                        </div>
                        <div className={`flex items-center gap-2 ${!icStatus?.status?.in_cooldown ? 'text-green-400' : 'text-yellow-400'}`}>
                          {!icStatus?.status?.in_cooldown ? '✓' : '○'} Cooldown: {!icStatus?.status?.in_cooldown ? 'Ready' : 'Waiting'}
                        </div>
                        <div className={`flex items-center gap-2 ${icStatus?.status?.enabled ? 'text-green-400' : 'text-red-400'}`}>
                          {icStatus?.status?.enabled ? '✓' : '✗'} IC Trading: {icStatus?.status?.enabled ? 'Enabled' : 'Disabled'}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* IC Performance Stats */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">IC Trading Performance</h3>
                  <div className="grid md:grid-cols-6 gap-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Total Trades</div>
                      <div className="text-xl font-bold">{icPerformance?.performance?.closed_trades?.total || 0}</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Win Rate</div>
                      <div className={`text-xl font-bold ${
                        (icPerformance?.performance?.closed_trades?.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {formatPct((icPerformance?.performance?.closed_trades?.win_rate || 0) * 100)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Profit Factor</div>
                      <div className={`text-xl font-bold ${
                        (icPerformance?.performance?.closed_trades?.profit_factor || 0) >= 1 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {(icPerformance?.performance?.closed_trades?.profit_factor || 0).toFixed(2)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Total P&L</div>
                      <div className={`text-xl font-bold ${
                        (icPerformance?.performance?.closed_trades?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {formatCurrency(icPerformance?.performance?.closed_trades?.total_pnl || 0)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Avg Win</div>
                      <div className="text-xl font-bold text-green-400">
                        {formatCurrency(icPerformance?.performance?.closed_trades?.best_trade || 0)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Avg Loss</div>
                      <div className="text-xl font-bold text-red-400">
                        {formatCurrency(icPerformance?.performance?.closed_trades?.worst_trade || 0)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Open IC Positions */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">Open IC Positions ({icPositions?.count || 0})</h3>
                  {icPositions?.positions?.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-gray-400 border-b border-gray-700">
                            <th className="text-left py-2 px-3">Position</th>
                            <th className="text-left py-2 px-3">Put Spread</th>
                            <th className="text-left py-2 px-3">Call Spread</th>
                            <th className="text-left py-2 px-3">Exp/DTE</th>
                            <th className="text-right py-2 px-3">Credit</th>
                            <th className="text-right py-2 px-3">Current</th>
                            <th className="text-right py-2 px-3">P&L</th>
                            <th className="text-left py-2 px-3">Oracle</th>
                          </tr>
                        </thead>
                        <tbody>
                          {icPositions.positions.map((pos: any) => (
                            <tr key={pos.position_id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-3 px-3">
                                <div className="font-mono text-xs">{pos.position_id?.slice(0, 16)}</div>
                                <div className="text-xs text-gray-400">{pos.contracts} contracts</div>
                              </td>
                              <td className="py-3 px-3 font-mono">{pos.put_spread}</td>
                              <td className="py-3 px-3 font-mono">{pos.call_spread}</td>
                              <td className="py-3 px-3">
                                <div>{pos.expiration}</div>
                                <div className="text-xs text-gray-400">{pos.dte} DTE</div>
                              </td>
                              <td className="py-3 px-3 text-right text-green-400">
                                ${pos.entry_credit?.toFixed(2)}
                              </td>
                              <td className="py-3 px-3 text-right">
                                ${pos.current_value?.toFixed(2)}
                              </td>
                              <td className={`py-3 px-3 text-right font-bold ${
                                (pos.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                              }`}>
                                {formatCurrency(pos.unrealized_pnl || 0)}
                                <div className="text-xs text-gray-400">{pos.pnl_pct?.toFixed(1)}%</div>
                              </td>
                              <td className="py-3 px-3">
                                <div className={`text-xs ${pos.oracle_confidence >= 0.7 ? 'text-green-400' : 'text-yellow-400'}`}>
                                  {formatPct((pos.oracle_confidence || 0) * 100)}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-6 text-center">
                      <div className="text-4xl mb-4">📊</div>
                      <p className="text-lg text-gray-300 font-medium">No Open IC Positions</p>
                      {totalBorrowed <= 0 ? (
                        <div className="mt-4 p-4 bg-yellow-900/30 border border-yellow-600/50 rounded-lg inline-block">
                          <p className="text-yellow-400 font-medium">⚠️ No capital to trade with</p>
                          <p className="text-sm text-gray-400 mt-1">Open box spreads first in the &quot;Box Spreads&quot; tab to fund IC trading</p>
                        </div>
                      ) : !icStatus?.status?.enabled ? (
                        <div className="mt-4 p-4 bg-red-900/30 border border-red-600/50 rounded-lg inline-block">
                          <p className="text-red-400 font-medium">❌ IC Trading is disabled</p>
                          <p className="text-sm text-gray-400 mt-1">Enable IC trading in settings to start generating trades</p>
                        </div>
                      ) : !icStatus?.status?.in_trading_window ? (
                        <div className="mt-4 p-4 bg-blue-900/30 border border-blue-600/50 rounded-lg inline-block">
                          <p className="text-blue-400 font-medium">⏰ Outside trading hours</p>
                          <p className="text-sm text-gray-400 mt-1">IC trades are generated 8:35 AM - 2:30 PM CT when Oracle approves</p>
                        </div>
                      ) : (
                        <div className="mt-4 p-4 bg-green-900/30 border border-green-600/50 rounded-lg inline-block">
                          <p className="text-green-400 font-medium">✓ Ready to trade</p>
                          <p className="text-sm text-gray-400 mt-1">
                            {formatCurrency(icStatus?.status?.available_capital || 0)} available from {positions?.positions?.length || 0} box spread(s)
                          </p>
                          <p className="text-xs text-gray-500 mt-1">Waiting for Oracle-approved signal...</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Recent Closed Trades */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">Recent Closed Trades</h3>
                  {icClosedTrades?.trades?.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-gray-400 border-b border-gray-700">
                            <th className="text-left py-2 px-3">Close Time</th>
                            <th className="text-left py-2 px-3">Strikes</th>
                            <th className="text-right py-2 px-3">Entry</th>
                            <th className="text-right py-2 px-3">Exit</th>
                            <th className="text-right py-2 px-3">P&L</th>
                            <th className="text-left py-2 px-3">Reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {icClosedTrades.trades.slice(0, 10).map((trade: any, idx: number) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-2 px-3 text-xs">
                                {trade.close_time ? new Date(trade.close_time).toLocaleString() : '-'}
                              </td>
                              <td className="py-2 px-3 font-mono text-xs">
                                P:{trade.put_short_strike}/{trade.put_long_strike} C:{trade.call_short_strike}/{trade.call_long_strike}
                              </td>
                              <td className="py-2 px-3 text-right">${trade.entry_credit?.toFixed(2)}</td>
                              <td className="py-2 px-3 text-right">${trade.exit_price?.toFixed(2)}</td>
                              <td className={`py-2 px-3 text-right font-bold ${
                                (trade.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                              }`}>
                                {formatCurrency(trade.realized_pnl || 0)}
                              </td>
                              <td className="py-2 px-3 text-xs text-gray-400">{trade.close_reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-8 text-center text-gray-400">
                      <p>No closed trades yet</p>
                    </div>
                  )}
                </div>

                {/* IC TRADING Equity Curve - SHORT-TERM AGGRESSIVE (like PEGASUS) */}
                <div className="bg-gray-800 rounded-lg p-6 border-l-4 border-green-500">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-bold flex items-center gap-2">
                        <span className="text-2xl">⚡</span>
                        IC Trading Returns ({selectedIcTimeframe.label})
                        <span className="text-xs bg-green-600 text-white px-2 py-0.5 rounded ml-2">SHORT-TERM</span>
                      </h3>
                      <p className="text-xs text-gray-400 mt-1">
                        Aggressive 0DTE Iron Condors • {icPerformance?.closed_trades?.total || 0} trades • {((icPerformance?.closed_trades?.win_rate || 0) * 100).toFixed(0)}% win rate
                      </p>
                    </div>
                    {/* Timeframe Selector - matching HERACLES */}
                    <div className="flex gap-1">
                      {IC_EQUITY_TIMEFRAMES.map((tf) => (
                        <button
                          key={tf.id}
                          onClick={() => setIcEquityTimeframe(tf.id)}
                          className={`px-3 py-1 text-xs rounded transition-colors ${
                            icEquityTimeframe === tf.id
                              ? 'bg-green-500 text-black font-semibold'
                              : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                          }`}
                        >
                          {tf.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Loading state */}
                  {(isIcIntraday ? icIntradayLoading : icEquityCurveLoading) ? (
                    <div className="h-64 flex items-center justify-center">
                      <div className="text-gray-400 animate-pulse">Loading equity data...</div>
                    </div>
                  ) : (() => {
                    // Select data source based on timeframe
                    const chartData = isIcIntraday
                      ? (icIntradayEquity?.snapshots || []).map((snap: any) => ({
                          time: snap.time,
                          equity: snap.total_equity,
                          pnl: snap.unrealized_pnl || 0,
                        }))
                      : (icEquityCurve?.data || []).map((point: any) => ({
                          time: point.time,
                          equity: point.equity,
                          pnl: point.cumulative_pnl,
                        }))

                    const startingCapital = isIcIntraday
                      ? (icIntradayEquity?.snapshots?.[0]?.starting_capital || 500000)
                      : (icEquityCurve?.starting_capital || 500000)

                    const currentEquity = chartData.length > 0
                      ? chartData[chartData.length - 1]?.equity || startingCapital
                      : startingCapital

                    const currentPnl = chartData.length > 0
                      ? chartData[chartData.length - 1]?.pnl || 0
                      : 0

                    const dataCount = isIcIntraday
                      ? (icIntradayEquity?.count || chartData.length)
                      : (icEquityCurve?.count || chartData.length)

                    return chartData.length > 0 ? (
                      <>
                        {/* Summary Stats */}
                        <div className="grid md:grid-cols-4 gap-4 mb-4">
                          <div className="bg-gray-700/50 rounded-lg p-3">
                            <div className="text-xs text-gray-400">Starting Capital</div>
                            <div className="text-lg font-bold text-blue-400">
                              {formatCurrency(startingCapital)}
                            </div>
                          </div>
                          <div className="bg-gray-700/50 rounded-lg p-3">
                            <div className="text-xs text-gray-400">Current Equity</div>
                            <div className={`text-lg font-bold ${
                              currentEquity >= startingCapital ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {formatCurrency(currentEquity)}
                            </div>
                          </div>
                          <div className="bg-gray-700/50 rounded-lg p-3">
                            <div className="text-xs text-gray-400">{isIcIntraday ? 'Unrealized P&L' : 'Cumulative P&L'}</div>
                            <div className={`text-lg font-bold ${
                              currentPnl >= 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {formatCurrency(currentPnl)}
                            </div>
                          </div>
                          <div className="bg-gray-700/50 rounded-lg p-3">
                            <div className="text-xs text-gray-400">{isIcIntraday ? 'Snapshots' : 'Trades'}</div>
                            <div className="text-lg font-bold text-orange-400">{dataCount}</div>
                          </div>
                        </div>

                        {/* Recharts LineChart - matching HERACLES style */}
                        <div className="h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={chartData}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                              <XAxis
                                dataKey="time"
                                stroke="#9CA3AF"
                                tick={{ fill: '#9CA3AF', fontSize: 11 }}
                                tickFormatter={(value) => {
                                  if (!value) return ''
                                  const date = new Date(value)
                                  if (isIcIntraday) {
                                    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
                                  }
                                  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                                }}
                              />
                              <YAxis
                                stroke="#9CA3AF"
                                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                                tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                                domain={['dataMin - 1000', 'dataMax + 1000']}
                              />
                              <Tooltip
                                contentStyle={{
                                  backgroundColor: '#1F2937',
                                  border: '1px solid #374151',
                                  borderRadius: '8px',
                                }}
                                labelFormatter={(value) => {
                                  if (!value) return ''
                                  const date = new Date(value)
                                  if (isIcIntraday) {
                                    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
                                  }
                                  return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
                                }}
                                formatter={(value: number, name: string) => [
                                  `$${value.toLocaleString()}`,
                                  name === 'equity' ? 'Equity' : 'P&L'
                                ]}
                              />
                              {/* Reference line at starting capital (red dashed) */}
                              <ReferenceLine
                                y={startingCapital}
                                stroke="#EF4444"
                                strokeDasharray="5 5"
                              />
                              {/* Equity line (GREEN for IC Trading - aggressive short-term) */}
                              <Line
                                type="monotone"
                                dataKey="equity"
                                stroke="#22C55E"
                                strokeWidth={2}
                                dot={chartData.length < 20}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </>
                    ) : (
                      <div className="h-64 flex items-center justify-center">
                        <div className="text-center text-gray-400">
                          <span className="text-4xl mb-2 block">⚡</span>
                          <p>No equity data for {selectedIcTimeframe.label}</p>
                          <p className="text-xs mt-1">{isIcIntraday ? 'Snapshots appear during market hours' : 'Data will appear after IC trades are executed'}</p>
                        </div>
                      </div>
                    )
                  })()}
                </div>

                {/* IC Signals (Scan Activity) - per STANDARDS.md */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">Recent IC Signals ({icSignals?.count || 0})</h3>
                  {icSignals?.signals?.length > 0 ? (
                    <div className="overflow-x-auto max-h-60">
                      <table className="w-full text-sm">
                        <thead className="sticky top-0 bg-gray-800">
                          <tr className="text-gray-400 border-b border-gray-700">
                            <th className="text-left py-2 px-3">Time</th>
                            <th className="text-left py-2 px-3">Structure</th>
                            <th className="text-right py-2 px-3">Credit</th>
                            <th className="text-right py-2 px-3">Oracle</th>
                            <th className="text-left py-2 px-3">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {icSignals.signals.map((signal: any, idx: number) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-2 px-3 text-xs">
                                {signal.signal_time ? new Date(signal.signal_time).toLocaleTimeString() : '-'}
                              </td>
                              <td className="py-2 px-3 font-mono text-xs">
                                {signal.put_long_strike}/{signal.put_short_strike} - {signal.call_short_strike}/{signal.call_long_strike}
                              </td>
                              <td className="py-2 px-3 text-right text-green-400">${signal.total_credit?.toFixed(2) || '0.00'}</td>
                              <td className="py-2 px-3 text-right">
                                <span className={signal.oracle_approved ? 'text-green-400' : 'text-red-400'}>
                                  {signal.oracle_confidence ? `${(signal.oracle_confidence * 100).toFixed(0)}%` : '-'}
                                </span>
                              </td>
                              <td className="py-2 px-3">
                                <span className={`px-2 py-0.5 rounded text-xs ${
                                  signal.was_executed ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
                                }`}>
                                  {signal.was_executed ? 'EXECUTED' : signal.skip_reason || 'SKIPPED'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-4 text-center text-gray-400 text-sm">
                      <p>No signals generated yet. Signals appear during market hours when conditions are met.</p>
                    </div>
                  )}
                </div>

                {/* IC Activity Logs - per STANDARDS.md */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">IC Activity Log ({icLogs?.count || 0})</h3>
                  {icLogs?.logs?.length > 0 ? (
                    <div className="overflow-x-auto max-h-60">
                      <table className="w-full text-sm">
                        <thead className="sticky top-0 bg-gray-800">
                          <tr className="text-gray-400 border-b border-gray-700">
                            <th className="text-left py-2 px-3">Time</th>
                            <th className="text-left py-2 px-3">Action</th>
                            <th className="text-left py-2 px-3">Message</th>
                            <th className="text-left py-2 px-3">Position</th>
                          </tr>
                        </thead>
                        <tbody>
                          {icLogs.logs.map((log: any, idx: number) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-2 px-3 text-xs">
                                {log.time ? new Date(log.time).toLocaleTimeString() : '-'}
                              </td>
                              <td className="py-2 px-3">
                                <span className={`px-2 py-0.5 rounded text-xs ${
                                  log.action?.includes('OPENED') ? 'bg-green-500/20 text-green-400' :
                                  log.action?.includes('CLOSED') ? 'bg-blue-500/20 text-blue-400' :
                                  log.action?.includes('ERROR') ? 'bg-red-500/20 text-red-400' :
                                  'bg-gray-500/20 text-gray-400'
                                }`}>
                                  {log.action}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-xs text-gray-300 max-w-xs truncate">{log.message}</td>
                              <td className="py-2 px-3 font-mono text-xs text-gray-400">{log.position_id || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-4 text-center text-gray-400 text-sm">
                      <p>No activity logs yet. Logs appear when IC trading actions occur.</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Analytics Tab - Enhanced */}
            {activeTab === 'analytics' && (
              <div className="space-y-6">
                {/* Key Performance Metrics */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">Performance Metrics</h2>
                  <div className="grid md:grid-cols-6 gap-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Return on Capital</div>
                      <div className={`text-2xl font-bold ${returnOnBorrowed >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatPct(returnOnBorrowed)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Cost Efficiency</div>
                      <div className={`text-2xl font-bold ${costEfficiency >= 1 ? 'text-green-400' : 'text-red-400'}`}>
                        {costEfficiency.toFixed(2)}x
                      </div>
                      <div className="text-xs text-gray-500">Returns / Cost</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Gross IC Returns</div>
                      <div className="text-2xl font-bold text-green-400">{formatCurrency(totalICReturns)}</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Borrowing Costs</div>
                      <div className="text-2xl font-bold text-red-400">{formatCurrency(totalCostAccrued)}</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Net Profit</div>
                      <div className={`text-2xl font-bold ${netPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(netPnL)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Open Positions</div>
                      <div className="text-2xl font-bold text-blue-400">{positions?.count || 0}</div>
                    </div>
                  </div>
                </div>

                {/* BOX SPREAD Equity Curve - LONG-TERM CAPITAL (Synthetic Borrowing) */}
                <div className="bg-gray-800 rounded-lg p-6 border-l-4 border-blue-500">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-bold flex items-center gap-2">
                        <span className="text-2xl">🏦</span>
                        Borrowed Capital ({selectedBoxTimeframe.label})
                        <span className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded ml-2">LONG-TERM</span>
                      </h3>
                      <p className="text-xs text-gray-400 mt-1">
                        {positions?.count || 0} box spread position{positions?.count !== 1 ? 's' : ''} •
                        {positions?.positions?.[0] ? (
                          <span className={`ml-1 ${positions.positions[0].current_dte <= 30 ? 'text-yellow-400 font-semibold' : 'text-gray-400'}`}>
                            {positions.positions[0].current_dte <= 30 ? '⚠️ ' : ''}
                            {positions.positions[0].current_dte} DTE to roll
                          </span>
                        ) : (
                          <span className="ml-1 text-gray-500">No active positions</span>
                        )}
                      </p>
                    </div>
                    {/* Roll Countdown Badge - prominent display */}
                    {positions?.positions?.[0] && (
                      <div className={`text-center px-4 py-2 rounded-lg ${
                        positions.positions[0].current_dte <= 7 ? 'bg-red-900/50 border border-red-500' :
                        positions.positions[0].current_dte <= 30 ? 'bg-yellow-900/50 border border-yellow-500' :
                        'bg-blue-900/30 border border-blue-500/30'
                      }`}>
                        <div className="text-xs text-gray-400">Roll In</div>
                        <div className={`text-2xl font-bold ${
                          positions.positions[0].current_dte <= 7 ? 'text-red-400' :
                          positions.positions[0].current_dte <= 30 ? 'text-yellow-400' :
                          'text-blue-400'
                        }`}>
                          {positions.positions[0].current_dte}
                        </div>
                        <div className="text-xs text-gray-400">days</div>
                      </div>
                    )}
                  </div>

                  {/* Timeframe Selector */}
                  <div className="flex justify-end mb-4">
                    <div className="flex bg-gray-700 rounded-lg p-1 gap-1">
                      {EQUITY_TIMEFRAMES.map((tf) => (
                        <button
                          key={tf.id}
                          onClick={() => setBoxEquityTimeframe(tf.id)}
                          className={`px-3 py-1 text-xs rounded transition-colors ${
                            boxEquityTimeframe === tf.id
                              ? 'bg-blue-500 text-black font-semibold'
                              : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                          }`}
                        >
                          {tf.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Loading state */}
                  {(isBoxIntraday ? boxIntradayLoading : boxEquityCurveLoading) ? (
                    <div className="h-64 flex items-center justify-center">
                      <div className="text-gray-400 animate-pulse">Loading equity data...</div>
                    </div>
                  ) : (() => {
                    // Select data source based on timeframe
                    const chartData = isBoxIntraday
                      ? (intradayEquity?.snapshots || []).map((snap: any) => ({
                          time: snap.snapshot_time,
                          equity: snap.total_equity,
                          pnl: snap.unrealized_pnl || 0,
                        }))
                      : (equityCurve?.equity_curve || []).map((point: any) => ({
                          time: point.date,
                          equity: point.equity,
                          pnl: point.cumulative_pnl,
                        }))

                    const startingCapital = equityCurve?.starting_capital || 500000

                    const currentEquity = chartData.length > 0
                      ? chartData[chartData.length - 1]?.equity || startingCapital
                      : startingCapital

                    const currentPnl = chartData.length > 0
                      ? chartData[chartData.length - 1]?.pnl || 0
                      : 0

                    const dataCount = isBoxIntraday
                      ? (intradayEquity?.snapshots?.length || 0)
                      : (equityCurve?.count || chartData.length)

                    return chartData.length > 0 ? (
                      <>
                        {/* Summary Stats */}
                        <div className="grid md:grid-cols-4 gap-4 mb-4">
                          <div className="bg-gray-700/50 rounded-lg p-3">
                            <div className="text-xs text-gray-400">Starting Capital</div>
                            <div className="text-lg font-bold text-blue-400">
                              {formatCurrency(startingCapital)}
                            </div>
                          </div>
                          <div className="bg-gray-700/50 rounded-lg p-3">
                            <div className="text-xs text-gray-400">Current Equity</div>
                            <div className={`text-lg font-bold ${
                              currentEquity >= startingCapital ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {formatCurrency(currentEquity)}
                            </div>
                          </div>
                          <div className="bg-gray-700/50 rounded-lg p-3">
                            <div className="text-xs text-gray-400">{isBoxIntraday ? 'Unrealized P&L' : 'Cumulative P&L'}</div>
                            <div className={`text-lg font-bold ${
                              currentPnl >= 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {formatCurrency(currentPnl)}
                            </div>
                          </div>
                          <div className="bg-gray-700/50 rounded-lg p-3">
                            <div className="text-xs text-gray-400">{isBoxIntraday ? 'Snapshots' : 'Days'}</div>
                            <div className="text-lg font-bold text-orange-400">{dataCount}</div>
                          </div>
                        </div>

                        {/* Recharts LineChart - matching HERACLES style */}
                        <div className="h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={chartData}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                              <XAxis
                                dataKey="time"
                                stroke="#9CA3AF"
                                tick={{ fill: '#9CA3AF', fontSize: 11 }}
                                tickFormatter={(value) => {
                                  if (!value) return ''
                                  const date = new Date(value)
                                  if (isBoxIntraday) {
                                    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
                                  }
                                  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                                }}
                              />
                              <YAxis
                                stroke="#9CA3AF"
                                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                                tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                                domain={['dataMin - 1000', 'dataMax + 1000']}
                              />
                              <Tooltip
                                contentStyle={{
                                  backgroundColor: '#1F2937',
                                  border: '1px solid #374151',
                                  borderRadius: '8px',
                                }}
                                labelFormatter={(value) => {
                                  if (!value) return ''
                                  const date = new Date(value)
                                  if (isBoxIntraday) {
                                    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
                                  }
                                  return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
                                }}
                                formatter={(value: number, name: string) => {
                                  if (name === 'equity') return [formatCurrency(value), 'Equity']
                                  return [formatCurrency(value), name]
                                }}
                              />
                              {/* Reference line at starting capital */}
                              <ReferenceLine
                                y={startingCapital}
                                stroke="#EF4444"
                                strokeDasharray="5 5"
                                strokeWidth={1}
                              />
                              {/* Equity line (BLUE for Box Spread - long-term capital) */}
                              <Line
                                type="monotone"
                                dataKey="equity"
                                stroke="#3B82F6"
                                strokeWidth={2}
                                dot={false}
                                activeDot={{ r: 4, fill: '#3B82F6' }}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </>
                    ) : (
                      <div className="h-64 flex items-center justify-center">
                        <div className="text-center text-gray-400">
                          <span className="text-4xl mb-2 block">🏦</span>
                          <p>No equity data for {selectedBoxTimeframe.label}</p>
                          <p className="text-xs mt-1">{isBoxIntraday ? 'Snapshots appear during market hours' : 'Data will appear after box spreads close'}</p>
                        </div>
                      </div>
                    )
                  })()}
                </div>

                {/* Interest Rates */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">Interest Rate Environment</h2>
                  {interestRates ? (
                    <div>
                      <div className="grid md:grid-cols-5 gap-3 mb-4">
                        <div className="bg-blue-900/30 rounded-lg p-4 text-center border border-blue-700/30">
                          <div className="text-xs text-gray-400 mb-1">Fed Funds</div>
                          <div className="text-xl font-bold text-blue-400">{formatPct(interestRates.fed_funds_rate)}</div>
                        </div>
                        <div className="bg-cyan-900/30 rounded-lg p-4 text-center border border-cyan-700/30">
                          <div className="text-xs text-gray-400 mb-1">SOFR</div>
                          <div className="text-xl font-bold text-cyan-400">{formatPct(interestRates.sofr_rate)}</div>
                        </div>
                        <div className="bg-purple-900/30 rounded-lg p-4 text-center border border-purple-700/30">
                          <div className="text-xs text-gray-400 mb-1">3M Treasury</div>
                          <div className="text-xl font-bold text-purple-400">{formatPct(interestRates.treasury_3m)}</div>
                        </div>
                        <div className="bg-red-900/30 rounded-lg p-4 text-center border border-red-700/30">
                          <div className="text-xs text-gray-400 mb-1">Margin Rate</div>
                          <div className="text-xl font-bold text-red-400">{formatPct(interestRates.margin_rate)}</div>
                        </div>
                        <div className="bg-green-900/30 rounded-lg p-4 text-center border border-green-700/30">
                          <div className="text-xs text-gray-400 mb-1">Box Spread</div>
                          <div className="text-xl font-bold text-green-400">{formatPct(rateAnalysis?.box_implied_rate || 0)}</div>
                        </div>
                      </div>
                      <div className="bg-black/30 rounded-lg p-3 flex justify-between items-center text-xs">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${interestRates.source === 'live' ? 'bg-green-500' : 'bg-yellow-500'}`}></span>
                          <span className="text-gray-400">Source: {interestRates.source?.toUpperCase()}</span>
                        </div>
                        <span className="text-gray-500">
                          Updated: {interestRates.last_updated ? new Date(interestRates.last_updated).toLocaleTimeString() : 'N/A'}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-4 text-gray-500">Loading rates...</div>
                  )}
                </div>

                {/* PROMETHEUS IC Trading Performance */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">PROMETHEUS IC Trading Performance</h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    {/* IC Statistics */}
                    <div className="bg-orange-900/30 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold text-orange-400">IC Trading</h3>
                        <span className="text-xs text-gray-400">SPX 0DTE</span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Total Trades:</span>
                          <span>{icPerformance?.performance?.closed_trades?.total || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Win Rate:</span>
                          <span className={(icPerformance?.performance?.closed_trades?.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-red-400'}>
                            {formatPct((icPerformance?.performance?.closed_trades?.win_rate || 0) * 100)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Open Positions:</span>
                          <span>{icStatus?.status?.open_positions || 0}</span>
                        </div>
                      </div>
                    </div>

                    {/* Returns */}
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold">Returns</h3>
                        <span className="text-xs text-gray-400">All IC Trades</span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Realized P&L:</span>
                          <span className={(icPerformance?.performance?.closed_trades?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {formatCurrency(icPerformance?.performance?.closed_trades?.total_pnl || 0)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Unrealized P&L:</span>
                          <span className={(icStatus?.status?.total_unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {formatCurrency(icStatus?.status?.total_unrealized_pnl || 0)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Profit Factor:</span>
                          <span>{(icPerformance?.performance?.closed_trades?.profit_factor || 0).toFixed(2)}</span>
                        </div>
                      </div>
                    </div>

                    {/* Net Performance */}
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold">Net Performance</h3>
                        <span className="text-xs text-gray-400">vs Borrowing Cost</span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">IC Returns:</span>
                          <span className="text-green-400">+{formatCurrency(combinedPerformance?.summary?.ic_trading?.total_realized_pnl || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Borrowing Cost:</span>
                          <span className="text-red-400">-{formatCurrency(combinedPerformance?.summary?.box_spread?.total_borrowing_cost || 0)}</span>
                        </div>
                        <div className="flex justify-between font-bold border-t border-gray-600 pt-2">
                          <span className="text-gray-300">Net Profit:</span>
                          <span className={(combinedPerformance?.summary?.net_profit || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {formatCurrency(combinedPerformance?.summary?.net_profit || 0)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Capital Flow Summary */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">Capital Flow Summary</h2>
                  <div className="grid md:grid-cols-2 gap-6">
                    <div>
                      <h3 className="text-sm font-medium text-green-400 mb-2">Inflows</h3>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Box Spread Credit:</span>
                          <span className="text-green-400">+{formatCurrency(totalBorrowed)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">IC Bot Returns:</span>
                          <span className="text-green-400">+{formatCurrency(totalICReturns)}</span>
                        </div>
                        <div className="border-t border-gray-700 pt-2 flex justify-between font-medium">
                          <span>Total Inflows:</span>
                          <span className="text-green-400">{formatCurrency(totalBorrowed + totalICReturns)}</span>
                        </div>
                      </div>
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-red-400 mb-2">Costs &amp; Outflows</h3>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Box Spread Owed:</span>
                          <span>{formatCurrency(positions?.positions?.[0]?.total_owed_at_expiration || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Borrowing Costs:</span>
                          <span className="text-red-400">-{formatCurrency(totalCostAccrued)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">IC Capital at Risk:</span>
                          <span>{formatCurrency(icStatus?.status?.total_capital_at_risk || 0)}</span>
                        </div>
                        <div className="border-t border-gray-700 pt-2 flex justify-between font-medium">
                          <span>Net P&L:</span>
                          <span className={netPnL >= 0 ? 'text-green-400' : 'text-red-400'}>{formatCurrency(netPnL)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Education Tab */}
            {activeTab === 'education' && (
              <div className="space-y-8">
                {/* Hero Section */}
                <div className="bg-gradient-to-r from-orange-900/50 via-red-900/30 to-orange-900/50 rounded-xl p-8 border border-orange-500/30">
                  <div className="text-center mb-6">
                    <h1 className="text-4xl font-bold text-white mb-2">PROMETHEUS</h1>
                    <p className="text-xl text-orange-300">Box Spread Synthetic Borrowing System</p>
                    <p className="text-gray-400 mt-2 max-w-2xl mx-auto">
                      Borrow capital at institutional rates using options, deploy to Iron Condor bots,
                      profit from the spread between borrowing cost and trading returns.
                    </p>
                  </div>
                </div>

                {/* System Architecture - Visual Flow */}
                <div className="bg-gray-800 rounded-xl p-6">
                  <h2 className="text-2xl font-bold mb-6 text-center">System Architecture</h2>

                  {/* 3-Step Visual Flow */}
                  <div className="grid md:grid-cols-3 gap-4 mb-8">
                    {/* Step 1: Borrow */}
                    <div className="relative">
                      <div className="bg-gradient-to-br from-blue-900/50 to-blue-800/30 rounded-xl p-6 border border-blue-500/30 h-full">
                        <div className="absolute -top-3 -left-3 w-10 h-10 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-lg">1</div>
                        <div className="text-center mb-4 pt-2">
                          <div className="text-4xl mb-2">📦</div>
                          <h3 className="text-xl font-bold text-blue-400">BORROW</h3>
                        </div>
                        <div className="bg-black/40 rounded-lg p-4">
                          <div className="text-sm text-center mb-3 text-gray-300">SPX Box Spread</div>
                          <div className="space-y-2 text-xs">
                            <div className="flex justify-between items-center bg-green-900/30 rounded px-2 py-1">
                              <span className="text-green-400">BUY</span>
                              <span>Call @ K1</span>
                            </div>
                            <div className="flex justify-between items-center bg-red-900/30 rounded px-2 py-1">
                              <span className="text-red-400">SELL</span>
                              <span>Call @ K2</span>
                            </div>
                            <div className="flex justify-between items-center bg-green-900/30 rounded px-2 py-1">
                              <span className="text-green-400">BUY</span>
                              <span>Put @ K2</span>
                            </div>
                            <div className="flex justify-between items-center bg-red-900/30 rounded px-2 py-1">
                              <span className="text-red-400">SELL</span>
                              <span>Put @ K1</span>
                            </div>
                          </div>
                          <div className="text-center mt-4 pt-3 border-t border-gray-700">
                            <span className="text-green-400 font-bold">= NET CREDIT</span>
                          </div>
                        </div>
                      </div>
                      {/* Arrow */}
                      <div className="hidden md:block absolute top-1/2 -right-2 transform translate-x-1/2 -translate-y-1/2 text-3xl text-gray-500">→</div>
                    </div>

                    {/* Step 2: Trade */}
                    <div className="relative">
                      <div className="bg-gradient-to-br from-orange-900/50 to-orange-800/30 rounded-xl p-6 border border-orange-500/30 h-full">
                        <div className="absolute -top-3 -left-3 w-10 h-10 bg-orange-600 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-lg">2</div>
                        <div className="text-center mb-4 pt-2">
                          <div className="text-4xl mb-2">📊</div>
                          <h3 className="text-xl font-bold text-orange-400">TRADE IC</h3>
                        </div>
                        <div className="bg-black/40 rounded-lg p-4">
                          <div className="text-sm text-center mb-3 text-gray-300">PROMETHEUS IC Trading</div>
                          <div className="space-y-3">
                            <div className="relative">
                              <div className="flex justify-between text-xs mb-1">
                                <span className="text-orange-400 font-medium">SPX Iron Condors</span>
                                <span>0DTE</span>
                              </div>
                              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full bg-orange-500 rounded-full" style={{ width: '100%' }}></div>
                              </div>
                            </div>
                            <div className="text-xs text-gray-400 mt-2 space-y-1">
                              <div>• Oracle-approved trades only</div>
                              <div>• 10 delta short strikes</div>
                              <div>• Every 10 minutes</div>
                              <div>• Max 3 positions</div>
                            </div>
                          </div>
                        </div>
                      </div>
                      {/* Arrow */}
                      <div className="hidden md:block absolute top-1/2 -right-2 transform translate-x-1/2 -translate-y-1/2 text-3xl text-gray-500">→</div>
                    </div>

                    {/* Step 3: Profit */}
                    <div className="relative">
                      <div className="bg-gradient-to-br from-green-900/50 to-green-800/30 rounded-xl p-6 border border-green-500/30 h-full">
                        <div className="absolute -top-3 -left-3 w-10 h-10 bg-green-600 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-lg">3</div>
                        <div className="text-center mb-4 pt-2">
                          <div className="text-4xl mb-2">📈</div>
                          <h3 className="text-xl font-bold text-green-400">PROFIT</h3>
                        </div>
                        <div className="bg-black/40 rounded-lg p-4">
                          <div className="text-sm text-center mb-3 text-gray-300">Net Calculation</div>
                          <div className="space-y-3 text-sm">
                            <div className="flex justify-between items-center">
                              <span className="text-gray-400">IC Returns</span>
                              <span className="text-green-400 font-bold">+2-4%/mo</span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-gray-400">Borrow Cost</span>
                              <span className="text-red-400 font-bold">-0.4%/mo</span>
                            </div>
                            <div className="border-t border-gray-600 pt-3 flex justify-between items-center">
                              <span className="font-medium">Net Profit</span>
                              <span className="text-green-400 font-bold text-lg">+1.6-3.6%</span>
                            </div>
                          </div>
                          <div className="text-center mt-3 text-xs text-gray-500">per month</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Why It Works */}
                  <div className="bg-black/30 rounded-lg p-4 text-center">
                    <p className="text-gray-300">
                      <span className="text-orange-400 font-medium">The Edge:</span> Borrow at
                      <span className="text-blue-400 font-bold"> ~4.5%/year</span> via box spreads vs
                      <span className="text-red-400 font-bold"> 8-9%/year</span> margin rate.
                      IC bots target <span className="text-green-400 font-bold">24-48%/year</span> returns.
                    </p>
                  </div>
                </div>

                {/* What is a Box Spread - Visual Explanation */}
                <div className="bg-gray-800 rounded-xl p-6">
                  <h2 className="text-2xl font-bold mb-6 text-orange-400">What is a Box Spread?</h2>

                  <div className="grid md:grid-cols-2 gap-6">
                    {/* Left: Structure */}
                    <div>
                      <p className="text-gray-300 mb-4">
                        A box spread combines 4 options to create a <strong className="text-white">synthetic zero-coupon bond</strong>.
                        The payoff at expiration is guaranteed regardless of where the market moves.
                      </p>

                      <div className="bg-gradient-to-br from-gray-700/50 to-gray-800/50 rounded-lg p-5 border border-gray-600/50">
                        <h4 className="font-medium text-white mb-4 text-center">The 4 Legs</h4>
                        <div className="space-y-3">
                          <div className="flex items-center gap-3 bg-green-900/20 rounded-lg p-3 border border-green-700/30">
                            <div className="w-8 h-8 bg-green-600 rounded flex items-center justify-center text-sm font-bold">+</div>
                            <div>
                              <div className="font-medium text-green-400">Long Call @ K1</div>
                              <div className="text-xs text-gray-400">Lower strike call (buy)</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 bg-red-900/20 rounded-lg p-3 border border-red-700/30">
                            <div className="w-8 h-8 bg-red-600 rounded flex items-center justify-center text-sm font-bold">−</div>
                            <div>
                              <div className="font-medium text-red-400">Short Call @ K2</div>
                              <div className="text-xs text-gray-400">Upper strike call (sell)</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 bg-green-900/20 rounded-lg p-3 border border-green-700/30">
                            <div className="w-8 h-8 bg-green-600 rounded flex items-center justify-center text-sm font-bold">+</div>
                            <div>
                              <div className="font-medium text-green-400">Long Put @ K2</div>
                              <div className="text-xs text-gray-400">Upper strike put (buy)</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 bg-red-900/20 rounded-lg p-3 border border-red-700/30">
                            <div className="w-8 h-8 bg-red-600 rounded flex items-center justify-center text-sm font-bold">−</div>
                            <div>
                              <div className="font-medium text-red-400">Short Put @ K1</div>
                              <div className="text-xs text-gray-400">Lower strike put (sell)</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Right: Key Properties */}
                    <div className="space-y-4">
                      <div className="bg-gradient-to-br from-blue-900/30 to-blue-800/20 rounded-lg p-5 border border-blue-600/30">
                        <div className="flex items-start gap-4">
                          <div className="w-12 h-12 bg-blue-600 rounded-lg flex items-center justify-center text-2xl flex-shrink-0">🎯</div>
                          <div>
                            <h4 className="font-bold text-blue-400 mb-1">Guaranteed Value</h4>
                            <p className="text-sm text-gray-300">Always worth exactly <span className="font-mono text-white">(K2 - K1) × 100</span> at expiration, regardless of market price</p>
                          </div>
                        </div>
                      </div>

                      <div className="bg-gradient-to-br from-purple-900/30 to-purple-800/20 rounded-lg p-5 border border-purple-600/30">
                        <div className="flex items-start gap-4">
                          <div className="w-12 h-12 bg-purple-600 rounded-lg flex items-center justify-center text-2xl flex-shrink-0">🛡️</div>
                          <div>
                            <h4 className="font-bold text-purple-400 mb-1">Zero Market Risk</h4>
                            <p className="text-sm text-gray-300">SPX can go up 1000 points or down 1000 points - the box value stays the same</p>
                          </div>
                        </div>
                      </div>

                      <div className="bg-gradient-to-br from-green-900/30 to-green-800/20 rounded-lg p-5 border border-green-600/30">
                        <div className="flex items-start gap-4">
                          <div className="w-12 h-12 bg-green-600 rounded-lg flex items-center justify-center text-2xl flex-shrink-0">💵</div>
                          <div>
                            <h4 className="font-bold text-green-400 mb-1">Synthetic Loan</h4>
                            <p className="text-sm text-gray-300">Credit received today, pay back face value at expiration. The discount = your interest rate.</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Rate Calculation - Interactive Example */}
                <div className="bg-gray-800 rounded-xl p-6">
                  <h2 className="text-2xl font-bold mb-6 text-orange-400">How the Rate is Calculated</h2>

                  {/* Formula */}
                  <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-xl p-6 mb-6 border border-gray-600">
                    <div className="text-center">
                      <div className="text-sm text-gray-400 mb-3">Implied Annual Rate Formula</div>
                      <div className="inline-block bg-black/50 rounded-lg px-8 py-4 border border-orange-500/30">
                        <span className="font-mono text-xl text-white">
                          Rate = <span className="text-blue-400">((FV / Credit)</span> <span className="text-gray-400">-</span> <span className="text-purple-400">1)</span> <span className="text-gray-400">×</span> <span className="text-green-400">(365 / DTE)</span> <span className="text-gray-400">×</span> <span className="text-orange-400">100</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Example Calculation */}
                  <div className="grid md:grid-cols-3 gap-6">
                    <div className="bg-gradient-to-br from-blue-900/30 to-blue-800/20 rounded-lg p-5 border border-blue-600/30">
                      <h4 className="font-bold text-blue-400 mb-4 text-center">Example Position</h4>
                      <div className="space-y-3 text-sm">
                        <div className="flex justify-between py-2 border-b border-gray-700">
                          <span className="text-gray-400">Strike Width</span>
                          <span className="font-mono font-bold">$50</span>
                        </div>
                        <div className="flex justify-between py-2 border-b border-gray-700">
                          <span className="text-gray-400">Face Value</span>
                          <span className="font-mono font-bold">$5,000</span>
                        </div>
                        <div className="flex justify-between py-2 border-b border-gray-700">
                          <span className="text-gray-400">Credit Received</span>
                          <span className="font-mono font-bold text-green-400">$4,890</span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span className="text-gray-400">DTE</span>
                          <span className="font-mono font-bold">180 days</span>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-purple-900/30 to-purple-800/20 rounded-lg p-5 border border-purple-600/30">
                      <h4 className="font-bold text-purple-400 mb-4 text-center">Calculation Steps</h4>
                      <div className="space-y-3 font-mono text-sm">
                        <div className="bg-black/30 rounded p-2">
                          <div className="text-gray-400 text-xs mb-1">Step 1: Ratio</div>
                          <div>$5,000 / $4,890 = <span className="text-white">1.0225</span></div>
                        </div>
                        <div className="bg-black/30 rounded p-2">
                          <div className="text-gray-400 text-xs mb-1">Step 2: Period Return</div>
                          <div>1.0225 - 1 = <span className="text-white">0.0225</span></div>
                        </div>
                        <div className="bg-black/30 rounded p-2">
                          <div className="text-gray-400 text-xs mb-1">Step 3: Annualize</div>
                          <div>0.0225 × (365/180) = <span className="text-white">0.0456</span></div>
                        </div>
                        <div className="bg-green-900/30 rounded p-2 border border-green-600/30">
                          <div className="text-gray-400 text-xs mb-1">Result</div>
                          <div className="text-green-400 font-bold text-lg">4.56% annual</div>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-green-900/30 to-green-800/20 rounded-lg p-5 border border-green-600/30">
                      <h4 className="font-bold text-green-400 mb-4 text-center">Rate Comparison</h4>
                      <div className="space-y-4">
                        <div className="flex items-center justify-between p-3 bg-red-900/20 rounded-lg border border-red-700/30">
                          <span className="text-sm">Margin Rate</span>
                          <span className="font-bold text-red-400 text-lg">8.5%</span>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-green-900/20 rounded-lg border border-green-700/30">
                          <span className="text-sm">Box Spread</span>
                          <span className="font-bold text-green-400 text-lg">4.56%</span>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-emerald-900/30 rounded-lg border-2 border-emerald-500/50">
                          <span className="font-medium">Your Savings</span>
                          <span className="font-bold text-emerald-400 text-xl">3.94%</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Why SPX */}
                <div className="bg-gray-800 rounded-xl p-6">
                  <h2 className="text-2xl font-bold mb-6 text-orange-400">Why SPX Options?</h2>

                  <div className="grid md:grid-cols-2 gap-6">
                    {/* SPX Advantages */}
                    <div className="space-y-3">
                      <h3 className="text-lg font-medium text-green-400 mb-4 flex items-center gap-2">
                        <span className="w-6 h-6 bg-green-600 rounded-full flex items-center justify-center text-sm">✓</span>
                        Why SPX Works
                      </h3>
                      {[
                        { title: 'European-Style Settlement', desc: 'Cannot be exercised early - eliminates assignment risk entirely' },
                        { title: 'Cash Settlement', desc: 'No stock delivery, just cash difference at expiration' },
                        { title: 'High Liquidity', desc: 'Tight bid/ask spreads = better effective borrowing rates' },
                        { title: 'Section 1256 Tax Treatment', desc: '60% long-term / 40% short-term capital gains treatment' },
                      ].map((item, idx) => (
                        <div key={idx} className="flex items-start gap-3 bg-green-900/10 rounded-lg p-4 border border-green-700/20">
                          <div className="w-6 h-6 bg-green-600/50 rounded flex items-center justify-center text-xs flex-shrink-0">✓</div>
                          <div>
                            <div className="font-medium text-white">{item.title}</div>
                            <div className="text-sm text-gray-400">{item.desc}</div>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* SPY Problems */}
                    <div className="space-y-3">
                      <h3 className="text-lg font-medium text-red-400 mb-4 flex items-center gap-2">
                        <span className="w-6 h-6 bg-red-600 rounded-full flex items-center justify-center text-sm">✗</span>
                        Why NOT SPY or ETFs
                      </h3>
                      {[
                        { title: 'American-Style Options', desc: 'Can be exercised early, especially near ex-dividend dates' },
                        { title: 'Physical Delivery', desc: 'Assignment means buying/selling actual shares' },
                        { title: 'Dividend Risk', desc: 'Deep ITM calls get assigned to capture dividends' },
                        { title: 'Assignment Destroys Position', desc: 'Early exercise breaks the box, creates losses' },
                      ].map((item, idx) => (
                        <div key={idx} className="flex items-start gap-3 bg-red-900/10 rounded-lg p-4 border border-red-700/20">
                          <div className="w-6 h-6 bg-red-600/50 rounded flex items-center justify-center text-xs flex-shrink-0">✗</div>
                          <div>
                            <div className="font-medium text-white">{item.title}</div>
                            <div className="text-sm text-gray-400">{item.desc}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Risk Management */}
                <div className="bg-gray-800 rounded-xl p-6">
                  <h2 className="text-2xl font-bold mb-6 text-orange-400">Understanding the Risks</h2>

                  <div className="grid md:grid-cols-2 gap-4">
                    {[
                      { icon: '💳', title: 'Margin Requirements', desc: 'Box spreads require significant margin. Your broker holds the full strike width as collateral until expiration.' },
                      { icon: '📉', title: 'Execution Slippage', desc: 'Four-leg orders can have slippage. Wide bid/ask spreads on any leg affect your effective borrowing rate.' },
                      { icon: '🔒', title: 'Rate Lock-In', desc: 'Once opened, your borrowing rate is locked until expiration. If rates drop, you cannot refinance without loss.' },
                      { icon: '⚠️', title: 'IC Bot Underperformance', desc: 'PROMETHEUS only profits if IC bot returns exceed borrowing costs. A losing streak means paying interest with no gains.' },
                    ].map((risk, idx) => (
                      <div key={idx} className="bg-gradient-to-br from-yellow-900/20 to-orange-900/10 rounded-lg p-5 border border-yellow-700/30">
                        <div className="flex items-start gap-4">
                          <div className="text-3xl flex-shrink-0">{risk.icon}</div>
                          <div>
                            <h4 className="font-bold text-yellow-400 mb-2">{risk.title}</h4>
                            <p className="text-sm text-gray-300">{risk.desc}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* How PROMETHEUS Manages This */}
                <div className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl p-6 border border-orange-500/20">
                  <h2 className="text-2xl font-bold mb-6 text-orange-400">How PROMETHEUS Manages Risk</h2>

                  <div className="grid md:grid-cols-3 gap-6">
                    <div className="bg-black/30 rounded-xl p-6 border border-gray-700 text-center">
                      <div className="w-16 h-16 bg-gradient-to-br from-blue-600 to-blue-800 rounded-xl mx-auto mb-4 flex items-center justify-center text-3xl">📊</div>
                      <h4 className="font-bold text-white mb-2">Rate Monitoring</h4>
                      <p className="text-sm text-gray-400">
                        Continuously monitors box spread implied rates vs Fed Funds. Only borrows when
                        rates are favorable (Fed Funds + 0.5% or less).
                      </p>
                    </div>

                    <div className="bg-black/30 rounded-xl p-6 border border-gray-700 text-center">
                      <div className="w-16 h-16 bg-gradient-to-br from-purple-600 to-purple-800 rounded-xl mx-auto mb-4 flex items-center justify-center text-3xl">🔄</div>
                      <h4 className="font-bold text-white mb-2">Rolling Strategy</h4>
                      <p className="text-sm text-gray-400">
                        Positions with less than 30 DTE are evaluated for rolling to maintain deployed
                        capital without gaps in funding.
                      </p>
                    </div>

                    <div className="bg-black/30 rounded-xl p-6 border border-gray-700 text-center">
                      <div className="w-16 h-16 bg-gradient-to-br from-green-600 to-green-800 rounded-xl mx-auto mb-4 flex items-center justify-center text-3xl">🛡️</div>
                      <h4 className="font-bold text-white mb-2">Reserve Buffer</h4>
                      <p className="text-sm text-gray-400">
                        10% of borrowed capital is held in reserve for margin calls or emergency
                        adjustments, never deployed to IC bots.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* How It Works Tab - Complete System Documentation with Wireframes */}
            {activeTab === 'howItWorks' && (
              <div className="space-y-8">
                {/* Header */}
                <div className="bg-gradient-to-r from-purple-900/50 via-indigo-900/30 to-purple-900/50 rounded-xl p-8 border border-purple-500/30">
                  <div className="text-center mb-4">
                    <h1 className="text-4xl font-bold text-white mb-2">PROMETHEUS System Flow</h1>
                    <p className="text-xl text-purple-300">Complete Operational Reference Guide</p>
                    <p className="text-gray-400 mt-2 max-w-2xl mx-auto">
                      This reference shows exactly how PROMETHEUS operates from market open to close.
                      Use this guide to understand what is happening at any moment.
                    </p>
                  </div>
                </div>

                {/* Table of Contents */}
                <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                  <h2 className="text-xl font-bold mb-4 text-orange-400">Quick Navigation</h2>
                  <div className="grid md:grid-cols-4 gap-4 text-sm">
                    <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
                      <div className="font-medium text-blue-400 mb-2">Part 1: Box Spreads</div>
                      <ul className="text-gray-400 space-y-1">
                        <li>1. Pre-Market Startup</li>
                        <li>2. Box Spread Lifecycle</li>
                        <li>9. MTM Calculation</li>
                        <li>10. Roll Execution</li>
                      </ul>
                    </div>
                    <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
                      <div className="font-medium text-orange-400 mb-2">Part 2: IC Trading</div>
                      <ul className="text-gray-400 space-y-1">
                        <li>3. IC Trading Cycle</li>
                        <li>4. Oracle Scan Activity</li>
                        <li>11. IC Exit Flow</li>
                      </ul>
                    </div>
                    <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
                      <div className="font-medium text-yellow-400 mb-2">Part 3: Analytics</div>
                      <ul className="text-gray-400 space-y-1">
                        <li>5. Daily P&L Breakdown</li>
                        <li>6. Risk Alerts</li>
                        <li>7. Complete Data Flow</li>
                      </ul>
                    </div>
                    <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
                      <div className="font-medium text-green-400 mb-2">Reference</div>
                      <ul className="text-gray-400 space-y-1">
                        <li>8. Daily Timeline</li>
                        <li>Key Config Values</li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* PART 1: PRE-MARKET STARTUP FLOW */}
                <div className="bg-gray-800 rounded-xl p-6 border border-blue-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center text-xl">1</span>
                    <span className="text-blue-400">Pre-Market Startup Flow (8:00-8:30 AM CT)</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-green-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PROMETHEUS PRE-MARKET STARTUP                             │
│                        (8:00 AM CT Daily)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌────────────────┐     ┌─────────────────────────────┐ │
│  │   SYSTEM    │────▶│  TRADIER API   │────▶│  POSITION RECONCILIATION    │ │
│  │   WAKES UP  │     │  (Production)  │     │                             │ │
│  └─────────────┘     └────────────────┘     │  • Load all open boxes      │ │
│                              │              │  • Calculate current MTM     │ │
│                              │              │  • Check DTE on each         │ │
│                              ▼              │  • Update cost accruals      │ │
│                      ┌────────────────┐     └─────────────────────────────┘ │
│                      │  RATE CHECK    │                    │                │
│                      │                │                    │                │
│                      │ Fed Funds: X%  │                    ▼                │
│                      │ Margin:    Y%  │     ┌─────────────────────────────┐ │
│                      │ Box Rate:  Z%  │     │       ROLL DECISIONS        │ │
│                      └────────────────┘     │                             │ │
│                                             │  IF DTE ≤ 30:              │ │
│                                             │    → Flag for roll          │ │
│                                             │    → Check new rates        │ │
│                                             │    → Queue if favorable     │ │
│                                             └─────────────────────────────┘ │
│                                                          │                  │
│                                                          ▼                  │
│                                             ┌─────────────────────────────┐ │
│                                             │     CAPITAL ALLOCATION      │ │
│                                             │                             │ │
│                                             │  Total Borrowed: $XXX       │ │
│                                             │  - Reserve (10%): $XXX      │ │
│                                             │  = Available: $XXX          │ │
│                                             │                             │ │
│                                             │  Per IC Trade: $5,000       │ │
│                                             │  Max Positions: 3           │ │
│                                             └─────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>

                  {/* Explanation */}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-600/30">
                      <h4 className="font-bold text-blue-400 mb-2">What Happens</h4>
                      <ul className="text-sm text-gray-300 space-y-2">
                        <li>1. System connects to Tradier PRODUCTION API</li>
                        <li>2. Loads all open box spread positions</li>
                        <li>3. Fetches current market prices for MTM</li>
                        <li>4. Calculates daily interest accrual</li>
                        <li>5. Checks which positions need rolling</li>
                      </ul>
                    </div>
                    <div className="bg-purple-900/20 rounded-lg p-4 border border-purple-600/30">
                      <h4 className="font-bold text-purple-400 mb-2">Key Thresholds</h4>
                      <ul className="text-sm text-gray-300 space-y-2">
                        <li><span className="text-yellow-400">Roll Threshold:</span> DTE ≤ 30 days</li>
                        <li><span className="text-yellow-400">Reserve:</span> 10% of borrowed capital</li>
                        <li><span className="text-yellow-400">Capital/Trade:</span> $5,000 per IC</li>
                        <li><span className="text-yellow-400">Max Positions:</span> 3 ICs at a time</li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* PART 2: BOX SPREAD SIDE */}
                <div className="bg-gray-800 rounded-xl p-6 border border-blue-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center text-xl">2</span>
                    <span className="text-blue-400">Box Spread Side - "The Loan"</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-cyan-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│                     BOX SPREAD POSITION LIFECYCLE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  OPEN NEW BOX                          DAILY MONITORING                     │
│  ═══════════                           ════════════════                     │
│  ┌───────────────┐                     ┌───────────────────────────────┐    │
│  │ Check Rates   │                     │  For each open box:           │    │
│  │               │                     │                               │    │
│  │ Box < Margin? │─── NO ──▶ SKIP      │  1. Fetch current prices      │    │
│  │               │                     │  2. Calculate MTM value       │    │
│  └───────┬───────┘                     │  3. Accrue daily interest     │    │
│          │                             │  4. Check roll eligibility    │    │
│         YES                            │                               │    │
│          │                             └───────────────────────────────┘    │
│          ▼                                          │                       │
│  ┌───────────────┐                                  ▼                       │
│  │ Select Strikes│                     ┌───────────────────────────────┐    │
│  │               │                     │  ROLL DECISION MATRIX         │    │
│  │ Lower: SPX-25 │                     │                               │    │
│  │ Upper: SPX+25 │                     │  DTE ≤ 0:   CRITICAL (roll!)  │    │
│  │ Width: 50pts  │                     │  DTE 1-7:   WARNING           │    │
│  └───────┬───────┘                     │  DTE 8-14:  SOON              │    │
│          │                             │  DTE 15-30: SCHEDULED         │    │
│          ▼                             │  DTE > 30:  OK                │    │
│  ┌───────────────┐                     └───────────────────────────────┘    │
│  │ Execute Box   │                                                          │
│  │               │                     EXPIRATION                           │
│  │ 4-leg order:  │                     ══════════                           │
│  │ +Call K1      │                     ┌───────────────────────────────┐    │
│  │ -Call K2      │                     │  Box settles at strike width  │    │
│  │ +Put  K2      │                     │  Cash-settled (SPX)           │    │
│  │ -Put  K1      │                     │  "Loan" repaid automatically  │    │
│  └───────┬───────┘                     │  No stock delivery            │    │
│          │                             └───────────────────────────────┘    │
│          ▼                                                                  │
│  ┌───────────────┐                                                          │
│  │ Record:       │                                                          │
│  │ • Credit rcvd │                                                          │
│  │ • Implied rate│                                                          │
│  │ • Expiration  │                                                          │
│  │ • Margin held │                                                          │
│  └───────────────┘                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>

                  {/* Capital Flow */}
                  <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg p-4 border border-blue-600/30 mb-4">
                    <h4 className="font-bold text-white mb-3">Capital Flow Example</h4>
                    <div className="grid md:grid-cols-4 gap-4 text-sm">
                      <div className="text-center">
                        <div className="text-gray-400">Box Credit</div>
                        <div className="text-2xl font-bold text-green-400">$49,250</div>
                        <div className="text-xs text-gray-500">($50 width × 10 contracts × 98.5)</div>
                      </div>
                      <div className="text-center">
                        <div className="text-gray-400">Reserve (10%)</div>
                        <div className="text-2xl font-bold text-yellow-400">$4,925</div>
                        <div className="text-xs text-gray-500">Safety buffer</div>
                      </div>
                      <div className="text-center">
                        <div className="text-gray-400">Available for IC</div>
                        <div className="text-2xl font-bold text-orange-400">$44,325</div>
                        <div className="text-xs text-gray-500">Deployed to trading</div>
                      </div>
                      <div className="text-center">
                        <div className="text-gray-400">Owed at Expiry</div>
                        <div className="text-2xl font-bold text-red-400">$50,000</div>
                        <div className="text-xs text-gray-500">Strike width × contracts × 100</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PART 3: IC TRADING CYCLE */}
                <div className="bg-gray-800 rounded-xl p-6 border border-orange-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-orange-600 rounded-lg flex items-center justify-center text-xl">3</span>
                    <span className="text-orange-400">IC Trading Cycle (Every 5-15 Minutes)</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-orange-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PROMETHEUS IC TRADING CYCLE                               │
│                    (Follows PEGASUS Trading Rules)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  SCAN TRIGGER   │   Every 5-15 minutes during market hours               │
│  │  (8:35 AM CT)   │   (configurable interval)                              │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐        ┌─────────────────────────────────────────┐     │
│  │ MARKET CHECK    │        │  VIX FILTER (from PEGASUS rules):       │     │
│  │                 │        │  • Min VIX: 12 (premiums too thin)      │     │
│  │ • Get SPX price │───────▶│  • Max VIX: 35 (too risky)              │     │
│  │ • Get VIX       │        │  • Mon/Fri Max: 30 (decay risk)         │     │
│  │ • Get GEX regime│        └─────────────────────────────────────────┘     │
│  └────────┬────────┘                         │                              │
│           │                                PASS?                            │
│           │                                  │                              │
│  ┌────────┴────────────────────────────────┐ │                              │
│  │                                          │ │                              │
│  │                   NO ◀───────────────────┘ │                              │
│  │                   │                        │                              │
│  │         Log: "VIX 38 too high"            YES                            │
│  │         Skip scan                          │                              │
│  │                                            ▼                              │
│  │                              ┌─────────────────────────────┐             │
│  │                              │       ORACLE CHECK          │             │
│  │                              │                             │             │
│  │                              │  get_pegasus_advice()       │             │
│  │                              │                             │             │
│  │                              │  Returns:                   │             │
│  │                              │  • advice: TRADE/SKIP/HOLD  │             │
│  │                              │  • confidence: 0-100%       │             │
│  │                              │  • win_probability: 0-100%  │             │
│  │                              │  • suggested_strikes        │             │
│  │                              │  • reasoning                │             │
│  │                              └──────────────┬──────────────┘             │
│  │                                             │                            │
│  │                                             ▼                            │
│  │                              ┌─────────────────────────────┐             │
│  │                              │    APPROVAL GATES            │             │
│  │                              │                             │             │
│  │                              │  1. Advice = TRADE_FULL     │             │
│  │                              │     or TRADE_REDUCED?       │             │
│  │                              │                             │             │
│  │                              │  2. Confidence ≥ 60%?       │             │
│  │                              │                             │             │
│  │                              │  3. Win Prob ≥ 55%?         │             │
│  │                              │                             │             │
│  │                              │  4. Max Positions < 3?      │             │
│  │                              └──────────────┬──────────────┘             │
│  │                                             │                            │
│  │                              ALL PASS?      │                            │
│  │                                │            │                            │
│  │                    NO ◀────────┘            │                            │
│  │                    │                       YES                           │
│  │         Log: "Oracle says SKIP"             │                            │
│  │         or "Confidence 45% < 60%"           ▼                            │
│  │                              ┌─────────────────────────────┐             │
│  │                              │     EXECUTE IC TRADE        │             │
│  │                              │                             │             │
│  │                              │  • Select strikes (~10Δ)    │             │
│  │                              │  • Size: $5,000 max risk    │             │
│  │                              │  • Execute 4-leg order      │             │
│  │                              │  • Record to database       │             │
│  │                              │  • Log scan activity        │             │
│  │                              └─────────────────────────────┘             │
│  │                                                                          │
│  └──────────────────────────────────────────────────────────────────────────┘
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>

                  {/* PEGASUS Rules Reference */}
                  <div className="bg-orange-900/20 rounded-lg p-4 border border-orange-600/30 mb-4">
                    <h4 className="font-bold text-orange-400 mb-3">PEGASUS Trading Rules (Used by PROMETHEUS IC)</h4>
                    <div className="grid md:grid-cols-3 gap-4 text-sm">
                      <div className="bg-black/30 rounded-lg p-3">
                        <div className="font-medium text-white mb-2">Entry Rules</div>
                        <ul className="text-gray-300 space-y-1">
                          <li>• Trading hours: 8:35 AM - 2:30 PM CT</li>
                          <li>• VIX range: 12-35 (12-30 Mon/Fri)</li>
                          <li>• Max 3 open positions</li>
                          <li>• Oracle confidence ≥ 60%</li>
                          <li>• Win probability ≥ 55%</li>
                        </ul>
                      </div>
                      <div className="bg-black/30 rounded-lg p-3">
                        <div className="font-medium text-white mb-2">Strike Selection</div>
                        <ul className="text-gray-300 space-y-1">
                          <li>• Target delta: ~10 (both sides)</li>
                          <li>• SPX $25 spread width</li>
                          <li>• Round to nearest $5</li>
                          <li>• Priority: Oracle → GEX → Delta</li>
                          <li>• 0DTE or 1DTE expiration</li>
                        </ul>
                      </div>
                      <div className="bg-black/30 rounded-lg p-3">
                        <div className="font-medium text-white mb-2">Exit Rules</div>
                        <ul className="text-gray-300 space-y-1">
                          <li>• Profit target: 50% of credit</li>
                          <li>• Stop loss: 200% of credit</li>
                          <li>• Force exit: 10 min before close</li>
                          <li>• Expiration: Auto-settle (SPX)</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PART 4: ORACLE SCAN ACTIVITY FORMAT */}
                <div className="bg-gray-800 rounded-xl p-6 border border-green-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-green-600 rounded-lg flex items-center justify-center text-xl">4</span>
                    <span className="text-green-400">Oracle Scan Activity Display</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-green-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│  PROMETHEUS IC - ORACLE SCAN ACTIVITY LOG                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  TIME        SPX     VIX   ORACLE   CONF   WIN%   DECISION    REASON        │
│  ────────────────────────────────────────────────────────────────────────── │
│  10:35:22   5982   18.4   TRADE    72%    68%    ✅ OPENED    IC 5945/6020  │
│  10:20:15   5978   18.6   TRADE    65%    62%    ⏸️ SKIP      Max positions │
│  10:05:08   5975   18.9   HOLD     52%    55%    ⏸️ SKIP      Conf < 60%    │
│  09:50:01   5972   19.1   SKIP     45%    48%    ⏸️ SKIP      Oracle: HOLD  │
│  09:35:44   5968   19.4   TRADE    78%    71%    ✅ OPENED    IC 5935/6010  │
│  09:20:37   5965   19.2   TRADE    71%    65%    ✅ OPENED    IC 5930/6005  │
│  09:05:30   5962   19.5   SKIP     42%    45%    ⏸️ SKIP      VIX spike     │
│  08:50:23   5960   20.1   N/A      --     --     ⏸️ SKIP      Pre-window    │
│                                                                             │
│  ────────────────────────────────────────────────────────────────────────── │
│  TODAY'S STATS:  8 scans | 3 trades | 5 skips | 37.5% trade rate           │
│                                                                             │
│  CLICK ROW FOR FULL ORACLE REASONING:                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  10:35:22 - TRADE_FULL Decision                                       │  │
│  │                                                                       │  │
│  │  Oracle says: "Strong IC conditions. VIX 18.4 in sweet spot.          │  │
│  │  Gamma regime POSITIVE = mean reversion favorable.                    │  │
│  │  Call wall at 6050, put wall at 5920 provide cushion.                 │  │
│  │  Day: Wednesday (best IC day historically)."                          │  │
│  │                                                                       │  │
│  │  Top Factors:                                                         │  │
│  │  1. vix_level: +15% (favorable range)                                 │  │
│  │  2. gex_regime: +12% (positive gamma)                                 │  │
│  │  3. day_of_week: +8% (mid-week)                                       │  │
│  │                                                                       │  │
│  │  Suggested Strikes: 5945P / 6020C (from Oracle)                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>
                </div>

                {/* PART 5: DAILY P&L BREAKDOWN */}
                <div className="bg-gray-800 rounded-xl p-6 border border-yellow-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-yellow-600 rounded-lg flex items-center justify-center text-xl">5</span>
                    <span className="text-yellow-400">Daily P&L Breakdown Format</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-yellow-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│  PROMETHEUS - DAILY P&L BREAKDOWN (Last 14 Days)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DATE         IC EARNED    BOX COST    NET P&L    CUMULATIVE    TRADES     │
│  ──────────────────────────────────────────────────────────────────────────│
│  2026-01-30     $425.00     -$12.50    +$412.50     $3,247.50      3       │
│  2026-01-29     $380.00     -$12.50    +$367.50     $2,835.00      2       │
│  2026-01-28    -$125.00     -$12.50    -$137.50     $2,467.50      2       │
│  2026-01-27     $290.00     -$12.50    +$277.50     $2,605.00      2       │
│  2026-01-24     $510.00     -$12.50    +$497.50     $2,327.50      3       │
│  2026-01-23     $445.00     -$12.50    +$432.50     $1,830.00      3       │
│  2026-01-22     $315.00     -$12.50    +$302.50     $1,397.50      2       │
│  ...                                                                        │
│  ──────────────────────────────────────────────────────────────────────────│
│                                                                             │
│  LEGEND:                                                                    │
│  IC EARNED = Premium collected from Iron Condor trades                      │
│  BOX COST  = Daily interest accrual on borrowed capital                     │
│  NET P&L   = IC Earned - Box Cost (what you actually made)                  │
│                                                                             │
│  ══════════════════════════════════════════════════════════════════════════│
│  BREAK-EVEN ANALYSIS:                                                       │
│  Daily Box Cost: $12.50  →  Need IC returns > $12.50/day to profit         │
│  Current Avg IC/Day: $377.14  →  Cost Efficiency: 30.2x                    │
│  ══════════════════════════════════════════════════════════════════════════│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>
                </div>

                {/* PART 6: RISK ALERTS */}
                <div className="bg-gray-800 rounded-xl p-6 border border-red-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-red-600 rounded-lg flex items-center justify-center text-xl">6</span>
                    <span className="text-red-400">Risk Alerts Display</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-red-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│  🚨 PROMETHEUS RISK ALERTS                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─ CRITICAL ─────────────────────────────────────────────────────────────┐ │
│  │ ⛔ BOX ROLL NEEDED: Position PROM-20241015 expires in 2 days!          │ │
│  │    Action: Roll to new expiration or close position                    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ WARNING ──────────────────────────────────────────────────────────────┐ │
│  │ ⚠️ IC NEAR STOP: Position IC-5945/6020 at 180% of credit              │ │
│  │    Current: $3.60 (entry: $2.00, stop: $4.00)                          │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ INFO ─────────────────────────────────────────────────────────────────┐ │
│  │ ℹ️ MARGIN UTILIZATION: 72% of available margin in use                  │ │
│  │    Consider reducing IC positions if approaching 85%                   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ALERT THRESHOLDS:                                                          │
│  ─────────────────                                                          │
│  Box Roll:  DTE ≤ 30 = Warning, DTE ≤ 7 = Critical                         │
│  IC Stop:   150% = Warning, 180% = Critical, 200% = Auto-close             │
│  Margin:    70% = Info, 85% = Warning, 95% = Critical                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>
                </div>

                {/* PART 7: DATA FLOW DIAGRAM */}
                <div className="bg-gray-800 rounded-xl p-6 border border-indigo-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center text-xl">7</span>
                    <span className="text-indigo-400">Complete Data Flow</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-indigo-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PROMETHEUS COMPLETE DATA FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │   TRADIER   │    │  FRED API   │    │ GEX CALC    │                     │
│  │ (Production)│    │ (Fed Funds) │    │ (Gamma)     │                     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                     │
│         │                  │                  │                            │
│         └──────────────────┼──────────────────┘                            │
│                            │                                               │
│                            ▼                                               │
│         ┌─────────────────────────────────────────────┐                    │
│         │              PROMETHEUS ENGINE              │                    │
│         │                                             │                    │
│         │  ┌───────────────┐   ┌───────────────────┐  │                    │
│         │  │ Box Spread    │   │ IC Signal         │  │                    │
│         │  │ Manager       │   │ Generator         │  │                    │
│         │  │               │   │                   │  │                    │
│         │  │ • Open/Close  │   │ • Uses Oracle     │  │                    │
│         │  │ • MTM Calc    │   │ • PEGASUS rules   │  │                    │
│         │  │ • Roll Logic  │   │ • Strike select   │  │                    │
│         │  └───────┬───────┘   └─────────┬─────────┘  │                    │
│         │          │                     │            │                    │
│         │          └──────────┬──────────┘            │                    │
│         │                     │                       │                    │
│         │                     ▼                       │                    │
│         │  ┌─────────────────────────────────────┐    │                    │
│         │  │         CAPITAL ALLOCATOR           │    │                    │
│         │  │                                     │    │                    │
│         │  │ Total Borrowed → Reserve (10%)      │    │                    │
│         │  │              → IC Trading (90%)     │    │                    │
│         │  └─────────────────────────────────────┘    │                    │
│         │                     │                       │                    │
│         └─────────────────────┼───────────────────────┘                    │
│                               │                                            │
│                               ▼                                            │
│         ┌─────────────────────────────────────────────┐                    │
│         │               POSTGRESQL DB                 │                    │
│         │                                             │                    │
│         │  Tables:                                    │                    │
│         │  • prometheus_box_positions (open boxes)    │                    │
│         │  • prometheus_box_closed (historical)       │                    │
│         │  • prometheus_ic_positions (open ICs)       │                    │
│         │  • prometheus_ic_closed (IC history)        │                    │
│         │  • prometheus_scan_activity (Oracle logs)   │                    │
│         │  • prometheus_equity_snapshots              │                    │
│         └─────────────────────────────────────────────┘                    │
│                               │                                            │
│                               ▼                                            │
│         ┌─────────────────────────────────────────────┐                    │
│         │              FRONTEND DASHBOARD             │                    │
│         │                                             │                    │
│         │  Tabs: Overview | Boxes | IC | Analytics    │                    │
│         │                                             │                    │
│         │  Refresh: 15-60 sec (configurable)          │                    │
│         └─────────────────────────────────────────────┘                    │
│                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>
                </div>

                {/* PART 8: DAILY TIMELINE */}
                <div className="bg-gray-800 rounded-xl p-6 border border-teal-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-teal-600 rounded-lg flex items-center justify-center text-xl">8</span>
                    <span className="text-teal-400">Daily Timeline (All Times CT)</span>
                  </h2>

                  {/* Timeline Table */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-700">
                          <th className="text-left py-2 px-3 text-gray-400">Time</th>
                          <th className="text-left py-2 px-3 text-gray-400">Event</th>
                          <th className="text-left py-2 px-3 text-gray-400">Description</th>
                        </tr>
                      </thead>
                      <tbody className="text-gray-300">
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3 font-mono text-yellow-400">8:00 AM</td>
                          <td className="py-2 px-3">System Startup</td>
                          <td className="py-2 px-3 text-gray-400">Connect to APIs, load positions, check rates</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3 font-mono text-green-400">8:30 AM</td>
                          <td className="py-2 px-3">Market Open</td>
                          <td className="py-2 px-3 text-gray-400">Begin box spread monitoring, IC trading preparation</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3 font-mono text-blue-400">8:35 AM</td>
                          <td className="py-2 px-3">IC Trading Starts</td>
                          <td className="py-2 px-3 text-gray-400">First Oracle check, begin 5-15 min scan cycle</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3 font-mono text-orange-400">9:30 AM</td>
                          <td className="py-2 px-3">Box Position Check</td>
                          <td className="py-2 px-3 text-gray-400">Daily box MTM update, roll decision evaluation</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3 font-mono text-purple-400">Ongoing</td>
                          <td className="py-2 px-3">IC Scan Cycle</td>
                          <td className="py-2 px-3 text-gray-400">Every 5-15 min: Oracle check, trade if approved</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3 font-mono text-blue-400">2:30 PM</td>
                          <td className="py-2 px-3">IC Entry Stops</td>
                          <td className="py-2 px-3 text-gray-400">No new IC trades, only manage existing</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3 font-mono text-red-400">2:50 PM</td>
                          <td className="py-2 px-3">Force Exit</td>
                          <td className="py-2 px-3 text-gray-400">Close all IC positions 10 min before market close</td>
                        </tr>
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3 font-mono text-gray-400">3:00 PM</td>
                          <td className="py-2 px-3">Market Close</td>
                          <td className="py-2 px-3 text-gray-400">0DTE ICs auto-settle (SPX cash settled)</td>
                        </tr>
                        <tr>
                          <td className="py-2 px-3 font-mono text-gray-500">After Hours</td>
                          <td className="py-2 px-3">Daily Summary</td>
                          <td className="py-2 px-3 text-gray-400">Update equity snapshots, log day results</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* PART 9: MTM CALCULATION FLOW */}
                <div className="bg-gray-800 rounded-xl p-6 border border-cyan-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-cyan-600 rounded-lg flex items-center justify-center text-xl">9</span>
                    <span className="text-cyan-400">Mark-to-Market (MTM) Calculation</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-cyan-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BOX SPREAD MTM CALCULATION                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: FETCH CURRENT PRICES (Tradier Production API)                      │
│  ═══════════════════════════════════════════════════════                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  For each leg of the box spread:                                    │    │
│  │                                                                     │    │
│  │  Long Call (K1):   Bid/Ask → Mid Price                             │    │
│  │  Short Call (K2):  Bid/Ask → Mid Price                             │    │
│  │  Long Put (K2):    Bid/Ask → Mid Price                             │    │
│  │  Short Put (K1):   Bid/Ask → Mid Price                             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  STEP 2: CALCULATE CURRENT BOX VALUE                                        │
│  ═══════════════════════════════════════════════════════                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                     │    │
│  │  Box Value = (Long Call - Short Call) + (Long Put - Short Put)     │    │
│  │            = Bull Call Spread + Bear Put Spread                    │    │
│  │                                                                     │    │
│  │  Example:                                                          │    │
│  │  Long Call 6000:  $52.30    Short Call 6050: $28.40               │    │
│  │  Long Put 6050:   $31.20    Short Put 6000:  $18.50               │    │
│  │                                                                     │    │
│  │  Box Value = (52.30 - 28.40) + (31.20 - 18.50) = $36.60/contract  │    │
│  │  10 contracts × $36.60 × 100 = $36,600 current value              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  STEP 3: CALCULATE UNREALIZED P&L                                           │
│  ═══════════════════════════════════════════════════════                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                     │    │
│  │  Entry Credit:     $49,250  (what we received when opening)        │    │
│  │  Current Value:    $36,600  (cost to close now)                    │    │
│  │  Interest Accrued: $1,250   (time cost so far)                     │    │
│  │                                                                     │    │
│  │  Unrealized P&L = Entry Credit - Current Value - Interest Accrued  │    │
│  │                 = $49,250 - $36,600 - $1,250                       │    │
│  │                 = $11,400 profit (if closed now)                   │    │
│  │                                                                     │    │
│  │  Note: Box approaches strike width ($50,000) at expiration        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>

                  {/* Explanation */}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="bg-cyan-900/20 rounded-lg p-4 border border-cyan-600/30">
                      <h4 className="font-bold text-cyan-400 mb-2">Why MTM Matters</h4>
                      <ul className="text-sm text-gray-300 space-y-2">
                        <li>• Shows real-time position value</li>
                        <li>• Helps decide early exit vs hold to expiration</li>
                        <li>• Tracks borrowing cost efficiency</li>
                        <li>• Alerts if position moves against us</li>
                      </ul>
                    </div>
                    <div className="bg-purple-900/20 rounded-lg p-4 border border-purple-600/30">
                      <h4 className="font-bold text-purple-400 mb-2">Update Frequency</h4>
                      <ul className="text-sm text-gray-300 space-y-2">
                        <li><span className="text-yellow-400">Dashboard:</span> Every 30 seconds</li>
                        <li><span className="text-yellow-400">Database:</span> Every 5 minutes</li>
                        <li><span className="text-yellow-400">Equity Snapshot:</span> Hourly</li>
                        <li><span className="text-yellow-400">EOD Reconciliation:</span> 3:15 PM CT</li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* PART 10: BOX ROLL EXECUTION */}
                <div className="bg-gray-800 rounded-xl p-6 border border-pink-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-pink-600 rounded-lg flex items-center justify-center text-xl">10</span>
                    <span className="text-pink-400">Box Spread Roll Execution</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-pink-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BOX SPREAD ROLL PROCESS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  TRIGGER: DTE ≤ 30 days on existing position                               │
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  CHECK CURRENT  │                                                        │
│  │  POSITION       │                                                        │
│  │                 │                                                        │
│  │  DTE: 28 days   │─── DTE > 30? ──▶ NO ROLL NEEDED                       │
│  │  Strikes: 6000/ │                                                        │
│  │           6050  │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│          YES (DTE ≤ 30)                                                     │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐     ┌─────────────────────────────────────────────┐    │
│  │  FIND NEW       │     │  NEW EXPIRATION CRITERIA:                   │    │
│  │  EXPIRATION     │────▶│                                             │    │
│  │                 │     │  • Target DTE: 90-365 days                  │    │
│  └─────────────────┘     │  • Same strike width (50 pts)               │    │
│                          │  • Liquid expiration (monthly preferred)    │    │
│                          │  • Check implied rate vs Fed Funds          │    │
│                          └─────────────────────────────────────────────┘    │
│                                        │                                    │
│                                        ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  RATE COMPARISON                                                    │    │
│  │                                                                     │    │
│  │  Current Fed Funds:     4.50%                                      │    │
│  │  Margin Rate:           7.25%                                      │    │
│  │  New Box Implied Rate:  4.85%                                      │    │
│  │                                                                     │    │
│  │  ✓ Box Rate < Margin Rate? YES → PROCEED WITH ROLL                 │    │
│  │  ✗ Box Rate ≥ Margin Rate? → ALERT, CONSIDER ALTERNATIVES          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                        │                                    │
│                                        ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  EXECUTE ROLL (Two-Step Process)                                    │    │
│  │                                                                     │    │
│  │  STEP 1: Close old box (4-leg order)                               │    │
│  │  ────────────────────────────────────                               │    │
│  │  • Sell to close Long Call K1                                      │    │
│  │  • Buy to close Short Call K2                                      │    │
│  │  • Sell to close Long Put K2                                       │    │
│  │  • Buy to close Short Put K1                                       │    │
│  │  • DEBIT: ~$49,800 (close to strike width near expiry)             │    │
│  │                                                                     │    │
│  │  STEP 2: Open new box (4-leg order)                                │    │
│  │  ────────────────────────────────────                               │    │
│  │  • Buy to open Long Call K1 (new strikes)                          │    │
│  │  • Sell to open Short Call K2                                      │    │
│  │  • Buy to open Long Put K2                                         │    │
│  │  • Sell to open Short Put K1                                       │    │
│  │  • CREDIT: ~$49,250 (new borrowed amount)                          │    │
│  │                                                                     │    │
│  │  NET ROLL COST: ~$550 (represents interest paid)                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>

                  {/* Explanation */}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="bg-pink-900/20 rounded-lg p-4 border border-pink-600/30">
                      <h4 className="font-bold text-pink-400 mb-2">Roll Timing Strategy</h4>
                      <ul className="text-sm text-gray-300 space-y-2">
                        <li>• Roll at 30 DTE for optimal liquidity</li>
                        <li>• Avoid rolling during high VIX spikes</li>
                        <li>• Best execution: 10:00 AM - 2:00 PM CT</li>
                        <li>• Never roll on expiration day</li>
                      </ul>
                    </div>
                    <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-600/30">
                      <h4 className="font-bold text-blue-400 mb-2">Roll Cost Tracking</h4>
                      <ul className="text-sm text-gray-300 space-y-2">
                        <li><span className="text-yellow-400">Debit to close:</span> Near strike width</li>
                        <li><span className="text-yellow-400">Credit to open:</span> Discounted by rate</li>
                        <li><span className="text-yellow-400">Net cost:</span> ≈ Accrued interest</li>
                        <li><span className="text-yellow-400">Logged:</span> prometheus_roll_history</li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* PART 11: IC POSITION EXIT FLOW */}
                <div className="bg-gray-800 rounded-xl p-6 border border-lime-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-lime-600 rounded-lg flex items-center justify-center text-xl">11</span>
                    <span className="text-lime-400">IC Position Exit Flow</span>
                  </h2>

                  {/* ASCII Wireframe */}
                  <div className="bg-black rounded-lg p-4 font-mono text-xs overflow-x-auto mb-6 flex justify-center">
                    <pre className="text-lime-400 whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────────────────┐
│                    IC POSITION EXIT DECISION TREE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  MONITORING LOOP (Every 1-2 Minutes)                                        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  FETCH CURRENT IC VALUE                                             │    │
│  │                                                                     │    │
│  │  Entry Credit:    $2.00/contract                                   │    │
│  │  Current Value:   $X.XX/contract (cost to close)                   │    │
│  │  P&L %:           ((Entry - Current) / Entry) × 100                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      EXIT DECISION CHECKS                           │    │
│  │                                                                     │    │
│  │  ┌─────────────────┐                                               │    │
│  │  │ PROFIT TARGET   │  Current ≤ 50% of Entry?                      │    │
│  │  │ (50% of credit) │  $2.00 entry → exit at ≤ $1.00               │    │
│  │  └────────┬────────┘                                               │    │
│  │           │ YES ──────────────────────────────▶ ✅ CLOSE: PROFIT   │    │
│  │           │ NO                                                      │    │
│  │           ▼                                                         │    │
│  │  ┌─────────────────┐                                               │    │
│  │  │ STOP LOSS       │  Current ≥ 200% of Entry?                     │    │
│  │  │ (200% of credit)│  $2.00 entry → exit at ≥ $4.00               │    │
│  │  └────────┬────────┘                                               │    │
│  │           │ YES ──────────────────────────────▶ ❌ CLOSE: STOP     │    │
│  │           │ NO                                                      │    │
│  │           ▼                                                         │    │
│  │  ┌─────────────────┐                                               │    │
│  │  │ FORCE EXIT      │  Time ≥ 2:50 PM CT?                           │    │
│  │  │ (10 min to close)│  (Must exit before 3:00 PM)                  │    │
│  │  └────────┬────────┘                                               │    │
│  │           │ YES ──────────────────────────────▶ 🕐 CLOSE: TIME     │    │
│  │           │ NO                                                      │    │
│  │           ▼                                                         │    │
│  │  ┌─────────────────┐                                               │    │
│  │  │ EXPIRATION      │  Is this 0DTE at 3:00 PM?                     │    │
│  │  │ (SPX auto-settle)│  SPX is cash-settled                         │    │
│  │  └────────┬────────┘                                               │    │
│  │           │ YES ──────────────────────────────▶ 📋 SETTLE: EXPIRY  │    │
│  │           │ NO                                                      │    │
│  │           ▼                                                         │    │
│  │       CONTINUE HOLDING                                              │    │
│  │       (Check again in 1-2 min)                                      │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  EXIT EXECUTION:                                                            │
│  ═══════════════                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  4-leg closing order:                                               │    │
│  │  • Buy to close Short Put                                          │    │
│  │  • Sell to close Long Put                                          │    │
│  │  • Buy to close Short Call                                         │    │
│  │  • Sell to close Long Call                                         │    │
│  │                                                                     │    │
│  │  Order Type: MARKET (for stops/force) or LIMIT (for profit)        │    │
│  │  Record: Close time, P&L, reason → prometheus_ic_closed            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
`}</pre>
                  </div>

                  {/* Exit Statistics Reference */}
                  <div className="bg-lime-900/20 rounded-lg p-4 border border-lime-600/30">
                    <h4 className="font-bold text-lime-400 mb-3">Exit Statistics (Expected Distribution)</h4>
                    <div className="grid md:grid-cols-4 gap-4 text-sm">
                      <div className="text-center">
                        <div className="text-2xl font-bold text-green-400">~60%</div>
                        <div className="text-gray-400">Profit Target</div>
                        <div className="text-xs text-gray-500">Best outcome</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-yellow-400">~20%</div>
                        <div className="text-gray-400">Expiration</div>
                        <div className="text-xs text-gray-500">Full premium kept</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-orange-400">~10%</div>
                        <div className="text-gray-400">Time Exit</div>
                        <div className="text-xs text-gray-500">Partial profit</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-red-400">~10%</div>
                        <div className="text-gray-400">Stop Loss</div>
                        <div className="text-xs text-gray-500">Managed risk</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* KEY CONFIG VALUES REFERENCE */}
                <div className="bg-gradient-to-r from-gray-800 to-gray-900 rounded-xl p-6 border border-orange-500/20">
                  <h2 className="text-2xl font-bold mb-6 text-orange-400">Key Configuration Values</h2>

                  <div className="grid md:grid-cols-2 gap-6">
                    {/* Box Spread Config */}
                    <div className="bg-black/30 rounded-lg p-4 border border-blue-700/30">
                      <h4 className="font-bold text-blue-400 mb-3">Box Spread Settings</h4>
                      <div className="space-y-2 text-sm font-mono">
                        <div className="flex justify-between">
                          <span className="text-gray-400">strike_width</span>
                          <span className="text-white">50 points</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">target_dte_min</span>
                          <span className="text-white">90 days</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">target_dte_max</span>
                          <span className="text-white">365 days</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">min_dte_to_hold</span>
                          <span className="text-white">30 days (roll threshold)</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">reserve_pct</span>
                          <span className="text-white">10%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">max_implied_rate</span>
                          <span className="text-white">6.0%</span>
                        </div>
                      </div>
                    </div>

                    {/* IC Config */}
                    <div className="bg-black/30 rounded-lg p-4 border border-orange-700/30">
                      <h4 className="font-bold text-orange-400 mb-3">IC Trading Settings (PEGASUS Rules)</h4>
                      <div className="space-y-2 text-sm font-mono">
                        <div className="flex justify-between">
                          <span className="text-gray-400">min_capital_per_trade</span>
                          <span className="text-white">$5,000</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">max_positions</span>
                          <span className="text-white">3</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">spread_width</span>
                          <span className="text-white">$25</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">profit_target</span>
                          <span className="text-white">50%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">stop_loss</span>
                          <span className="text-white">200%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">min_oracle_confidence</span>
                          <span className="text-white">60%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">min_win_probability</span>
                          <span className="text-white">55%</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Print/Export Note */}
                <div className="bg-gray-800/50 rounded-lg p-4 text-center text-sm text-gray-400 border border-gray-700">
                  <p>This documentation is designed for on-screen reference. Bookmark this tab for quick access during trading hours.</p>
                </div>
              </div>
            )}
          </>
        )}
            </div>
          </div>
        </div>
      </main>
    </>
  )
}
