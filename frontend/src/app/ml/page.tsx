'use client'

import { useState } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  useMLStatus,
  useMLDataQuality,
  useMLFeatureImportance,
  useMLStrategyExplanation,
  useMLDecisionLogs
} from '@/lib/hooks/useMarketData'
import { Brain, AlertTriangle, CheckCircle, XCircle, RefreshCw, Database, Zap, Target, BarChart3 } from 'lucide-react'

export default function MLSystemPage() {
  const [training, setTraining] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'features' | 'logs' | 'strategy'>('overview')

  // SWR hooks with automatic caching and deduplication
  const { data: statusData, isLoading: statusLoading, mutate: mutateStatus } = useMLStatus()
  const { data: qualityData, mutate: mutateQuality } = useMLDataQuality()

  // Only fetch tab data when the tab is active (conditional fetching)
  const { data: featuresData, isLoading: featuresLoading } = useMLFeatureImportance(
    activeTab === 'features' ? undefined : { revalidateOnMount: false }
  )
  const { data: strategyData, isLoading: strategyLoading } = useMLStrategyExplanation(
    activeTab === 'strategy' ? undefined : { revalidateOnMount: false }
  )
  const { data: logsData, isLoading: logsLoading, mutate: mutateLogs } = useMLDecisionLogs(50,
    activeTab === 'logs' ? undefined : { revalidateOnMount: false }
  )

  // Extract data from responses
  const status = statusData?.data || statusData
  const dataQuality = qualityData?.data || null
  const features = featuresData?.data?.features || []
  const strategyExplanation = strategyData?.data || null
  const logs = logsData?.data?.logs || []

  const loading = statusLoading

  const handleTrain = async () => {
    setTraining(true)
    try {
      const res = await apiClient.trainML(30)
      if (res.data?.success) {
        // Revalidate the data after training
        mutateStatus()
        mutateQuality()
      }
    } catch (e) {
      console.error('Training failed:', e)
    }
    setTraining(false)
  }

  const handleRefresh = () => {
    mutateStatus()
    mutateQuality()
    if (activeTab === 'logs') mutateLogs()
  }

  const getQualityColor = (quality: string) => {
    switch (quality) {
      case 'EXCELLENT': return 'text-green-400'
      case 'GOOD': return 'text-blue-400'
      case 'ADEQUATE': return 'text-yellow-400'
      case 'MINIMAL': return 'text-orange-400'
      default: return 'text-red-400'
    }
  }

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8 pt-20">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8 flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                <Brain className="w-8 h-8 text-purple-400" />
                JUBILEE
              </h1>
              <p className="text-gray-400">
                Predictive Risk Optimization Through Machine Evaluation & Training for Honest Earnings Utility System
              </p>
            </div>
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400"
            >
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-6">
            {['overview', 'features', 'strategy', 'logs'].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab as any)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  activeTab === tab
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          {loading && !status ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
            </div>
          ) : (
            <>
              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Status Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {/* ML Availability */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        {status?.ml_library_available ? (
                          <CheckCircle className="w-6 h-6 text-green-400" />
                        ) : (
                          <XCircle className="w-6 h-6 text-red-400" />
                        )}
                        <h3 className="text-lg font-semibold text-white">ML Library</h3>
                      </div>
                      <p className={status?.ml_library_available ? 'text-green-400' : 'text-red-400'}>
                        {status?.ml_library_available ? 'Available' : 'Not Available'}
                      </p>
                    </div>

                    {/* Model Status */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        {status?.model_trained ? (
                          <CheckCircle className="w-6 h-6 text-green-400" />
                        ) : (
                          <AlertTriangle className="w-6 h-6 text-yellow-400" />
                        )}
                        <h3 className="text-lg font-semibold text-white">Model Status</h3>
                      </div>
                      <p className={status?.model_trained ? 'text-green-400' : 'text-yellow-400'}>
                        {status?.model_trained ? 'Trained' : 'Not Trained'}
                      </p>
                      {status?.training_metrics && (
                        <p className="text-sm text-gray-400 mt-2">
                          Accuracy: {(status.training_metrics.accuracy * 100).toFixed(1)}%
                        </p>
                      )}
                    </div>

                    {/* Training Data */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        <Database className="w-6 h-6 text-blue-400" />
                        <h3 className="text-lg font-semibold text-white">Training Data</h3>
                      </div>
                      <p className="text-2xl font-bold text-white">
                        {status?.training_data_available || 0}
                      </p>
                      <p className="text-sm text-gray-400">
                        {status?.can_train ? 'Ready to train' : `Need ${30 - (status?.training_data_available || 0)} more`}
                      </p>
                    </div>
                  </div>

                  {/* Honest Assessment */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Target className="w-5 h-5 text-purple-400" />
                      Honest Assessment
                    </h3>
                    <p className="text-gray-300 text-lg">{status?.honest_assessment}</p>
                  </div>

                  {/* Data Quality */}
                  {dataQuality && (
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                        <BarChart3 className="w-5 h-5 text-blue-400" />
                        Data Quality
                      </h3>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                          <p className="text-gray-400 text-sm">Total Trades</p>
                          <p className="text-2xl font-bold text-white">{dataQuality.total_trades}</p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Win Rate</p>
                          <p className="text-2xl font-bold text-green-400">{dataQuality.win_rate?.toFixed(1)}%</p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Total P&L</p>
                          <p className={`text-2xl font-bold ${dataQuality.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            ${dataQuality.total_pnl?.toFixed(2)}
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Quality</p>
                          <p className={`text-2xl font-bold ${getQualityColor(dataQuality.quality)}`}>
                            {dataQuality.quality}
                          </p>
                        </div>
                      </div>
                      <p className="text-gray-400 mt-4">{dataQuality.recommendation}</p>
                    </div>
                  )}

                  {/* Train Button */}
                  {status?.can_train && (
                    <div className="flex justify-center">
                      <button
                        onClick={handleTrain}
                        disabled={training}
                        className="px-6 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white font-medium rounded-lg flex items-center gap-2"
                      >
                        {training ? (
                          <>
                            <RefreshCw className="w-5 h-5 animate-spin" />
                            Training...
                          </>
                        ) : (
                          <>
                            <Zap className="w-5 h-5" />
                            Train ML Model
                          </>
                        )}
                      </button>
                    </div>
                  )}

                  {/* What ML Can/Cannot Do */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-gray-800 rounded-lg p-6 border border-green-900">
                      <h3 className="text-lg font-semibold text-green-400 mb-4">What ML CAN Do</h3>
                      <ul className="space-y-2">
                        {status?.what_ml_can_do?.map((item: string, i: number) => (
                          <li key={i} className="flex items-start gap-2 text-gray-300">
                            <CheckCircle className="w-4 h-4 text-green-400 mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-red-900">
                      <h3 className="text-lg font-semibold text-red-400 mb-4">What ML CANNOT Do</h3>
                      <ul className="space-y-2">
                        {status?.what_ml_cannot_do?.map((item: string, i: number) => (
                          <li key={i} className="flex items-start gap-2 text-gray-300">
                            <XCircle className="w-4 h-4 text-red-400 mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {/* Features Tab */}
              {activeTab === 'features' && (
                <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                  <h3 className="text-lg font-semibold text-white mb-6">Feature Importance</h3>
                  {featuresLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
                    </div>
                  ) : features.length > 0 ? (
                    <div className="space-y-4">
                      {features.map((feature: any, i: number) => (
                        <div key={i} className="space-y-2">
                          <div className="flex justify-between items-center">
                            <span className="text-white font-medium">{feature.name}</span>
                            <span className="text-purple-400">{feature.importance.toFixed(1)}%</span>
                          </div>
                          <div className="w-full bg-gray-700 rounded-full h-3">
                            <div
                              className="bg-gradient-to-r from-purple-600 to-purple-400 h-3 rounded-full"
                              style={{ width: `${Math.min(feature.importance, 100)}%` }}
                            />
                          </div>
                          <p className="text-sm text-gray-400">{feature.meaning}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-400">Train the model to see feature importance</p>
                  )}
                </div>
              )}

              {/* Strategy Tab */}
              {activeTab === 'strategy' && (
                <div className="space-y-6">
                  {strategyLoading ? (
                    <div className="flex items-center justify-center py-20">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
                    </div>
                  ) : strategyExplanation ? (
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h3 className="text-xl font-semibold text-white mb-2">{strategyExplanation.strategy}</h3>

                      {/* Why It Works */}
                      <div className="mt-6">
                        <h4 className="text-lg font-medium text-green-400 mb-4">Why It Works</h4>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          {Object.entries(strategyExplanation.why_it_works || {}).map(([key, value]: [string, any]) => (
                            <div key={key} className="bg-gray-900 rounded-lg p-4">
                              <h5 className="text-white font-medium mb-2">{key.replace(/_/g, ' ')}</h5>
                              <p className="text-gray-400 text-sm">{value.explanation}</p>
                              <p className="text-green-400 text-sm mt-2">{value.you_benefit}</p>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Why It Can Fail */}
                      <div className="mt-6">
                        <h4 className="text-lg font-medium text-red-400 mb-4">Why It Can Fail</h4>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          {Object.entries(strategyExplanation.why_it_can_fail || {}).map(([key, value]: [string, any]) => (
                            <div key={key} className="bg-gray-900 rounded-lg p-4 border border-red-900/30">
                              <h5 className="text-white font-medium mb-2">{key.replace(/_/g, ' ')}</h5>
                              <p className="text-gray-400 text-sm">{value.explanation}</p>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Realistic Expectations */}
                      <div className="mt-6">
                        <h4 className="text-lg font-medium text-blue-400 mb-4">Realistic Expectations</h4>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          {Object.entries(strategyExplanation.realistic_expectations || {}).map(([key, value]) => (
                            <div key={key} className="bg-gray-900 rounded-lg p-4 text-center">
                              <p className="text-gray-400 text-sm">{key.replace(/_/g, ' ')}</p>
                              <p className="text-white font-bold mt-1">{String(value)}</p>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Bottom Line */}
                      <div className="mt-6 bg-purple-900/30 rounded-lg p-4 border border-purple-700">
                        <p className="text-gray-200">{strategyExplanation.bottom_line}</p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-gray-400">Strategy explanation not available</p>
                  )}
                </div>
              )}

              {/* Logs Tab */}
              {activeTab === 'logs' && (
                <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                  <div className="p-4 border-b border-gray-700">
                    <h3 className="text-lg font-semibold text-white">ML Decision Logs</h3>
                    <p className="text-sm text-gray-400">Recent ML actions and predictions</p>
                  </div>
                  <div className="max-h-[600px] overflow-y-auto">
                    {logsLoading ? (
                      <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
                      </div>
                    ) : logs.length > 0 ? (
                      <table className="w-full">
                        <thead className="bg-gray-900 sticky top-0">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Time</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Action</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Score</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Recommendation</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Details</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-700">
                          {logs.map((log: any) => (
                            <tr key={log.id} className="hover:bg-gray-700/50">
                              <td className="px-4 py-3 text-sm text-gray-400">
                                {new Date(log.timestamp).toLocaleString()}
                              </td>
                              <td className="px-4 py-3">
                                <span className={`px-2 py-1 rounded text-xs font-medium ${
                                  log.action.includes('TRAIN') ? 'bg-purple-900 text-purple-300' :
                                  log.action.includes('SCORE') ? 'bg-blue-900 text-blue-300' :
                                  'bg-gray-700 text-gray-300'
                                }`}>
                                  {log.action}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-sm">
                                {log.ml_score !== null ? (
                                  <span className={log.ml_score > 0.6 ? 'text-green-400' : 'text-yellow-400'}>
                                    {(log.ml_score * 100).toFixed(1)}%
                                  </span>
                                ) : (
                                  <span className="text-gray-500">-</span>
                                )}
                              </td>
                              <td className="px-4 py-3">
                                {log.recommendation && (
                                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                                    log.recommendation === 'TRADE' ? 'bg-green-900 text-green-300' :
                                    log.recommendation === 'SKIP' ? 'bg-red-900 text-red-300' :
                                    'bg-gray-700 text-gray-300'
                                  }`}>
                                    {log.recommendation}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-400 max-w-xs truncate">
                                {log.reasoning || (log.details ? JSON.stringify(log.details).slice(0, 50) + '...' : '-')}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div className="p-8 text-center text-gray-400">
                        No ML logs yet. Train the model or run backtests to generate logs.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
