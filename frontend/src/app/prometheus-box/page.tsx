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
  current_dte: number
  contracts: number
  total_credit_received: number
  total_owed_at_expiration: number
  borrowing_cost: number
  implied_annual_rate: number
  total_ic_returns: number
  net_profit: number
  status: string
  early_assignment_risk: string
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
                {/* Architecture Diagram */}
                <div className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg p-6 border border-orange-900/50">
                  <h2 className="text-2xl font-bold mb-4">How PROMETHEUS Works</h2>
                  <div className="bg-black/40 rounded-lg p-6 font-mono text-sm overflow-x-auto">
                    <pre className="text-gray-300 whitespace-pre">
{`┌─────────────────────────────────────────────────────────────────────────────┐
│                           PROMETHEUS ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────┘

  STEP 1: BORROW                              STEP 2: DEPLOY
  ════════════════                            ══════════════

  ┌──────────────────────┐                    ┌─────────────────────────────────┐
  │    📦 BOX SPREAD     │                    │     💰 CAPITAL ALLOCATION       │
  │    (SPX Options)     │                    │                                 │
  │                      │   Credit           │   ┌───────┐  35%   ┌─────────┐  │
  │  Sell Call Spread    │──────────────────▶ │   │ ARES  │───────▶│ SPY 0DTE│  │
  │  + Sell Put Spread   │                    │   └───────┘        │   IC    │  │
  │  = CASH TODAY        │                    │                    └─────────┘  │
  │                      │                    │   ┌───────┐  35%   ┌─────────┐  │
  │  Rate: ~4.5%/yr      │                    │   │ TITAN │───────▶│SPX Aggr │  │
  │  (vs 8.5% margin)    │                    │   └───────┘        │   IC    │  │
  └──────────────────────┘                    │                    └─────────┘  │
                                              │   ┌───────┐  20%   ┌─────────┐  │
  STEP 3: PROFIT                              │   │PEGASUS│───────▶│SPX Weekly│ │
  ══════════════                              │   └───────┘        │   IC    │  │
                                              │                    └─────────┘  │
  IC Returns - Borrowing Cost = NET PROFIT    │   ┌───────┐  10%                │
                                              │   │RESERVE│ (Margin buffer)     │
  Target: IC bots return 2-4%/month           │   └───────┘                     │
  Cost: Box spread ~0.4%/month                └─────────────────────────────────┘
  Spread: +1.6-3.6%/month profit potential`}
                    </pre>
                  </div>
                </div>

                {/* Rate Analysis */}
                {rateAnalysis && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4">Current Rate Analysis</h2>
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
                    <h2 className="text-xl font-bold mb-4">Capital Deployment</h2>
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
                  </div>
                )}
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
              <div className="space-y-6">
                {/* What is a Box Spread */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-2xl font-bold mb-4 text-orange-400">What is a Box Spread?</h2>
                  <div className="grid md:grid-cols-2 gap-6">
                    <div>
                      <p className="text-gray-300 mb-4">
                        A box spread is a combination of options that creates a <strong className="text-white">synthetic loan</strong>.
                        You receive cash today and pay back a fixed amount at expiration.
                      </p>
                      <div className="bg-gray-700/50 rounded-lg p-4 mb-4">
                        <h4 className="font-medium text-white mb-2">The Structure</h4>
                        <div className="space-y-2 text-sm">
                          <div className="flex items-center gap-2">
                            <span className="text-green-400">+</span>
                            <span>Buy Call at Lower Strike (K1)</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-red-400">−</span>
                            <span>Sell Call at Upper Strike (K2)</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-green-400">+</span>
                            <span>Buy Put at Upper Strike (K2)</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-red-400">−</span>
                            <span>Sell Put at Lower Strike (K1)</span>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="bg-black/30 rounded-lg p-4">
                      <h4 className="font-medium text-white mb-3">Key Properties</h4>
                      <div className="space-y-3 text-sm">
                        <div className="flex items-start gap-3">
                          <span className="text-blue-400 text-lg">1</span>
                          <div>
                            <div className="font-medium">Guaranteed Payout</div>
                            <div className="text-gray-400">Always worth exactly (K2 - K1) × 100 at expiration</div>
                          </div>
                        </div>
                        <div className="flex items-start gap-3">
                          <span className="text-blue-400 text-lg">2</span>
                          <div>
                            <div className="font-medium">No Market Risk</div>
                            <div className="text-gray-400">Price moves don&apos;t affect the final value</div>
                          </div>
                        </div>
                        <div className="flex items-start gap-3">
                          <span className="text-blue-400 text-lg">3</span>
                          <div>
                            <div className="font-medium">Implied Interest Rate</div>
                            <div className="text-gray-400">The discount from face value is your borrowing cost</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Rate Calculation */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-2xl font-bold mb-4 text-orange-400">How the Rate is Calculated</h2>
                  <div className="bg-black/30 rounded-lg p-6 mb-4">
                    <div className="text-center mb-4">
                      <div className="text-lg text-gray-400 mb-2">Implied Annual Rate Formula</div>
                      <div className="text-2xl font-mono text-white bg-gray-700/50 inline-block px-6 py-3 rounded">
                        Rate = ((Face Value / Credit) - 1) × (365 / DTE) × 100
                      </div>
                    </div>
                  </div>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <h4 className="font-medium text-blue-400 mb-2">Example Trade</h4>
                      <div className="text-sm space-y-1">
                        <div>Strike Width: $50</div>
                        <div>Face Value: $5,000</div>
                        <div>Credit Received: $4,890</div>
                        <div>DTE: 180 days</div>
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <h4 className="font-medium text-green-400 mb-2">Calculation</h4>
                      <div className="text-sm space-y-1 font-mono">
                        <div>($5,000 / $4,890) - 1</div>
                        <div>= 0.0225 (2.25%)</div>
                        <div>× (365 / 180)</div>
                        <div className="text-green-400 font-bold">= 4.56% annual</div>
                      </div>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <h4 className="font-medium text-purple-400 mb-2">Compare To</h4>
                      <div className="text-sm space-y-1">
                        <div className="flex justify-between">
                          <span>Margin Rate:</span>
                          <span className="text-red-400">8-9%</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Box Spread:</span>
                          <span className="text-green-400">4-5%</span>
                        </div>
                        <div className="flex justify-between font-bold pt-2 border-t border-gray-600">
                          <span>Your Savings:</span>
                          <span className="text-green-400">3-4%</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Why SPX */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-2xl font-bold mb-4 text-orange-400">Why SPX Options?</h2>
                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="space-y-4">
                      <div className="flex items-start gap-3">
                        <div className="w-8 h-8 bg-green-900/50 rounded-lg flex items-center justify-center text-green-400">✓</div>
                        <div>
                          <div className="font-medium">European-Style Settlement</div>
                          <div className="text-sm text-gray-400">Cannot be exercised early, eliminating assignment risk</div>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <div className="w-8 h-8 bg-green-900/50 rounded-lg flex items-center justify-center text-green-400">✓</div>
                        <div>
                          <div className="font-medium">Cash Settlement</div>
                          <div className="text-sm text-gray-400">No stock delivery required, just cash difference</div>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <div className="w-8 h-8 bg-green-900/50 rounded-lg flex items-center justify-center text-green-400">✓</div>
                        <div>
                          <div className="font-medium">High Liquidity</div>
                          <div className="text-sm text-gray-400">Tight bid/ask spreads for better rates</div>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <div className="w-8 h-8 bg-green-900/50 rounded-lg flex items-center justify-center text-green-400">✓</div>
                        <div>
                          <div className="font-medium">Section 1256 Tax Treatment</div>
                          <div className="text-sm text-gray-400">60/40 long-term/short-term capital gains</div>
                        </div>
                      </div>
                    </div>
                    <div className="bg-red-900/20 border border-red-700/50 rounded-lg p-4">
                      <h4 className="font-medium text-red-400 mb-3">Why NOT SPY or Other ETFs?</h4>
                      <div className="space-y-3 text-sm">
                        <div className="flex items-start gap-2">
                          <span className="text-red-400">✗</span>
                          <span><strong>American-style options</strong> - Can be exercised early, especially near ex-dividend dates</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="text-red-400">✗</span>
                          <span><strong>Physical delivery</strong> - Assignment means buying/selling shares</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="text-red-400">✗</span>
                          <span><strong>Dividend risk</strong> - Deep ITM options get assigned for dividends</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Risks */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-2xl font-bold mb-4 text-orange-400">Understanding the Risks</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-4">
                      <h4 className="font-medium text-yellow-400 mb-2">Margin Requirements</h4>
                      <p className="text-sm text-gray-300">
                        Box spreads require significant margin. Your broker holds the full strike width as collateral
                        until expiration. This is the capital you&apos;re effectively borrowing against.
                      </p>
                    </div>
                    <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-4">
                      <h4 className="font-medium text-yellow-400 mb-2">Execution Slippage</h4>
                      <p className="text-sm text-gray-300">
                        Four-leg orders can have slippage. Wide bid/ask spreads on any leg affect your
                        effective borrowing rate. Always use limit orders.
                      </p>
                    </div>
                    <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-4">
                      <h4 className="font-medium text-yellow-400 mb-2">Rate Lock-In</h4>
                      <p className="text-sm text-gray-300">
                        Once opened, your borrowing rate is locked until expiration. If market rates drop
                        significantly, you can&apos;t refinance without closing at a loss.
                      </p>
                    </div>
                    <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-4">
                      <h4 className="font-medium text-yellow-400 mb-2">IC Bot Underperformance</h4>
                      <p className="text-sm text-gray-300">
                        PROMETHEUS only profits if IC bot returns exceed borrowing costs. A losing streak
                        in ARES/TITAN/PEGASUS means you&apos;re paying interest with no offsetting gains.
                      </p>
                    </div>
                  </div>
                </div>

                {/* How PROMETHEUS Manages This */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-2xl font-bold mb-4 text-orange-400">How PROMETHEUS Manages This</h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-3xl mb-2">📊</div>
                      <h4 className="font-medium mb-2">Rate Monitoring</h4>
                      <p className="text-sm text-gray-400">
                        Continuously monitors box spread implied rates vs Fed Funds. Only borrows when
                        rates are favorable (typically Fed Funds + 0.5% or less).
                      </p>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-3xl mb-2">🔄</div>
                      <h4 className="font-medium mb-2">Rolling Strategy</h4>
                      <p className="text-sm text-gray-400">
                        Positions with less than 30 DTE are evaluated for rolling to maintain deployed
                        capital without gaps.
                      </p>
                    </div>
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <div className="text-3xl mb-2">🛡️</div>
                      <h4 className="font-medium mb-2">Reserve Buffer</h4>
                      <p className="text-sm text-gray-400">
                        10% of borrowed capital is held in reserve for margin calls or emergency
                        adjustments, not deployed to IC bots.
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
