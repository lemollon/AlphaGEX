'use client'

import React, { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, AlertCircle, BarChart3, Activity, Target, ArrowUpRight, ArrowDownRight, Zap } from 'lucide-react'

interface OverviewMetrics {
  period_days: number
  total_signals: number
  total_with_outcomes: number
  wins: number
  losses: number
  win_rate: number
  avg_win_pct: number
  avg_loss_pct: number
  avg_confidence: number
  high_confidence_signals: number
  critical_alerts: number
  top_patterns: Array<{ pattern: string; count: number }>
}

interface PatternPerformance {
  pattern_type: string
  total_signals: number
  wins: number
  losses: number
  win_rate: number
  avg_confidence: number
  avg_win_pct: number
  avg_loss_pct: number
  max_gain_pct: number
  max_loss_pct: number
  expectancy: number
}

interface HistoricalSignal {
  timestamp: string
  price: number
  pattern: string
  confidence: number
  direction: string
  risk_level: string
  description: string
  psychology_trap: string
  outcome_1d: number | null
  outcome_5d: number | null
  correct: number | null
  vix: number | null
  vix_change: number | null
  vol_regime: string | null
}

interface ChartData {
  daily_signals: Array<{
    date: string
    count: number
    high_confidence: number
    avg_confidence: number
  }>
  win_rate_timeline: Array<{
    date: string
    win_rate: number
    total_signals: number
  }>
  pattern_timeline: Record<string, Record<string, number>>
}

interface VIXCorrelation {
  by_vix_level: Array<{
    vix_level: string
    total_signals: number
    win_rate: number
    avg_price_change: number
  }>
  by_spike_status: Array<{
    vix_spike: boolean
    total_signals: number
    win_rate: number
    avg_price_change: number
  }>
}

