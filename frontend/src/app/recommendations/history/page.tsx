'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { TrendingUp, Target, Award, AlertCircle, CheckCircle, XCircle, DollarSign } from 'lucide-react'

interface Recommendation {
  recommendation_date: string
  strategy_type: string
  entry_strike: number
  exit_strike: number
  direction: string
  confidence_pct: number
  recommended_entry_price: number
  actual_entry_price: number | null
  actual_exit_price: number | null
  outcome: string | null
  pnl: number | null
  outcome_date: string | null
  reasoning: string
}

interface PerformanceBucket {
  confidence_range: string
  total_recommendations: number
  executed_trades: number
  winning_trades: number
  losing_trades: number
  win_rate_pct: number
  avg_pnl: number
  total_pnl: number
}

export default function RecommendationsHistory() {
  const [loading, setLoading] = useState(true)
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [performance, setPerformance] = useState<PerformanceBucket[]>([])
  const [days, setDays] = useState(30)
  const [filterOutcome, setFilterOutcome] = useState<string>('all')

  useEffect(() => {
    fetchData()
  }, [days])

  const fetchData = async () => {
    try {
      setLoading(true)

      const [historyRes, perfRes] = await Promise.all([
        apiClient.getRecommendationsHistory(days),
        apiClient.getRecommendationPerformance()
      ])

      if (historyRes.data.success) {
        setRecommendations(historyRes.data.recommendations)
      }

      if (perfRes.data.success) {
        setPerformance(perfRes.data.performance_buckets)
      }
    } catch (error) {
      console.error('Error fetching recommendations:', error)
    } finally {
      setLoading(false)
    }
  }

  const filteredRecommendations = recommendations.filter(rec => {
    if (filterOutcome === 'all') return true
    if (filterOutcome === 'executed') return rec.actual_entry_price !== null
    if (filterOutcome === 'pending') return rec.actual_entry_price === null
    if (filterOutcome === 'winners') return rec.outcome === 'WIN'
    if (filterOutcome === 'losers') return rec.outcome === 'LOSS'
    return true
  })

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 90) return 'text-green-400'
    if (confidence >= 80) return 'text-blue-400'
    if (confidence >= 70) return 'text-yellow-400'
    return 'text-gray-400'
  }

  const getOutcomeBadge = (rec: Recommendation) => {
    if (!rec.outcome) {
      return (
        <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-gray-600/20 text-gray-400 text-xs font-medium">
          <AlertCircle className="h-3 w-3" />
          Pending
        </span>
      )
    }

    if (rec.outcome === 'WIN') {
      return (
        <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-green-500/20 text-green-400 text-xs font-medium">
          <CheckCircle className="h-3 w-3" />
          Winner
        </span>
      )
    }

    return (
      <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-red-500/20 text-red-400 text-xs font-medium">
        <XCircle className="h-3 w-3" />
        Loser
      </span>
    )
  }

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Recommendations History</h1>
            <p className="text-gray-400">
              Track AI-generated trade recommendations and their outcomes
            </p>
          </div>

          {/* Filters */}
          <div className="flex gap-4 mb-6">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="px-4 py-2 bg-gray-800 border border-gray-700 text-white rounded-lg"
            >
              <option value={7}>Last 7 Days</option>
              <option value={30}>Last 30 Days</option>
              <option value={60}>Last 60 Days</option>
              <option value={90}>Last 90 Days</option>
            </select>

            <select
              value={filterOutcome}
              onChange={(e) => setFilterOutcome(e.target.value)}
              className="px-4 py-2 bg-gray-800 border border-gray-700 text-white rounded-lg"
            >
              <option value="all">All Recommendations</option>
              <option value="executed">Executed Only</option>
              <option value="pending">Pending Only</option>
              <option value="winners">Winners Only</option>
              <option value="losers">Losers Only</option>
            </select>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
          ) : (
            <>
              {/* Performance by Confidence */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                {performance.map((bucket, idx) => (
                  <div key={idx} className="bg-gray-800 rounded-xl p-6 shadow-lg">
                    <div className="text-sm text-gray-400 mb-2">{bucket.confidence_range}</div>
                    <div className="text-2xl font-bold text-white mb-4">
                      {bucket.win_rate_pct.toFixed(1)}%
                    </div>
                    <div className="space-y-1 text-xs text-gray-400">
                      <div className="flex justify-between">
                        <span>Total:</span>
                        <span className="text-white">{bucket.total_recommendations}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Executed:</span>
                        <span className="text-white">{bucket.executed_trades}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Winners:</span>
                        <span className="text-green-400">{bucket.winning_trades}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Losers:</span>
                        <span className="text-red-400">{bucket.losing_trades}</span>
                      </div>
                      <div className="flex justify-between border-t border-gray-700 pt-1 mt-2">
                        <span>Avg P&L:</span>
                        <span className={bucket.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                          ${bucket.avg_pnl.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Recommendations List */}
              <div className="bg-gray-800 rounded-xl shadow-lg">
                <div className="p-6 border-b border-gray-700">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Target className="h-5 w-5 text-blue-500" />
                      <h2 className="text-xl font-semibold text-white">Trade Recommendations</h2>
                    </div>
                    <span className="text-sm text-gray-400">{filteredRecommendations.length} total</span>
                  </div>
                </div>

                <div className="p-6">
                  {filteredRecommendations.length === 0 ? (
                    <div className="text-center text-gray-400 py-20">
                      <Target className="h-16 w-16 mx-auto mb-4 text-gray-600" />
                      <p>No recommendations found</p>
                      <p className="text-sm mt-1">AI will generate trade recommendations as opportunities arise</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 gap-4">
                      {filteredRecommendations.map((rec, idx) => (
                        <div
                          key={idx}
                          className="bg-gray-750 rounded-lg p-6 border border-gray-700 hover:border-gray-600 transition"
                        >
                          <div className="flex items-start justify-between mb-4">
                            <div className="flex-1">
                              <div className="flex items-center gap-3 mb-2">
                                <h3 className="text-lg font-semibold text-white">
                                  {rec.strategy_type}
                                </h3>
                                <span className={`text-sm font-medium ${rec.direction === 'BULLISH' ? 'text-green-400' : 'text-red-400'}`}>
                                  {rec.direction}
                                </span>
                                <span className={`text-sm font-bold ${getConfidenceColor(rec.confidence_pct)}`}>
                                  {rec.confidence_pct}% confidence
                                </span>
                              </div>
                              <div className="text-sm text-gray-400">
                                {new Date(rec.recommendation_date).toLocaleString()}
                              </div>
                            </div>
                            {getOutcomeBadge(rec)}
                          </div>

                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                            <div>
                              <div className="text-xs text-gray-500 mb-1">Entry Strike</div>
                              <div className="text-white font-medium">${rec.entry_strike}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500 mb-1">Exit Strike</div>
                              <div className="text-white font-medium">${rec.exit_strike}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500 mb-1">Recommended Price</div>
                              <div className="text-white font-medium">${rec.recommended_entry_price.toFixed(2)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500 mb-1">P&L</div>
                              {rec.pnl !== null ? (
                                <div className={`font-bold flex items-center gap-1 ${rec.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  <DollarSign className="h-4 w-4" />
                                  {rec.pnl >= 0 ? '+' : ''}{rec.pnl.toFixed(2)}
                                </div>
                              ) : (
                                <div className="text-gray-500">—</div>
                              )}
                            </div>
                          </div>

                          {rec.actual_entry_price && (
                            <div className="grid grid-cols-3 gap-4 mb-4 p-3 bg-gray-800 rounded border border-gray-700">
                              <div>
                                <div className="text-xs text-gray-500 mb-1">Actual Entry</div>
                                <div className="text-white font-medium">${rec.actual_entry_price.toFixed(2)}</div>
                              </div>
                              <div>
                                <div className="text-xs text-gray-500 mb-1">Actual Exit</div>
                                <div className="text-white font-medium">
                                  {rec.actual_exit_price ? `$${rec.actual_exit_price.toFixed(2)}` : '—'}
                                </div>
                              </div>
                              <div>
                                <div className="text-xs text-gray-500 mb-1">Outcome Date</div>
                                <div className="text-gray-300 text-sm">
                                  {rec.outcome_date ? new Date(rec.outcome_date).toLocaleDateString() : '—'}
                                </div>
                              </div>
                            </div>
                          )}

                          <div className="bg-gray-800 rounded p-3 border border-gray-700">
                            <div className="text-xs text-gray-500 mb-1">AI Reasoning</div>
                            <p className="text-sm text-gray-300">{rec.reasoning}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
