'use client'

import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, BarChart3, Activity, PlayCircle, Filter, ChevronDown, Target, Zap } from 'lucide-react'
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import Navigation from '@/components/Navigation'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function PsychologyPerformance() {
  const [overview, setOverview] = useState<any>(null)
  const [patterns, setPatterns] = useState<any[]>([])
  const [signals, setSignals] = useState<any[]>([])
  const [positions, setPositions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [filterPattern, setFilterPattern] = useState<string | null>(null)
  const [filterConfidence, setFilterConfidence] = useState<number>(0)
  const [filterRisk, setFilterRisk] = useState<string | null>(null)
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      const [overviewRes, patternsRes, signalsRes, positionsRes] = await Promise.all([
        fetch(`${API_URL}/api/psychology/performance/overview`),
        fetch(`${API_URL}/api/psychology/performance/patterns`),
        fetch(`${API_URL}/api/psychology/performance/signals`),
        fetch(`${API_URL}/api/autonomous/positions?status=all`)
      ])

      if (overviewRes.ok) {
        const data = await overviewRes.json()
        setOverview(data.overview)
      }

      if (patternsRes.ok) {
        const data = await patternsRes.json()
        setPatterns(data.patterns || [])
      }

      if (signalsRes.ok) {
        const data = await signalsRes.json()
        setSignals(data.signals || [])
      }

      if (positionsRes.ok) {
        const data = await positionsRes.json()
        setPositions(data.positions || [])
      }

    } catch (err) {
      console.error('Failed to fetch performance data:', err)
      setError('Failed to load performance data')
    } finally {
      setLoading(false)
    }
  }

  // Calculate insights
  const insights = overview ? {
    bestPattern: patterns.length > 0 ? patterns.reduce((best, p) => p.win_rate > best.win_rate ? p : best) : null,
    worstPattern: patterns.length > 0 ? patterns.reduce((worst, p) => p.win_rate < worst.win_rate ? p : worst) : null,
    currentStreak: (() => {
      let streak = 0
      for (const sig of signals) {
        if (sig.correct === null) break
        if (sig.correct === 1) streak++
        else break
      }
      return streak
    })(),
    totalPnL: positions.reduce((sum, p) => sum + (p.pnl || 0), 0)
  } : null

  // Filter signals
  const filteredSignals = signals.filter(sig => {
    if (filterPattern && sig.pattern !== filterPattern) return false
    if (filterConfidence > 0 && sig.confidence < filterConfidence) return false
    if (filterRisk && sig.risk_level !== filterRisk) return false
    return true
  })

  // Prepare chart data
  const winRateData = signals.slice(0, 30).reverse().map((sig, idx) => ({
    index: idx + 1,
    winRate: sig.correct !== null ? (sig.correct * 100) : null
  })).filter(d => d.winRate !== null)

  const patternDistData = patterns.map(p => ({
    name: p.pattern_type.replace(/_/g, ' '),
    value: p.total_signals
  }))

  const activityData = signals.slice(0, 20).reverse().map((sig, idx) => ({
    day: `D${idx + 1}`,
    signals: 1
  })).reduce((acc: any[], curr) => {
    const existing = acc.find(a => a.day === curr.day)
    if (existing) existing.signals++
    else acc.push(curr)
    return acc
  }, [])

  const pnlData = positions.slice(0, 20).map((p, idx) => ({
    trade: `T${idx + 1}`,
    pnl: p.pnl || 0
  }))

  const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <Navigation />
        <main className="pt-16">
          <div className="container mx-auto px-4 py-8">
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-500 border-t-transparent" />
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <Navigation />
        <main className="pt-16">
          <div className="container mx-auto px-4 py-8">
            <div className="bg-red-500/10 border border-red-500 rounded-lg p-6 text-red-400">
              {error}
            </div>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <Navigation />

      <main className="pt-16">
        <div className="container mx-auto px-4 py-8 space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">Psychology Trap Performance</h1>
              <p className="text-gray-400 mt-1">Track win rates, analyze patterns, improve edge</p>
            </div>
            <button
              onClick={fetchData}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg"
            >
              Refresh
            </button>
          </div>

          {/* Empty State */}
          {overview && overview.total_signals === 0 && (
            <div className="bg-gray-900 border-2 border-dashed border-gray-700 rounded-xl p-12 text-center">
              <BarChart3 className="w-20 h-20 mx-auto mb-6 text-gray-600" />
              <h2 className="text-3xl font-bold mb-4">No Performance Data Yet</h2>
              <p className="text-gray-400 text-lg mb-8 max-w-2xl mx-auto">
                Start using Psychology Trap Analysis to build your performance history.
                Every signal you analyze will be tracked here with outcomes.
              </p>
              <button
                onClick={() => window.location.href = '/psychology'}
                className="px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 rounded-lg font-bold text-lg inline-flex items-center gap-3"
              >
                <PlayCircle className="w-6 h-6" />
                Run Analysis Now
              </button>
            </div>
          )}

          {/* Has Data */}
          {overview && overview.total_signals > 0 && (
            <>
              {/* Overview Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="text-sm text-gray-400 mb-1">Total Signals</div>
                  <div className="text-3xl font-bold">{overview.total_signals}</div>
                </div>

                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="text-sm text-gray-400 mb-1">Win Rate</div>
                  <div className="text-3xl font-bold text-green-400">{overview.win_rate.toFixed(1)}%</div>
                  <div className="text-xs text-gray-500 mt-1">{overview.wins}W / {overview.losses}L</div>
                </div>

                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="text-sm text-gray-400 mb-1">Avg Confidence</div>
                  <div className="text-3xl font-bold text-purple-400">{overview.avg_confidence.toFixed(0)}%</div>
                </div>

                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="text-sm text-gray-400 mb-1">Current Streak</div>
                  <div className="text-3xl font-bold text-yellow-400">{insights?.currentStreak || 0}</div>
                  <div className="text-xs text-gray-500 mt-1">consecutive wins</div>
                </div>
              </div>

              {/* Insights Section */}
              {insights && (
                <div className="bg-gradient-to-br from-purple-900/20 to-pink-900/10 border border-purple-500/30 rounded-xl p-6">
                  <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    <Zap className="w-6 h-6 text-yellow-400" />
                    Automated Insights
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {insights.bestPattern && (
                      <div className="bg-gray-950/50 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">Best Pattern</div>
                        <div className="text-lg font-bold text-green-400">
                          {insights.bestPattern.pattern_type.replace(/_/g, ' ')}
                        </div>
                        <div className="text-sm text-gray-300">{insights.bestPattern.win_rate.toFixed(0)}% win rate</div>
                      </div>
                    )}
                    {insights.worstPattern && (
                      <div className="bg-gray-950/50 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">Worst Pattern</div>
                        <div className="text-lg font-bold text-red-400">
                          {insights.worstPattern.pattern_type.replace(/_/g, ' ')}
                        </div>
                        <div className="text-sm text-gray-300">{insights.worstPattern.win_rate.toFixed(0)}% win rate</div>
                      </div>
                    )}
                    <div className="bg-gray-950/50 rounded-lg p-4">
                      <div className="text-sm text-gray-400 mb-1">Trade Journal P&L</div>
                      <div className={`text-lg font-bold ${insights.totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${insights.totalPnL.toFixed(2)}
                      </div>
                      <div className="text-sm text-gray-300">{positions.length} positions</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Advanced Filters */}
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                <button
                  onClick={() => setShowFilters(!showFilters)}
                  className="flex items-center gap-2 text-lg font-bold mb-4"
                >
                  <Filter className="w-5 h-5" />
                  Advanced Filters
                  <ChevronDown className={`w-5 h-5 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
                </button>

                {showFilters && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm text-gray-400 mb-2">Pattern Type</label>
                      <select
                        value={filterPattern || ''}
                        onChange={(e) => setFilterPattern(e.target.value || null)}
                        className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2"
                      >
                        <option value="">All Patterns</option>
                        {patterns.map(p => (
                          <option key={p.pattern_type} value={p.pattern_type}>
                            {p.pattern_type.replace(/_/g, ' ')}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm text-gray-400 mb-2">Min Confidence: {filterConfidence}%</label>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={filterConfidence}
                        onChange={(e) => setFilterConfidence(Number(e.target.value))}
                        className="w-full"
                      />
                    </div>

                    <div>
                      <label className="block text-sm text-gray-400 mb-2">Risk Level</label>
                      <select
                        value={filterRisk || ''}
                        onChange={(e) => setFilterRisk(e.target.value || null)}
                        className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2"
                      >
                        <option value="">All Risk Levels</option>
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                        <option value="extreme">Extreme</option>
                      </select>
                    </div>
                  </div>
                )}

                <div className="mt-4 text-sm text-gray-400">
                  Showing {filteredSignals.length} of {signals.length} signals
                </div>
              </div>

              {/* Charts Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                {/* Win Rate Timeline */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">Win Rate Timeline</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={winRateData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="index" stroke="#9ca3af" />
                      <YAxis stroke="#9ca3af" domain={[0, 100]} />
                      <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                      <Line type="monotone" dataKey="winRate" stroke="#10b981" strokeWidth={2} dot={{ fill: '#10b981' }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Pattern Distribution */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">Pattern Distribution</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie
                        data={patternDistData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={(entry) => entry.name.substring(0, 15)}
                        outerRadius={80}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {patternDistData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                {/* Signal Activity */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">Signal Activity</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={activityData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="day" stroke="#9ca3af" />
                      <YAxis stroke="#9ca3af" />
                      <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                      <Bar dataKey="signals" fill="#8b5cf6" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Cumulative P&L */}
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4">Trade Journal P&L</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={pnlData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="trade" stroke="#9ca3af" />
                      <YAxis stroke="#9ca3af" />
                      <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }} />
                      <Line type="monotone" dataKey="pnl" stroke="#f59e0b" strokeWidth={2} dot={{ fill: '#f59e0b' }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

              </div>

              {/* Pattern Performance Table */}
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                <h2 className="text-xl font-bold mb-4">Pattern Performance</h2>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b border-gray-700">
                      <tr className="text-left text-sm text-gray-400">
                        <th className="pb-3">Pattern</th>
                        <th className="pb-3">Signals</th>
                        <th className="pb-3">Win Rate</th>
                        <th className="pb-3">Avg Win</th>
                        <th className="pb-3">Avg Loss</th>
                        <th className="pb-3">Expectancy</th>
                      </tr>
                    </thead>
                    <tbody className="text-sm">
                      {patterns.map((p, idx) => (
                        <tr key={idx} className="border-b border-gray-800">
                          <td className="py-3">{p.pattern_type.replace(/_/g, ' ')}</td>
                          <td className="py-3">{p.total_signals}</td>
                          <td className={`py-3 font-bold ${p.win_rate >= 70 ? 'text-green-400' : p.win_rate >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
                            {p.win_rate.toFixed(1)}%
                          </td>
                          <td className="py-3 text-green-400">+{p.avg_win_pct.toFixed(2)}%</td>
                          <td className="py-3 text-red-400">{p.avg_loss_pct.toFixed(2)}%</td>
                          <td className={`py-3 font-bold ${p.expectancy >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {p.expectancy.toFixed(2)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Recent Signals */}
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                <h2 className="text-xl font-bold mb-4">Recent Signals ({filteredSignals.length})</h2>
                <div className="space-y-3">
                  {filteredSignals.slice(0, 10).map((sig, idx) => (
                    <div key={idx} className="bg-gray-950/50 rounded-lg p-4 border border-gray-800">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="font-bold text-purple-400">{sig.pattern.replace(/_/g, ' ')}</span>
                            <span className={`px-2 py-1 rounded text-xs ${sig.correct === 1 ? 'bg-green-500/20 text-green-400' : sig.correct === 0 ? 'bg-red-500/20 text-red-400' : 'bg-gray-700 text-gray-400'}`}>
                              {sig.correct === 1 ? 'WIN' : sig.correct === 0 ? 'LOSS' : 'PENDING'}
                            </span>
                            <span className="text-xs text-gray-500">{new Date(sig.timestamp).toLocaleDateString()}</span>
                          </div>
                          <div className="text-sm text-gray-300">{sig.psychology_trap}</div>
                          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                            <span>Confidence: {sig.confidence}%</span>
                            <span>Price: ${sig.price.toFixed(2)}</span>
                            {sig.outcome_5d !== null && (
                              <span className={sig.outcome_5d >= 0 ? 'text-green-400' : 'text-red-400'}>
                                5d: {sig.outcome_5d >= 0 ? '+' : ''}{sig.outcome_5d.toFixed(2)}%
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Trade Journal Integration */}
              {positions.length > 0 && (
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h2 className="text-xl font-bold mb-4">Trade Journal Positions</h2>
                  <div className="space-y-3">
                    {positions.slice(0, 5).map((pos, idx) => (
                      <div key={idx} className="bg-gray-950/50 rounded-lg p-4 border border-gray-800">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-bold">{pos.symbol} {pos.option_type.toUpperCase()} ${pos.strike}</div>
                            <div className="text-sm text-gray-400">{pos.strategy} • {pos.status}</div>
                          </div>
                          <div className="text-right">
                            <div className={`text-lg font-bold ${pos.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              ${pos.pnl?.toFixed(2) || '0.00'}
                            </div>
                            <div className="text-sm text-gray-400">{pos.contracts} contracts</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </>
          )}

        </div>
      </main>
    </div>
  )
}