export default function PerformancePage() {
  const [overview, setOverview] = useState<OverviewMetrics | null>(null)
  const [patterns, setPatterns] = useState<PatternPerformance[]>([])
  const [signals, setSignals] = useState<HistoricalSignal[]>([])
  const [chartData, setChartData] = useState<ChartData | null>(null)
  const [vixCorrelation, setVixCorrelation] = useState<VIXCorrelation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedPeriod, setSelectedPeriod] = useState(30)

  useEffect(() => {
    fetchPerformanceData()
  }, [selectedPeriod])

  const fetchPerformanceData = async () => {
    setLoading(true)
    setError(null)

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

      // Fetch all performance data in parallel
      const [overviewRes, patternsRes, signalsRes, chartRes, vixRes] = await Promise.all([
        fetch(`${backendUrl}/api/psychology/performance/overview?days=${selectedPeriod}`),
        fetch(`${backendUrl}/api/psychology/performance/by-pattern?days=90`),
        fetch(`${backendUrl}/api/psychology/performance/signals?limit=50`),
        fetch(`${backendUrl}/api/psychology/performance/chart-data?days=${selectedPeriod}`),
        fetch(`${backendUrl}/api/psychology/performance/vix-correlation?days=90`)
      ])

      if (!overviewRes.ok) throw new Error('Failed to fetch overview')
      if (!patternsRes.ok) throw new Error('Failed to fetch patterns')
      if (!signalsRes.ok) throw new Error('Failed to fetch signals')
      if (!chartRes.ok) throw new Error('Failed to fetch chart data')
      if (!vixRes.ok) throw new Error('Failed to fetch VIX correlation')

      const overviewData = await overviewRes.json()
      const patternsData = await patternsRes.json()
      const signalsData = await signalsRes.json()
      const chartDataRes = await chartRes.json()
      const vixData = await vixRes.json()

      setOverview(overviewData.metrics)
      setPatterns(patternsData.patterns)
      setSignals(signalsData.signals)
      setChartData(chartDataRes.chart_data)
      setVixCorrelation(vixData.correlation)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      console.error('Performance data fetch error:', err)
    } finally {
      setLoading(false)
    }
  }

  const getPatternColor = (pattern: string): string => {
    const criticalPatterns = ['GAMMA_SQUEEZE_CASCADE', 'FLIP_POINT_CRITICAL', 'CAPITULATION_CASCADE']
    const bullishPatterns = ['LIBERATION_TRADE', 'EXPLOSIVE_CONTINUATION', 'DESTINATION_TRADE']
    const bearishPatterns = ['FALSE_FLOOR', 'CAPITULATION_CASCADE']

    if (criticalPatterns.includes(pattern)) return 'text-purple-400'
    if (bullishPatterns.includes(pattern)) return 'text-green-400'
    if (bearishPatterns.includes(pattern)) return 'text-red-400'
    return 'text-blue-400'
  }

  const getWinRateColor = (winRate: number): string => {
    if (winRate >= 70) return 'text-green-400'
    if (winRate >= 60) return 'text-yellow-400'
    if (winRate >= 50) return 'text-orange-400'
    return 'text-red-400'
  }

  const formatPattern = (pattern: string): string => {
    return pattern.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center">
          <Activity className="w-12 h-12 animate-spin mx-auto mb-4 text-purple-500" />
          <p className="text-gray-400">Loading performance data...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-4 text-red-500" />
          <p className="text-red-400">{error}</p>
          <button
            onClick={fetchPerformanceData}
            className="mt-4 px-6 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-black text-white p-4 md:p-8">
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
              Performance Dashboard
            </h1>
            <p className="text-gray-400 mt-2">Psychology Trap Detection Analytics</p>
          </div>

          {/* Period Selector */}
          <div className="flex gap-2">
            {[7, 30, 90].map((days) => (
              <button
                key={days}
                onClick={() => setSelectedPeriod(days)}
                className={`px-4 py-2 rounded-lg transition-colors ${
                  selectedPeriod === days
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {days}D
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto space-y-8">
        {/* Overview Metrics */}
        {overview && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Total Signals */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-gray-400 text-sm">Total Signals</h3>
                <BarChart3 className="w-5 h-5 text-blue-400" />
              </div>
              <div className="text-3xl font-bold">{overview.total_signals}</div>
              <p className="text-xs text-gray-500 mt-1">
                {overview.total_with_outcomes} with outcomes
              </p>
            </div>

            {/* Win Rate */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-gray-400 text-sm">Win Rate</h3>
                <Target className="w-5 h-5 text-green-400" />
              </div>
              <div className={`text-3xl font-bold ${getWinRateColor(overview.win_rate)}`}>
                {overview.win_rate}%
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {overview.wins}W / {overview.losses}L
              </p>
            </div>

            {/* Avg Confidence */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-gray-400 text-sm">Avg Confidence</h3>
                <Activity className="w-5 h-5 text-purple-400" />
              </div>
              <div className="text-3xl font-bold">{overview.avg_confidence}%</div>
              <p className="text-xs text-gray-500 mt-1">
                {overview.high_confidence_signals} high confidence
              </p>
            </div>

            {/* Critical Alerts */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-gray-400 text-sm">Critical Alerts</h3>
                <Zap className="w-5 h-5 text-yellow-400" />
              </div>
              <div className="text-3xl font-bold text-yellow-400">
                {overview.critical_alerts}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Gamma Squeeze & Flip Point
              </p>
            </div>
          </div>
        )}

        {/* Win/Loss Stats */}
        {overview && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="text-xl font-bold mb-4">Win/Loss Analysis</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Average Win */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <ArrowUpRight className="w-5 h-5 text-green-400" />
                  <h3 className="text-gray-400">Average Win</h3>
                </div>
                <div className="text-3xl font-bold text-green-400">
                  +{overview.avg_win_pct}%
                </div>
                <p className="text-sm text-gray-500 mt-1">
                  Based on {overview.wins} winning signals
                </p>
              </div>

              {/* Average Loss */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <ArrowDownRight className="w-5 h-5 text-red-400" />
                  <h3 className="text-gray-400">Average Loss</h3>
                </div>
                <div className="text-3xl font-bold text-red-400">
                  {overview.avg_loss_pct}%
                </div>
                <p className="text-sm text-gray-500 mt-1">
                  Based on {overview.losses} losing signals
                </p>
              </div>
            </div>

            {/* Top Patterns */}
            {overview.top_patterns.length > 0 && (
              <div className="mt-6 pt-6 border-t border-gray-800">
                <h3 className="text-gray-400 mb-3">Most Frequent Patterns</h3>
                <div className="space-y-2">
                  {overview.top_patterns.map((pattern, idx) => (
                    <div key={idx} className="flex items-center justify-between">
                      <span className={`font-mono text-sm ${getPatternColor(pattern.pattern)}`}>
                        {formatPattern(pattern.pattern)}
                      </span>
                      <span className="text-gray-500">{pattern.count} signals</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Pattern Performance Table */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-xl font-bold mb-4">Pattern Performance (90 Days)</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left py-3 px-2 text-gray-400 font-medium">Pattern</th>
                  <th className="text-center py-3 px-2 text-gray-400 font-medium">Signals</th>
                  <th className="text-center py-3 px-2 text-gray-400 font-medium">Win Rate</th>
                  <th className="text-center py-3 px-2 text-gray-400 font-medium">Avg Confidence</th>
                  <th className="text-center py-3 px-2 text-gray-400 font-medium">Avg Win</th>
                  <th className="text-center py-3 px-2 text-gray-400 font-medium">Avg Loss</th>
                  <th className="text-center py-3 px-2 text-gray-400 font-medium">Expectancy</th>
                </tr>
              </thead>
              <tbody>
                {patterns.map((pattern, idx) => (
                  <tr key={idx} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                    <td className={`py-3 px-2 font-mono ${getPatternColor(pattern.pattern_type)}`}>
                      {formatPattern(pattern.pattern_type)}
                    </td>
                    <td className="text-center py-3 px-2">{pattern.total_signals}</td>
                    <td className={`text-center py-3 px-2 font-bold ${getWinRateColor(pattern.win_rate)}`}>
                      {pattern.win_rate}%
                    </td>
                    <td className="text-center py-3 px-2">{pattern.avg_confidence}%</td>
                    <td className="text-center py-3 px-2 text-green-400">
                      +{pattern.avg_win_pct}%
                    </td>
                    <td className="text-center py-3 px-2 text-red-400">
                      {pattern.avg_loss_pct}%
                    </td>
                    <td className={`text-center py-3 px-2 font-bold ${
                      pattern.expectancy > 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {pattern.expectancy > 0 ? '+' : ''}{pattern.expectancy}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* VIX Correlation Analysis */}
        {vixCorrelation && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* By VIX Level */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <h2 className="text-xl font-bold mb-4">Performance by VIX Level</h2>
              <div className="space-y-3">
                {vixCorrelation.by_vix_level.map((level, idx) => (
                  <div key={idx} className="bg-gray-800/50 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold">{level.vix_level}</span>
                      <span className={`font-bold ${getWinRateColor(level.win_rate)}`}>
                        {level.win_rate}%
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 flex items-center justify-between">
                      <span>{level.total_signals} signals</span>
                      <span className={level.avg_price_change > 0 ? 'text-green-400' : 'text-red-400'}>
                        Avg: {level.avg_price_change > 0 ? '+' : ''}{level.avg_price_change}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* By VIX Spike Status */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <h2 className="text-xl font-bold mb-4">VIX Spike Impact</h2>
              <div className="space-y-3">
                {vixCorrelation.by_spike_status.map((status, idx) => (
                  <div key={idx} className="bg-gray-800/50 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold">
                        {status.vix_spike ? '⚡ VIX Spike Detected' : '📊 Normal VIX'}
                      </span>
                      <span className={`font-bold ${getWinRateColor(status.win_rate)}`}>
                        {status.win_rate}%
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 flex items-center justify-between">
                      <span>{status.total_signals} signals</span>
                      <span className={status.avg_price_change > 0 ? 'text-green-400' : 'text-red-400'}>
                        Avg: {status.avg_price_change > 0 ? '+' : ''}{status.avg_price_change}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-4 p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg">
                <p className="text-xs text-purple-300">
                  💡 VIX spikes often indicate dealer amplification is active, which can improve pattern reliability.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Recent Signals */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-xl font-bold mb-4">Recent Signals (Last 50)</h2>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {signals.map((signal, idx) => (
              <div key={idx} className="bg-gray-800/50 rounded-lg p-4 hover:bg-gray-800 transition-colors">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`font-mono text-sm font-bold ${getPatternColor(signal.pattern)}`}>
                        {formatPattern(signal.pattern)}
                      </span>
                      {signal.correct !== null && (
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          signal.correct === 1 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                        }`}>
                          {signal.correct === 1 ? '✓ WIN' : '✗ LOSS'}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400">{signal.description}</p>
                    {signal.psychology_trap && (
                      <p className="text-xs text-yellow-400 mt-1">🧠 {signal.psychology_trap}</p>
                    )}
                  </div>
                  <div className="text-right ml-4">
                    <div className="text-sm font-bold">${signal.price.toFixed(2)}</div>
                    <div className="text-xs text-gray-500">
                      {new Date(signal.timestamp).toLocaleDateString()}
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs mt-3 pt-3 border-t border-gray-700">
                  <div className="flex items-center gap-3">
                    <span className="text-gray-500">Confidence: {signal.confidence}%</span>
                    {signal.vix && (
                      <span className="text-gray-500">VIX: {signal.vix.toFixed(1)}</span>
                    )}
                  </div>
                  {signal.outcome_1d !== null && (
                    <span className={`font-bold ${signal.outcome_1d > 0 ? 'text-green-400' : 'text-red-400'}`}>
                      1D: {signal.outcome_1d > 0 ? '+' : ''}{signal.outcome_1d.toFixed(2)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Simple Win Rate Timeline */}
        {chartData && chartData.win_rate_timeline.length > 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="text-xl font-bold mb-4">Cumulative Win Rate Trend</h2>
            <div className="space-y-2">
              {chartData.win_rate_timeline.slice(-10).map((point, idx) => (
                <div key={idx} className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">{point.date}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-gray-400">{point.total_signals} signals</span>
                    <span className={`font-bold ${getWinRateColor(point.win_rate)}`}>
                      {point.win_rate}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
