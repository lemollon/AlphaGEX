'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { Activity, TrendingUp, Target, BarChart3, AlertCircle, CheckCircle, Settings } from 'lucide-react'
import CoolEmptyState from '@/components/CoolEmptyState'

interface ProbabilityOutcome {
  prediction_date: string
  pattern_type: string
  predicted_probability: number
  actual_outcome: boolean
  correct_prediction: boolean
  outcome_timestamp: string
}

interface ProbabilityWeight {
  weight_name: string
  weight_value: number
  description: string
  last_updated: string
  calibration_count: number
}

interface CalibrationEvent {
  calibration_date: string
  weight_name: string
  old_value: number
  new_value: number
  reason: string
  performance_delta: number
}

export default function ProbabilityDashboard() {
  const [loading, setLoading] = useState(true)
  const [outcomes, setOutcomes] = useState<ProbabilityOutcome[]>([])
  const [weights, setWeights] = useState<ProbabilityWeight[]>([])
  const [calibrationHistory, setCalibrationHistory] = useState<CalibrationEvent[]>([])
  const [stats, setStats] = useState<any>(null)
  const [days, setDays] = useState(30)

  useEffect(() => {
    fetchData()
  }, [days])

  const fetchData = async () => {
    try {
      setLoading(true)

      const [outcomesRes, weightsRes, calibrationRes] = await Promise.all([
        apiClient.getProbabilityOutcomes(days),
        apiClient.getProbabilityWeights(),
        apiClient.getCalibrationHistory(90)
      ])

      if (outcomesRes.data.success) {
        setOutcomes(outcomesRes.data.outcomes)
        setStats(outcomesRes.data.stats)
      }

      if (weightsRes.data.success) {
        setWeights(weightsRes.data.weights)
      }

      if (calibrationRes.data.success) {
        setCalibrationHistory(calibrationRes.data.calibration_history)
      }
    } catch (error) {
      logger.error('Error fetching probability data:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">PYTHIA</h1>
            <p className="text-gray-400">
              Predictive Yield Through Holistic Intelligence Analysis - Track prediction accuracy, probability weights, and model calibration
            </p>
          </div>

          {/* Time Filter */}
          <div className="mb-6">
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
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-blue-100 text-sm mb-1">Overall Accuracy</p>
                      <h3 className="text-3xl font-bold text-white">
                        {stats ? `${stats.accuracy_pct.toFixed(1)}%` : 'N/A'}
                      </h3>
                    </div>
                    <Target className="h-12 w-12 text-blue-200" />
                  </div>
                </div>

                <div className="bg-gradient-to-br from-green-500 to-green-600 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-green-100 text-sm mb-1">Total Predictions</p>
                      <h3 className="text-3xl font-bold text-white">
                        {stats ? stats.total_predictions : 0}
                      </h3>
                    </div>
                    <Activity className="h-12 w-12 text-green-200" />
                  </div>
                </div>

                <div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-purple-100 text-sm mb-1">Correct Predictions</p>
                      <h3 className="text-3xl font-bold text-white">
                        {stats ? stats.correct : 0}
                      </h3>
                    </div>
                    <CheckCircle className="h-12 w-12 text-purple-200" />
                  </div>
                </div>
              </div>

              {/* Recent Outcomes */}
              <div className="bg-gray-800 rounded-xl shadow-lg mb-8">
                <div className="p-6 border-b border-gray-700">
                  <div className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-blue-500" />
                    <h2 className="text-xl font-semibold text-white">Recent Predictions</h2>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  {outcomes.length === 0 ? (
                    <div className="p-8">
                      <CoolEmptyState
                        icon={Target}
                        title="No Prediction Data Yet"
                        description="Historical data is available via Polygon. Run the backfill script to populate your database with historical predictions and pattern analysis."
                        showProgress={false}
                        variant="gradient"
                      />
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead className="bg-gray-750">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Date</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Pattern</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Predicted</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Actual</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Result</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {outcomes.slice(0, 10).map((outcome, idx) => (
                          <tr key={idx} className="hover:bg-gray-750">
                            <td className="px-6 py-4 text-sm text-gray-300">
                              {new Date(outcome.prediction_date).toLocaleDateString()}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300">{outcome.pattern_type}</td>
                            <td className="px-6 py-4 text-sm text-gray-300">
                              {(outcome.predicted_probability * 100).toFixed(1)}%
                            </td>
                            <td className="px-6 py-4 text-sm">
                              {outcome.actual_outcome ? (
                                <span className="text-green-400">Success</span>
                              ) : (
                                <span className="text-red-400">Failed</span>
                              )}
                            </td>
                            <td className="px-6 py-4 text-sm">
                              {outcome.correct_prediction ? (
                                <span className="inline-flex items-center gap-1 px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs">
                                  <CheckCircle className="h-3 w-3" />
                                  Correct
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs">
                                  <AlertCircle className="h-3 w-3" />
                                  Incorrect
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Probability Weights */}
              <div className="bg-gray-800 rounded-xl shadow-lg mb-8">
                <div className="p-6 border-b border-gray-700">
                  <div className="flex items-center gap-2">
                    <Settings className="h-5 w-5 text-purple-500" />
                    <h2 className="text-xl font-semibold text-white">Probability Weights</h2>
                  </div>
                </div>

                <div className="p-6">
                  {weights.length === 0 ? (
                    <div className="text-center text-gray-400 py-8">
                      <AlertCircle className="h-12 w-12 mx-auto mb-3 text-gray-600" />
                      <p>No probability weights configured yet</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {weights.map((weight, idx) => (
                        <div key={idx} className="bg-gray-750 rounded-lg p-4 border border-gray-700">
                          <div className="flex items-center justify-between mb-2">
                            <h3 className="text-white font-medium">{weight.weight_name}</h3>
                            <span className="text-blue-400 font-semibold">{weight.weight_value.toFixed(2)}</span>
                          </div>
                          <p className="text-sm text-gray-400 mb-2">{weight.description}</p>
                          <div className="flex items-center justify-between text-xs text-gray-500">
                            <span>Updated: {new Date(weight.last_updated).toLocaleDateString()}</span>
                            <span>Calibrated {weight.calibration_count}x</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Calibration History */}
              <div className="bg-gray-800 rounded-xl shadow-lg">
                <div className="p-6 border-b border-gray-700">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-green-500" />
                    <h2 className="text-xl font-semibold text-white">Model Calibration History</h2>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  {calibrationHistory.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">
                      <AlertCircle className="h-12 w-12 mx-auto mb-3 text-gray-600" />
                      <p>No calibration events yet</p>
                      <p className="text-sm mt-1">Model will self-adjust weights based on performance</p>
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead className="bg-gray-750">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Date</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Weight</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Change</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Performance Δ</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Reason</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {calibrationHistory.slice(0, 10).map((event, idx) => (
                          <tr key={idx} className="hover:bg-gray-750">
                            <td className="px-6 py-4 text-sm text-gray-300">
                              {new Date(event.calibration_date).toLocaleDateString()}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300">{event.weight_name}</td>
                            <td className="px-6 py-4 text-sm">
                              <span className="text-gray-400">{event.old_value.toFixed(2)}</span>
                              {' → '}
                              <span className="text-white font-medium">{event.new_value.toFixed(2)}</span>
                            </td>
                            <td className="px-6 py-4 text-sm">
                              {event.performance_delta > 0 ? (
                                <span className="text-green-400">+{event.performance_delta.toFixed(2)}%</span>
                              ) : (
                                <span className="text-red-400">{event.performance_delta.toFixed(2)}%</span>
                              )}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-400">{event.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
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
