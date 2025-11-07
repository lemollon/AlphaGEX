'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  TrendingUp,
  TrendingDown,
  BarChart3,
  Clock,
  Target,
  DollarSign,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Award,
  Activity,
  Calendar,
  Zap
} from 'lucide-react'

interface Strategy {
  name: string
  type: string
  action: string
  confidence: number
  win_rate: string
  base_win_rate: string
  your_win_rate: string
  expected_value: number
  expected_move: string
  risk_reward: number
  conditions_met: string[]
  optimal_dte: number
  entry_timing: {
    immediate: boolean
    wait_for: string | null
    best_window: string | null
    avoid_window: string | null
    reasoning: string
  }
  strike: number | string
  premium: number
  best_days: string[]
  day_match: boolean
  reasoning: string
}

interface MarketConditions {
  spot: number
  net_gex: number
  flip_point: number
  call_wall: number
  put_wall: number
  vix: number
  dist_to_flip: string
  wall_spread: string
  day: string
  time: string
}

interface ComparisonData {
  timestamp: string
  market_conditions: MarketConditions
  strategies: Strategy[]
  recommendation: string
  best_strategy: Strategy | null
  total_strategies_available: number
}

export default function StrategyComparisonPage() {
  const [loading, setLoading] = useState(false)
  const [comparisonData, setComparisonData] = useState<ComparisonData | null>(null)
  const [symbol, setSymbol] = useState('SPY')
  const [error, setError] = useState<string | null>(null)

  const popularSymbols = ['SPY', 'QQQ', 'IWM', 'AAPL', 'TSLA', 'NVDA', 'META', 'AMZN']

  useEffect(() => {
    fetchComparison()
  }, [])

  const fetchComparison = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.compareStrategies(symbol)
      if (response.data.success) {
        setComparisonData(response.data.data)
      } else {
        setError('Failed to fetch strategy comparison')
      }
    } catch (error: any) {
      console.error('Error fetching comparison:', error)
      setError(error.response?.data?.detail || 'Failed to fetch data. Make sure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 80) return 'text-green-400'
    if (confidence >= 70) return 'text-yellow-400'
    return 'text-orange-400'
  }

  const getConfidenceBg = (confidence: number) => {
    if (confidence >= 80) return 'bg-green-500/20 border-green-500/30'
    if (confidence >= 70) return 'bg-yellow-500/20 border-yellow-500/30'
    return 'bg-orange-500/20 border-orange-500/30'
  }

  const getStrategyIcon = (type: string) => {
    if (type.includes('Bullish')) return <TrendingUp className="w-5 h-5" />
    if (type.includes('Bearish')) return <TrendingDown className="w-5 h-5" />
    if (type.includes('Range')) return <BarChart3 className="w-5 h-5" />
    return <Activity className="w-5 h-5" />
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      <Navigation />

      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-4xl font-bold text-white mb-2">Multi-Strategy Optimizer</h1>
              <p className="text-gray-400">Compare all strategies side-by-side and find the best setup for current conditions</p>
            </div>

            <div className="flex items-center gap-4">
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="px-4 py-2 bg-gray-800 text-white rounded-lg border border-gray-700 focus:border-blue-500 focus:outline-none"
              >
                {popularSymbols.map((sym) => (
                  <option key={sym} value={sym}>{sym}</option>
                ))}
              </select>

              <button
                onClick={fetchComparison}
                disabled={loading}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                {loading ? 'Analyzing...' : 'Refresh'}
              </button>
            </div>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5" />
            <div>
              <p className="text-red-400 font-medium">Error</p>
              <p className="text-red-300/80 text-sm">{error}</p>
            </div>
          </div>
        )}

        {loading && !comparisonData ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <RefreshCw className="w-12 h-12 text-blue-400 animate-spin mx-auto mb-4" />
              <p className="text-gray-400">Analyzing market conditions and comparing strategies...</p>
            </div>
          </div>
        ) : comparisonData ? (
          <>
            {/* Market Conditions */}
            <div className="mb-8 p-6 bg-gray-800/50 rounded-xl border border-gray-700">
              <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-400" />
                Current Market Conditions
              </h2>

              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                <div>
                  <p className="text-gray-400 text-sm">Spot Price</p>
                  <p className="text-white font-bold">${comparisonData.market_conditions.spot.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm">Net GEX</p>
                  <p className={`font-bold ${comparisonData.market_conditions.net_gex < 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {(comparisonData.market_conditions.net_gex / 1e9).toFixed(2)}B
                  </p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm">Flip Point</p>
                  <p className="text-white font-bold">${comparisonData.market_conditions.flip_point.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm">Call Wall</p>
                  <p className="text-green-400 font-bold">${comparisonData.market_conditions.call_wall.toFixed(0)}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm">Put Wall</p>
                  <p className="text-red-400 font-bold">${comparisonData.market_conditions.put_wall.toFixed(0)}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm">VIX</p>
                  <p className="text-purple-400 font-bold">{comparisonData.market_conditions.vix.toFixed(1)}</p>
                </div>
              </div>

              <div className="mt-4 flex items-center gap-6 text-sm">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-400">{comparisonData.market_conditions.day}, {comparisonData.market_conditions.time}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-400">Dist to Flip: {comparisonData.market_conditions.dist_to_flip}</span>
                </div>
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-400">Wall Spread: {comparisonData.market_conditions.wall_spread}</span>
                </div>
              </div>
            </div>

            {/* Best Strategy Recommendation */}
            {comparisonData.best_strategy && (
              <div className={`mb-8 p-6 rounded-xl border-2 ${getConfidenceBg(comparisonData.best_strategy.confidence)}`}>
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <Award className="w-8 h-8 text-yellow-400" />
                    <div>
                      <h2 className="text-2xl font-bold text-white">{comparisonData.recommendation}</h2>
                      <p className="text-gray-300 mt-1">{comparisonData.best_strategy.action}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-400">Expected Value</p>
                    <p className="text-3xl font-bold text-green-400">${comparisonData.best_strategy.expected_value.toFixed(2)}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                  <div>
                    <p className="text-gray-400 text-sm">Confidence</p>
                    <p className={`text-2xl font-bold ${getConfidenceColor(comparisonData.best_strategy.confidence)}`}>
                      {comparisonData.best_strategy.confidence}%
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Win Rate</p>
                    <p className="text-white font-bold">{comparisonData.best_strategy.win_rate}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Risk:Reward</p>
                    <p className="text-white font-bold">{comparisonData.best_strategy.risk_reward}:1</p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Expected Move</p>
                    <p className="text-white font-bold">{comparisonData.best_strategy.expected_move}</p>
                  </div>
                </div>

                {/* Entry Timing */}
                <div className="mt-4 p-4 bg-black/20 rounded-lg">
                  <h3 className="text-white font-bold mb-2 flex items-center gap-2">
                    <Zap className="w-4 h-4 text-yellow-400" />
                    Entry Timing Optimization
                  </h3>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-gray-400 mb-1">Status</p>
                      {comparisonData.best_strategy.entry_timing.immediate ? (
                        <div className="flex items-center gap-2 text-green-400">
                          <CheckCircle className="w-4 h-4" />
                          <span className="font-medium">Enter Now</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-yellow-400">
                          <Clock className="w-4 h-4" />
                          <span className="font-medium">Wait for {comparisonData.best_strategy.entry_timing.wait_for}</span>
                        </div>
                      )}
                    </div>
                    <div>
                      <p className="text-sm text-gray-400 mb-1">Best Window</p>
                      <p className="text-white font-medium">{comparisonData.best_strategy.entry_timing.best_window || 'Anytime'}</p>
                    </div>
                  </div>
                  <p className="text-gray-300 text-sm mt-2">{comparisonData.best_strategy.entry_timing.reasoning}</p>
                </div>
              </div>
            )}

            {/* All Strategies Comparison */}
            <div>
              <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
                <BarChart3 className="w-6 h-6 text-blue-400" />
                All Strategies Side-by-Side ({comparisonData.total_strategies_available} available)
              </h2>

              {comparisonData.strategies.length === 0 ? (
                <div className="p-8 bg-gray-800/50 rounded-xl border border-gray-700 text-center">
                  <AlertTriangle className="w-12 h-12 text-yellow-400 mx-auto mb-4" />
                  <p className="text-white font-bold mb-2">No High-Confidence Setups</p>
                  <p className="text-gray-400">Market conditions don't favor any strategy right now. Wait for better conditions.</p>
                </div>
              ) : (
                <div className="grid gap-6">
                  {comparisonData.strategies.map((strategy, index) => (
                    <div
                      key={index}
                      className={`p-6 rounded-xl border transition-all ${
                        index === 0
                          ? `${getConfidenceBg(strategy.confidence)} border-2`
                          : 'bg-gray-800/30 border-gray-700'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className={`p-3 rounded-lg ${
                            strategy.type.includes('Bullish') ? 'bg-green-500/20' :
                            strategy.type.includes('Bearish') ? 'bg-red-500/20' :
                            'bg-blue-500/20'
                          }`}>
                            {getStrategyIcon(strategy.type)}
                          </div>
                          <div>
                            <h3 className="text-xl font-bold text-white">{strategy.name.replace(/_/g, ' ')}</h3>
                            <p className="text-gray-400">{strategy.type}</p>
                          </div>
                          {index === 0 && (
                            <span className="px-3 py-1 bg-yellow-500/20 text-yellow-400 text-sm font-bold rounded-full">
                              BEST
                            </span>
                          )}
                        </div>

                        <div className="text-right">
                          <p className="text-sm text-gray-400">Expected Value</p>
                          <p className="text-2xl font-bold text-green-400">${strategy.expected_value.toFixed(2)}</p>
                        </div>
                      </div>

                      {/* Strategy Action */}
                      <div className="mb-4 p-3 bg-blue-500/10 rounded-lg border border-blue-500/30">
                        <p className="text-blue-300 font-bold text-lg">{strategy.action}</p>
                      </div>

                      {/* Key Metrics */}
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
                        <div>
                          <p className="text-gray-400 text-sm">Confidence</p>
                          <p className={`text-xl font-bold ${getConfidenceColor(strategy.confidence)}`}>
                            {strategy.confidence}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Win Rate</p>
                          <p className="text-white font-bold">{strategy.win_rate}</p>
                          <p className="text-gray-500 text-xs">Base: {strategy.base_win_rate}</p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Your Win Rate</p>
                          <p className="text-purple-400 font-bold">{strategy.your_win_rate}</p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Risk:Reward</p>
                          <p className="text-white font-bold">{strategy.risk_reward}:1</p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Optimal DTE</p>
                          <p className="text-white font-bold">{strategy.optimal_dte} days</p>
                        </div>
                      </div>

                      {/* Conditions Met */}
                      <div className="mb-4">
                        <p className="text-gray-400 text-sm mb-2">Conditions</p>
                        <div className="flex flex-wrap gap-2">
                          {strategy.conditions_met.map((condition, idx) => (
                            <span
                              key={idx}
                              className={`px-2 py-1 rounded text-xs ${
                                condition.startsWith('✓')
                                  ? 'bg-green-500/20 text-green-400'
                                  : 'bg-yellow-500/20 text-yellow-400'
                              }`}
                            >
                              {condition}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Best Days */}
                      <div className="flex items-center gap-4 text-sm">
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-gray-400" />
                          <span className="text-gray-400">Best Days: {strategy.best_days.join(', ')}</span>
                          {strategy.day_match && (
                            <CheckCircle className="w-4 h-4 text-green-400" />
                          )}
                        </div>
                      </div>

                      {/* Reasoning */}
                      <div className="mt-4 p-3 bg-black/20 rounded-lg">
                        <p className="text-gray-300 text-sm">{strategy.reasoning}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Timestamp */}
            <div className="mt-6 text-center text-gray-500 text-sm">
              Last updated: {comparisonData.timestamp}
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
