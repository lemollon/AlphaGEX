'use client'

import { useState, useEffect } from 'react'
import useSWR from 'swr'
import Navigation from '@/components/Navigation'

const fetcher = (url: string) => fetch(url).then(res => res.json())

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
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'analytics' | 'education' | 'calculator'>('overview')
  const [educationTopic, setEducationTopic] = useState('overview')

  // Calculator state
  const [calcStrikeWidth, setCalcStrikeWidth] = useState(50)
  const [calcDte, setCalcDte] = useState(180)
  const [calcMarketPrice, setCalcMarketPrice] = useState(49.5)

  // Data fetching
  const { data: status, error: statusError } = useSWR('/api/prometheus-box/status', fetcher, { refreshInterval: 30000 })
  const { data: positions } = useSWR('/api/prometheus-box/positions', fetcher, { refreshInterval: 30000 })
  const { data: rateAnalysis } = useSWR('/api/prometheus-box/analytics/rates', fetcher, { refreshInterval: 60000 })
  const { data: capitalFlow } = useSWR('/api/prometheus-box/analytics/capital-flow', fetcher, { refreshInterval: 30000 })
  const { data: dailyBriefing } = useSWR('/api/prometheus-box/operations/daily-briefing', fetcher, { refreshInterval: 60000 })
  const { data: educationContent } = useSWR(`/api/prometheus-box/education/${educationTopic}`, fetcher)
  const { data: calcResult } = useSWR(
    `/api/prometheus-box/education/calculator?strike_width=${calcStrikeWidth}&dte=${calcDte}&market_price=${calcMarketPrice}`,
    fetcher
  )

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
            {['overview', 'positions', 'analytics', 'education', 'calculator'].map((tab) => (
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
                {/* Daily Briefing */}
                {dailyBriefing && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                      📋 Daily Briefing
                    </h2>

                    {/* Recommendations */}
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

                    {/* Warnings */}
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

                    {/* Tip of the Day */}
                    {dailyBriefing.education?.daily_tip && (
                      <div className="bg-blue-900/30 rounded-lg p-4 mt-4">
                        <h3 className="text-sm font-medium text-blue-400 mb-2">💡 Tip of the Day</h3>
                        <p className="text-sm text-gray-300">{dailyBriefing.education.daily_tip}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Rate Analysis */}
                {rateAnalysis && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                      📊 Current Rate Analysis
                    </h2>

                    <div className="grid md:grid-cols-3 gap-6">
                      <div>
                        <div className="text-sm text-gray-400">Box Spread Implied Rate</div>
                        <div className="text-2xl font-bold text-blue-400">
                          {formatPct(rateAnalysis.box_implied_rate)}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-400">Broker Margin Rate</div>
                        <div className="text-2xl font-bold text-red-400">
                          {formatPct(rateAnalysis.broker_margin_rate)}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-400">Your Savings</div>
                        <div className="text-2xl font-bold text-green-400">
                          {formatPct(Math.abs(rateAnalysis.spread_to_margin))}
                        </div>
                      </div>
                    </div>

                    <div className={`mt-4 p-4 rounded-lg ${
                      rateAnalysis.is_favorable ? 'bg-green-900/30' : 'bg-yellow-900/30'
                    }`}>
                      <div className={`font-medium ${
                        rateAnalysis.is_favorable ? 'text-green-400' : 'text-yellow-400'
                      }`}>
                        {rateAnalysis.recommendation}
                      </div>
                      <p className="text-sm text-gray-300 mt-1 whitespace-pre-wrap">
                        {rateAnalysis.reasoning}
                      </p>
                    </div>
                  </div>
                )}

                {/* Capital Flow */}
                {capitalFlow && (
                  <div className="bg-gray-800 rounded-lg p-6">
                    <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                      💰 Capital Flow to IC Bots
                    </h2>

                    <div className="space-y-4">
                      {['ares', 'titan', 'pegasus'].map((bot) => {
                        const data = capitalFlow.deployment_summary?.[bot]
                        if (!data) return null
                        return (
                          <div key={bot} className="bg-gray-700/50 rounded-lg p-4">
                            <div className="flex justify-between items-center">
                              <div className="font-medium text-lg">
                                {bot.toUpperCase()}
                              </div>
                              <div className={`text-sm px-2 py-1 rounded ${
                                data.roi > 0 ? 'bg-green-900/50 text-green-400' : 'bg-gray-600 text-gray-300'
                              }`}>
                                ROI: {formatPct(data.roi)}
                              </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4 mt-2 text-sm">
                              <div>
                                <span className="text-gray-400">Deployed: </span>
                                <span>{formatCurrency(data.deployed)}</span>
                              </div>
                              <div>
                                <span className="text-gray-400">Returns: </span>
                                <span className={data.returns >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  {formatCurrency(data.returns)}
                                </span>
                              </div>
                            </div>
                          </div>
                        )
                      })}
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
                    <p className="text-sm text-gray-400">
                      {positions?.count || 0} active positions
                    </p>
                  </div>

                  {positions?.open_positions?.length > 0 ? (
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
                          {positions.open_positions.map((pos: Position) => (
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
                      <p>No open positions</p>
                      <p className="text-sm mt-2">Run a signal scan to find opportunities</p>
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

            {/* Analytics Tab */}
            {activeTab === 'analytics' && (
              <div className="space-y-6">
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">Performance Summary</h2>
                  <p className="text-gray-400">
                    Detailed analytics coming soon...
                  </p>
                </div>
              </div>
            )}

            {/* Education Tab */}
            {activeTab === 'education' && (
              <div className="grid md:grid-cols-4 gap-6">
                {/* Topic List */}
                <div className="md:col-span-1">
                  <div className="bg-gray-800 rounded-lg p-4">
                    <h3 className="font-medium mb-4">Topics</h3>
                    <div className="space-y-2">
                      {[
                        { id: 'overview', name: 'Overview' },
                        { id: 'mechanics', name: 'How It Works' },
                        { id: 'risks', name: 'Understanding Risks' },
                        { id: 'comparison', name: 'vs Alternatives' },
                      ].map((topic) => (
                        <button
                          key={topic.id}
                          onClick={() => setEducationTopic(topic.id)}
                          className={`w-full text-left px-3 py-2 rounded transition-colors ${
                            educationTopic === topic.id
                              ? 'bg-orange-600 text-white'
                              : 'text-gray-400 hover:bg-gray-700'
                          }`}
                        >
                          {topic.name}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Content */}
                <div className="md:col-span-3">
                  <div className="bg-gray-800 rounded-lg p-6">
                    {educationContent ? (
                      <div>
                        <h2 className="text-2xl font-bold mb-4">{educationContent.title}</h2>
                        <div className="prose prose-invert max-w-none">
                          <pre className="whitespace-pre-wrap font-sans text-gray-300">
                            {educationContent.content}
                          </pre>
                        </div>
                      </div>
                    ) : (
                      <p className="text-gray-400">Select a topic to learn more</p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Calculator Tab */}
            {activeTab === 'calculator' && (
              <div className="grid md:grid-cols-2 gap-6">
                {/* Inputs */}
                <div className="bg-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">📱 Box Spread Calculator</h2>
                  <p className="text-sm text-gray-400 mb-6">
                    Experiment with different parameters to understand box spread borrowing costs.
                  </p>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Strike Width (points)
                      </label>
                      <input
                        type="number"
                        value={calcStrikeWidth}
                        onChange={(e) => setCalcStrikeWidth(Number(e.target.value))}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Example: 50 points = $5,000 per contract at expiration
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Days to Expiration (DTE)
                      </label>
                      <input
                        type="number"
                        value={calcDte}
                        onChange={(e) => setCalcDte(Number(e.target.value))}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Longer DTE usually means lower implied rates
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Market Price (per share)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={calcMarketPrice}
                        onChange={(e) => setCalcMarketPrice(Number(e.target.value))}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        This is what you receive when selling the box spread
                      </p>
                    </div>
                  </div>
                </div>

                {/* Results */}
                {calcResult && (
                  <div className="space-y-4">
                    <div className="bg-gray-800 rounded-lg p-6">
                      <h3 className="font-medium mb-4">Per Contract</h3>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-sm text-gray-400">Cash Received</div>
                          <div className="text-xl font-bold text-green-400">
                            {formatCurrency(calcResult.per_contract?.cash_received)}
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-400">Owed at Expiration</div>
                          <div className="text-xl font-bold text-red-400">
                            {formatCurrency(calcResult.per_contract?.cash_owed_at_expiration)}
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-400">Borrowing Cost</div>
                          <div className="text-xl font-bold">
                            {formatCurrency(calcResult.per_contract?.borrowing_cost)}
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-400">Daily Cost</div>
                          <div className="text-xl font-bold">
                            {formatCurrency(calcResult.per_contract?.daily_cost)}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gray-800 rounded-lg p-6">
                      <h3 className="font-medium mb-4">Implied Rates</h3>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-sm text-gray-400">Annual Rate</div>
                          <div className="text-xl font-bold text-blue-400">
                            {formatPct(calcResult.rates?.implied_annual_rate)}
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-400">Monthly Rate</div>
                          <div className="text-xl font-bold">
                            {formatPct(calcResult.rates?.implied_monthly_rate)}
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-400">vs Margin Rate</div>
                          <div className="text-xl font-bold text-green-400">
                            Save {formatPct(calcResult.rates?.savings_vs_margin_pct)}
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-400">Break-even IC Return</div>
                          <div className="text-xl font-bold">
                            {formatPct(calcResult.break_even?.required_monthly_ic_return)}/mo
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="bg-blue-900/30 rounded-lg p-4">
                      <h3 className="font-medium text-blue-400 mb-2">Example with 10 Contracts</h3>
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="text-gray-400">Cash Received: </span>
                          <span className="text-green-400">
                            {formatCurrency(calcResult.example_10_contracts?.cash_received)}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-400">Total Cost: </span>
                          <span>
                            {formatCurrency(calcResult.example_10_contracts?.total_borrowing_cost)}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-400">vs Margin Savings: </span>
                          <span className="text-green-400">
                            {formatCurrency(calcResult.example_10_contracts?.vs_margin_savings)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
