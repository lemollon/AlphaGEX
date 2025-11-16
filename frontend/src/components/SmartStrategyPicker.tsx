'use client'

import { useState, useEffect } from 'react'
import { Target, TrendingUp, AlertCircle, CheckCircle, PlayCircle, ExternalLink } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface StrategyRecommendation {
  strategy_name: string
  win_rate: number
  expectancy_pct: number
  total_trades: number
  confidence_score: number
  conditions_met: number
  conditions_total: number
  market_match: string
  setup_link?: string
}

interface MarketConditions {
  current_pattern: string
  vix: number
  net_gex: number
  rsi_score: number
  spy_price: number
  confidence: number
}

export default function SmartStrategyPicker() {
  const [recommendations, setRecommendations] = useState<StrategyRecommendation[]>([])
  const [marketConditions, setMarketConditions] = useState<MarketConditions | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchRecommendations()
  }, [])

  const fetchRecommendations = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await fetch(`${API_URL}/api/backtests/smart-recommendations`)

      if (response.ok) {
        const data = await response.json()
        setRecommendations(data.recommendations || [])
        setMarketConditions(data.market_conditions || null)
      } else {
        setError('Unable to fetch recommendations - run Psychology Analysis first')
      }
    } catch (err) {
      console.error('Failed to fetch smart recommendations:', err)
      setError('Failed to connect to API')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="bg-gradient-to-br from-purple-900/20 to-blue-900/20 border-2 border-purple-500/50 rounded-xl p-6">
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
          <div className="text-lg font-semibold">Analyzing current market conditions...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-gradient-to-br from-yellow-900/20 to-orange-900/20 border-2 border-yellow-500/50 rounded-xl p-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-6 h-6 text-yellow-400 flex-shrink-0 mt-1" />
          <div>
            <h3 className="text-lg font-bold text-yellow-400 mb-2">Market Data Not Available</h3>
            <p className="text-gray-300 mb-3">{error}</p>
            <a
              href="/psychology"
              className="inline-flex items-center gap-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 rounded-lg font-semibold text-sm"
            >
              <PlayCircle className="w-4 h-4" />
              Run Psychology Analysis
            </a>
          </div>
        </div>
      </div>
    )
  }

  if (!marketConditions || recommendations.length === 0) {
    return (
      <div className="bg-gradient-to-br from-gray-900/50 to-gray-800/50 border-2 border-gray-700 rounded-xl p-6">
        <div className="text-center">
          <Target className="w-12 h-12 mx-auto mb-3 text-gray-500" />
          <h3 className="text-lg font-bold text-gray-400 mb-2">No Strategies Match Current Conditions</h3>
          <p className="text-gray-500 text-sm">Market conditions may be too uncertain or no backtested strategies apply.</p>
        </div>
      </div>
    )
  }

  const getConfidenceColor = (score: number) => {
    if (score >= 80) return 'text-green-400'
    if (score >= 60) return 'text-yellow-400'
    return 'text-orange-400'
  }

  const getConfidenceBadge = (score: number) => {
    if (score >= 80) return { label: 'HIGH', color: 'bg-green-500/20 text-green-400 border-green-500' }
    if (score >= 60) return { label: 'MEDIUM', color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500' }
    return { label: 'LOW', color: 'bg-orange-500/20 text-orange-400 border-orange-500' }
  }

  return (
    <div className="bg-gradient-to-br from-purple-900/30 via-blue-900/20 to-indigo-900/30 border-2 border-purple-500/50 rounded-xl overflow-hidden shadow-2xl">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-600/20 to-blue-600/20 border-b border-purple-500/30 p-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-3 mb-2">
              <Target className="w-7 h-7 text-purple-400" />
              Smart Strategy Picker
            </h2>
            <p className="text-gray-300">Top strategies for current market conditions</p>
          </div>
          <button
            onClick={fetchRecommendations}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg font-semibold text-sm"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Current Market Status */}
      <div className="bg-gray-950/50 border-b border-purple-500/30 p-6">
        <h3 className="text-sm font-bold text-gray-400 uppercase tracking-wide mb-3">Current Market Status</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div>
            <div className="text-xs text-gray-500 mb-1">Pattern</div>
            <div className="font-bold text-purple-400">{marketConditions.current_pattern.replace(/_/g, ' ')}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">SPY Price</div>
            <div className="font-bold">${marketConditions.spy_price.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">VIX</div>
            <div className="font-bold">{marketConditions.vix.toFixed(1)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">Net GEX</div>
            <div className={`font-bold ${marketConditions.net_gex < 0 ? 'text-red-400' : 'text-green-400'}`}>
              ${(marketConditions.net_gex / 1e9).toFixed(1)}B
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">RSI Score</div>
            <div className="font-bold">{marketConditions.rsi_score}/100</div>
          </div>
        </div>
      </div>

      {/* Top 3 Recommendations */}
      <div className="p-6">
        <h3 className="text-lg font-bold text-white mb-4">🎯 Top 3 Strategies for This Pattern</h3>
        <div className="space-y-4">
          {recommendations.slice(0, 3).map((rec, idx) => {
            const confidenceBadge = getConfidenceBadge(rec.confidence_score)
            return (
              <div
                key={idx}
                className="bg-gray-900/50 border border-gray-700 hover:border-purple-500/50 rounded-lg p-5 transition-all"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-xl ${
                      idx === 0 ? 'bg-yellow-500/20 text-yellow-400' :
                      idx === 1 ? 'bg-gray-500/20 text-gray-400' :
                      'bg-orange-500/20 text-orange-400'
                    }`}>
                      {idx + 1}
                    </div>
                    <div>
                      <h4 className="font-bold text-lg text-white">{rec.strategy_name.replace(/_/g, ' ')}</h4>
                      <p className="text-sm text-gray-400">{rec.market_match}</p>
                    </div>
                  </div>
                  <div className={`px-3 py-1 rounded-full text-xs font-bold border ${confidenceBadge.color}`}>
                    {confidenceBadge.label} CONFIDENCE
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Win Rate</div>
                    <div className="text-lg font-bold text-green-400">{rec.win_rate.toFixed(1)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Expectancy</div>
                    <div className="text-lg font-bold text-green-400">{rec.expectancy_pct.toFixed(2)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Sample Size</div>
                    <div className="text-lg font-bold">{rec.total_trades} trades</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">Conditions Met</div>
                    <div className="text-lg font-bold">
                      {rec.conditions_met}/{rec.conditions_total}
                      {rec.conditions_met === rec.conditions_total && (
                        <CheckCircle className="inline w-4 h-4 ml-1 text-green-400" />
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <a
                    href={rec.setup_link || `/psychology?pattern=${rec.strategy_name}`}
                    className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg font-semibold text-sm text-center flex items-center justify-center gap-2"
                  >
                    <ExternalLink className="w-4 h-4" />
                    View Exact Setup
                  </a>
                  <button
                    onClick={() => window.location.href = '/autonomous'}
                    className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg font-semibold text-sm text-center"
                  >
                    Open Position
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        {recommendations.length > 3 && (
          <div className="mt-4 text-center text-sm text-gray-400">
            +{recommendations.length - 3} more strategies available below
          </div>
        )}
      </div>
    </div>
  )
}
