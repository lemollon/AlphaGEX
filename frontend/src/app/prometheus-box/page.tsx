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
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'ic-trading' | 'analytics' | 'education'>('overview')
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
                {/* THE STORY - How PROMETHEUS Works */}
                <div className="bg-gradient-to-r from-gray-800 via-gray-800 to-gray-800 rounded-lg p-6 border border-orange-500/30">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    <span className="text-2xl">📖</span> How PROMETHEUS Works
                  </h2>
                  <div className="grid md:grid-cols-4 gap-4">
                    {/* Step 1: Borrow */}
                    <div className="relative">
                      <div className="bg-blue-900/40 rounded-lg p-4 border border-blue-600/50 h-full">
                        <div className="text-3xl mb-2">1️⃣</div>
                        <div className="text-lg font-bold text-blue-400">BORROW</div>
                        <div className="text-sm text-gray-300 mt-2">
                          Sell SPX box spreads to generate cash at low rates (~4-5%/year)
                        </div>
                        <div className="mt-3 text-xs text-gray-400">
                          <strong>Capital Locked:</strong> Strike width × 100 per contract as collateral
                        </div>
                      </div>
                      <div className="hidden md:block absolute -right-2 top-1/2 text-2xl z-10">→</div>
                    </div>
                    {/* Step 2: Deploy */}
                    <div className="relative">
                      <div className="bg-orange-900/40 rounded-lg p-4 border border-orange-600/50 h-full">
                        <div className="text-3xl mb-2">2️⃣</div>
                        <div className="text-lg font-bold text-orange-400">DEPLOY</div>
                        <div className="text-sm text-gray-300 mt-2">
                          Use borrowed capital to trade PROMETHEUS Iron Condors on SPX
                        </div>
                        <div className="mt-3 text-xs text-gray-400">
                          <strong>Strategy:</strong> 0DTE SPX Iron Condors, Oracle-approved
                        </div>
                      </div>
                      <div className="hidden md:block absolute -right-2 top-1/2 text-2xl z-10">→</div>
                    </div>
                    {/* Step 3: Earn */}
                    <div className="relative">
                      <div className="bg-green-900/40 rounded-lg p-4 border border-green-600/50 h-full">
                        <div className="text-3xl mb-2">3️⃣</div>
                        <div className="text-lg font-bold text-green-400">EARN</div>
                        <div className="text-sm text-gray-300 mt-2">
                          IC trading generates premium income (~20-40%/year target)
                        </div>
                        <div className="mt-3 text-xs text-gray-400">
                          <strong>Daily:</strong> Premium collected minus any losses
                        </div>
                      </div>
                      <div className="hidden md:block absolute -right-2 top-1/2 text-2xl z-10">→</div>
                    </div>
                    {/* Step 4: Profit */}
                    <div>
                      <div className="bg-purple-900/40 rounded-lg p-4 border border-purple-600/50 h-full">
                        <div className="text-3xl mb-2">4️⃣</div>
                        <div className="text-lg font-bold text-purple-400">PROFIT</div>
                        <div className="text-sm text-gray-300 mt-2">
                          Net = IC Returns − Borrowing Cost = Your Edge
                        </div>
                        <div className="mt-3 text-xs text-gray-400">
                          <strong>Goal:</strong> Earn more than you pay to borrow
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 p-3 bg-black/30 rounded-lg text-sm text-gray-300">
                    <strong className="text-orange-400">Why it works:</strong> Box spreads let you borrow at near risk-free rates (~Fed Funds).
                    If your IC trading earns more than the borrowing cost, you profit the difference.
                    This is <em>synthetic leverage</em> without margin interest.
                  </div>
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
                      <div className={`text-2xl font-bold ${(icPerformance?.performance?.today?.pnl_today || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(icPerformance?.performance?.today?.pnl_today || 0)}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {icPerformance?.performance?.today?.trades_today || 0} trades closed today
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
                        No active box spread position. System scans for favorable opportunities daily at 9:30 AM CT.
                      </p>
                      {rateAnalysis && (
                        <div className={`inline-block px-4 py-2 rounded-lg ${rateAnalysis.is_favorable ? 'bg-green-900/50 text-green-400 border border-green-600' : 'bg-yellow-900/50 text-yellow-400 border border-yellow-600'}`}>
                          Current rates are <strong>{rateAnalysis.is_favorable ? 'FAVORABLE' : 'UNFAVORABLE'}</strong> for new positions
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
              </div>
            )}

            {/* Positions Tab */}
            {activeTab === 'positions' && (
              <div className="space-y-6">
                <div className="bg-gray-800 rounded-lg overflow-hidden">
                  <div className="p-4 border-b border-gray-700">
                    <h2 className="text-xl font-bold">Open Box Spread Positions</h2>
                    <p className="text-sm text-gray-400">{positions?.count || 0} active</p>
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
                      <p className="text-sm mt-2">PROMETHEUS scans for opportunities daily at 9:30 AM CT</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* IC Trading Tab */}
            {activeTab === 'ic-trading' && (
              <div className="space-y-6">
                {/* IC Status Header */}
                <div className="bg-gradient-to-br from-orange-900/30 to-gray-800 rounded-lg p-6 border border-orange-500/50">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="text-3xl">📊</div>
                      <div>
                        <h2 className="text-xl font-bold">Iron Condor Trading</h2>
                        <p className="text-sm text-gray-400">Trading with borrowed capital from box spreads</p>
                      </div>
                    </div>
                    <div className={`px-3 py-1 rounded-full text-sm font-medium ${
                      icStatus?.status?.enabled ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      {icStatus?.status?.enabled ? 'ENABLED' : 'DISABLED'}
                    </div>
                  </div>

                  {/* Quick Stats */}
                  <div className="grid md:grid-cols-5 gap-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Open Positions</div>
                      <div className="text-2xl font-bold">{icStatus?.status?.open_positions || 0}</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Unrealized P&L</div>
                      <div className={`text-2xl font-bold ${(icStatus?.status?.total_unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(icStatus?.status?.total_unrealized_pnl || 0)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Available Capital</div>
                      <div className="text-2xl font-bold text-blue-400">
                        {formatCurrency(icStatus?.status?.available_capital || 0)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Todays Trades</div>
                      <div className="text-2xl font-bold">{icStatus?.status?.daily_trades || 0} / {icStatus?.status?.max_daily_trades || 3}</div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Can Trade?</div>
                      <div className={`text-2xl font-bold ${icStatus?.status?.can_trade ? 'text-green-400' : 'text-yellow-400'}`}>
                        {icStatus?.status?.can_trade ? 'YES' : 'NO'}
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
                  <div className="grid md:grid-cols-4 gap-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Total Borrowed</div>
                      <div className="text-xl font-bold text-blue-400">
                        {formatCurrency(combinedPerformance?.summary?.box_spread?.total_borrowed || 0)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">Borrowing Cost</div>
                      <div className="text-xl font-bold text-red-400">
                        -{formatCurrency(combinedPerformance?.summary?.box_spread?.total_borrowing_cost || 0)}
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-xs text-gray-400 mb-1">IC Returns</div>
                      <div className="text-xl font-bold text-green-400">
                        +{formatCurrency(combinedPerformance?.summary?.ic_trading?.total_realized_pnl || 0)}
                      </div>
                    </div>
                    <div className={`rounded-lg p-4 ${
                      (combinedPerformance?.summary?.net_profit || 0) >= 0
                        ? 'bg-green-500/20 border border-green-500/50'
                        : 'bg-red-500/20 border border-red-500/50'
                    }`}>
                      <div className="text-xs text-gray-300 mb-1">NET PROFIT</div>
                      <div className={`text-2xl font-bold ${(combinedPerformance?.summary?.net_profit || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(combinedPerformance?.summary?.net_profit || 0)}
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
                    <div className="p-8 text-center text-gray-400">
                      <div className="text-4xl mb-4">📊</div>
                      <p className="text-lg">No Open IC Positions</p>
                      <p className="text-sm mt-2">IC trades are generated every 10 minutes when Oracle approves</p>
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
                        <div className="text-center py-8 text-gray-400">
                          <p>No equity history yet. Data appears after positions close.</p>
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
                        <div className="text-center py-8 text-gray-400">
                          <p>No intraday snapshots yet. Data appears during market hours.</p>
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
          </>
        )}
      </div>
    </div>
  )
}
