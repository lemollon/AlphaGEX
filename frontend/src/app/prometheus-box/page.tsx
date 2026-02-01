'use client'

import { useState } from 'react'
import useSWR from 'swr'
import Navigation from '@/components/Navigation'

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
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'ic-trading' | 'analytics' | 'education' | 'howItWorks'>('overview')
  const [equityView, setEquityView] = useState<'historical' | 'intraday'>('historical')

  // Data fetching - Box Spread
  const { data: status, error: statusError } = useSWR('/api/prometheus-box/status', fetcher, { refreshInterval: 30000 })
  const { data: positions } = useSWR('/api/prometheus-box/positions', fetcher, { refreshInterval: 30000 })
  const { data: rateAnalysis } = useSWR('/api/prometheus-box/analytics/rates', fetcher, { refreshInterval: 60000 })
  const { data: capitalFlow } = useSWR('/api/prometheus-box/analytics/capital-flow', fetcher, { refreshInterval: 30000 })
  const { data: equityCurve } = useSWR('/api/prometheus-box/equity-curve', fetcher, { refreshInterval: 60000 })
  const { data: intradayEquity } = useSWR('/api/prometheus-box/equity-curve/intraday', fetcher, { refreshInterval: 30000 })
  const { data: interestRates } = useSWR('/api/prometheus-box/analytics/interest-rates', fetcher, { refreshInterval: 300000 })

  // IC Trading data - All required endpoints per STANDARDS.md
  const { data: icStatus } = useSWR('/api/prometheus-box/ic/status', fetcher, { refreshInterval: 30000 })
  const { data: icPositions } = useSWR('/api/prometheus-box/ic/positions', fetcher, { refreshInterval: 15000 })
  const { data: icPerformance } = useSWR('/api/prometheus-box/ic/performance', fetcher, { refreshInterval: 30000 })
  const { data: icClosedTrades } = useSWR('/api/prometheus-box/ic/closed-trades?limit=20', fetcher, { refreshInterval: 60000 })
  const { data: icEquityCurve } = useSWR('/api/prometheus-box/ic/equity-curve', fetcher, { refreshInterval: 60000 })
  const { data: icIntradayEquity } = useSWR('/api/prometheus-box/ic/equity-curve/intraday', fetcher, { refreshInterval: 30000 })
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

  // Calculate derived metrics for Analytics
  const totalBorrowed = status?.total_borrowed || 0
  const totalICReturns = status?.total_ic_returns || 0
  const totalBorrowingCosts = status?.total_borrowing_costs || 0
  const netPnL = status?.net_unrealized_pnl || 0
  const returnOnBorrowed = totalBorrowed > 0 ? (netPnL / totalBorrowed) * 100 : 0
  const costEfficiency = totalBorrowingCosts > 0 ? (totalICReturns / totalBorrowingCosts) : 0

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <Navigation />

      {/* Header */}
      <div className="bg-gradient-to-r from-orange-900 via-red-900 to-orange-900 p-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-4">
            <div className="text-5xl">🔥</div>
            <div>
              <h1 className="text-3xl font-bold">PROMETHEUS</h1>
              <p className="text-orange-300">Box Spread Synthetic Borrowing</p>
            </div>
          </div>

          {/* Quick Stats */}
          {status && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-6">
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">Status</div>
                <div className={`text-xl font-bold ${status.system_status === 'active' ? 'text-green-400' : 'text-yellow-400'}`}>
                  {status.system_status?.toUpperCase() || 'PAPER'}
                </div>
              </div>
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">Total Borrowed</div>
                <div className="text-xl font-bold text-blue-400">{formatCurrency(totalBorrowed)}</div>
              </div>
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">IC Returns</div>
                <div className="text-xl font-bold text-green-400">{formatCurrency(totalICReturns)}</div>
              </div>
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">Borrowing Costs</div>
                <div className="text-xl font-bold text-red-400">{formatCurrency(totalBorrowingCosts)}</div>
              </div>
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">Net P&L</div>
                <div className={`text-xl font-bold ${netPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {formatCurrency(netPnL)}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-1">
            {[
              { key: 'overview', label: 'Overview' },
              { key: 'positions', label: 'Box Spreads' },
              { key: 'ic-trading', label: 'IC Trading' },
              { key: 'analytics', label: 'Analytics' },
              { key: 'education', label: 'Education' },
              { key: 'howItWorks', label: 'How It Works' },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key as any)}
                className={`px-6 py-3 font-medium transition-colors ${
                  activeTab === tab.key ? 'bg-orange-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto p-6">
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
                          IC: <span className="text-green-400">+{formatCurrency(totalICReturns)}</span>
                        </div>
                        <div className="text-xs text-gray-500">
                          Cost: <span className="text-red-400">-{formatCurrency(totalBorrowingCosts)}</span>
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
                  </h2>
                  <div className="grid md:grid-cols-4 gap-4">
                    <div className="bg-gradient-to-br from-green-900/30 to-gray-800 rounded-lg p-4 border border-green-700/30">
                      <div className="text-xs text-gray-400 mb-1">Today&apos;s IC P&L</div>
                      <div className={`text-2xl font-bold ${(icPerformance?.performance?.today?.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(icPerformance?.performance?.today?.pnl || 0)}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {icPerformance?.performance?.today?.trades || 0} trades closed today
                      </div>
                    </div>
                    <div className="bg-gradient-to-br from-orange-900/30 to-gray-800 rounded-lg p-4 border border-orange-700/30">
                      <div className="text-xs text-gray-400 mb-1">IC Positions Open</div>
                      <div className="text-2xl font-bold text-orange-400">
                        {icStatus?.status?.open_positions || 0}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Unrealized: {formatCurrency(icStatus?.status?.total_unrealized_pnl || 0)}
                      </div>
                    </div>
                    <div className="bg-gradient-to-br from-blue-900/30 to-gray-800 rounded-lg p-4 border border-blue-700/30">
                      <div className="text-xs text-gray-400 mb-1">Trade Activity</div>
                      <div className="text-2xl font-bold text-blue-400">
                        {icStatus?.status?.daily_trades || 0} / {icStatus?.status?.max_daily_trades || 5}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Trades today / max allowed
                      </div>
                    </div>
                    <div className="bg-gradient-to-br from-purple-900/30 to-gray-800 rounded-lg p-4 border border-purple-700/30">
                      <div className="text-xs text-gray-400 mb-1">Borrowing Cost Today</div>
                      <div className="text-2xl font-bold text-purple-400">
                        {positions?.positions?.length > 0
                          ? formatCurrency(positions.positions.reduce((sum: number, p: Position) => sum + (p.daily_cost || 0), 0))
                          : formatCurrency(0)}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Daily interest accrual
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
                            <span className="text-red-400 font-bold text-xl">-{formatCurrency(totalBorrowingCosts)}</span>
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
                                <div className="mt-4 pt-4 border-t border-gray-700">
                                  <div className="text-xs text-gray-500 mb-2">Strike Range</div>
                                  <div className="flex items-center gap-2">
                                    <span className="text-2xl font-bold text-blue-400">${pos.lower_strike}</span>
                                    <span className="text-gray-500">→</span>
                                    <span className="text-2xl font-bold text-purple-400">${pos.upper_strike}</span>
                                    <span className="ml-2 text-sm text-gray-400">({pos.strike_width}pt width)</span>
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
                      icStatus?.status?.enabled ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'
                    }`}>
                      {icStatus?.status?.enabled ? 'ACTIVE' : 'STANDBY'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-400 mb-4">
                    Trades SPX 0DTE Iron Condors using capital from box spread borrowing.
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

                {/* System Performance Summary */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">System Performance Summary</h2>
                  <div className="grid md:grid-cols-4 gap-4">
                    <div className="bg-gradient-to-br from-blue-900/40 to-blue-900/20 rounded-lg p-4 text-center border border-blue-700/30">
                      <div className="text-xs text-blue-300 mb-1">Total Capital Working</div>
                      <div className="text-2xl font-bold text-white">{formatCurrency(totalBorrowed)}</div>
                    </div>
                    <div className="bg-gradient-to-br from-green-900/40 to-green-900/20 rounded-lg p-4 text-center border border-green-700/30">
                      <div className="text-xs text-green-300 mb-1">Gross IC Returns</div>
                      <div className="text-2xl font-bold text-green-400">{formatCurrency(totalICReturns)}</div>
                    </div>
                    <div className="bg-gradient-to-br from-red-900/40 to-red-900/20 rounded-lg p-4 text-center border border-red-700/30">
                      <div className="text-xs text-red-300 mb-1">Borrowing Costs</div>
                      <div className="text-2xl font-bold text-red-400">{formatCurrency(totalBorrowingCosts)}</div>
                    </div>
                    <div className={`bg-gradient-to-br ${netPnL >= 0 ? 'from-emerald-900/40 to-emerald-900/20 border-emerald-700/30' : 'from-rose-900/40 to-rose-900/20 border-rose-700/30'} rounded-lg p-4 text-center border`}>
                      <div className={`text-xs ${netPnL >= 0 ? 'text-emerald-300' : 'text-rose-300'} mb-1`}>Net Profit</div>
                      <div className={`text-2xl font-bold ${netPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{formatCurrency(netPnL)}</div>
                    </div>
                  </div>
                  {/* ROI bar */}
                  {totalBorrowed > 0 && (
                    <div className="mt-4 pt-4 border-t border-gray-700">
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-400">Return on Borrowed Capital</span>
                        <span className={`font-bold ${returnOnBorrowed >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {formatPct(returnOnBorrowed)}
                        </span>
                      </div>
                      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all ${returnOnBorrowed >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                          style={{ width: `${Math.min(100, Math.abs(returnOnBorrowed) * 10)}%` }}
                        />
                      </div>
                    </div>
                  )}
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
                            {/* Position Header */}
                            <div className="flex justify-between items-start mb-4 pb-3 border-b border-gray-700">
                              <div>
                                <div className="text-lg font-bold text-white">
                                  {pos.ticker} {pos.lower_strike}/{pos.upper_strike}
                                  <span className="text-gray-400 font-normal ml-2">(${pos.strike_width} width)</span>
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
                      {reconciliation.risk_alerts?.count > 0 && (
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
                        {formatCurrency(totalBorrowingCosts)}
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
                                <div>{pos.ticker}</div>
                                <div className="text-sm text-gray-400">{pos.lower_strike}/{pos.upper_strike}</div>
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

                {/* Combined Performance - The Key Metric */}
                <div className="bg-gray-800 rounded-lg p-6 border-2 border-orange-500/30">
                  <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                    <span>Combined Performance</span>
                    <span className="text-sm font-normal text-gray-400">(Are IC returns &gt; borrowing costs?)</span>
                  </h3>
                  <div className="grid md:grid-cols-4 gap-4 mb-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Total Borrowed</div>
                      <div className="text-xl font-bold text-blue-400">
                        {formatCurrency(combinedPerformance?.summary?.box_spread?.total_borrowed || totalBorrowed || 0)}
                      </div>
                      <div className="text-xs text-gray-500">{positions?.positions?.length || 0} box spreads</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Borrowing Cost</div>
                      <div className="text-xl font-bold text-red-400">
                        -{formatCurrency(combinedPerformance?.summary?.box_spread?.total_borrowing_cost || totalBorrowingCosts || 0)}
                      </div>
                      <div className="text-xs text-gray-500">
                        {formatCurrency((totalBorrowed * (rateAnalysis?.box_implied_rate || 4.0) / 100) / 365)}/day
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">IC Returns (Realized)</div>
                      <div className="text-xl font-bold text-green-400">
                        +{formatCurrency(combinedPerformance?.summary?.ic_trading?.total_realized_pnl || icPerformance?.performance?.closed_trades?.total_pnl || 0)}
                      </div>
                      <div className="text-xs text-gray-500">
                        +{formatCurrency(icStatus?.status?.total_unrealized_pnl || 0)} unrealized
                      </div>
                    </div>
                    <div className={`rounded-lg p-4 ${
                      (combinedPerformance?.summary?.net_profit || netPnL || 0) >= 0
                        ? 'bg-green-500/20 border border-green-500/50'
                        : 'bg-red-500/20 border border-red-500/50'
                    }`}>
                      <div className="text-xs text-gray-300 mb-1">NET PROFIT</div>
                      <div className={`text-2xl font-bold ${(combinedPerformance?.summary?.net_profit || netPnL || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(combinedPerformance?.summary?.net_profit || netPnL || 0)}
                      </div>
                    </div>
                  </div>

                  {/* Break-Even Analysis */}
                  {totalBorrowed > 0 && (
                    <div className="bg-black/30 rounded-lg p-4 border border-gray-600">
                      <h4 className="text-sm font-bold text-gray-300 mb-3">📊 BREAK-EVEN ANALYSIS</h4>
                      <div className="grid md:grid-cols-3 gap-4 text-sm">
                        <div>
                          <div className="text-xs text-gray-400">Monthly Break-Even</div>
                          <div className="text-lg font-bold text-yellow-400">
                            {formatCurrency((totalBorrowed * (rateAnalysis?.box_implied_rate || 4.0) / 100) / 12)}
                          </div>
                          <div className="text-xs text-gray-500">IC returns needed to cover borrowing</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">Actual Monthly IC Return</div>
                          <div className={`text-lg font-bold ${(icPerformance?.performance?.today?.pnl || 0) * 30 > (totalBorrowed * (rateAnalysis?.box_implied_rate || 4.0) / 100) / 12 ? 'text-green-400' : 'text-red-400'}`}>
                            {formatCurrency((icPerformance?.performance?.closed_trades?.total_pnl || 0) / Math.max(1, Math.ceil((Date.now() - new Date(positions?.positions?.[0]?.open_time || Date.now()).getTime()) / (30 * 24 * 60 * 60 * 1000))))}
                          </div>
                          <div className="text-xs text-gray-500">Average monthly performance</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">Cost Efficiency</div>
                          <div className={`text-lg font-bold ${costEfficiency > 1 ? 'text-green-400' : 'text-red-400'}`}>
                            {costEfficiency.toFixed(1)}x
                          </div>
                          <div className="text-xs text-gray-500">
                            {costEfficiency > 1 ? `IC returns are ${costEfficiency.toFixed(1)}x borrowing costs` : 'Below break-even'}
                          </div>
                        </div>
                      </div>
                      <div className="mt-3 pt-3 border-t border-gray-600">
                        <div className={`text-sm font-medium ${costEfficiency > 1 ? 'text-green-400' : 'text-yellow-400'}`}>
                          {costEfficiency > 1.5
                            ? '✅ PROFITABLE: IC returns significantly exceed borrowing costs'
                            : costEfficiency > 1
                              ? '✓ PROFITABLE: IC returns exceed borrowing costs'
                              : '⚠️ BELOW BREAK-EVEN: IC returns not covering borrowing costs yet'}
                        </div>
                      </div>
                    </div>
                  )}
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

                {/* IC Intraday Equity - per STANDARDS.md */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">IC Intraday Equity ({icIntradayEquity?.date || 'Today'})</h3>
                  {icIntradayEquity?.snapshots?.length > 0 ? (
                    <div className="space-y-4">
                      <div className="grid md:grid-cols-4 gap-4">
                        <div className="bg-gray-700/50 rounded-lg p-3">
                          <div className="text-xs text-gray-400">Market Open</div>
                          <div className="text-lg font-bold text-blue-400">
                            {formatCurrency(icIntradayEquity.snapshots[0]?.total_equity || 0)}
                          </div>
                        </div>
                        <div className="bg-gray-700/50 rounded-lg p-3">
                          <div className="text-xs text-gray-400">Current</div>
                          <div className="text-lg font-bold">
                            {formatCurrency(icIntradayEquity.snapshots[icIntradayEquity.snapshots.length - 1]?.total_equity || 0)}
                          </div>
                        </div>
                        <div className="bg-gray-700/50 rounded-lg p-3">
                          <div className="text-xs text-gray-400">Day Change</div>
                          <div className={`text-lg font-bold ${
                            (icIntradayEquity.snapshots[icIntradayEquity.snapshots.length - 1]?.total_equity || 0) -
                            (icIntradayEquity.snapshots[0]?.total_equity || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {formatCurrency(
                              (icIntradayEquity.snapshots[icIntradayEquity.snapshots.length - 1]?.total_equity || 0) -
                              (icIntradayEquity.snapshots[0]?.total_equity || 0)
                            )}
                          </div>
                        </div>
                        <div className="bg-gray-700/50 rounded-lg p-3">
                          <div className="text-xs text-gray-400">Snapshots</div>
                          <div className="text-lg font-bold text-blue-400">{icIntradayEquity.count || 0}</div>
                        </div>
                      </div>
                      <div className="overflow-x-auto max-h-40">
                        <table className="w-full text-xs">
                          <thead className="sticky top-0 bg-gray-800">
                            <tr className="text-gray-400 border-b border-gray-700">
                              <th className="text-left py-1 px-2">Time</th>
                              <th className="text-right py-1 px-2">Equity</th>
                              <th className="text-right py-1 px-2">Unrealized</th>
                              <th className="text-right py-1 px-2">Positions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {icIntradayEquity.snapshots.slice(-10).map((snap: any, idx: number) => (
                              <tr key={idx} className="border-b border-gray-700/30">
                                <td className="py-1 px-2">{new Date(snap.time).toLocaleTimeString()}</td>
                                <td className="py-1 px-2 text-right">{formatCurrency(snap.total_equity)}</td>
                                <td className={`py-1 px-2 text-right ${snap.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatCurrency(snap.unrealized_pnl)}
                                </td>
                                <td className="py-1 px-2 text-right">{snap.open_positions}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 text-center text-gray-400 text-sm">
                      <p>No intraday snapshots yet. Data appears during market hours.</p>
                    </div>
                  )}
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
                      <div className="text-2xl font-bold text-red-400">{formatCurrency(totalBorrowingCosts)}</div>
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

                {/* Equity Curve - Historical & Intraday */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold">Equity Curve</h2>
                    <div className="flex bg-gray-700 rounded-lg p-1">
                      <button
                        onClick={() => setEquityView('historical')}
                        className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                          equityView === 'historical' ? 'bg-orange-600 text-white' : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Historical
                      </button>
                      <button
                        onClick={() => setEquityView('intraday')}
                        className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                          equityView === 'intraday' ? 'bg-orange-600 text-white' : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Intraday
                      </button>
                    </div>
                  </div>

                  {/* Historical View */}
                  {equityView === 'historical' && (
                    <>
                      {equityCurve?.equity_curve && equityCurve.equity_curve.length > 0 ? (
                        <div>
                          <div className="flex justify-between items-center text-sm text-gray-400 mb-4">
                            <span>Starting: {formatCurrency(equityCurve.starting_capital)}</span>
                            <span>Current: {formatCurrency(equityCurve.equity_curve[equityCurve.equity_curve.length - 1]?.equity || equityCurve.starting_capital)}</span>
                          </div>
                          <div className="bg-black/30 rounded-lg p-4 mb-4">
                            <div className="h-48 relative">
                              {(() => {
                                const data = equityCurve.equity_curve.slice(-30)
                                if (data.length < 2) return <div className="text-center text-gray-500 pt-20">Insufficient data</div>
                                const values = data.map((d: any) => d.equity)
                                const min = Math.min(...values)
                                const max = Math.max(...values)
                                const range = max - min || 1
                                return (
                                  <svg className="w-full h-full" viewBox="0 0 400 150" preserveAspectRatio="none">
                                    <line x1="0" y1="75" x2="400" y2="75" stroke="#374151" strokeWidth="0.5" />
                                    <polyline fill="none" stroke="#22c55e" strokeWidth="2"
                                      points={data.map((d: any, i: number) => {
                                        const x = (i / (data.length - 1)) * 400
                                        const y = 150 - ((d.equity - min) / range) * 140 - 5
                                        return `${x},${y}`
                                      }).join(' ')}
                                    />
                                    <polygon fill="url(#equityGradHist)" points={`0,150 ${data.map((d: any, i: number) => {
                                      const x = (i / (data.length - 1)) * 400
                                      const y = 150 - ((d.equity - min) / range) * 140 - 5
                                      return `${x},${y}`
                                    }).join(' ')} 400,150`} />
                                    <defs>
                                      <linearGradient id="equityGradHist" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3" />
                                        <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                                      </linearGradient>
                                    </defs>
                                  </svg>
                                )
                              })()}
                            </div>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-left text-gray-400 border-b border-gray-700">
                                  <th className="pb-2">Date</th>
                                  <th className="pb-2 text-right">Daily P&L</th>
                                  <th className="pb-2 text-right">Cumulative</th>
                                  <th className="pb-2 text-right">Equity</th>
                                </tr>
                              </thead>
                              <tbody>
                                {equityCurve.equity_curve.slice(-10).map((point: any, idx: number) => (
                                  <tr key={idx} className="border-b border-gray-700/50">
                                    <td className="py-2">{point.date}</td>
                                    <td className={`py-2 text-right ${point.daily_profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                      {formatCurrency(point.daily_profit)}
                                    </td>
                                    <td className={`py-2 text-right ${point.cumulative_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                      {formatCurrency(point.cumulative_pnl)}
                                    </td>
                                    <td className="py-2 text-right font-medium">{formatCurrency(point.equity)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ) : (
                        <div className="py-12">
                          {/* Empty State Chart Placeholder */}
                          <div className="bg-black/30 rounded-lg p-6 mb-6">
                            <div className="h-48 relative flex items-center justify-center">
                              {/* Faded placeholder chart lines */}
                              <svg className="w-full h-full absolute" viewBox="0 0 400 150" preserveAspectRatio="none">
                                {/* Grid lines */}
                                <line x1="0" y1="37.5" x2="400" y2="37.5" stroke="#374151" strokeWidth="0.5" strokeDasharray="4,4" strokeOpacity="0.5" />
                                <line x1="0" y1="75" x2="400" y2="75" stroke="#374151" strokeWidth="0.5" strokeDasharray="4,4" strokeOpacity="0.5" />
                                <line x1="0" y1="112.5" x2="400" y2="112.5" stroke="#374151" strokeWidth="0.5" strokeDasharray="4,4" strokeOpacity="0.5" />
                                {/* Placeholder growth line */}
                                <polyline
                                  fill="none"
                                  stroke="#22c55e"
                                  strokeWidth="2"
                                  strokeDasharray="8,4"
                                  strokeOpacity="0.3"
                                  points="0,120 50,110 100,105 150,95 200,85 250,75 300,60 350,50 400,40"
                                />
                                <polygon
                                  fill="url(#emptyGradient)"
                                  fillOpacity="0.1"
                                  points="0,150 0,120 50,110 100,105 150,95 200,85 250,75 300,60 350,50 400,40 400,150"
                                />
                                <defs>
                                  <linearGradient id="emptyGradient" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3" />
                                    <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                                  </linearGradient>
                                </defs>
                              </svg>
                              {/* Centered icon and text */}
                              <div className="relative z-10 text-center">
                                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-emerald-900/30 border border-emerald-700/50 flex items-center justify-center">
                                  <svg className="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                                  </svg>
                                </div>
                                <h4 className="text-lg font-medium text-gray-300 mb-1">No Equity History Yet</h4>
                                <p className="text-sm text-gray-500">Your equity curve will appear here after IC trades close</p>
                              </div>
                            </div>
                          </div>

                          {/* What You'll See */}
                          <div className="grid grid-cols-3 gap-4 mb-6">
                            <div className="bg-black/20 rounded-lg p-4 border border-gray-800/50">
                              <div className="flex items-center gap-2 mb-2">
                                <div className="w-6 h-6 rounded bg-green-900/50 flex items-center justify-center">
                                  <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                                  </svg>
                                </div>
                                <span className="text-sm font-medium text-gray-300">Daily P&L</span>
                              </div>
                              <p className="text-xs text-gray-500">Track your daily IC returns minus borrowing costs</p>
                            </div>
                            <div className="bg-black/20 rounded-lg p-4 border border-gray-800/50">
                              <div className="flex items-center gap-2 mb-2">
                                <div className="w-6 h-6 rounded bg-blue-900/50 flex items-center justify-center">
                                  <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                                  </svg>
                                </div>
                                <span className="text-sm font-medium text-gray-300">Cumulative Growth</span>
                              </div>
                              <p className="text-xs text-gray-500">See your total equity growth over time</p>
                            </div>
                            <div className="bg-black/20 rounded-lg p-4 border border-gray-800/50">
                              <div className="flex items-center gap-2 mb-2">
                                <div className="w-6 h-6 rounded bg-purple-900/50 flex items-center justify-center">
                                  <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                  </svg>
                                </div>
                                <span className="text-sm font-medium text-gray-300">Trade History</span>
                              </div>
                              <p className="text-xs text-gray-500">Full breakdown of each day&apos;s activity</p>
                            </div>
                          </div>

                          {/* Getting Started */}
                          <div className="bg-gradient-to-r from-emerald-900/20 to-transparent rounded-lg p-4 border border-emerald-800/30">
                            <div className="flex items-start gap-3">
                              <div className="w-8 h-8 rounded-full bg-emerald-900/50 flex items-center justify-center flex-shrink-0 mt-0.5">
                                <span className="text-emerald-400 text-sm">💡</span>
                              </div>
                              <div>
                                <h5 className="text-sm font-medium text-emerald-400 mb-1">How to Get Started</h5>
                                <ol className="text-xs text-gray-400 space-y-1">
                                  <li>1. Open a box spread position in the <span className="text-emerald-400">Box Spreads</span> tab to borrow capital</li>
                                  <li>2. PROMETHEUS will automatically deploy capital to IC trades when conditions are favorable</li>
                                  <li>3. Once trades close, your equity curve will update showing net profit after borrowing costs</li>
                                </ol>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </>
                  )}

                  {/* Intraday View */}
                  {equityView === 'intraday' && (
                    <>
                      {intradayEquity?.snapshots && intradayEquity.snapshots.length > 0 ? (
                        <div>
                          <div className="flex justify-between items-center text-sm text-gray-400 mb-4">
                            <span>Market Open: {formatCurrency(intradayEquity.snapshots[0]?.total_equity || 0)}</span>
                            <span>Current: {formatCurrency(intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.total_equity || 0)}</span>
                          </div>
                          <div className="bg-black/30 rounded-lg p-4 mb-4">
                            <div className="h-48 relative">
                              {(() => {
                                const data = intradayEquity.snapshots
                                if (data.length < 2) return <div className="text-center text-gray-500 pt-20">Insufficient data</div>
                                const values = data.map((d: any) => d.total_equity)
                                const min = Math.min(...values)
                                const max = Math.max(...values)
                                const range = max - min || 1
                                const openValue = data[0]?.total_equity || 0
                                const currentValue = data[data.length - 1]?.total_equity || 0
                                const isPositive = currentValue >= openValue
                                return (
                                  <svg className="w-full h-full" viewBox="0 0 400 150" preserveAspectRatio="none">
                                    {/* Zero line at opening value */}
                                    <line
                                      x1="0"
                                      y1={150 - ((openValue - min) / range) * 140 - 5}
                                      x2="400"
                                      y2={150 - ((openValue - min) / range) * 140 - 5}
                                      stroke="#6b7280"
                                      strokeWidth="1"
                                      strokeDasharray="4,4"
                                    />
                                    <polyline fill="none" stroke={isPositive ? '#22c55e' : '#ef4444'} strokeWidth="2"
                                      points={data.map((d: any, i: number) => {
                                        const x = (i / (data.length - 1)) * 400
                                        const y = 150 - ((d.total_equity - min) / range) * 140 - 5
                                        return `${x},${y}`
                                      }).join(' ')}
                                    />
                                    <polygon fill={`url(#equityGradIntra${isPositive ? 'Up' : 'Down'})`} points={`0,150 ${data.map((d: any, i: number) => {
                                      const x = (i / (data.length - 1)) * 400
                                      const y = 150 - ((d.total_equity - min) / range) * 140 - 5
                                      return `${x},${y}`
                                    }).join(' ')} 400,150`} />
                                    <defs>
                                      <linearGradient id="equityGradIntraUp" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3" />
                                        <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                                      </linearGradient>
                                      <linearGradient id="equityGradIntraDown" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#ef4444" stopOpacity="0.3" />
                                        <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
                                      </linearGradient>
                                    </defs>
                                  </svg>
                                )
                              })()}
                            </div>
                          </div>
                          {/* Intraday Change Summary */}
                          <div className="grid grid-cols-3 gap-4 mb-4">
                            <div className="bg-black/30 rounded-lg p-3 text-center">
                              <div className="text-xs text-gray-400">Day&apos;s Change</div>
                              <div className={`text-lg font-bold ${
                                (intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.total_equity || 0) -
                                (intradayEquity.snapshots[0]?.total_equity || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                              }`}>
                                {formatCurrency(
                                  (intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.total_equity || 0) -
                                  (intradayEquity.snapshots[0]?.total_equity || 0)
                                )}
                              </div>
                            </div>
                            <div className="bg-black/30 rounded-lg p-3 text-center">
                              <div className="text-xs text-gray-400">Unrealized P&L</div>
                              <div className={`text-lg font-bold ${
                                (intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                              }`}>
                                {formatCurrency(intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.unrealized_pnl || 0)}
                              </div>
                            </div>
                            <div className="bg-black/30 rounded-lg p-3 text-center">
                              <div className="text-xs text-gray-400">Snapshots</div>
                              <div className="text-lg font-bold text-blue-400">{intradayEquity.snapshots.length}</div>
                            </div>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-left text-gray-400 border-b border-gray-700">
                                  <th className="pb-2">Time</th>
                                  <th className="pb-2 text-right">Equity</th>
                                  <th className="pb-2 text-right">Unrealized P&L</th>
                                  <th className="pb-2 text-right">Source</th>
                                </tr>
                              </thead>
                              <tbody>
                                {intradayEquity.snapshots.slice(-10).map((snap: any, idx: number) => (
                                  <tr key={idx} className="border-b border-gray-700/50">
                                    <td className="py-2">{new Date(snap.snapshot_time).toLocaleTimeString()}</td>
                                    <td className="py-2 text-right font-medium">{formatCurrency(snap.total_equity)}</td>
                                    <td className={`py-2 text-right ${snap.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                      {formatCurrency(snap.unrealized_pnl)}
                                    </td>
                                    <td className="py-2 text-right text-xs text-gray-500">{snap.quote_source || 'calculated'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ) : (
                        <div className="py-12">
                          {/* Empty State Chart Placeholder */}
                          <div className="bg-black/30 rounded-lg p-6 mb-6">
                            <div className="h-48 relative flex items-center justify-center">
                              {/* Faded placeholder real-time chart */}
                              <svg className="w-full h-full absolute" viewBox="0 0 400 150" preserveAspectRatio="none">
                                {/* Grid lines */}
                                <line x1="0" y1="75" x2="400" y2="75" stroke="#6b7280" strokeWidth="1" strokeDasharray="4,4" strokeOpacity="0.3" />
                                {/* Time markers */}
                                <line x1="100" y1="0" x2="100" y2="150" stroke="#374151" strokeWidth="0.5" strokeOpacity="0.3" />
                                <line x1="200" y1="0" x2="200" y2="150" stroke="#374151" strokeWidth="0.5" strokeOpacity="0.3" />
                                <line x1="300" y1="0" x2="300" y2="150" stroke="#374151" strokeWidth="0.5" strokeOpacity="0.3" />
                                {/* Placeholder intraday movement */}
                                <polyline
                                  fill="none"
                                  stroke="#3b82f6"
                                  strokeWidth="2"
                                  strokeDasharray="6,3"
                                  strokeOpacity="0.3"
                                  points="0,75 30,70 60,78 90,65 120,72 150,68 180,60 210,65 240,55 270,62 300,50 330,58 360,45 400,52"
                                />
                              </svg>
                              {/* Centered icon and text */}
                              <div className="relative z-10 text-center">
                                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-blue-900/30 border border-blue-700/50 flex items-center justify-center">
                                  <svg className="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                </div>
                                <h4 className="text-lg font-medium text-gray-300 mb-1">No Intraday Data Yet</h4>
                                <p className="text-sm text-gray-500">Real-time snapshots appear during market hours (8:30 AM - 3:00 PM CT)</p>
                              </div>
                            </div>
                          </div>

                          {/* What Intraday Shows */}
                          <div className="grid grid-cols-3 gap-4 mb-6">
                            <div className="bg-black/20 rounded-lg p-4 border border-gray-800/50">
                              <div className="flex items-center gap-2 mb-2">
                                <div className="w-6 h-6 rounded bg-blue-900/50 flex items-center justify-center">
                                  <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                  </svg>
                                </div>
                                <span className="text-sm font-medium text-gray-300">Live Updates</span>
                              </div>
                              <p className="text-xs text-gray-500">Snapshots taken every 5 minutes during market hours</p>
                            </div>
                            <div className="bg-black/20 rounded-lg p-4 border border-gray-800/50">
                              <div className="flex items-center gap-2 mb-2">
                                <div className="w-6 h-6 rounded bg-yellow-900/50 flex items-center justify-center">
                                  <svg className="w-4 h-4 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                </div>
                                <span className="text-sm font-medium text-gray-300">Unrealized P&L</span>
                              </div>
                              <p className="text-xs text-gray-500">Mark-to-market value of open positions</p>
                            </div>
                            <div className="bg-black/20 rounded-lg p-4 border border-gray-800/50">
                              <div className="flex items-center gap-2 mb-2">
                                <div className="w-6 h-6 rounded bg-cyan-900/50 flex items-center justify-center">
                                  <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                                  </svg>
                                </div>
                                <span className="text-sm font-medium text-gray-300">Position Tracking</span>
                              </div>
                              <p className="text-xs text-gray-500">Monitor IC trades as they develop</p>
                            </div>
                          </div>

                          {/* Market Hours Info */}
                          <div className="bg-gradient-to-r from-blue-900/20 to-transparent rounded-lg p-4 border border-blue-800/30">
                            <div className="flex items-start gap-3">
                              <div className="w-8 h-8 rounded-full bg-blue-900/50 flex items-center justify-center flex-shrink-0 mt-0.5">
                                <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                              </div>
                              <div>
                                <h5 className="text-sm font-medium text-blue-400 mb-1">Market Hours Only</h5>
                                <p className="text-xs text-gray-400">
                                  Intraday snapshots are captured during market hours: <span className="text-blue-400">8:30 AM - 3:00 PM CT</span>.
                                  Check back during trading hours to see real-time equity updates.
                                </p>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </>
                  )}
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
                          <span className="text-red-400">-{formatCurrency(totalBorrowingCosts)}</span>
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
                    <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
                      <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
                      </svg>
                    </div>
                    <h1 className="text-4xl font-bold text-white mb-2">PROMETHEUS System Flow</h1>
                    <p className="text-xl text-purple-300">Complete Operational Reference Guide</p>
                    <p className="text-gray-400 mt-2 max-w-2xl mx-auto">
                      Visual decision trees showing exactly how PROMETHEUS operates from market open to close.
                      Every decision point, threshold, and data flow documented.
                    </p>
                  </div>
                </div>

                {/* Quick Navigation */}
                <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
                  <h2 className="text-xl font-bold mb-4 text-orange-400 flex items-center gap-2">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
                    </svg>
                    Quick Navigation
                  </h2>
                  <div className="grid md:grid-cols-3 gap-4 text-sm">
                    <div className="bg-gradient-to-br from-blue-900/30 to-blue-900/10 rounded-lg p-4 border border-blue-700/30 hover:border-blue-500/50 transition-colors">
                      <div className="flex items-center gap-2 mb-3">
                        <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold">1</div>
                        <span className="font-medium text-blue-400">Box Spreads</span>
                      </div>
                      <ul className="text-gray-400 space-y-1 ml-10">
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-blue-500 rounded-full"></span>Pre-Market Startup</li>
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-blue-500 rounded-full"></span>Position Lifecycle</li>
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-blue-500 rounded-full"></span>Roll Decision Matrix</li>
                      </ul>
                    </div>
                    <div className="bg-gradient-to-br from-orange-900/30 to-orange-900/10 rounded-lg p-4 border border-orange-700/30 hover:border-orange-500/50 transition-colors">
                      <div className="flex items-center gap-2 mb-3">
                        <div className="w-8 h-8 rounded-lg bg-orange-600 flex items-center justify-center text-white font-bold">2</div>
                        <span className="font-medium text-orange-400">IC Trading</span>
                      </div>
                      <ul className="text-gray-400 space-y-1 ml-10">
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-orange-500 rounded-full"></span>Oracle Approval Flow</li>
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-orange-500 rounded-full"></span>PEGASUS Rules</li>
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-orange-500 rounded-full"></span>Position Management</li>
                      </ul>
                    </div>
                    <div className="bg-gradient-to-br from-green-900/30 to-green-900/10 rounded-lg p-4 border border-green-700/30 hover:border-green-500/50 transition-colors">
                      <div className="flex items-center gap-2 mb-3">
                        <div className="w-8 h-8 rounded-lg bg-green-600 flex items-center justify-center text-white font-bold">3</div>
                        <span className="font-medium text-green-400">Reference</span>
                      </div>
                      <ul className="text-gray-400 space-y-1 ml-10">
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-green-500 rounded-full"></span>Daily Timeline</li>
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-green-500 rounded-full"></span>Data Flow Diagram</li>
                        <li className="flex items-center gap-2"><span className="w-1 h-1 bg-green-500 rounded-full"></span>Key Thresholds</li>
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

                  {/* Visual Flowchart */}
                  <div className="bg-gradient-to-b from-blue-900/20 to-transparent rounded-xl p-6 mb-6">
                    {/* Row 1: System Wakes → Tradier API → Position Reconciliation */}
                    <div className="flex flex-wrap items-start justify-center gap-4 mb-6">
                      {/* System Wakes */}
                      <div className="flex flex-col items-center">
                        <div className="w-32 bg-gradient-to-br from-blue-600 to-blue-700 rounded-xl p-4 text-center border-2 border-blue-400 shadow-lg shadow-blue-500/20">
                          <div className="w-10 h-10 mx-auto mb-2 rounded-full bg-blue-500/30 flex items-center justify-center">
                            <svg className="w-6 h-6 text-blue-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707" />
                            </svg>
                          </div>
                          <div className="text-white font-bold text-sm">SYSTEM</div>
                          <div className="text-blue-200 text-xs">Wakes Up</div>
                          <div className="text-blue-300 text-xs mt-1">8:00 AM CT</div>
                        </div>
                      </div>

                      {/* Arrow */}
                      <div className="flex items-center py-8">
                        <div className="w-8 h-0.5 bg-blue-500"></div>
                        <div className="w-0 h-0 border-t-4 border-b-4 border-l-8 border-transparent border-l-blue-500"></div>
                      </div>

                      {/* Tradier API */}
                      <div className="flex flex-col items-center">
                        <div className="w-36 bg-gradient-to-br from-green-600 to-green-700 rounded-xl p-4 text-center border-2 border-green-400 shadow-lg shadow-green-500/20">
                          <div className="w-10 h-10 mx-auto mb-2 rounded-full bg-green-500/30 flex items-center justify-center">
                            <svg className="w-6 h-6 text-green-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                          </div>
                          <div className="text-white font-bold text-sm">TRADIER API</div>
                          <div className="text-green-200 text-xs">Production</div>
                        </div>
                      </div>

                      {/* Arrow */}
                      <div className="flex items-center py-8">
                        <div className="w-8 h-0.5 bg-green-500"></div>
                        <div className="w-0 h-0 border-t-4 border-b-4 border-l-8 border-transparent border-l-green-500"></div>
                      </div>

                      {/* Position Reconciliation */}
                      <div className="flex flex-col items-center">
                        <div className="w-48 bg-gradient-to-br from-purple-600 to-purple-700 rounded-xl p-4 border-2 border-purple-400 shadow-lg shadow-purple-500/20">
                          <div className="flex items-center justify-center gap-2 mb-2">
                            <svg className="w-6 h-6 text-purple-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                            </svg>
                            <span className="text-white font-bold text-sm">RECONCILIATION</span>
                          </div>
                          <ul className="text-xs text-purple-100 text-left space-y-1">
                            <li className="flex items-center gap-1"><span className="text-green-400">✓</span> Load open boxes</li>
                            <li className="flex items-center gap-1"><span className="text-green-400">✓</span> Calculate MTM</li>
                            <li className="flex items-center gap-1"><span className="text-green-400">✓</span> Check DTE</li>
                            <li className="flex items-center gap-1"><span className="text-green-400">✓</span> Update accruals</li>
                          </ul>
                        </div>
                      </div>
                    </div>

                    {/* Row 2: Rate Check + Roll Decisions + Capital Allocation */}
                    <div className="flex flex-wrap items-start justify-center gap-6">
                      {/* Rate Check */}
                      <div className="w-40 bg-gradient-to-br from-yellow-600/80 to-yellow-700/80 rounded-xl p-4 border-2 border-yellow-500/50">
                        <div className="flex items-center justify-center gap-2 mb-2">
                          <svg className="w-5 h-5 text-yellow-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                          </svg>
                          <span className="text-white font-bold text-sm">RATE CHECK</span>
                        </div>
                        <div className="space-y-1 text-xs">
                          <div className="flex justify-between"><span className="text-yellow-200">Fed Funds:</span><span className="text-white font-mono">X%</span></div>
                          <div className="flex justify-between"><span className="text-yellow-200">Margin:</span><span className="text-white font-mono">Y%</span></div>
                          <div className="flex justify-between"><span className="text-yellow-200">Box Rate:</span><span className="text-white font-mono">Z%</span></div>
                        </div>
                      </div>

                      {/* Arrow down to Roll Decisions */}
                      <div className="hidden md:flex flex-col items-center">
                        <div className="w-0.5 h-6 bg-purple-500"></div>
                        <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-transparent border-t-purple-500"></div>
                      </div>

                      {/* Roll Decisions */}
                      <div className="w-56 bg-gradient-to-br from-red-600/80 to-red-700/80 rounded-xl p-4 border-2 border-red-500/50">
                        <div className="flex items-center justify-center gap-2 mb-2">
                          <svg className="w-5 h-5 text-red-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                          <span className="text-white font-bold text-sm">ROLL DECISIONS</span>
                        </div>
                        <div className="bg-black/30 rounded-lg p-2 text-xs">
                          <div className="text-red-200 mb-1">IF DTE ≤ 30:</div>
                          <ul className="text-red-100 space-y-0.5 ml-2">
                            <li>→ Flag for roll</li>
                            <li>→ Check new rates</li>
                            <li>→ Queue if favorable</li>
                          </ul>
                        </div>
                      </div>

                      {/* Arrow to Capital Allocation */}
                      <div className="hidden md:flex items-center">
                        <div className="w-8 h-0.5 bg-emerald-500"></div>
                        <div className="w-0 h-0 border-t-4 border-b-4 border-l-8 border-transparent border-l-emerald-500"></div>
                      </div>

                      {/* Capital Allocation */}
                      <div className="w-52 bg-gradient-to-br from-emerald-600 to-emerald-700 rounded-xl p-4 border-2 border-emerald-400 shadow-lg shadow-emerald-500/20">
                        <div className="flex items-center justify-center gap-2 mb-2">
                          <svg className="w-5 h-5 text-emerald-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          <span className="text-white font-bold text-sm">CAPITAL</span>
                        </div>
                        <div className="space-y-1 text-xs bg-black/20 rounded-lg p-2">
                          <div className="flex justify-between"><span className="text-emerald-200">Total Borrowed:</span><span className="text-white">$XXX</span></div>
                          <div className="flex justify-between"><span className="text-emerald-200">- Reserve (10%):</span><span className="text-yellow-300">$XXX</span></div>
                          <div className="flex justify-between border-t border-emerald-500/30 pt-1"><span className="text-emerald-200">= Available:</span><span className="text-green-300 font-bold">$XXX</span></div>
                        </div>
                        <div className="mt-2 pt-2 border-t border-emerald-500/30 text-xs text-emerald-100">
                          <div>Per IC: $5,000 | Max: 3</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Explanation Cards */}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-600/30">
                      <h4 className="font-bold text-blue-400 mb-3 flex items-center gap-2">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        What Happens
                      </h4>
                      <ol className="text-sm text-gray-300 space-y-2">
                        <li className="flex gap-2"><span className="text-blue-400 font-bold">1.</span> System connects to Tradier PRODUCTION API</li>
                        <li className="flex gap-2"><span className="text-blue-400 font-bold">2.</span> Loads all open box spread positions</li>
                        <li className="flex gap-2"><span className="text-blue-400 font-bold">3.</span> Fetches current market prices for MTM</li>
                        <li className="flex gap-2"><span className="text-blue-400 font-bold">4.</span> Calculates daily interest accrual</li>
                        <li className="flex gap-2"><span className="text-blue-400 font-bold">5.</span> Checks which positions need rolling</li>
                      </ol>
                    </div>
                    <div className="bg-purple-900/20 rounded-lg p-4 border border-purple-600/30">
                      <h4 className="font-bold text-purple-400 mb-3 flex items-center gap-2">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        Key Thresholds
                      </h4>
                      <div className="text-sm text-gray-300 space-y-2">
                        <div className="flex justify-between items-center bg-black/20 rounded px-3 py-1.5">
                          <span className="text-yellow-400">Roll Threshold</span>
                          <span className="font-mono text-white">DTE ≤ 30 days</span>
                        </div>
                        <div className="flex justify-between items-center bg-black/20 rounded px-3 py-1.5">
                          <span className="text-yellow-400">Reserve</span>
                          <span className="font-mono text-white">10% of borrowed</span>
                        </div>
                        <div className="flex justify-between items-center bg-black/20 rounded px-3 py-1.5">
                          <span className="text-yellow-400">Capital/Trade</span>
                          <span className="font-mono text-white">$5,000 per IC</span>
                        </div>
                        <div className="flex justify-between items-center bg-black/20 rounded px-3 py-1.5">
                          <span className="text-yellow-400">Max Positions</span>
                          <span className="font-mono text-white">3 ICs at a time</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PART 2: BOX SPREAD SIDE */}
                <div className="bg-gray-800 rounded-xl p-6 border border-cyan-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-cyan-600 rounded-lg flex items-center justify-center text-xl">2</span>
                    <span className="text-cyan-400">Box Spread Side - &quot;The Loan&quot;</span>
                  </h2>

                  {/* Visual Lifecycle - Two Column Layout */}
                  <div className="grid md:grid-cols-2 gap-6 mb-6">
                    {/* Left Column: Open New Box Flow */}
                    <div className="bg-gradient-to-b from-cyan-900/30 to-transparent rounded-xl p-5 border border-cyan-700/30">
                      <h3 className="text-lg font-bold text-cyan-400 mb-4 text-center">OPEN NEW BOX</h3>

                      {/* Decision: Check Rates */}
                      <div className="flex flex-col items-center">
                        <div className="w-full max-w-xs bg-gradient-to-br from-yellow-600/80 to-yellow-700/80 rounded-xl p-4 border-2 border-yellow-500/50 mb-3">
                          <div className="text-center text-white font-bold mb-2">Check Rates</div>
                          <div className="bg-black/30 rounded-lg p-2 text-center">
                            <span className="text-yellow-200 text-sm">Box Rate &lt; Margin Rate?</span>
                          </div>
                        </div>

                        {/* Decision Branch */}
                        <div className="flex items-center gap-4 mb-3">
                          <div className="flex items-center">
                            <div className="w-16 h-0.5 bg-red-500"></div>
                            <div className="px-2 py-1 bg-red-600 rounded text-xs text-white">NO</div>
                            <div className="w-8 h-0.5 bg-red-500"></div>
                            <div className="px-3 py-1 bg-red-900/50 rounded border border-red-600 text-red-400 text-xs">SKIP</div>
                          </div>
                        </div>

                        <div className="flex flex-col items-center">
                          <div className="w-0.5 h-4 bg-green-500"></div>
                          <div className="px-2 py-0.5 bg-green-600 rounded text-xs text-white mb-1">YES</div>
                          <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-transparent border-t-green-500"></div>
                        </div>

                        {/* Select Strikes */}
                        <div className="w-full max-w-xs bg-gradient-to-br from-blue-600/80 to-blue-700/80 rounded-xl p-4 border-2 border-blue-500/50 my-3">
                          <div className="text-center text-white font-bold mb-2">Select Strikes</div>
                          <div className="grid grid-cols-3 gap-2 text-xs text-center">
                            <div className="bg-black/30 rounded p-1"><span className="text-blue-200">Lower:</span> <span className="text-white">SPX-25</span></div>
                            <div className="bg-black/30 rounded p-1"><span className="text-blue-200">Upper:</span> <span className="text-white">SPX+25</span></div>
                            <div className="bg-black/30 rounded p-1"><span className="text-blue-200">Width:</span> <span className="text-white">50pts</span></div>
                          </div>
                        </div>

                        <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-transparent border-t-blue-500 my-2"></div>

                        {/* Execute Box */}
                        <div className="w-full max-w-xs bg-gradient-to-br from-purple-600 to-purple-700 rounded-xl p-4 border-2 border-purple-400 mb-3">
                          <div className="text-center text-white font-bold mb-2">Execute 4-Leg Order</div>
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <div className="bg-green-900/50 rounded p-1.5 text-center"><span className="text-green-400">+Call K1</span></div>
                            <div className="bg-red-900/50 rounded p-1.5 text-center"><span className="text-red-400">-Call K2</span></div>
                            <div className="bg-green-900/50 rounded p-1.5 text-center"><span className="text-green-400">+Put K2</span></div>
                            <div className="bg-red-900/50 rounded p-1.5 text-center"><span className="text-red-400">-Put K1</span></div>
                          </div>
                        </div>

                        <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-transparent border-t-purple-500 my-2"></div>

                        {/* Record */}
                        <div className="w-full max-w-xs bg-gradient-to-br from-emerald-600 to-emerald-700 rounded-xl p-4 border-2 border-emerald-400">
                          <div className="text-center text-white font-bold mb-2">Record Position</div>
                          <div className="text-xs text-emerald-100 space-y-1">
                            <div className="flex items-center gap-2"><span className="text-emerald-300">•</span> Credit received</div>
                            <div className="flex items-center gap-2"><span className="text-emerald-300">•</span> Implied rate</div>
                            <div className="flex items-center gap-2"><span className="text-emerald-300">•</span> Expiration date</div>
                            <div className="flex items-center gap-2"><span className="text-emerald-300">•</span> Margin held</div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Right Column: Daily Monitoring + Roll Matrix + Expiration */}
                    <div className="space-y-4">
                      {/* Daily Monitoring */}
                      <div className="bg-gradient-to-br from-indigo-900/30 to-transparent rounded-xl p-5 border border-indigo-700/30">
                        <h3 className="text-lg font-bold text-indigo-400 mb-3 text-center">DAILY MONITORING</h3>
                        <div className="bg-black/30 rounded-lg p-4">
                          <div className="text-indigo-200 text-sm mb-2 font-medium">For each open box:</div>
                          <ol className="text-sm text-indigo-100 space-y-1.5">
                            <li className="flex items-center gap-2"><span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-xs flex items-center justify-center">1</span> Fetch current prices</li>
                            <li className="flex items-center gap-2"><span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-xs flex items-center justify-center">2</span> Calculate MTM value</li>
                            <li className="flex items-center gap-2"><span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-xs flex items-center justify-center">3</span> Accrue daily interest</li>
                            <li className="flex items-center gap-2"><span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-xs flex items-center justify-center">4</span> Check roll eligibility</li>
                          </ol>
                        </div>
                      </div>

                      {/* Roll Decision Matrix */}
                      <div className="bg-gradient-to-br from-red-900/30 to-transparent rounded-xl p-5 border border-red-700/30">
                        <h3 className="text-lg font-bold text-red-400 mb-3 text-center">ROLL DECISION MATRIX</h3>
                        <div className="space-y-2">
                          <div className="flex items-center justify-between bg-red-900/50 rounded-lg px-3 py-2 border border-red-600">
                            <span className="text-red-200 font-mono text-sm">DTE ≤ 0</span>
                            <span className="px-2 py-0.5 bg-red-600 rounded text-white text-xs font-bold">CRITICAL</span>
                          </div>
                          <div className="flex items-center justify-between bg-orange-900/30 rounded-lg px-3 py-2 border border-orange-700/50">
                            <span className="text-orange-200 font-mono text-sm">DTE 1-7</span>
                            <span className="px-2 py-0.5 bg-orange-600 rounded text-white text-xs">WARNING</span>
                          </div>
                          <div className="flex items-center justify-between bg-yellow-900/30 rounded-lg px-3 py-2 border border-yellow-700/50">
                            <span className="text-yellow-200 font-mono text-sm">DTE 8-14</span>
                            <span className="px-2 py-0.5 bg-yellow-600 rounded text-white text-xs">SOON</span>
                          </div>
                          <div className="flex items-center justify-between bg-blue-900/30 rounded-lg px-3 py-2 border border-blue-700/50">
                            <span className="text-blue-200 font-mono text-sm">DTE 15-30</span>
                            <span className="px-2 py-0.5 bg-blue-600 rounded text-white text-xs">SCHEDULED</span>
                          </div>
                          <div className="flex items-center justify-between bg-green-900/30 rounded-lg px-3 py-2 border border-green-700/50">
                            <span className="text-green-200 font-mono text-sm">DTE &gt; 30</span>
                            <span className="px-2 py-0.5 bg-green-600 rounded text-white text-xs">OK</span>
                          </div>
                        </div>
                      </div>

                      {/* Expiration */}
                      <div className="bg-gradient-to-br from-gray-700/50 to-transparent rounded-xl p-5 border border-gray-600/30">
                        <h3 className="text-lg font-bold text-gray-300 mb-3 text-center">EXPIRATION</h3>
                        <div className="bg-black/30 rounded-lg p-3 text-sm text-gray-200 space-y-1">
                          <div className="flex items-center gap-2"><span className="text-green-400">✓</span> Box settles at strike width</div>
                          <div className="flex items-center gap-2"><span className="text-green-400">✓</span> Cash-settled (SPX)</div>
                          <div className="flex items-center gap-2"><span className="text-green-400">✓</span> &quot;Loan&quot; repaid automatically</div>
                          <div className="flex items-center gap-2"><span className="text-green-400">✓</span> No stock delivery</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Capital Flow Example */}
                  <div className="bg-gradient-to-r from-cyan-900/30 via-blue-900/30 to-purple-900/30 rounded-xl p-5 border border-cyan-600/30">
                    <h4 className="font-bold text-white mb-4 flex items-center gap-2 justify-center">
                      <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Capital Flow Example
                    </h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="bg-black/30 rounded-xl p-4 text-center border border-green-600/30">
                        <div className="text-gray-400 text-sm mb-1">Box Credit</div>
                        <div className="text-2xl font-bold text-green-400">$49,250</div>
                        <div className="text-xs text-gray-500 mt-1">$50 width × 10 contracts × 98.5</div>
                      </div>
                      <div className="bg-black/30 rounded-xl p-4 text-center border border-yellow-600/30">
                        <div className="text-gray-400 text-sm mb-1">Reserve (10%)</div>
                        <div className="text-2xl font-bold text-yellow-400">$4,925</div>
                        <div className="text-xs text-gray-500 mt-1">Safety buffer</div>
                      </div>
                      <div className="bg-black/30 rounded-xl p-4 text-center border border-orange-600/30">
                        <div className="text-gray-400 text-sm mb-1">Available for IC</div>
                        <div className="text-2xl font-bold text-orange-400">$44,325</div>
                        <div className="text-xs text-gray-500 mt-1">Deployed to trading</div>
                      </div>
                      <div className="bg-black/30 rounded-xl p-4 text-center border border-red-600/30">
                        <div className="text-gray-400 text-sm mb-1">Owed at Expiry</div>
                        <div className="text-2xl font-bold text-red-400">$50,000</div>
                        <div className="text-xs text-gray-500 mt-1">Strike width × contracts × 100</div>
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

                  {/* Visual Decision Tree Flowchart */}
                  <div className="bg-gradient-to-b from-orange-900/20 to-transparent rounded-xl p-6 mb-6">
                    <div className="text-center text-sm text-orange-300 mb-4">Follows PEGASUS Trading Rules</div>

                    {/* Flow Container */}
                    <div className="flex flex-col items-center">
                      {/* Scan Trigger */}
                      <div className="w-full max-w-md bg-gradient-to-br from-orange-600 to-orange-700 rounded-xl p-4 border-2 border-orange-400 shadow-lg shadow-orange-500/20 mb-4">
                        <div className="flex items-center justify-center gap-2 mb-2">
                          <svg className="w-6 h-6 text-orange-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          <span className="text-white font-bold">SCAN TRIGGER</span>
                        </div>
                        <div className="text-center text-orange-100 text-sm">
                          Every 5-15 minutes during 8:35 AM - 2:30 PM CT
                        </div>
                      </div>

                      {/* Arrow */}
                      <div className="flex flex-col items-center mb-4">
                        <div className="w-0.5 h-4 bg-orange-500"></div>
                        <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-transparent border-t-orange-500"></div>
                      </div>

                      {/* Market Check + VIX Filter Row */}
                      <div className="flex flex-wrap items-start justify-center gap-4 mb-4">
                        {/* Market Check */}
                        <div className="w-48 bg-gradient-to-br from-blue-600/80 to-blue-700/80 rounded-xl p-4 border-2 border-blue-500/50">
                          <div className="text-center text-white font-bold mb-2">MARKET CHECK</div>
                          <ul className="text-xs text-blue-100 space-y-1">
                            <li className="flex items-center gap-1"><span className="text-blue-300">•</span> Get SPX price</li>
                            <li className="flex items-center gap-1"><span className="text-blue-300">•</span> Get VIX</li>
                            <li className="flex items-center gap-1"><span className="text-blue-300">•</span> Get GEX regime</li>
                          </ul>
                        </div>

                        {/* Arrow */}
                        <div className="flex items-center py-6">
                          <div className="w-6 h-0.5 bg-blue-500"></div>
                          <div className="w-0 h-0 border-t-4 border-b-4 border-l-8 border-transparent border-l-blue-500"></div>
                        </div>

                        {/* VIX Filter */}
                        <div className="w-56 bg-gradient-to-br from-yellow-600/80 to-yellow-700/80 rounded-xl p-4 border-2 border-yellow-500/50">
                          <div className="text-center text-white font-bold mb-2">VIX FILTER</div>
                          <div className="text-xs text-yellow-100 space-y-1">
                            <div className="flex justify-between bg-black/20 rounded px-2 py-1">
                              <span>Min VIX:</span><span className="text-white font-mono">12</span>
                            </div>
                            <div className="flex justify-between bg-black/20 rounded px-2 py-1">
                              <span>Max VIX:</span><span className="text-white font-mono">35</span>
                            </div>
                            <div className="flex justify-between bg-black/20 rounded px-2 py-1">
                              <span>Mon/Fri:</span><span className="text-white font-mono">30</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* VIX Decision Branch */}
                      <div className="flex items-center gap-6 mb-4">
                        <div className="flex items-center">
                          <div className="w-20 h-0.5 bg-red-500"></div>
                          <div className="px-2 py-1 bg-red-600 rounded text-xs text-white font-bold">FAIL</div>
                          <div className="w-8 h-0.5 bg-red-500"></div>
                          <div className="px-4 py-2 bg-red-900/50 rounded-lg border border-red-600 text-red-400 text-xs">
                            <div className="font-bold">SKIP SCAN</div>
                            <div className="text-red-300">Log: &quot;VIX too high&quot;</div>
                          </div>
                        </div>
                      </div>

                      {/* Pass Arrow */}
                      <div className="flex flex-col items-center mb-4">
                        <div className="px-3 py-1 bg-green-600 rounded text-xs text-white font-bold">PASS</div>
                        <div className="w-0.5 h-4 bg-green-500"></div>
                        <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-transparent border-t-green-500"></div>
                      </div>

                      {/* Oracle Check */}
                      <div className="w-full max-w-sm bg-gradient-to-br from-purple-600 to-purple-700 rounded-xl p-5 border-2 border-purple-400 shadow-lg shadow-purple-500/20 mb-4">
                        <div className="flex items-center justify-center gap-2 mb-3">
                          <svg className="w-6 h-6 text-purple-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                          </svg>
                          <span className="text-white font-bold">ORACLE CHECK</span>
                        </div>
                        <div className="bg-black/30 rounded-lg p-3 text-xs">
                          <div className="text-purple-200 mb-2 font-mono">get_pegasus_advice()</div>
                          <div className="text-purple-100 space-y-1">
                            <div className="flex items-center gap-2"><span className="text-purple-300">→</span> advice: TRADE/SKIP/HOLD</div>
                            <div className="flex items-center gap-2"><span className="text-purple-300">→</span> confidence: 0-100%</div>
                            <div className="flex items-center gap-2"><span className="text-purple-300">→</span> win_probability: 0-100%</div>
                            <div className="flex items-center gap-2"><span className="text-purple-300">→</span> suggested_strikes</div>
                            <div className="flex items-center gap-2"><span className="text-purple-300">→</span> reasoning</div>
                          </div>
                        </div>
                      </div>

                      {/* Arrow */}
                      <div className="flex flex-col items-center mb-4">
                        <div className="w-0.5 h-4 bg-purple-500"></div>
                        <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-transparent border-t-purple-500"></div>
                      </div>

                      {/* Approval Gates */}
                      <div className="w-full max-w-md bg-gradient-to-br from-indigo-600/80 to-indigo-700/80 rounded-xl p-5 border-2 border-indigo-500/50 mb-4">
                        <div className="text-center text-white font-bold mb-3">APPROVAL GATES</div>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="bg-black/30 rounded-lg p-2 flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-indigo-500 text-white text-xs flex items-center justify-center">1</span>
                            <span className="text-xs text-indigo-100">Advice = TRADE?</span>
                          </div>
                          <div className="bg-black/30 rounded-lg p-2 flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-indigo-500 text-white text-xs flex items-center justify-center">2</span>
                            <span className="text-xs text-indigo-100">Confidence ≥ 60%</span>
                          </div>
                          <div className="bg-black/30 rounded-lg p-2 flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-indigo-500 text-white text-xs flex items-center justify-center">3</span>
                            <span className="text-xs text-indigo-100">Win Prob ≥ 55%</span>
                          </div>
                          <div className="bg-black/30 rounded-lg p-2 flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-indigo-500 text-white text-xs flex items-center justify-center">4</span>
                            <span className="text-xs text-indigo-100">Positions &lt; 3</span>
                          </div>
                        </div>
                      </div>

                      {/* All Pass Decision */}
                      <div className="flex flex-wrap items-center justify-center gap-6 mb-4">
                        <div className="flex items-center">
                          <div className="px-4 py-2 bg-red-900/50 rounded-lg border border-red-600 text-xs">
                            <div className="text-red-400 font-bold">ANY FAIL → SKIP</div>
                            <div className="text-red-300 text-xs">Log reason</div>
                          </div>
                          <div className="w-8 h-0.5 bg-red-500"></div>
                          <div className="px-2 py-1 bg-red-600 rounded text-xs text-white font-bold">NO</div>
                        </div>
                        <div className="flex flex-col items-center">
                          <div className="px-3 py-1 bg-green-600 rounded text-xs text-white font-bold">ALL PASS</div>
                          <div className="w-0.5 h-4 bg-green-500"></div>
                          <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-transparent border-t-green-500"></div>
                        </div>
                      </div>

                      {/* Execute IC Trade */}
                      <div className="w-full max-w-md bg-gradient-to-br from-emerald-600 to-emerald-700 rounded-xl p-5 border-2 border-emerald-400 shadow-lg shadow-emerald-500/20">
                        <div className="flex items-center justify-center gap-2 mb-3">
                          <svg className="w-6 h-6 text-emerald-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          <span className="text-white font-bold">EXECUTE IC TRADE</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div className="bg-black/30 rounded-lg p-2 flex items-center gap-2">
                            <span className="text-emerald-300">•</span>
                            <span className="text-emerald-100">Select strikes (~10Δ)</span>
                          </div>
                          <div className="bg-black/30 rounded-lg p-2 flex items-center gap-2">
                            <span className="text-emerald-300">•</span>
                            <span className="text-emerald-100">Size: $5,000 max risk</span>
                          </div>
                          <div className="bg-black/30 rounded-lg p-2 flex items-center gap-2">
                            <span className="text-emerald-300">•</span>
                            <span className="text-emerald-100">Execute 4-leg order</span>
                          </div>
                          <div className="bg-black/30 rounded-lg p-2 flex items-center gap-2">
                            <span className="text-emerald-300">•</span>
                            <span className="text-emerald-100">Record to database</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* PEGASUS Rules Reference */}
                  <div className="bg-gradient-to-r from-orange-900/20 to-transparent rounded-xl p-5 border border-orange-600/30">
                    <h4 className="font-bold text-orange-400 mb-4 flex items-center gap-2">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      </svg>
                      PEGASUS Trading Rules (Used by PROMETHEUS IC)
                    </h4>
                    <div className="grid md:grid-cols-3 gap-4">
                      <div className="bg-black/30 rounded-xl p-4 border border-blue-700/30">
                        <div className="font-medium text-blue-400 mb-3 flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
                          </svg>
                          Entry Rules
                        </div>
                        <ul className="text-sm text-gray-300 space-y-1.5">
                          <li className="flex items-start gap-2"><span className="text-blue-400 mt-1">•</span> Trading hours: 8:35 AM - 2:30 PM CT</li>
                          <li className="flex items-start gap-2"><span className="text-blue-400 mt-1">•</span> VIX range: 12-35 (12-30 Mon/Fri)</li>
                          <li className="flex items-start gap-2"><span className="text-blue-400 mt-1">•</span> Max 3 open positions</li>
                          <li className="flex items-start gap-2"><span className="text-blue-400 mt-1">•</span> Oracle confidence ≥ 60%</li>
                          <li className="flex items-start gap-2"><span className="text-blue-400 mt-1">•</span> Win probability ≥ 55%</li>
                        </ul>
                      </div>
                      <div className="bg-black/30 rounded-xl p-4 border border-purple-700/30">
                        <div className="font-medium text-purple-400 mb-3 flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                          </svg>
                          Strike Selection
                        </div>
                        <ul className="text-sm text-gray-300 space-y-1.5">
                          <li className="flex items-start gap-2"><span className="text-purple-400 mt-1">•</span> Target delta: ~10 (both sides)</li>
                          <li className="flex items-start gap-2"><span className="text-purple-400 mt-1">•</span> SPX $25 spread width</li>
                          <li className="flex items-start gap-2"><span className="text-purple-400 mt-1">•</span> Round to nearest $5</li>
                          <li className="flex items-start gap-2"><span className="text-purple-400 mt-1">•</span> Priority: Oracle → GEX → Delta</li>
                          <li className="flex items-start gap-2"><span className="text-purple-400 mt-1">•</span> 0DTE or 1DTE expiration</li>
                        </ul>
                      </div>
                      <div className="bg-black/30 rounded-xl p-4 border border-red-700/30">
                        <div className="font-medium text-red-400 mb-3 flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                          </svg>
                          Exit Rules
                        </div>
                        <ul className="text-sm text-gray-300 space-y-1.5">
                          <li className="flex items-start gap-2"><span className="text-green-400 mt-1">•</span> Profit target: 50% of credit</li>
                          <li className="flex items-start gap-2"><span className="text-red-400 mt-1">•</span> Stop loss: 200% of credit</li>
                          <li className="flex items-start gap-2"><span className="text-yellow-400 mt-1">•</span> Force exit: 10 min before close</li>
                          <li className="flex items-start gap-2"><span className="text-gray-400 mt-1">•</span> Expiration: Auto-settle (SPX)</li>
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

                  {/* Visual Activity Log */}
                  <div className="space-y-4">
                    {/* Header Bar */}
                    <div className="bg-gradient-to-r from-green-900/40 to-gray-900 rounded-lg p-4 border border-green-600/40">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 bg-green-600/30 rounded-lg flex items-center justify-center">
                            <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                            </svg>
                          </div>
                          <span className="font-bold text-green-300">PROMETHEUS IC - Oracle Scan Activity Log</span>
                        </div>
                        <span className="text-xs text-gray-400 bg-black/30 px-3 py-1 rounded">Live Feed</span>
                      </div>
                    </div>

                    {/* Activity Log Table */}
                    <div className="bg-black/40 rounded-xl border border-gray-700 overflow-hidden">
                      {/* Table Header */}
                      <div className="grid grid-cols-8 gap-2 px-4 py-3 bg-gray-800/80 border-b border-gray-700 text-xs font-medium text-gray-400 uppercase">
                        <div>Time</div>
                        <div>SPX</div>
                        <div>VIX</div>
                        <div>Oracle</div>
                        <div>Conf</div>
                        <div>Win%</div>
                        <div>Decision</div>
                        <div>Reason</div>
                      </div>

                      {/* Log Entries */}
                      <div className="divide-y divide-gray-800">
                        {/* Entry 1 - Trade Opened */}
                        <div className="grid grid-cols-8 gap-2 px-4 py-3 text-sm hover:bg-green-900/10 transition-colors cursor-pointer">
                          <div className="font-mono text-gray-300">10:35:22</div>
                          <div className="text-white">5982</div>
                          <div className="text-yellow-400">18.4</div>
                          <div><span className="px-2 py-0.5 bg-green-600/30 text-green-400 rounded text-xs">TRADE</span></div>
                          <div className="text-green-400">72%</div>
                          <div className="text-green-400">68%</div>
                          <div className="flex items-center gap-1">
                            <span className="text-green-400">✓</span>
                            <span className="text-green-400">OPENED</span>
                          </div>
                          <div className="text-gray-400 text-xs">IC 5945/6020</div>
                        </div>

                        {/* Entry 2 - Skipped */}
                        <div className="grid grid-cols-8 gap-2 px-4 py-3 text-sm hover:bg-gray-800/50 transition-colors cursor-pointer">
                          <div className="font-mono text-gray-300">10:20:15</div>
                          <div className="text-white">5978</div>
                          <div className="text-yellow-400">18.6</div>
                          <div><span className="px-2 py-0.5 bg-green-600/30 text-green-400 rounded text-xs">TRADE</span></div>
                          <div className="text-green-400">65%</div>
                          <div className="text-green-400">62%</div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-400">⏸</span>
                            <span className="text-gray-400">SKIP</span>
                          </div>
                          <div className="text-gray-400 text-xs">Max positions</div>
                        </div>

                        {/* Entry 3 - Low Conf */}
                        <div className="grid grid-cols-8 gap-2 px-4 py-3 text-sm hover:bg-gray-800/50 transition-colors cursor-pointer">
                          <div className="font-mono text-gray-300">10:05:08</div>
                          <div className="text-white">5975</div>
                          <div className="text-yellow-400">18.9</div>
                          <div><span className="px-2 py-0.5 bg-yellow-600/30 text-yellow-400 rounded text-xs">HOLD</span></div>
                          <div className="text-yellow-400">52%</div>
                          <div className="text-yellow-400">55%</div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-400">⏸</span>
                            <span className="text-gray-400">SKIP</span>
                          </div>
                          <div className="text-gray-400 text-xs">Conf &lt; 60%</div>
                        </div>

                        {/* Entry 4 - Oracle HOLD */}
                        <div className="grid grid-cols-8 gap-2 px-4 py-3 text-sm hover:bg-gray-800/50 transition-colors cursor-pointer">
                          <div className="font-mono text-gray-300">09:50:01</div>
                          <div className="text-white">5972</div>
                          <div className="text-yellow-400">19.1</div>
                          <div><span className="px-2 py-0.5 bg-gray-600/30 text-gray-400 rounded text-xs">SKIP</span></div>
                          <div className="text-gray-400">45%</div>
                          <div className="text-gray-400">48%</div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-400">⏸</span>
                            <span className="text-gray-400">SKIP</span>
                          </div>
                          <div className="text-gray-400 text-xs">Oracle: HOLD</div>
                        </div>

                        {/* Entry 5 - Trade Opened */}
                        <div className="grid grid-cols-8 gap-2 px-4 py-3 text-sm hover:bg-green-900/10 transition-colors cursor-pointer">
                          <div className="font-mono text-gray-300">09:35:44</div>
                          <div className="text-white">5968</div>
                          <div className="text-yellow-400">19.4</div>
                          <div><span className="px-2 py-0.5 bg-green-600/30 text-green-400 rounded text-xs">TRADE</span></div>
                          <div className="text-green-400">78%</div>
                          <div className="text-green-400">71%</div>
                          <div className="flex items-center gap-1">
                            <span className="text-green-400">✓</span>
                            <span className="text-green-400">OPENED</span>
                          </div>
                          <div className="text-gray-400 text-xs">IC 5935/6010</div>
                        </div>

                        {/* Entry 6 - Trade Opened */}
                        <div className="grid grid-cols-8 gap-2 px-4 py-3 text-sm hover:bg-green-900/10 transition-colors cursor-pointer">
                          <div className="font-mono text-gray-300">09:20:37</div>
                          <div className="text-white">5965</div>
                          <div className="text-yellow-400">19.2</div>
                          <div><span className="px-2 py-0.5 bg-green-600/30 text-green-400 rounded text-xs">TRADE</span></div>
                          <div className="text-green-400">71%</div>
                          <div className="text-green-400">65%</div>
                          <div className="flex items-center gap-1">
                            <span className="text-green-400">✓</span>
                            <span className="text-green-400">OPENED</span>
                          </div>
                          <div className="text-gray-400 text-xs">IC 5930/6005</div>
                        </div>

                        {/* Entry 7 - VIX Spike */}
                        <div className="grid grid-cols-8 gap-2 px-4 py-3 text-sm hover:bg-gray-800/50 transition-colors cursor-pointer">
                          <div className="font-mono text-gray-300">09:05:30</div>
                          <div className="text-white">5962</div>
                          <div className="text-red-400">19.5</div>
                          <div><span className="px-2 py-0.5 bg-gray-600/30 text-gray-400 rounded text-xs">SKIP</span></div>
                          <div className="text-gray-400">42%</div>
                          <div className="text-gray-400">45%</div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-400">⏸</span>
                            <span className="text-gray-400">SKIP</span>
                          </div>
                          <div className="text-gray-400 text-xs">VIX spike</div>
                        </div>

                        {/* Entry 8 - Pre-window */}
                        <div className="grid grid-cols-8 gap-2 px-4 py-3 text-sm bg-gray-900/50">
                          <div className="font-mono text-gray-500">08:50:23</div>
                          <div className="text-gray-500">5960</div>
                          <div className="text-gray-500">20.1</div>
                          <div><span className="px-2 py-0.5 bg-gray-700/30 text-gray-500 rounded text-xs">N/A</span></div>
                          <div className="text-gray-500">--</div>
                          <div className="text-gray-500">--</div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-500">⏸</span>
                            <span className="text-gray-500">SKIP</span>
                          </div>
                          <div className="text-gray-500 text-xs">Pre-window</div>
                        </div>
                      </div>

                      {/* Stats Footer */}
                      <div className="bg-gray-800/60 px-4 py-3 border-t border-gray-700">
                        <div className="flex items-center justify-between">
                          <span className="text-gray-400 text-sm font-medium">TODAY'S STATS:</span>
                          <div className="flex items-center gap-4 text-sm">
                            <span className="text-gray-300"><strong className="text-white">8</strong> scans</span>
                            <span className="text-green-400"><strong>3</strong> trades</span>
                            <span className="text-gray-400"><strong>5</strong> skips</span>
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded"><strong>37.5%</strong> trade rate</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Oracle Reasoning Expansion Panel */}
                    <div className="bg-gradient-to-r from-green-900/30 to-gray-900 rounded-xl border border-green-600/30 overflow-hidden">
                      <div className="px-4 py-3 bg-green-900/40 border-b border-green-600/30">
                        <div className="flex items-center gap-2">
                          <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                          <span className="font-medium text-green-300">Click row for full Oracle reasoning</span>
                          <span className="text-xs text-gray-400 ml-2">→ Example: 10:35:22</span>
                        </div>
                      </div>
                      <div className="p-4">
                        {/* Decision Header */}
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-green-400 bg-black/40 px-2 py-1 rounded">10:35:22</span>
                            <span className="px-3 py-1 bg-green-600/30 text-green-400 rounded-lg font-medium">TRADE_FULL Decision</span>
                          </div>
                          <span className="text-gray-400 text-sm">IC 5945/6020</span>
                        </div>

                        {/* Oracle Reasoning */}
                        <div className="bg-black/30 rounded-lg p-4 mb-4 border-l-4 border-green-500">
                          <p className="text-gray-300 italic">
                            "Strong IC conditions. VIX 18.4 in sweet spot. Gamma regime POSITIVE = mean reversion favorable.
                            Call wall at 6050, put wall at 5920 provide cushion. Day: Wednesday (best IC day historically)."
                          </p>
                        </div>

                        {/* Top Factors Grid */}
                        <div className="grid grid-cols-3 gap-3 mb-4">
                          <div className="bg-black/40 rounded-lg p-3 border border-green-700/30">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-gray-400 text-xs">1. vix_level</span>
                              <span className="text-green-400 font-bold">+15%</span>
                            </div>
                            <div className="text-xs text-gray-500">favorable range</div>
                            <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                              <div className="h-full w-[75%] bg-gradient-to-r from-green-600 to-green-400 rounded-full"></div>
                            </div>
                          </div>
                          <div className="bg-black/40 rounded-lg p-3 border border-green-700/30">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-gray-400 text-xs">2. gex_regime</span>
                              <span className="text-green-400 font-bold">+12%</span>
                            </div>
                            <div className="text-xs text-gray-500">positive gamma</div>
                            <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                              <div className="h-full w-[65%] bg-gradient-to-r from-green-600 to-green-400 rounded-full"></div>
                            </div>
                          </div>
                          <div className="bg-black/40 rounded-lg p-3 border border-green-700/30">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-gray-400 text-xs">3. day_of_week</span>
                              <span className="text-green-400 font-bold">+8%</span>
                            </div>
                            <div className="text-xs text-gray-500">mid-week</div>
                            <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                              <div className="h-full w-[50%] bg-gradient-to-r from-green-600 to-green-400 rounded-full"></div>
                            </div>
                          </div>
                        </div>

                        {/* Suggested Strikes */}
                        <div className="flex items-center justify-center gap-4 p-3 bg-green-900/20 rounded-lg border border-green-600/30">
                          <span className="text-gray-400">Suggested Strikes:</span>
                          <span className="px-3 py-1 bg-red-600/20 text-red-400 rounded font-mono font-bold">5945P</span>
                          <span className="text-gray-500">/</span>
                          <span className="px-3 py-1 bg-green-600/20 text-green-400 rounded font-mono font-bold">6020C</span>
                          <span className="text-xs text-gray-500">(from Oracle)</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PART 5: DAILY P&L BREAKDOWN */}
                <div className="bg-gray-800 rounded-xl p-6 border border-yellow-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-yellow-600 rounded-lg flex items-center justify-center text-xl">5</span>
                    <span className="text-yellow-400">Daily P&L Breakdown Format</span>
                  </h2>

                  {/* Visual P&L Display */}
                  <div className="space-y-4">
                    {/* Header */}
                    <div className="bg-gradient-to-r from-yellow-900/40 to-gray-900 rounded-lg p-4 border border-yellow-600/40">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 bg-yellow-600/30 rounded-lg flex items-center justify-center">
                            <svg className="w-5 h-5 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          </div>
                          <span className="font-bold text-yellow-300">PROMETHEUS - Daily P&L Breakdown (Last 14 Days)</span>
                        </div>
                      </div>
                    </div>

                    {/* P&L Table */}
                    <div className="bg-black/40 rounded-xl border border-gray-700 overflow-hidden">
                      {/* Table Header */}
                      <div className="grid grid-cols-6 gap-2 px-4 py-3 bg-gray-800/80 border-b border-gray-700 text-xs font-medium text-gray-400 uppercase">
                        <div>Date</div>
                        <div className="text-right">IC Earned</div>
                        <div className="text-right">Box Cost</div>
                        <div className="text-right">Net P&L</div>
                        <div className="text-right">Cumulative</div>
                        <div className="text-center">Trades</div>
                      </div>

                      {/* Table Rows */}
                      <div className="divide-y divide-gray-800">
                        {/* Row 1 */}
                        <div className="grid grid-cols-6 gap-2 px-4 py-3 text-sm hover:bg-yellow-900/10 transition-colors">
                          <div className="font-mono text-gray-300">2026-01-30</div>
                          <div className="text-right text-green-400 font-medium">$425.00</div>
                          <div className="text-right text-red-400">-$12.50</div>
                          <div className="text-right">
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded font-medium">+$412.50</span>
                          </div>
                          <div className="text-right text-white font-medium">$3,247.50</div>
                          <div className="text-center"><span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded">3</span></div>
                        </div>

                        {/* Row 2 */}
                        <div className="grid grid-cols-6 gap-2 px-4 py-3 text-sm hover:bg-yellow-900/10 transition-colors">
                          <div className="font-mono text-gray-300">2026-01-29</div>
                          <div className="text-right text-green-400 font-medium">$380.00</div>
                          <div className="text-right text-red-400">-$12.50</div>
                          <div className="text-right">
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded font-medium">+$367.50</span>
                          </div>
                          <div className="text-right text-white font-medium">$2,835.00</div>
                          <div className="text-center"><span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded">2</span></div>
                        </div>

                        {/* Row 3 - Loss */}
                        <div className="grid grid-cols-6 gap-2 px-4 py-3 text-sm hover:bg-red-900/10 transition-colors bg-red-900/5">
                          <div className="font-mono text-gray-300">2026-01-28</div>
                          <div className="text-right text-red-400 font-medium">-$125.00</div>
                          <div className="text-right text-red-400">-$12.50</div>
                          <div className="text-right">
                            <span className="px-2 py-0.5 bg-red-600/20 text-red-400 rounded font-medium">-$137.50</span>
                          </div>
                          <div className="text-right text-white font-medium">$2,467.50</div>
                          <div className="text-center"><span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded">2</span></div>
                        </div>

                        {/* Row 4 */}
                        <div className="grid grid-cols-6 gap-2 px-4 py-3 text-sm hover:bg-yellow-900/10 transition-colors">
                          <div className="font-mono text-gray-300">2026-01-27</div>
                          <div className="text-right text-green-400 font-medium">$290.00</div>
                          <div className="text-right text-red-400">-$12.50</div>
                          <div className="text-right">
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded font-medium">+$277.50</span>
                          </div>
                          <div className="text-right text-white font-medium">$2,605.00</div>
                          <div className="text-center"><span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded">2</span></div>
                        </div>

                        {/* Row 5 */}
                        <div className="grid grid-cols-6 gap-2 px-4 py-3 text-sm hover:bg-yellow-900/10 transition-colors">
                          <div className="font-mono text-gray-300">2026-01-24</div>
                          <div className="text-right text-green-400 font-medium">$510.00</div>
                          <div className="text-right text-red-400">-$12.50</div>
                          <div className="text-right">
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded font-medium">+$497.50</span>
                          </div>
                          <div className="text-right text-white font-medium">$2,327.50</div>
                          <div className="text-center"><span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded">3</span></div>
                        </div>

                        {/* Row 6 */}
                        <div className="grid grid-cols-6 gap-2 px-4 py-3 text-sm hover:bg-yellow-900/10 transition-colors">
                          <div className="font-mono text-gray-300">2026-01-23</div>
                          <div className="text-right text-green-400 font-medium">$445.00</div>
                          <div className="text-right text-red-400">-$12.50</div>
                          <div className="text-right">
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded font-medium">+$432.50</span>
                          </div>
                          <div className="text-right text-white font-medium">$1,830.00</div>
                          <div className="text-center"><span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded">3</span></div>
                        </div>

                        {/* Row 7 */}
                        <div className="grid grid-cols-6 gap-2 px-4 py-3 text-sm hover:bg-yellow-900/10 transition-colors">
                          <div className="font-mono text-gray-300">2026-01-22</div>
                          <div className="text-right text-green-400 font-medium">$315.00</div>
                          <div className="text-right text-red-400">-$12.50</div>
                          <div className="text-right">
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded font-medium">+$302.50</span>
                          </div>
                          <div className="text-right text-white font-medium">$1,397.50</div>
                          <div className="text-center"><span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded">2</span></div>
                        </div>

                        {/* More indicator */}
                        <div className="px-4 py-2 text-center text-gray-500 text-sm bg-gray-900/30">
                          ... 7 more days
                        </div>
                      </div>
                    </div>

                    {/* Legend & Break-Even Analysis */}
                    <div className="grid md:grid-cols-2 gap-4">
                      {/* Legend */}
                      <div className="bg-black/30 rounded-xl p-4 border border-gray-700">
                        <h4 className="font-medium text-yellow-400 mb-3 flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          Legend
                        </h4>
                        <div className="space-y-2 text-sm">
                          <div className="flex items-start gap-3">
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded text-xs shrink-0">IC EARNED</span>
                            <span className="text-gray-400">Premium collected from Iron Condor trades</span>
                          </div>
                          <div className="flex items-start gap-3">
                            <span className="px-2 py-0.5 bg-red-600/20 text-red-400 rounded text-xs shrink-0">BOX COST</span>
                            <span className="text-gray-400">Daily interest accrual on borrowed capital</span>
                          </div>
                          <div className="flex items-start gap-3">
                            <span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded text-xs shrink-0">NET P&L</span>
                            <span className="text-gray-400">IC Earned - Box Cost (what you actually made)</span>
                          </div>
                        </div>
                      </div>

                      {/* Break-Even Analysis */}
                      <div className="bg-gradient-to-br from-yellow-900/30 to-gray-900 rounded-xl p-4 border border-yellow-600/30">
                        <h4 className="font-medium text-yellow-400 mb-3 flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                          </svg>
                          Break-Even Analysis
                        </h4>
                        <div className="space-y-3">
                          <div className="flex items-center justify-between p-2 bg-black/30 rounded-lg">
                            <span className="text-gray-400 text-sm">Daily Box Cost</span>
                            <div className="flex items-center gap-2">
                              <span className="text-red-400 font-bold">$12.50</span>
                              <span className="text-gray-500 text-xs">→ Need IC returns &gt; $12.50/day</span>
                            </div>
                          </div>
                          <div className="flex items-center justify-between p-2 bg-black/30 rounded-lg">
                            <span className="text-gray-400 text-sm">Avg IC/Day</span>
                            <span className="text-green-400 font-bold">$377.14</span>
                          </div>
                          <div className="flex items-center justify-between p-3 bg-green-900/30 rounded-lg border border-green-600/30">
                            <span className="text-green-300 font-medium">Cost Efficiency</span>
                            <span className="text-2xl font-bold text-green-400">30.2x</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PART 6: RISK ALERTS */}
                <div className="bg-gray-800 rounded-xl p-6 border border-red-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-red-600 rounded-lg flex items-center justify-center text-xl">6</span>
                    <span className="text-red-400">Risk Alerts Display</span>
                  </h2>

                  {/* Visual Risk Alerts */}
                  <div className="space-y-4">
                    {/* Header */}
                    <div className="bg-gradient-to-r from-red-900/40 to-gray-900 rounded-lg p-4 border border-red-600/40">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-red-600/30 rounded-lg flex items-center justify-center animate-pulse">
                          <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                        </div>
                        <span className="font-bold text-red-300">PROMETHEUS RISK ALERTS</span>
                      </div>
                    </div>

                    {/* Alert Cards */}
                    <div className="space-y-3">
                      {/* CRITICAL Alert */}
                      <div className="bg-gradient-to-r from-red-900/50 to-red-900/20 rounded-xl border-2 border-red-500 overflow-hidden">
                        <div className="px-4 py-2 bg-red-600 flex items-center gap-2">
                          <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                          </svg>
                          <span className="font-bold text-white uppercase text-sm">Critical</span>
                        </div>
                        <div className="p-4">
                          <div className="flex items-start gap-3">
                            <div className="w-8 h-8 bg-red-600/30 rounded-lg flex items-center justify-center shrink-0">
                              <span className="text-lg">⛔</span>
                            </div>
                            <div className="flex-1">
                              <div className="font-bold text-red-300 mb-1">BOX ROLL NEEDED</div>
                              <div className="text-gray-300 text-sm mb-2">
                                Position <span className="font-mono text-red-400">PROM-20241015</span> expires in <span className="text-red-400 font-bold">2 days!</span>
                              </div>
                              <div className="flex items-center gap-2 text-sm">
                                <span className="text-gray-400">Action:</span>
                                <span className="px-2 py-0.5 bg-red-600/30 text-red-300 rounded">Roll to new expiration or close position</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* WARNING Alert */}
                      <div className="bg-gradient-to-r from-yellow-900/40 to-yellow-900/10 rounded-xl border-2 border-yellow-500/60 overflow-hidden">
                        <div className="px-4 py-2 bg-yellow-600 flex items-center gap-2">
                          <svg className="w-4 h-4 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                          <span className="font-bold text-black uppercase text-sm">Warning</span>
                        </div>
                        <div className="p-4">
                          <div className="flex items-start gap-3">
                            <div className="w-8 h-8 bg-yellow-600/30 rounded-lg flex items-center justify-center shrink-0">
                              <span className="text-lg">⚠️</span>
                            </div>
                            <div className="flex-1">
                              <div className="font-bold text-yellow-300 mb-1">IC NEAR STOP</div>
                              <div className="text-gray-300 text-sm mb-2">
                                Position <span className="font-mono text-yellow-400">IC-5945/6020</span> at <span className="text-yellow-400 font-bold">180%</span> of credit
                              </div>
                              <div className="flex items-center gap-4 text-sm">
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-400">Current:</span>
                                  <span className="font-mono text-yellow-400">$3.60</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-400">Entry:</span>
                                  <span className="font-mono text-gray-300">$2.00</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-400">Stop:</span>
                                  <span className="font-mono text-red-400">$4.00</span>
                                </div>
                              </div>
                              {/* Progress bar showing proximity to stop */}
                              <div className="mt-3 h-2 bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full w-[90%] bg-gradient-to-r from-yellow-500 to-red-500 rounded-full"></div>
                              </div>
                              <div className="flex justify-between text-xs text-gray-500 mt-1">
                                <span>Entry</span>
                                <span>Stop (200%)</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* INFO Alert */}
                      <div className="bg-gradient-to-r from-blue-900/30 to-blue-900/10 rounded-xl border border-blue-500/40 overflow-hidden">
                        <div className="px-4 py-2 bg-blue-600/80 flex items-center gap-2">
                          <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          <span className="font-bold text-white uppercase text-sm">Info</span>
                        </div>
                        <div className="p-4">
                          <div className="flex items-start gap-3">
                            <div className="w-8 h-8 bg-blue-600/30 rounded-lg flex items-center justify-center shrink-0">
                              <span className="text-lg">ℹ️</span>
                            </div>
                            <div className="flex-1">
                              <div className="font-bold text-blue-300 mb-1">MARGIN UTILIZATION</div>
                              <div className="text-gray-300 text-sm mb-2">
                                <span className="text-blue-400 font-bold">72%</span> of available margin in use
                              </div>
                              <div className="text-sm text-gray-400">
                                Consider reducing IC positions if approaching 85%
                              </div>
                              {/* Margin utilization bar */}
                              <div className="mt-3 h-2 bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full w-[72%] bg-gradient-to-r from-blue-500 to-blue-400 rounded-full"></div>
                              </div>
                              <div className="flex justify-between text-xs text-gray-500 mt-1">
                                <span>0%</span>
                                <span className="text-yellow-400">85% Warning</span>
                                <span className="text-red-400">95% Critical</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Alert Thresholds Reference */}
                    <div className="bg-black/40 rounded-xl p-4 border border-gray-700">
                      <h4 className="font-medium text-gray-300 mb-4 flex items-center gap-2">
                        <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        Alert Thresholds
                      </h4>
                      <div className="grid md:grid-cols-3 gap-4">
                        {/* Box Roll */}
                        <div className="bg-gray-900/50 rounded-lg p-3">
                          <div className="font-medium text-gray-300 mb-2 text-sm">Box Roll</div>
                          <div className="space-y-1 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">DTE ≤ 30</span>
                              <span className="px-2 py-0.5 bg-yellow-600/30 text-yellow-400 rounded">Warning</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">DTE ≤ 7</span>
                              <span className="px-2 py-0.5 bg-red-600/30 text-red-400 rounded">Critical</span>
                            </div>
                          </div>
                        </div>

                        {/* IC Stop */}
                        <div className="bg-gray-900/50 rounded-lg p-3">
                          <div className="font-medium text-gray-300 mb-2 text-sm">IC Stop</div>
                          <div className="space-y-1 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">150%</span>
                              <span className="px-2 py-0.5 bg-yellow-600/30 text-yellow-400 rounded">Warning</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">180%</span>
                              <span className="px-2 py-0.5 bg-red-600/30 text-red-400 rounded">Critical</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">200%</span>
                              <span className="px-2 py-0.5 bg-red-600 text-white rounded">Auto-close</span>
                            </div>
                          </div>
                        </div>

                        {/* Margin */}
                        <div className="bg-gray-900/50 rounded-lg p-3">
                          <div className="font-medium text-gray-300 mb-2 text-sm">Margin</div>
                          <div className="space-y-1 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">70%</span>
                              <span className="px-2 py-0.5 bg-blue-600/30 text-blue-400 rounded">Info</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">85%</span>
                              <span className="px-2 py-0.5 bg-yellow-600/30 text-yellow-400 rounded">Warning</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">95%</span>
                              <span className="px-2 py-0.5 bg-red-600/30 text-red-400 rounded">Critical</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PART 7: DATA FLOW DIAGRAM */}
                <div className="bg-gray-800 rounded-xl p-6 border border-indigo-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center text-xl">7</span>
                    <span className="text-indigo-400">Complete Data Flow</span>
                  </h2>

                  {/* Visual Data Flow Architecture */}
                  <div className="space-y-6">
                    {/* Header */}
                    <div className="bg-gradient-to-r from-indigo-900/40 to-gray-900 rounded-lg p-4 border border-indigo-600/40 text-center">
                      <span className="font-bold text-indigo-300">PROMETHEUS COMPLETE DATA FLOW</span>
                    </div>

                    {/* Data Sources Layer */}
                    <div>
                      <div className="text-xs text-gray-500 uppercase tracking-wider mb-3 text-center">External Data Sources</div>
                      <div className="grid grid-cols-3 gap-4">
                        {/* Tradier */}
                        <div className="bg-gradient-to-br from-blue-900/40 to-blue-900/20 rounded-xl p-4 border border-blue-500/40 text-center">
                          <div className="w-12 h-12 bg-blue-600/30 rounded-xl mx-auto mb-3 flex items-center justify-center">
                            <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                            </svg>
                          </div>
                          <div className="font-bold text-blue-300">TRADIER</div>
                          <div className="text-xs text-gray-400 mt-1">(Production API)</div>
                          <div className="text-xs text-gray-500 mt-2">Options quotes, execution</div>
                        </div>

                        {/* FRED API */}
                        <div className="bg-gradient-to-br from-green-900/40 to-green-900/20 rounded-xl p-4 border border-green-500/40 text-center">
                          <div className="w-12 h-12 bg-green-600/30 rounded-xl mx-auto mb-3 flex items-center justify-center">
                            <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          </div>
                          <div className="font-bold text-green-300">FRED API</div>
                          <div className="text-xs text-gray-400 mt-1">(Fed Funds Rate)</div>
                          <div className="text-xs text-gray-500 mt-2">Interest rate benchmarks</div>
                        </div>

                        {/* GEX Calculator */}
                        <div className="bg-gradient-to-br from-purple-900/40 to-purple-900/20 rounded-xl p-4 border border-purple-500/40 text-center">
                          <div className="w-12 h-12 bg-purple-600/30 rounded-xl mx-auto mb-3 flex items-center justify-center">
                            <svg className="w-6 h-6 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                            </svg>
                          </div>
                          <div className="font-bold text-purple-300">GEX CALC</div>
                          <div className="text-xs text-gray-400 mt-1">(Gamma Engine)</div>
                          <div className="text-xs text-gray-500 mt-2">Market structure signals</div>
                        </div>
                      </div>
                    </div>

                    {/* Arrow Down */}
                    <div className="flex justify-center">
                      <div className="w-0 h-0 border-l-[20px] border-l-transparent border-r-[20px] border-r-transparent border-t-[16px] border-t-indigo-500"></div>
                    </div>

                    {/* Prometheus Engine */}
                    <div className="bg-gradient-to-br from-indigo-900/50 to-gray-900 rounded-2xl border-2 border-indigo-500/60 p-5">
                      <div className="text-center mb-4">
                        <span className="px-4 py-1.5 bg-indigo-600 rounded-lg font-bold text-white">PROMETHEUS ENGINE</span>
                      </div>

                      {/* Two Managers */}
                      <div className="grid md:grid-cols-2 gap-4 mb-4">
                        {/* Box Spread Manager */}
                        <div className="bg-black/40 rounded-xl p-4 border border-blue-600/40">
                          <div className="font-bold text-blue-300 mb-3 flex items-center gap-2">
                            <div className="w-6 h-6 bg-blue-600/30 rounded flex items-center justify-center">
                              <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                              </svg>
                            </div>
                            Box Spread Manager
                          </div>
                          <ul className="text-sm text-gray-300 space-y-1.5">
                            <li className="flex items-center gap-2">
                              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full"></span>
                              Open/Close positions
                            </li>
                            <li className="flex items-center gap-2">
                              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full"></span>
                              MTM Calculation
                            </li>
                            <li className="flex items-center gap-2">
                              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full"></span>
                              Roll Logic
                            </li>
                          </ul>
                        </div>

                        {/* IC Signal Generator */}
                        <div className="bg-black/40 rounded-xl p-4 border border-orange-600/40">
                          <div className="font-bold text-orange-300 mb-3 flex items-center gap-2">
                            <div className="w-6 h-6 bg-orange-600/30 rounded flex items-center justify-center">
                              <svg className="w-4 h-4 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                              </svg>
                            </div>
                            IC Signal Generator
                          </div>
                          <ul className="text-sm text-gray-300 space-y-1.5">
                            <li className="flex items-center gap-2">
                              <span className="w-1.5 h-1.5 bg-orange-400 rounded-full"></span>
                              Uses Oracle
                            </li>
                            <li className="flex items-center gap-2">
                              <span className="w-1.5 h-1.5 bg-orange-400 rounded-full"></span>
                              PEGASUS rules
                            </li>
                            <li className="flex items-center gap-2">
                              <span className="w-1.5 h-1.5 bg-orange-400 rounded-full"></span>
                              Strike selection
                            </li>
                          </ul>
                        </div>
                      </div>

                      {/* Capital Allocator */}
                      <div className="bg-gradient-to-r from-emerald-900/40 to-gray-900 rounded-xl p-4 border border-emerald-500/40">
                        <div className="font-bold text-emerald-300 mb-3 text-center">CAPITAL ALLOCATOR</div>
                        <div className="flex items-center justify-center gap-8">
                          <div className="text-center">
                            <div className="text-gray-400 text-xs mb-1">Total Borrowed</div>
                            <div className="text-emerald-400 font-bold">100%</div>
                          </div>
                          <div className="text-gray-500">→</div>
                          <div className="flex gap-4">
                            <div className="text-center px-4 py-2 bg-yellow-900/30 rounded-lg border border-yellow-600/30">
                              <div className="text-yellow-400 font-bold">10%</div>
                              <div className="text-gray-400 text-xs">Reserve</div>
                            </div>
                            <div className="text-center px-4 py-2 bg-green-900/30 rounded-lg border border-green-600/30">
                              <div className="text-green-400 font-bold">90%</div>
                              <div className="text-gray-400 text-xs">IC Trading</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Arrow Down */}
                    <div className="flex justify-center">
                      <div className="w-0 h-0 border-l-[20px] border-l-transparent border-r-[20px] border-r-transparent border-t-[16px] border-t-indigo-500"></div>
                    </div>

                    {/* PostgreSQL Database */}
                    <div className="bg-gradient-to-br from-cyan-900/40 to-gray-900 rounded-xl p-5 border border-cyan-500/40">
                      <div className="flex items-center justify-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-cyan-600/30 rounded-lg flex items-center justify-center">
                          <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                          </svg>
                        </div>
                        <span className="font-bold text-cyan-300">POSTGRESQL DB</span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                        <div className="px-3 py-2 bg-black/40 rounded-lg border border-gray-700">
                          <span className="text-cyan-400 font-mono">prometheus_box_positions</span>
                          <div className="text-gray-500 text-[10px]">Open boxes</div>
                        </div>
                        <div className="px-3 py-2 bg-black/40 rounded-lg border border-gray-700">
                          <span className="text-cyan-400 font-mono">prometheus_box_closed</span>
                          <div className="text-gray-500 text-[10px]">Historical</div>
                        </div>
                        <div className="px-3 py-2 bg-black/40 rounded-lg border border-gray-700">
                          <span className="text-cyan-400 font-mono">prometheus_ic_positions</span>
                          <div className="text-gray-500 text-[10px]">Open ICs</div>
                        </div>
                        <div className="px-3 py-2 bg-black/40 rounded-lg border border-gray-700">
                          <span className="text-cyan-400 font-mono">prometheus_ic_closed</span>
                          <div className="text-gray-500 text-[10px]">IC history</div>
                        </div>
                        <div className="px-3 py-2 bg-black/40 rounded-lg border border-gray-700">
                          <span className="text-cyan-400 font-mono">prometheus_scan_activity</span>
                          <div className="text-gray-500 text-[10px]">Oracle logs</div>
                        </div>
                        <div className="px-3 py-2 bg-black/40 rounded-lg border border-gray-700">
                          <span className="text-cyan-400 font-mono">prometheus_equity_snapshots</span>
                          <div className="text-gray-500 text-[10px]">Equity curve</div>
                        </div>
                      </div>
                    </div>

                    {/* Arrow Down */}
                    <div className="flex justify-center">
                      <div className="w-0 h-0 border-l-[20px] border-l-transparent border-r-[20px] border-r-transparent border-t-[16px] border-t-indigo-500"></div>
                    </div>

                    {/* Frontend Dashboard */}
                    <div className="bg-gradient-to-br from-pink-900/40 to-gray-900 rounded-xl p-5 border border-pink-500/40">
                      <div className="flex items-center justify-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-pink-600/30 rounded-lg flex items-center justify-center">
                          <svg className="w-5 h-5 text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                          </svg>
                        </div>
                        <span className="font-bold text-pink-300">FRONTEND DASHBOARD</span>
                      </div>
                      <div className="flex items-center justify-center gap-2 mb-3">
                        <span className="px-3 py-1 bg-pink-600/30 text-pink-300 rounded-lg text-sm">Overview</span>
                        <span className="px-3 py-1 bg-pink-600/30 text-pink-300 rounded-lg text-sm">Boxes</span>
                        <span className="px-3 py-1 bg-pink-600/30 text-pink-300 rounded-lg text-sm">IC</span>
                        <span className="px-3 py-1 bg-pink-600/30 text-pink-300 rounded-lg text-sm">Analytics</span>
                      </div>
                      <div className="text-center text-sm text-gray-400">
                        Refresh: <span className="text-pink-400 font-mono">15-60 sec</span> (configurable)
                      </div>
                    </div>
                  </div>
                </div>

                {/* PART 8: DAILY TIMELINE */}
                <div className="bg-gray-800 rounded-xl p-6 border border-teal-500/30">
                  <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                    <span className="w-10 h-10 bg-teal-600 rounded-lg flex items-center justify-center text-xl">8</span>
                    <span className="text-teal-400">Daily Timeline (All Times CT)</span>
                  </h2>

                  {/* Visual Timeline */}
                  <div className="relative">
                    {/* Timeline line */}
                    <div className="absolute left-[60px] top-0 bottom-0 w-0.5 bg-gradient-to-b from-yellow-500 via-blue-500 to-gray-600"></div>

                    <div className="space-y-4">
                      {/* 8:00 AM - System Startup */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-sm text-yellow-400 font-bold">8:00 AM</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-yellow-500 border-4 border-gray-800 z-10 mt-1 shrink-0"></div>
                        <div className="flex-1 bg-gradient-to-r from-yellow-900/30 to-gray-900 rounded-lg p-3 border border-yellow-600/30">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                            <span className="font-bold text-yellow-300">System Startup</span>
                          </div>
                          <p className="text-sm text-gray-400">Connect to APIs, load positions, check rates</p>
                        </div>
                      </div>

                      {/* 8:30 AM - Market Open */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-sm text-green-400 font-bold">8:30 AM</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-green-500 border-4 border-gray-800 z-10 mt-1 shrink-0"></div>
                        <div className="flex-1 bg-gradient-to-r from-green-900/30 to-gray-900 rounded-lg p-3 border border-green-600/30">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <span className="font-bold text-green-300">Market Open</span>
                          </div>
                          <p className="text-sm text-gray-400">Begin box spread monitoring, IC trading preparation</p>
                        </div>
                      </div>

                      {/* 8:35 AM - IC Trading Starts */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-sm text-blue-400 font-bold">8:35 AM</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-blue-500 border-4 border-gray-800 z-10 mt-1 shrink-0"></div>
                        <div className="flex-1 bg-gradient-to-r from-blue-900/30 to-gray-900 rounded-lg p-3 border border-blue-600/30">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                            <span className="font-bold text-blue-300">IC Trading Starts</span>
                          </div>
                          <p className="text-sm text-gray-400">First Oracle check, begin 5-15 min scan cycle</p>
                        </div>
                      </div>

                      {/* 9:30 AM - Box Position Check */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-sm text-orange-400 font-bold">9:30 AM</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-orange-500 border-4 border-gray-800 z-10 mt-1 shrink-0"></div>
                        <div className="flex-1 bg-gradient-to-r from-orange-900/30 to-gray-900 rounded-lg p-3 border border-orange-600/30">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                            </svg>
                            <span className="font-bold text-orange-300">Box Position Check</span>
                          </div>
                          <p className="text-sm text-gray-400">Daily box MTM update, roll decision evaluation</p>
                        </div>
                      </div>

                      {/* Ongoing - IC Scan Cycle */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-xs text-purple-400 font-bold">Ongoing</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-purple-500 border-4 border-gray-800 z-10 mt-1 shrink-0 animate-pulse"></div>
                        <div className="flex-1 bg-gradient-to-r from-purple-900/30 to-gray-900 rounded-lg p-3 border border-purple-600/30 border-dashed">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            <span className="font-bold text-purple-300">IC Scan Cycle</span>
                            <span className="text-xs text-purple-400 bg-purple-600/20 px-2 py-0.5 rounded">Every 5-15 min</span>
                          </div>
                          <p className="text-sm text-gray-400">Oracle check → trade if approved</p>
                        </div>
                      </div>

                      {/* 2:30 PM - IC Entry Stops */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-sm text-blue-400 font-bold">2:30 PM</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-blue-500 border-4 border-gray-800 z-10 mt-1 shrink-0"></div>
                        <div className="flex-1 bg-gradient-to-r from-blue-900/30 to-gray-900 rounded-lg p-3 border border-blue-600/30">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <span className="font-bold text-blue-300">IC Entry Stops</span>
                          </div>
                          <p className="text-sm text-gray-400">No new IC trades, only manage existing</p>
                        </div>
                      </div>

                      {/* 2:50 PM - Force Exit */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-sm text-red-400 font-bold">2:50 PM</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-red-500 border-4 border-gray-800 z-10 mt-1 shrink-0"></div>
                        <div className="flex-1 bg-gradient-to-r from-red-900/30 to-gray-900 rounded-lg p-3 border border-red-600/30">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <span className="font-bold text-red-300">Force Exit</span>
                          </div>
                          <p className="text-sm text-gray-400">Close all IC positions 10 min before market close</p>
                        </div>
                      </div>

                      {/* 3:00 PM - Market Close */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-sm text-gray-400 font-bold">3:00 PM</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-gray-500 border-4 border-gray-800 z-10 mt-1 shrink-0"></div>
                        <div className="flex-1 bg-gradient-to-r from-gray-700/30 to-gray-900 rounded-lg p-3 border border-gray-600/30">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                            </svg>
                            <span className="font-bold text-gray-300">Market Close</span>
                          </div>
                          <p className="text-sm text-gray-400">0DTE ICs auto-settle (SPX cash settled)</p>
                        </div>
                      </div>

                      {/* After Hours - Daily Summary */}
                      <div className="flex items-start gap-4 relative">
                        <div className="w-[55px] text-right shrink-0">
                          <span className="font-mono text-xs text-gray-500 font-bold">After Hrs</span>
                        </div>
                        <div className="w-4 h-4 rounded-full bg-gray-600 border-4 border-gray-800 z-10 mt-1 shrink-0"></div>
                        <div className="flex-1 bg-gradient-to-r from-gray-800/30 to-gray-900 rounded-lg p-3 border border-gray-700/30">
                          <div className="flex items-center gap-2 mb-1">
                            <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            <span className="font-bold text-gray-400">Daily Summary</span>
                          </div>
                          <p className="text-sm text-gray-500">Update equity snapshots, log day results</p>
                        </div>
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
  )
}
