'use client'

import { useState } from 'react'
import useSWR from 'swr'
import ReactMarkdown from 'react-markdown'
import Navigation from '@/components/Navigation'

// API URL for backend calls - must be set in production
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

interface RateAnalysis {
  box_implied_rate: number
  fed_funds_rate: number
  broker_margin_rate: number
  spread_to_margin: number
  is_favorable: boolean
  recommendation: string
  reasoning: string
}

interface CapitalFlow {
  total_cash_generated: number
  total_deployed: number
  total_returns: number
  deployment_summary: {
    ares: { deployed: number; returns: number; roi: number }
    titan: { deployed: number; returns: number; roi: number }
    pegasus: { deployed: number; returns: number; roi: number }
  }
}

export default function PrometheusBoxDashboard() {
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'analytics' | 'education'>('overview')
  const [educationTopic, setEducationTopic] = useState('overview')

  // Data fetching - PROMETHEUS
  const { data: status, error: statusError } = useSWR('/api/prometheus-box/status', fetcher, { refreshInterval: 30000 })
  const { data: positions } = useSWR('/api/prometheus-box/positions', fetcher, { refreshInterval: 30000 })
  const { data: rateAnalysis } = useSWR('/api/prometheus-box/analytics/rates', fetcher, { refreshInterval: 60000 })
  const { data: capitalFlow } = useSWR('/api/prometheus-box/analytics/capital-flow', fetcher, { refreshInterval: 30000 })
  const { data: dailyBriefing } = useSWR('/api/prometheus-box/operations/daily-briefing', fetcher, { refreshInterval: 60000 })
  const { data: educationContent } = useSWR(`/api/prometheus-box/education/${educationTopic}`, fetcher)

  // Analytics data - Equity curves and IC bot positions
  const { data: equityCurve } = useSWR('/api/prometheus-box/equity-curve', fetcher, { refreshInterval: 60000 })
  const { data: intradayEquity } = useSWR('/api/prometheus-box/equity-curve/intraday', fetcher, { refreshInterval: 30000 })

  // Live interest rates
  const { data: interestRates } = useSWR('/api/prometheus-box/analytics/interest-rates', fetcher, { refreshInterval: 300000 }) // 5 min refresh

  // IC Bot positions - to show where capital is deployed
  const { data: aresPositions } = useSWR('/api/ares/positions', fetcher, { refreshInterval: 30000 })
  const { data: titanPositions } = useSWR('/api/titan/positions', fetcher, { refreshInterval: 30000 })
  const { data: pegasusPositions } = useSWR('/api/pegasus/positions', fetcher, { refreshInterval: 30000 })

  const isLoading = !status
  const isError = statusError

  // Format currency
  const formatCurrency = (value: number) => {
    if (value === undefined || value === null) return '$0.00'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value)
  }

  // Format percentage
  const formatPct = (value: number, decimals = 2) => {
    if (value === undefined || value === null) return '0.00%'
    return `${value.toFixed(decimals)}%`
  }

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
              <p className="text-orange-300">Box Spread Synthetic Borrowing Bot</p>
              <p className="text-sm text-gray-400 mt-1">
                Bringing fire (capital) to fuel Iron Condor strategies
              </p>
            </div>
          </div>

          {/* Quick Stats */}
          {status && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-6">
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">System Status</div>
                <div className={`text-xl font-bold ${
                  status.system_status === 'active' ? 'text-green-400' : 'text-yellow-400'
                }`}>
                  {status.system_status?.toUpperCase() || 'UNKNOWN'}
                </div>
              </div>
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">Total Borrowed</div>
                <div className="text-xl font-bold text-blue-400">
                  {formatCurrency(status.total_borrowed)}
                </div>
              </div>
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">IC Returns</div>
                <div className="text-xl font-bold text-green-400">
                  {formatCurrency(status.total_ic_returns)}
                </div>
              </div>
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">Borrowing Costs</div>
                <div className="text-xl font-bold text-red-400">
                  {formatCurrency(status.total_borrowing_costs)}
                </div>
              </div>
              <div className="bg-black/30 rounded-lg p-4">
                <div className="text-sm text-gray-400">Net P&L</div>
                <div className={`text-xl font-bold ${
                  (status.net_unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {formatCurrency(status.net_unrealized_pnl)}
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
                className={`px-4 py-3 font-medium transition-colors ${
                  activeTab === tab
                    ? 'bg-orange-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-700'
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
            <p className="text-sm text-gray-400 mt-2">The system may be initializing or unavailable</p>
          </div>
        )}

        {!isLoading && !isError && (
          <>
            {/* Overview Tab */}
            {activeTab === 'overview' && (
              <div className="space-y-6">

                {/* SECTION 1: How It Works - Visual Architecture */}
                <div className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg p-6 border border-orange-900/50">
                  <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
                    🏗️ How PROMETHEUS Works
                  </h2>
                  <p className="text-gray-400 mb-6">
                    PROMETHEUS borrows money cheaply using box spreads, then deploys that capital to your Iron Condor bots to generate returns.
                  </p>

                  {/* Visual Architecture Diagram */}
                  <div className="bg-black/40 rounded-lg p-6 font-mono text-sm overflow-x-auto">
                    <pre className="text-gray-300 whitespace-pre">
{`┌─────────────────────────────────────────────────────────────────────────────┐
│                           PROMETHEUS ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────┘

  STEP 1: BORROW CAPITAL                    STEP 2: DEPLOY TO IC BOTS
  ══════════════════════                    ════════════════════════

  ┌──────────────────────┐                  ┌─────────────────────────────────┐
  │    📦 BOX SPREAD     │                  │     💰 CAPITAL DEPLOYMENT       │
  │    (SPX Options)     │                  │                                 │
  │                      │                  │   ┌───────┐  35%   ┌─────────┐  │
  │  Sell Call Spread    │   You Receive    │   │ ARES  │───────▶│ SPY 0DTE│  │
  │  + Sell Put Spread   │───────────────▶  │   │ $175K │        │Iron Cond│  │
  │  = CREDIT TODAY      │    $500,000      │   └───────┘        └─────────┘  │
  │                      │                  │                                 │
  │  Example:            │                  │   ┌───────┐  35%   ┌─────────┐  │
  │  5900/5950 Box       │                  │   │ TITAN │───────▶│ SPX Aggr│  │
  │  180 days to expiry  │                  │   │ $175K │        │Iron Cond│  │
  │  @ 4.5% implied rate │                  │   └───────┘        └─────────┘  │
  └──────────────────────┘                  │                                 │
           │                                │   ┌───────┐  20%   ┌─────────┐  │
           │ At Expiration                  │   │PEGASUS│───────▶│ SPX Wkly│  │
           │ You Owe $505,625               │   │ $100K │        │Iron Cond│  │
           ▼                                │   └───────┘        └─────────┘  │
  ┌──────────────────────┐                  │                                 │
  │ 📊 BORROWING COST    │                  │   ┌───────┐  10%                │
  │ $5,625 over 180 days │                  │   │RESERVE│ (Safety buffer)     │
  │ = 4.5% annual rate   │                  │   │ $50K  │                     │
  │ (vs 8.5% margin!)    │                  │   └───────┘                     │
  └──────────────────────┘                  └─────────────────────────────────┘

  STEP 3: GENERATE RETURNS                  STEP 4: PROFIT CALCULATION
  ════════════════════════                  ═════════════════════════

  ┌─────────────────────────────────┐       ┌─────────────────────────────────┐
  │     📈 IC BOT RETURNS           │       │     ✨ YOUR PROFIT              │
  │                                 │       │                                 │
  │  ARES trades daily 0DTE ICs     │       │  IC Bot Returns:    +$15,000    │
  │  → Target: 2-4% monthly         │       │  Borrowing Cost:     -$5,625    │
  │                                 │       │  ─────────────────────────────  │
  │  TITAN trades aggressive ICs    │       │  NET PROFIT:         +$9,375    │
  │  → Target: 2-4% monthly         │       │                                 │
  │                                 │       │  ROI on borrowed capital:       │
  │  PEGASUS trades weekly ICs      │       │  $9,375 / $500,000 = 1.875%     │
  │  → Target: 1-3% monthly         │       │  (over ~6 months)               │
  │                                 │       │                                 │
  └─────────────────────────────────┘       └─────────────────────────────────┘`}
                    </pre>
                  </div>

                  {/* The Profit Equation */}
                  <div className="mt-6 bg-green-900/20 border border-green-700/50 rounded-lg p-4">
                    <h3 className="text-lg font-bold text-green-400 mb-2">💡 The Profit Equation</h3>
                    <div className="text-center text-xl font-mono py-4 bg-black/30 rounded">
                      <span className="text-green-400">PROFIT</span>
                      <span className="text-gray-400"> = </span>
                      <span className="text-blue-400">IC Bot Returns</span>
                      <span className="text-gray-400"> − </span>
                      <span className="text-red-400">Box Spread Borrowing Cost</span>
                    </div>
                    <p className="text-sm text-gray-400 mt-3">
                      <strong>Why this works:</strong> Box spreads let you borrow at ~4-5% annual rate, while broker margin costs ~8-9%.
                      Your IC bots typically return 2-4% monthly. As long as IC returns exceed the borrowing cost, you profit.
                    </p>
                  </div>
                </div>

                {/* SECTION 2: Live System Status */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    ⚡ Live System Status
                  </h2>

                  <div className="grid md:grid-cols-2 gap-6">
                    {/* Trading Mode & Schedule */}
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <h3 className="font-medium text-gray-300 mb-3">Trading Configuration</h3>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Mode:</span>
                          <span className={`font-medium ${status?.mode === 'live' ? 'text-green-400' : 'text-yellow-400'}`}>
                            {status?.mode?.toUpperCase() || 'PAPER'} TRADING
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Underlying:</span>
                          <span className="text-white">SPX (European-style options)</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Strike Width:</span>
                          <span className="text-white">$50 (default)</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Target DTE:</span>
                          <span className="text-white">90-180 days</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Max Positions:</span>
                          <span className="text-white">{status?.config?.max_positions || 3}</span>
                        </div>
                      </div>
                    </div>

                    {/* Scheduler Info */}
                    <div className="bg-gray-700/50 rounded-lg p-4">
                      <h3 className="font-medium text-gray-300 mb-3">Automated Trading Schedule</h3>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Daily Cycle:</span>
                          <span className="text-white">9:30 AM CT</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Signal Scans:</span>
                          <span className="text-white">Weekly (Mondays)</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Equity Snapshots:</span>
                          <span className="text-white">Every 30 minutes</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Roll Check:</span>
                          <span className="text-white">Daily (positions {'<'} 30 DTE)</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Open Positions:</span>
                          <span className="text-blue-400 font-medium">{positions?.count || 0}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Current Activity */}
                  <div className="mt-4 p-4 bg-blue-900/20 border border-blue-700/30 rounded-lg">
                    <div className="flex items-center gap-2">
                      <div className={`w-3 h-3 rounded-full ${(positions?.count || 0) > 0 ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`}></div>
                      <span className="text-sm">
                        {(positions?.count || 0) > 0
                          ? `Active: ${positions?.count} box spread position(s) generating capital for IC bots`
                          : 'Idle: No open positions. System will scan for opportunities on next scheduled run.'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* SECTION 3: Rate Comparison - When is it worth borrowing? */}
                {rateAnalysis && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                      📊 Is Borrowing Worth It Right Now?
                    </h2>

                    <div className="grid md:grid-cols-4 gap-4 mb-4">
                      <div className="bg-blue-900/30 rounded-lg p-4 text-center">
                        <div className="text-xs text-gray-400 mb-1">Box Spread Rate</div>
                        <div className="text-2xl font-bold text-blue-400">
                          {formatPct(rateAnalysis.box_implied_rate)}
                        </div>
                        <div className="text-xs text-gray-500">What you pay to borrow</div>
                      </div>
                      <div className="bg-red-900/30 rounded-lg p-4 text-center">
                        <div className="text-xs text-gray-400 mb-1">Margin Rate</div>
                        <div className="text-2xl font-bold text-red-400">
                          {formatPct(rateAnalysis.broker_margin_rate)}
                        </div>
                        <div className="text-xs text-gray-500">Traditional borrowing</div>
                      </div>
                      <div className="bg-green-900/30 rounded-lg p-4 text-center">
                        <div className="text-xs text-gray-400 mb-1">Your Savings</div>
                        <div className="text-2xl font-bold text-green-400">
                          {formatPct(Math.abs(rateAnalysis.spread_to_margin))}
                        </div>
                        <div className="text-xs text-gray-500">vs margin borrowing</div>
                      </div>
                      <div className="bg-purple-900/30 rounded-lg p-4 text-center">
                        <div className="text-xs text-gray-400 mb-1">Break-Even</div>
                        <div className="text-2xl font-bold text-purple-400">
                          {formatPct(rateAnalysis.box_implied_rate / 12)}
                        </div>
                        <div className="text-xs text-gray-500">Monthly IC return needed</div>
                      </div>
                    </div>

                    <div className={`p-4 rounded-lg ${
                      rateAnalysis.is_favorable ? 'bg-green-900/30 border border-green-700/50' : 'bg-yellow-900/30 border border-yellow-700/50'
                    }`}>
                      <div className={`font-medium flex items-center gap-2 ${
                        rateAnalysis.is_favorable ? 'text-green-400' : 'text-yellow-400'
                      }`}>
                        {rateAnalysis.is_favorable ? '✅' : '⚠️'} {rateAnalysis.recommendation}
                      </div>
                      <p className="text-sm text-gray-300 mt-2">
                        {rateAnalysis.reasoning}
                      </p>
                    </div>
                  </div>
                )}

                {/* SECTION 4: Where Does the Money Go? */}
                {capitalFlow && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-2 flex items-center gap-2">
                      💰 Where Does the Borrowed Capital Go?
                    </h2>
                    <p className="text-gray-400 text-sm mb-4">
                      When PROMETHEUS borrows via box spreads, it deploys the capital to these Iron Condor bots to generate returns:
                    </p>

                    <div className="grid md:grid-cols-3 gap-4">
                      {[
                        { name: 'ARES', pct: 35, desc: 'SPY 0DTE Iron Condors', color: 'red' },
                        { name: 'TITAN', pct: 35, desc: 'SPX Aggressive Iron Condors', color: 'blue' },
                        { name: 'PEGASUS', pct: 20, desc: 'SPX Weekly Iron Condors', color: 'purple' },
                      ].map((bot) => {
                        const data = capitalFlow.deployment_summary?.[bot.name.toLowerCase()] || { deployed: 0, returns: 0, roi: 0 }
                        return (
                          <div key={bot.name} className={`bg-${bot.color}-900/20 border border-${bot.color}-700/30 rounded-lg p-4`}>
                            <div className="flex justify-between items-start mb-2">
                              <div>
                                <div className="font-bold text-lg">{bot.name}</div>
                                <div className="text-xs text-gray-400">{bot.desc}</div>
                              </div>
                              <div className="text-xs bg-gray-700 px-2 py-1 rounded">
                                {bot.pct}% allocation
                              </div>
                            </div>
                            <div className="mt-3 space-y-1 text-sm">
                              <div className="flex justify-between">
                                <span className="text-gray-400">Deployed:</span>
                                <span className="font-medium">{formatCurrency(data.deployed)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-400">Returns:</span>
                                <span className={`font-medium ${data.returns >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatCurrency(data.returns)}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-400">ROI:</span>
                                <span className={`font-medium ${data.roi >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatPct(data.roi)}
                                </span>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>

                    {/* Reserve */}
                    <div className="mt-4 bg-gray-700/30 rounded-lg p-4">
                      <div className="flex justify-between items-center">
                        <div>
                          <div className="font-medium">🛡️ Reserve (10%)</div>
                          <div className="text-xs text-gray-400">Safety buffer for margin & emergencies</div>
                        </div>
                        <div className="text-right">
                          <div className="font-medium">{formatCurrency(capitalFlow.reserve || 0)}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* SECTION 5: Daily Briefing (at bottom) */}
                {dailyBriefing && (dailyBriefing.actions?.recommendations?.length > 0 || dailyBriefing.actions?.warnings?.length > 0 || dailyBriefing.daily_tip) && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                      📋 Today&apos;s Briefing
                    </h2>

                    {dailyBriefing.actions?.recommendations?.length > 0 && (
                      <div className="mb-4">
                        <h3 className="text-sm font-medium text-green-400 mb-2">Recommendations</h3>
                        <ul className="space-y-1">
                          {dailyBriefing.actions.recommendations.map((rec: string, i: number) => (
                            <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                              <span className="text-green-400">→</span> {rec}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {dailyBriefing.actions?.warnings?.length > 0 && (
                      <div className="mb-4">
                        <h3 className="text-sm font-medium text-yellow-400 mb-2">Warnings</h3>
                        <ul className="space-y-1">
                          {dailyBriefing.actions.warnings.map((warn: string, i: number) => (
                            <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                              <span className="text-yellow-400">⚠️</span> {warn}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {(dailyBriefing.education?.daily_tip || dailyBriefing.daily_tip) && (
                      <div className="bg-blue-900/30 rounded-lg p-4">
                        <h3 className="text-sm font-medium text-blue-400 mb-2">💡 Tip of the Day</h3>
                        <p className="text-sm text-gray-300">{dailyBriefing.education?.daily_tip || dailyBriefing.daily_tip}</p>
                      </div>
                    )}
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
                    <p className="text-sm text-gray-400">
                      {positions?.count || 0} active positions
                    </p>
                  </div>

                  {positions?.positions?.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="bg-gray-700/50">
                          <tr>
                            <th className="px-4 py-3 text-left text-sm">Position</th>
                            <th className="px-4 py-3 text-left text-sm">Strikes</th>
                            <th className="px-4 py-3 text-left text-sm">Expiration</th>
                            <th className="px-4 py-3 text-right text-sm">Cash Received</th>
                            <th className="px-4 py-3 text-right text-sm">Borrowing Cost</th>
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
                                <div className="text-sm text-gray-400">
                                  {pos.lower_strike}/{pos.upper_strike}
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <div>{pos.expiration}</div>
                                <div className="text-sm text-gray-400">{pos.current_dte} DTE</div>
                              </td>
                              <td className="px-4 py-3 text-right">
                                <div>{formatCurrency(pos.total_credit_received)}</div>
                                <div className="text-xs text-gray-400">
                                  @ {formatPct(pos.implied_annual_rate)}
                                </div>
                              </td>
                              <td className="px-4 py-3 text-right text-red-400">
                                {formatCurrency(pos.borrowing_cost)}
                              </td>
                              <td className="px-4 py-3 text-right text-green-400">
                                {formatCurrency(pos.total_ic_returns)}
                              </td>
                              <td className={`px-4 py-3 text-right font-medium ${
                                pos.net_profit >= 0 ? 'text-green-400' : 'text-red-400'
                              }`}>
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
                      <p className="text-lg">No Open Box Spread Positions</p>
                      <p className="text-sm mt-2 max-w-md mx-auto">
                        PROMETHEUS automatically scans for box spread opportunities during the daily cycle at 9:30 AM CT.
                        When favorable rates are found, positions are opened automatically.
                      </p>
                      <div className="mt-4 p-4 bg-blue-900/20 border border-blue-700/30 rounded-lg inline-block text-left">
                        <div className="text-xs text-blue-400 font-medium mb-2">Automated Schedule:</div>
                        <div className="text-xs text-gray-400 space-y-1">
                          <div>• Daily cycle: 9:30 AM CT</div>
                          <div>• Roll check: When DTE &lt; 30</div>
                          <div>• Equity snapshots: Every 30 minutes</div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Position Summary */}
                {positions?.summary && (
                  <div className="grid md:grid-cols-4 gap-4">
                    <div className="bg-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400">Total Borrowed</div>
                      <div className="text-xl font-bold text-blue-400">
                        {formatCurrency(positions.summary.total_borrowed)}
                      </div>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400">Total Deployed</div>
                      <div className="text-xl font-bold">
                        {formatCurrency(positions.summary.total_deployed)}
                      </div>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400">Total Returns</div>
                      <div className="text-xl font-bold text-green-400">
                        {formatCurrency(positions.summary.total_returns)}
                      </div>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400">Net Profit</div>
                      <div className={`text-xl font-bold ${
                        positions.summary.net_profit >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {formatCurrency(positions.summary.net_profit)}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Analytics Tab - Full Transparency */}
            {activeTab === 'analytics' && (
              <div className="space-y-6">

                {/* Capital Flow Summary - Where is every dollar? */}
                <div className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg p-6 border border-orange-900/30">
                  <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
                    💰 Capital Traceability
                  </h2>
                  <p className="text-gray-400 text-sm mb-6">
                    Track every dollar from box spread borrowing through IC bot deployment to returns
                  </p>

                  {/* Money Flow Visualization */}
                  <div className="grid md:grid-cols-5 gap-2 items-center mb-6">
                    {/* Step 1: Borrowed */}
                    <div className="bg-blue-900/30 rounded-lg p-4 text-center border border-blue-700/30">
                      <div className="text-xs text-gray-400 mb-1">BORROWED</div>
                      <div className="text-xl font-bold text-blue-400">
                        {formatCurrency(status?.total_borrowed || 0)}
                      </div>
                      <div className="text-xs text-gray-500">via Box Spreads</div>
                    </div>

                    <div className="text-center text-2xl text-gray-600">→</div>

                    {/* Step 2: Deployed */}
                    <div className="bg-purple-900/30 rounded-lg p-4 text-center border border-purple-700/30">
                      <div className="text-xs text-gray-400 mb-1">DEPLOYED</div>
                      <div className="text-xl font-bold text-purple-400">
                        {formatCurrency(capitalFlow?.total_deployed || 0)}
                      </div>
                      <div className="text-xs text-gray-500">to IC Bots</div>
                    </div>

                    <div className="text-center text-2xl text-gray-600">→</div>

                    {/* Step 3: Returns */}
                    <div className="bg-green-900/30 rounded-lg p-4 text-center border border-green-700/30">
                      <div className="text-xs text-gray-400 mb-1">RETURNS</div>
                      <div className="text-xl font-bold text-green-400">
                        {formatCurrency(status?.total_ic_returns || 0)}
                      </div>
                      <div className="text-xs text-gray-500">from IC Trading</div>
                    </div>
                  </div>

                  {/* Detailed Breakdown */}
                  <div className="bg-black/30 rounded-lg p-4 font-mono text-sm">
                    <div className="grid md:grid-cols-2 gap-6">
                      {/* Left: Sources */}
                      <div>
                        <div className="text-orange-400 font-bold mb-2">📥 CAPITAL SOURCES</div>
                        <div className="space-y-1">
                          <div className="flex justify-between">
                            <span className="text-gray-400">Box Spread Credit:</span>
                            <span className="text-blue-400">+{formatCurrency(status?.total_borrowed || 0)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">IC Bot Returns:</span>
                            <span className="text-green-400">+{formatCurrency(status?.total_ic_returns || 0)}</span>
                          </div>
                          <div className="border-t border-gray-700 my-2"></div>
                          <div className="flex justify-between font-bold">
                            <span>Total Inflows:</span>
                            <span className="text-white">
                              {formatCurrency((status?.total_borrowed || 0) + (status?.total_ic_returns || 0))}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Uses */}
                      <div>
                        <div className="text-orange-400 font-bold mb-2">📤 CAPITAL USES</div>
                        <div className="space-y-1">
                          <div className="flex justify-between">
                            <span className="text-gray-400">→ ARES (35%):</span>
                            <span>{formatCurrency(capitalFlow?.deployment_summary?.ares?.deployed || 0)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">→ TITAN (35%):</span>
                            <span>{formatCurrency(capitalFlow?.deployment_summary?.titan?.deployed || 0)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">→ PEGASUS (20%):</span>
                            <span>{formatCurrency(capitalFlow?.deployment_summary?.pegasus?.deployed || 0)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">→ Reserve (10%):</span>
                            <span>{formatCurrency(capitalFlow?.reserve || 0)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">Borrowing Cost:</span>
                            <span className="text-red-400">-{formatCurrency(status?.total_borrowing_costs || 0)}</span>
                          </div>
                          <div className="border-t border-gray-700 my-2"></div>
                          <div className="flex justify-between font-bold">
                            <span>Net P&L:</span>
                            <span className={`${(status?.net_unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {formatCurrency(status?.net_unrealized_pnl || 0)}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Equity Curve */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    📈 Equity Curve
                  </h2>

                  {equityCurve?.equity_curve && equityCurve.equity_curve.length > 0 ? (
                    <div>
                      <div className="flex justify-between items-center text-sm text-gray-400 mb-4">
                        <span>Starting Capital: {formatCurrency(equityCurve.starting_capital)}</span>
                        <span>Current Equity: {formatCurrency(equityCurve.equity_curve[equityCurve.equity_curve.length - 1]?.equity || equityCurve.starting_capital)}</span>
                      </div>

                      {/* Visual Chart */}
                      <div className="bg-black/30 rounded-lg p-4 mb-4">
                        <div className="h-48 relative">
                          {(() => {
                            const data = equityCurve.equity_curve.slice(-30)
                            if (data.length < 2) return <div className="text-center text-gray-500 pt-20">Not enough data points for chart</div>

                            const values = data.map((d: any) => d.equity)
                            const min = Math.min(...values)
                            const max = Math.max(...values)
                            const range = max - min || 1

                            return (
                              <svg className="w-full h-full" viewBox="0 0 400 150" preserveAspectRatio="none">
                                {/* Grid lines */}
                                <line x1="0" y1="37.5" x2="400" y2="37.5" stroke="#374151" strokeWidth="0.5" />
                                <line x1="0" y1="75" x2="400" y2="75" stroke="#374151" strokeWidth="0.5" />
                                <line x1="0" y1="112.5" x2="400" y2="112.5" stroke="#374151" strokeWidth="0.5" />

                                {/* Starting capital line */}
                                {(() => {
                                  const startY = 150 - ((equityCurve.starting_capital - min) / range) * 140 - 5
                                  return (
                                    <line x1="0" y1={startY} x2="400" y2={startY} stroke="#f97316" strokeWidth="1" strokeDasharray="4,4" opacity="0.5" />
                                  )
                                })()}

                                {/* Equity line */}
                                <polyline
                                  fill="none"
                                  stroke="#22c55e"
                                  strokeWidth="2"
                                  points={data.map((d: any, i: number) => {
                                    const x = (i / (data.length - 1)) * 400
                                    const y = 150 - ((d.equity - min) / range) * 140 - 5
                                    return `${x},${y}`
                                  }).join(' ')}
                                />

                                {/* Area fill */}
                                <polygon
                                  fill="url(#equityGradient)"
                                  points={`0,150 ${data.map((d: any, i: number) => {
                                    const x = (i / (data.length - 1)) * 400
                                    const y = 150 - ((d.equity - min) / range) * 140 - 5
                                    return `${x},${y}`
                                  }).join(' ')} 400,150`}
                                />

                                <defs>
                                  <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3" />
                                    <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                                  </linearGradient>
                                </defs>
                              </svg>
                            )
                          })()}
                        </div>
                        <div className="flex justify-between text-xs text-gray-500 mt-2">
                          <span>{equityCurve.equity_curve[0]?.date || 'Start'}</span>
                          <span>{equityCurve.equity_curve[equityCurve.equity_curve.length - 1]?.date || 'Now'}</span>
                        </div>
                      </div>

                      {/* Data Table */}
                      <div className="bg-black/30 rounded-lg p-4 overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left text-gray-400 border-b border-gray-700">
                              <th className="pb-2">Date</th>
                              <th className="pb-2 text-right">Daily P&L</th>
                              <th className="pb-2 text-right">Cumulative</th>
                              <th className="pb-2 text-right">Equity</th>
                              <th className="pb-2 text-right">Positions</th>
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
                                <td className="py-2 text-right text-gray-400">{point.positions_closed}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-gray-400">
                      <div className="text-4xl mb-2">📊</div>
                      <p>No equity history yet.</p>
                      <p className="text-sm mt-2">Equity curve will appear after positions are opened and closed.</p>
                      <p className="text-xs mt-4 text-gray-500">
                        PROMETHEUS runs automatically at 9:30 AM CT daily to manage positions.
                      </p>
                    </div>
                  )}

                  {/* Intraday Snapshots */}
                  {intradayEquity?.snapshots && intradayEquity.snapshots.length > 0 && (
                    <div className="mt-6">
                      <h3 className="text-lg font-medium mb-3">Today&apos;s Snapshots</h3>
                      <div className="bg-black/30 rounded-lg p-4 overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left text-gray-400 border-b border-gray-700">
                              <th className="pb-2">Time</th>
                              <th className="pb-2 text-right">Equity</th>
                              <th className="pb-2 text-right">Unrealized</th>
                              <th className="pb-2 text-right">Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {intradayEquity.snapshots.slice(-5).map((snap: any, idx: number) => (
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

                {/* IC Bot Positions - Where is the money working? */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    🤖 IC Bot Positions (Funded by PROMETHEUS)
                  </h2>
                  <p className="text-gray-400 text-sm mb-4">
                    These are the active Iron Condor positions that PROMETHEUS capital is funding
                  </p>

                  <div className="space-y-6">
                    {/* ARES Positions */}
                    <div className="bg-red-900/10 border border-red-900/30 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold text-lg flex items-center gap-2">
                          <span className="text-red-400">⚔️</span> ARES (SPY 0DTE)
                        </h3>
                        <div className="text-sm">
                          <span className="text-gray-400">Allocated: </span>
                          <span className="font-medium">{formatCurrency(capitalFlow?.deployment_summary?.ares?.deployed || 0)}</span>
                        </div>
                      </div>
                      {aresPositions?.positions && aresPositions.positions.length > 0 ? (
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="text-left text-gray-400 border-b border-gray-700">
                                <th className="pb-2">Symbol</th>
                                <th className="pb-2">Strikes</th>
                                <th className="pb-2 text-right">Entry</th>
                                <th className="pb-2 text-right">Current</th>
                                <th className="pb-2 text-right">P&L</th>
                              </tr>
                            </thead>
                            <tbody>
                              {aresPositions.positions.slice(0, 5).map((pos: any, idx: number) => (
                                <tr key={idx} className="border-b border-gray-700/50">
                                  <td className="py-2">{pos.symbol || pos.ticker || 'SPY'}</td>
                                  <td className="py-2">{pos.short_put_strike}/{pos.short_call_strike}</td>
                                  <td className="py-2 text-right">{formatCurrency(pos.entry_credit || pos.entry_price)}</td>
                                  <td className="py-2 text-right">{formatCurrency(pos.current_value || pos.current_price)}</td>
                                  <td className={`py-2 text-right ${(pos.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatCurrency(pos.unrealized_pnl || 0)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="text-gray-500 text-sm">No active ARES positions</p>
                      )}
                    </div>

                    {/* TITAN Positions */}
                    <div className="bg-blue-900/10 border border-blue-900/30 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold text-lg flex items-center gap-2">
                          <span className="text-blue-400">🏛️</span> TITAN (SPX Aggressive)
                        </h3>
                        <div className="text-sm">
                          <span className="text-gray-400">Allocated: </span>
                          <span className="font-medium">{formatCurrency(capitalFlow?.deployment_summary?.titan?.deployed || 0)}</span>
                        </div>
                      </div>
                      {titanPositions?.positions && titanPositions.positions.length > 0 ? (
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="text-left text-gray-400 border-b border-gray-700">
                                <th className="pb-2">Symbol</th>
                                <th className="pb-2">Strikes</th>
                                <th className="pb-2 text-right">Entry</th>
                                <th className="pb-2 text-right">Current</th>
                                <th className="pb-2 text-right">P&L</th>
                              </tr>
                            </thead>
                            <tbody>
                              {titanPositions.positions.slice(0, 5).map((pos: any, idx: number) => (
                                <tr key={idx} className="border-b border-gray-700/50">
                                  <td className="py-2">{pos.symbol || pos.ticker || 'SPX'}</td>
                                  <td className="py-2">{pos.short_put_strike}/{pos.short_call_strike}</td>
                                  <td className="py-2 text-right">{formatCurrency(pos.entry_credit || pos.entry_price)}</td>
                                  <td className="py-2 text-right">{formatCurrency(pos.current_value || pos.current_price)}</td>
                                  <td className={`py-2 text-right ${(pos.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatCurrency(pos.unrealized_pnl || 0)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="text-gray-500 text-sm">No active TITAN positions</p>
                      )}
                    </div>

                    {/* PEGASUS Positions */}
                    <div className="bg-purple-900/10 border border-purple-900/30 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold text-lg flex items-center gap-2">
                          <span className="text-purple-400">🦄</span> PEGASUS (SPX Weekly)
                        </h3>
                        <div className="text-sm">
                          <span className="text-gray-400">Allocated: </span>
                          <span className="font-medium">{formatCurrency(capitalFlow?.deployment_summary?.pegasus?.deployed || 0)}</span>
                        </div>
                      </div>
                      {pegasusPositions?.positions && pegasusPositions.positions.length > 0 ? (
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="text-left text-gray-400 border-b border-gray-700">
                                <th className="pb-2">Symbol</th>
                                <th className="pb-2">Strikes</th>
                                <th className="pb-2 text-right">Entry</th>
                                <th className="pb-2 text-right">Current</th>
                                <th className="pb-2 text-right">P&L</th>
                              </tr>
                            </thead>
                            <tbody>
                              {pegasusPositions.positions.slice(0, 5).map((pos: any, idx: number) => (
                                <tr key={idx} className="border-b border-gray-700/50">
                                  <td className="py-2">{pos.symbol || pos.ticker || 'SPX'}</td>
                                  <td className="py-2">{pos.short_put_strike}/{pos.short_call_strike}</td>
                                  <td className="py-2 text-right">{formatCurrency(pos.entry_credit || pos.entry_price)}</td>
                                  <td className="py-2 text-right">{formatCurrency(pos.current_value || pos.current_price)}</td>
                                  <td className={`py-2 text-right ${(pos.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {formatCurrency(pos.unrealized_pnl || 0)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="text-gray-500 text-sm">No active PEGASUS positions</p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Live Interest Rates */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    💹 Live Interest Rates
                  </h2>
                  <p className="text-gray-400 text-sm mb-4">
                    Real-time benchmark rates for comparing box spread borrowing costs
                  </p>

                  {interestRates ? (
                    <div>
                      <div className="grid md:grid-cols-5 gap-3 mb-4">
                        <div className="bg-blue-900/30 rounded-lg p-4 text-center border border-blue-700/30">
                          <div className="text-xs text-gray-400 mb-1">Fed Funds</div>
                          <div className="text-xl font-bold text-blue-400">{formatPct(interestRates.fed_funds_rate)}</div>
                          <div className="text-xs text-gray-500">Risk-free rate</div>
                        </div>
                        <div className="bg-cyan-900/30 rounded-lg p-4 text-center border border-cyan-700/30">
                          <div className="text-xs text-gray-400 mb-1">SOFR</div>
                          <div className="text-xl font-bold text-cyan-400">{formatPct(interestRates.sofr_rate)}</div>
                          <div className="text-xs text-gray-500">Repo market</div>
                        </div>
                        <div className="bg-purple-900/30 rounded-lg p-4 text-center border border-purple-700/30">
                          <div className="text-xs text-gray-400 mb-1">3M Treasury</div>
                          <div className="text-xl font-bold text-purple-400">{formatPct(interestRates.treasury_3m)}</div>
                          <div className="text-xs text-gray-500">T-Bill yield</div>
                        </div>
                        <div className="bg-red-900/30 rounded-lg p-4 text-center border border-red-700/30">
                          <div className="text-xs text-gray-400 mb-1">Margin Rate</div>
                          <div className="text-xl font-bold text-red-400">{formatPct(interestRates.margin_rate)}</div>
                          <div className="text-xs text-gray-500">Broker estimate</div>
                        </div>
                        <div className="bg-green-900/30 rounded-lg p-4 text-center border border-green-700/30">
                          <div className="text-xs text-gray-400 mb-1">Box Spread</div>
                          <div className="text-xl font-bold text-green-400">{formatPct(rateAnalysis?.box_implied_rate || 0)}</div>
                          <div className="text-xs text-gray-500">Your rate</div>
                        </div>
                      </div>

                      <div className="bg-black/30 rounded-lg p-3 flex justify-between items-center text-xs">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${interestRates.source === 'live' ? 'bg-green-500' : interestRates.source === 'cached' ? 'bg-yellow-500' : 'bg-gray-500'}`}></span>
                          <span className="text-gray-400">
                            Source: {interestRates.source?.toUpperCase() || 'UNKNOWN'}
                          </span>
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

                {/* Rate Trend */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    📉 Borrowing Rate Trend
                  </h2>
                  <p className="text-gray-400 text-sm mb-4">
                    Historical box spread implied rates help you understand if rates are favorable
                  </p>

                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="bg-black/30 rounded-lg p-4 text-center">
                      <div className="text-sm text-gray-400 mb-1">Current Rate</div>
                      <div className="text-2xl font-bold text-blue-400">
                        {formatPct(rateAnalysis?.box_implied_rate || 0)}
                      </div>
                    </div>
                    <div className="bg-black/30 rounded-lg p-4 text-center">
                      <div className="text-sm text-gray-400 mb-1">30-Day Avg</div>
                      <div className="text-2xl font-bold">
                        {formatPct(rateAnalysis?.avg_box_rate_30d || rateAnalysis?.box_implied_rate || 0)}
                      </div>
                    </div>
                    <div className="bg-black/30 rounded-lg p-4 text-center">
                      <div className="text-sm text-gray-400 mb-1">Trend</div>
                      <div className={`text-2xl font-bold ${
                        rateAnalysis?.rate_trend === 'FALLING' ? 'text-green-400' :
                        rateAnalysis?.rate_trend === 'RISING' ? 'text-red-400' : 'text-gray-400'
                      }`}>
                        {rateAnalysis?.rate_trend || 'STABLE'}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Education Tab */}
            {activeTab === 'education' && (
              <div className="grid md:grid-cols-4 gap-6">
                {/* Topic List */}
                <div className="md:col-span-1">
                  <div className="bg-gray-800 rounded-lg p-4">
                    <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                      <span className="text-orange-400">📚</span> Learn
                    </h3>
                    <div className="space-y-1">
                      {[
                        { id: 'overview', name: 'Overview', icon: '🏠' },
                        { id: 'mechanics', name: 'How It Works', icon: '⚙️' },
                        { id: 'risks', name: 'Understanding Risks', icon: '⚠️' },
                        { id: 'comparison', name: 'vs Alternatives', icon: '⚖️' },
                      ].map((topic) => (
                        <button
                          key={topic.id}
                          onClick={() => setEducationTopic(topic.id)}
                          className={`w-full text-left px-4 py-3 rounded-lg transition-all ${
                            educationTopic === topic.id
                              ? 'bg-gradient-to-r from-orange-600 to-red-600 text-white shadow-lg'
                              : 'text-gray-400 hover:bg-gray-700 hover:text-white'
                          }`}
                        >
                          <span className="mr-2">{topic.icon}</span>
                          {topic.name}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Content */}
                <div className="md:col-span-3">
                  <div className="bg-gray-800 rounded-lg overflow-hidden">
                    {educationContent ? (
                      <div>
                        {/* Header */}
                        <div className="bg-gradient-to-r from-orange-900/50 to-red-900/50 px-6 py-4 border-b border-gray-700">
                          <h2 className="text-2xl font-bold">{educationContent.title}</h2>
                        </div>

                        {/* Content with proper markdown styling */}
                        <div className="p-6">
                          <div className="prose prose-invert prose-orange max-w-none
                            prose-headings:text-white prose-headings:font-bold
                            prose-h1:text-2xl prose-h1:border-b prose-h1:border-gray-700 prose-h1:pb-2 prose-h1:mb-4
                            prose-h2:text-xl prose-h2:text-orange-400 prose-h2:mt-6 prose-h2:mb-3
                            prose-h3:text-lg prose-h3:text-gray-200 prose-h3:mt-4 prose-h3:mb-2
                            prose-p:text-gray-300 prose-p:leading-relaxed prose-p:mb-4
                            prose-strong:text-white prose-strong:font-semibold
                            prose-ul:text-gray-300 prose-ul:my-4 prose-ul:space-y-2
                            prose-ol:text-gray-300 prose-ol:my-4 prose-ol:space-y-2
                            prose-li:leading-relaxed
                            prose-code:bg-gray-700 prose-code:px-2 prose-code:py-0.5 prose-code:rounded prose-code:text-orange-300
                            prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-700 prose-pre:rounded-lg
                            prose-blockquote:border-l-4 prose-blockquote:border-orange-500 prose-blockquote:bg-gray-700/50 prose-blockquote:pl-4 prose-blockquote:py-2 prose-blockquote:italic
                            prose-a:text-orange-400 prose-a:no-underline hover:prose-a:underline
                            prose-table:border-collapse prose-table:w-full
                            prose-th:bg-gray-700 prose-th:px-4 prose-th:py-2 prose-th:text-left prose-th:border prose-th:border-gray-600
                            prose-td:px-4 prose-td:py-2 prose-td:border prose-td:border-gray-700
                          ">
                            <ReactMarkdown>
                              {educationContent.content}
                            </ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="p-6 text-center text-gray-400">
                        <div className="text-4xl mb-4">📖</div>
                        <p>Select a topic to learn more about box spread synthetic borrowing</p>
                      </div>
                    )}
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
