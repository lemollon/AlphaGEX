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
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'analytics' | 'education'>('overview')

  // Data fetching
  const { data: status, error: statusError } = useSWR('/api/prometheus-box/status', fetcher, { refreshInterval: 30000 })
  const { data: positions } = useSWR('/api/prometheus-box/positions', fetcher, { refreshInterval: 30000 })
  const { data: rateAnalysis } = useSWR('/api/prometheus-box/analytics/rates', fetcher, { refreshInterval: 60000 })
  const { data: capitalFlow } = useSWR('/api/prometheus-box/analytics/capital-flow', fetcher, { refreshInterval: 30000 })
  const { data: equityCurve } = useSWR('/api/prometheus-box/equity-curve', fetcher, { refreshInterval: 60000 })
  const { data: intradayEquity } = useSWR('/api/prometheus-box/equity-curve/intraday', fetcher, { refreshInterval: 30000 })
  const { data: interestRates } = useSWR('/api/prometheus-box/analytics/interest-rates', fetcher, { refreshInterval: 300000 })

  // IC Bot positions for capital deployment tracking
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
            {['overview', 'positions', 'analytics', 'education'].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab as any)}
                className={`px-6 py-3 font-medium transition-colors ${
                  activeTab === tab ? 'bg-orange-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-700'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
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

                          {/* Mini Equity Curve Sparkline */}
                          {equityCurve?.equity_curve && equityCurve.equity_curve.length > 0 && (
                            <div className="bg-black/40 rounded-lg p-4">
                              <div className="flex justify-between items-center mb-3">
                                <h3 className="text-sm font-medium text-gray-400">EQUITY CURVE (Last 30 Days)</h3>
                                <div className="flex items-center gap-2 text-sm">
                                  <span className="text-gray-500">Current:</span>
                                  <span className={`font-bold ${(equityCurve.equity_curve[equityCurve.equity_curve.length - 1]?.equity || 0) >= (equityCurve.starting_capital || 0) ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatCurrency(equityCurve.equity_curve[equityCurve.equity_curve.length - 1]?.equity || equityCurve.starting_capital)}
                                  </span>
                                </div>
                              </div>
                              <div className="h-24 relative bg-gray-900/50 rounded">
                                {(() => {
                                  const data = equityCurve.equity_curve.slice(-30)
                                  if (data.length < 2) return <div className="text-center text-gray-500 pt-8 text-sm">Insufficient data</div>
                                  const values = data.map((d: any) => d.equity)
                                  const min = Math.min(...values) * 0.99
                                  const max = Math.max(...values) * 1.01
                                  const range = max - min || 1
                                  const startVal = data[0]?.equity || 0
                                  const endVal = data[data.length - 1]?.equity || 0
                                  const isUp = endVal >= startVal
                                  return (
                                    <svg className="w-full h-full" viewBox="0 0 400 96" preserveAspectRatio="none">
                                      {/* Grid lines */}
                                      <line x1="0" y1="24" x2="400" y2="24" stroke="#374151" strokeWidth="0.5" strokeDasharray="4" />
                                      <line x1="0" y1="48" x2="400" y2="48" stroke="#374151" strokeWidth="0.5" strokeDasharray="4" />
                                      <line x1="0" y1="72" x2="400" y2="72" stroke="#374151" strokeWidth="0.5" strokeDasharray="4" />
                                      {/* Area fill */}
                                      <polygon
                                        fill={isUp ? 'url(#equityGradUp)' : 'url(#equityGradDown)'}
                                        points={`0,96 ${data.map((d: any, i: number) => {
                                          const x = (i / (data.length - 1)) * 400
                                          const y = 96 - ((d.equity - min) / range) * 88 - 4
                                          return `${x},${y}`
                                        }).join(' ')} 400,96`}
                                      />
                                      {/* Line */}
                                      <polyline
                                        fill="none"
                                        stroke={isUp ? '#22c55e' : '#ef4444'}
                                        strokeWidth="2"
                                        points={data.map((d: any, i: number) => {
                                          const x = (i / (data.length - 1)) * 400
                                          const y = 96 - ((d.equity - min) / range) * 88 - 4
                                          return `${x},${y}`
                                        }).join(' ')}
                                      />
                                      <defs>
                                        <linearGradient id="equityGradUp" x1="0" y1="0" x2="0" y2="1">
                                          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3" />
                                          <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                                        </linearGradient>
                                        <linearGradient id="equityGradDown" x1="0" y1="0" x2="0" y2="1">
                                          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.3" />
                                          <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
                                        </linearGradient>
                                      </defs>
                                    </svg>
                                  )
                                })()}
                              </div>
                              <div className="flex justify-between text-xs text-gray-500 mt-1">
                                <span>{equityCurve.equity_curve.slice(-30)[0]?.date || ''}</span>
                                <span className={((equityCurve.equity_curve[equityCurve.equity_curve.length - 1]?.cumulative_pnl || 0) >= 0) ? 'text-green-400' : 'text-red-400'}>
                                  Total P&L: {formatCurrency(equityCurve.equity_curve[equityCurve.equity_curve.length - 1]?.cumulative_pnl || 0)}
                                </span>
                                <span>{equityCurve.equity_curve[equityCurve.equity_curve.length - 1]?.date || ''}</span>
                              </div>
                            </div>
                          )}

                          {/* Money Life Cycle - Visual Timeline */}
                          <div className="bg-black/40 rounded-lg p-4">
                            <h3 className="text-sm font-medium text-gray-400 mb-4">MONEY LIFE CYCLE</h3>
                            <div className="relative">
                              {/* Timeline bar */}
                              <div className="absolute left-4 right-4 top-8 h-1 bg-gray-700 rounded">
                                {/* Progress indicator */}
                                <div
                                  className="absolute left-0 top-0 h-full bg-gradient-to-r from-green-500 via-blue-500 to-purple-500 rounded"
                                  style={{ width: `${progressPct}%` }}
                                />
                              </div>

                              {/* Timeline stages */}
                              <div className="relative flex justify-between">
                                {/* Day 0: Credit Received */}
                                <div className="flex flex-col items-center w-1/3">
                                  <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center text-white text-sm font-bold z-10 border-2 border-green-400">
                                    $
                                  </div>
                                  <div className="mt-3 text-center">
                                    <div className="text-xs text-gray-500">Day 0</div>
                                    <div className="text-sm font-medium text-green-400">Credit Received</div>
                                    <div className="text-xs text-gray-400">{formatCurrency(creditReceived)}</div>
                                  </div>
                                </div>

                                {/* Now: Holding Period */}
                                <div className="flex flex-col items-center w-1/3">
                                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold z-10 border-2 ${daysElapsed > 0 ? 'bg-blue-600 border-blue-400' : 'bg-gray-600 border-gray-400'}`}>
                                    {Math.round(progressPct)}%
                                  </div>
                                  <div className="mt-3 text-center">
                                    <div className="text-xs text-gray-500">Now ({daysElapsed} days)</div>
                                    <div className="text-sm font-medium text-blue-400">Interest Accruing</div>
                                    <div className="text-xs text-gray-400">-{formatCurrency(costAccruedSoFar)} accrued</div>
                                    <div className="text-xs text-green-400">+{formatCurrency(pos.total_ic_returns)} IC returns</div>
                                  </div>
                                </div>

                                {/* Expiration: Repay Face Value */}
                                <div className="flex flex-col items-center w-1/3">
                                  <div className="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center text-white text-sm font-bold z-10 border-2 border-gray-400">
                                    ⏱
                                  </div>
                                  <div className="mt-3 text-center">
                                    <div className="text-xs text-gray-500">Day {totalDays}</div>
                                    <div className="text-sm font-medium text-gray-400">Repay Face Value</div>
                                    <div className="text-xs text-red-400">-{formatCurrency(owedAtExpiration)}</div>
                                    <div className="text-xs text-gray-500">({pos.current_dte} days left)</div>
                                  </div>
                                </div>
                              </div>

                              {/* Net projection */}
                              <div className="mt-6 pt-4 border-t border-gray-700 grid grid-cols-3 gap-4 text-center text-xs">
                                <div>
                                  <span className="text-gray-500">Total Borrowed:</span>
                                  <span className="ml-1 text-green-400 font-medium">{formatCurrency(creditReceived)}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Proj. Total Cost:</span>
                                  <span className="ml-1 text-red-400 font-medium">{formatCurrency(projectedTotalCost)}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Net at Exp:</span>
                                  <span className={`ml-1 font-medium ${creditReceived - owedAtExpiration + pos.total_ic_returns >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatCurrency(creditReceived - owedAtExpiration + pos.total_ic_returns)}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Today's Intraday Activity */}
                          {intradayEquity?.snapshots && intradayEquity.snapshots.length > 0 && (
                            <div className="bg-black/40 rounded-lg p-4">
                              <div className="flex justify-between items-center mb-3">
                                <h3 className="text-sm font-medium text-gray-400">TODAY&apos;S ACTIVITY</h3>
                                <span className="text-xs text-gray-500">{intradayEquity.snapshots.length} snapshots</span>
                              </div>
                              <div className="grid md:grid-cols-4 gap-3 mb-3">
                                <div className="bg-gray-800/50 rounded p-2 text-center">
                                  <div className="text-xs text-gray-500">Open</div>
                                  <div className="font-medium">{formatCurrency(intradayEquity.snapshots[0]?.total_equity)}</div>
                                </div>
                                <div className="bg-gray-800/50 rounded p-2 text-center">
                                  <div className="text-xs text-gray-500">Current</div>
                                  <div className="font-medium">{formatCurrency(intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.total_equity)}</div>
                                </div>
                                <div className="bg-gray-800/50 rounded p-2 text-center">
                                  <div className="text-xs text-gray-500">Change</div>
                                  <div className={`font-medium ${(intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.total_equity - intradayEquity.snapshots[0]?.total_equity) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatCurrency(intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.total_equity - intradayEquity.snapshots[0]?.total_equity)}
                                  </div>
                                </div>
                                <div className="bg-gray-800/50 rounded p-2 text-center">
                                  <div className="text-xs text-gray-500">Unrealized</div>
                                  <div className={`font-medium ${(intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatCurrency(intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.unrealized_pnl || 0)}
                                  </div>
                                </div>
                              </div>
                              {/* Mini intraday sparkline */}
                              <div className="h-12 relative bg-gray-900/50 rounded">
                                {(() => {
                                  const snaps = intradayEquity.snapshots
                                  if (snaps.length < 2) return null
                                  const values = snaps.map((s: any) => s.total_equity)
                                  const min = Math.min(...values) * 0.9999
                                  const max = Math.max(...values) * 1.0001
                                  const range = max - min || 1
                                  const isUp = values[values.length - 1] >= values[0]
                                  return (
                                    <svg className="w-full h-full" viewBox="0 0 400 48" preserveAspectRatio="none">
                                      <polyline
                                        fill="none"
                                        stroke={isUp ? '#22c55e' : '#ef4444'}
                                        strokeWidth="1.5"
                                        points={snaps.map((s: any, i: number) => {
                                          const x = (i / (snaps.length - 1)) * 400
                                          const y = 48 - ((s.total_equity - min) / range) * 44 - 2
                                          return `${x},${y}`
                                        }).join(' ')}
                                      />
                                    </svg>
                                  )
                                })()}
                              </div>
                              <div className="flex justify-between text-xs text-gray-500 mt-1">
                                <span>{new Date(intradayEquity.snapshots[0]?.snapshot_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                                <span>Intraday P&L Trend</span>
                                <span>{new Date(intradayEquity.snapshots[intradayEquity.snapshots.length - 1]?.snapshot_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* No Position State */}
                {(!positions?.positions || positions.positions.length === 0) && (
                  <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
                    <div className="text-5xl mb-4">📦</div>
                    <h2 className="text-2xl font-bold mb-2">No Active Position</h2>
                    <p className="text-gray-400 mb-4">PROMETHEUS scans for favorable box spread opportunities daily at 9:30 AM CT</p>
                    {rateAnalysis && (
                      <div className={`inline-block px-4 py-2 rounded-lg ${rateAnalysis.is_favorable ? 'bg-green-900/50 text-green-400' : 'bg-yellow-900/50 text-yellow-400'}`}>
                        Current rates are {rateAnalysis.is_favorable ? 'FAVORABLE' : 'UNFAVORABLE'} for new positions
                      </div>
                    )}
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

                {/* Capital Deployment */}
                {capitalFlow && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4">Capital Deployment to IC Bots</h2>
                    <div className="grid md:grid-cols-3 gap-4">
                      {[
                        { name: 'ARES', pct: 35, desc: 'SPY 0DTE IC', color: 'red', data: capitalFlow.deployment_summary?.ares },
                        { name: 'TITAN', pct: 35, desc: 'SPX Aggressive IC', color: 'blue', data: capitalFlow.deployment_summary?.titan },
                        { name: 'PEGASUS', pct: 20, desc: 'SPX Weekly IC', color: 'purple', data: capitalFlow.deployment_summary?.pegasus },
                      ].map((bot) => (
                        <div key={bot.name} className="bg-gray-700/50 rounded-lg p-4">
                          <div className="flex justify-between items-start mb-2">
                            <div className="font-bold text-lg">{bot.name}</div>
                            <div className="text-xs bg-gray-600 px-2 py-1 rounded">{bot.pct}%</div>
                          </div>
                          <div className="text-xs text-gray-400 mb-3">{bot.desc}</div>
                          <div className="space-y-1 text-sm">
                            <div className="flex justify-between">
                              <span className="text-gray-400">Deployed:</span>
                              <span>{formatCurrency(bot.data?.deployed || 0)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-gray-400">Returns:</span>
                              <span className={(bot.data?.returns || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {formatCurrency(bot.data?.returns || 0)}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-gray-400">ROI:</span>
                              <span className={(bot.data?.roi || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {formatPct(bot.data?.roi || 0)}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    {/* Reserve note */}
                    <div className="mt-4 text-sm text-gray-400 bg-gray-700/30 rounded-lg p-3">
                      <span className="text-gray-500">+10% Reserve Buffer:</span> Held for margin calls and emergency adjustments
                    </div>
                  </div>
                )}

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

                {/* Equity Curve */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">Equity Curve</h2>
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
                                <polygon fill="url(#equityGrad)" points={`0,150 ${data.map((d: any, i: number) => {
                                  const x = (i / (data.length - 1)) * 400
                                  const y = 150 - ((d.equity - min) / range) * 140 - 5
                                  return `${x},${y}`
                                }).join(' ')} 400,150`} />
                                <defs>
                                  <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
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

                {/* IC Bot Attribution */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">IC Bot Performance Attribution</h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    {/* ARES */}
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold">ARES</h3>
                        <span className="text-xs text-gray-400">SPY 0DTE</span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Allocated:</span>
                          <span>{formatCurrency(capitalFlow?.deployment_summary?.ares?.deployed || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Returns:</span>
                          <span className={(capitalFlow?.deployment_summary?.ares?.returns || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {formatCurrency(capitalFlow?.deployment_summary?.ares?.returns || 0)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Open Positions:</span>
                          <span>{aresPositions?.positions?.length || 0}</span>
                        </div>
                      </div>
                    </div>

                    {/* TITAN */}
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold">TITAN</h3>
                        <span className="text-xs text-gray-400">SPX Aggressive</span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Allocated:</span>
                          <span>{formatCurrency(capitalFlow?.deployment_summary?.titan?.deployed || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Returns:</span>
                          <span className={(capitalFlow?.deployment_summary?.titan?.returns || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {formatCurrency(capitalFlow?.deployment_summary?.titan?.returns || 0)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Open Positions:</span>
                          <span>{titanPositions?.positions?.length || 0}</span>
                        </div>
                      </div>
                    </div>

                    {/* PEGASUS */}
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold">PEGASUS</h3>
                        <span className="text-xs text-gray-400">SPX Weekly</span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Allocated:</span>
                          <span>{formatCurrency(capitalFlow?.deployment_summary?.pegasus?.deployed || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Returns:</span>
                          <span className={(capitalFlow?.deployment_summary?.pegasus?.returns || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {formatCurrency(capitalFlow?.deployment_summary?.pegasus?.returns || 0)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Open Positions:</span>
                          <span>{pegasusPositions?.positions?.length || 0}</span>
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
                      <h3 className="text-sm font-medium text-red-400 mb-2">Outflows</h3>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">ARES Deployment:</span>
                          <span>{formatCurrency(capitalFlow?.deployment_summary?.ares?.deployed || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">TITAN Deployment:</span>
                          <span>{formatCurrency(capitalFlow?.deployment_summary?.titan?.deployed || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">PEGASUS Deployment:</span>
                          <span>{formatCurrency(capitalFlow?.deployment_summary?.pegasus?.deployed || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Borrowing Costs:</span>
                          <span className="text-red-400">-{formatCurrency(totalBorrowingCosts)}</span>
                        </div>
                        <div className="border-t border-gray-700 pt-2 flex justify-between font-medium">
                          <span>Net P&L:</span>
                          <span className={netPnL >= 0 ? 'text-green-400' : 'text-red-400'}>{formatCurrency(netPnL)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Intraday Snapshots */}
                {intradayEquity?.snapshots && intradayEquity.snapshots.length > 0 && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4">Today&apos;s Equity Snapshots</h2>
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
                )}
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

                    {/* Step 2: Deploy */}
                    <div className="relative">
                      <div className="bg-gradient-to-br from-purple-900/50 to-purple-800/30 rounded-xl p-6 border border-purple-500/30 h-full">
                        <div className="absolute -top-3 -left-3 w-10 h-10 bg-purple-600 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-lg">2</div>
                        <div className="text-center mb-4 pt-2">
                          <div className="text-4xl mb-2">💰</div>
                          <h3 className="text-xl font-bold text-purple-400">DEPLOY</h3>
                        </div>
                        <div className="bg-black/40 rounded-lg p-4">
                          <div className="text-sm text-center mb-3 text-gray-300">Capital Allocation</div>
                          <div className="space-y-3">
                            <div className="relative">
                              <div className="flex justify-between text-xs mb-1">
                                <span className="text-red-400 font-medium">ARES</span>
                                <span>35%</span>
                              </div>
                              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full bg-red-500 rounded-full" style={{ width: '35%' }}></div>
                              </div>
                            </div>
                            <div className="relative">
                              <div className="flex justify-between text-xs mb-1">
                                <span className="text-blue-400 font-medium">TITAN</span>
                                <span>35%</span>
                              </div>
                              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full bg-blue-500 rounded-full" style={{ width: '35%' }}></div>
                              </div>
                            </div>
                            <div className="relative">
                              <div className="flex justify-between text-xs mb-1">
                                <span className="text-purple-400 font-medium">PEGASUS</span>
                                <span>20%</span>
                              </div>
                              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full bg-purple-500 rounded-full" style={{ width: '20%' }}></div>
                              </div>
                            </div>
                            <div className="relative">
                              <div className="flex justify-between text-xs mb-1">
                                <span className="text-gray-400 font-medium">RESERVE</span>
                                <span>10%</span>
                              </div>
                              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full bg-gray-500 rounded-full" style={{ width: '10%' }}></div>
                              </div>
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
