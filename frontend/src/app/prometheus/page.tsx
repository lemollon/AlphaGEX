'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { api } from '@/lib/api'
import useSWR from 'swr'
import {
  Brain,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Database,
  Zap,
  Target,
  BarChart3,
  Activity,
  Clock,
  TrendingUp,
  TrendingDown,
  Filter,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  Flame,
  Shield,
  Eye,
  FileText,
  Settings,
  ChevronRight,
  Play,
  Pause
} from 'lucide-react'

// API fetcher for SWR
const fetcher = (url: string) => api.get(url).then(res => res.data)

interface MLStatus {
  ml_library_available: boolean
  model_trained: boolean
  model_version: string | null
  is_calibrated: boolean
  training_data_available: number
  can_train: boolean
  honest_assessment: string
  what_ml_can_do: string[]
  what_ml_cannot_do: string[]
  training_metrics?: {
    accuracy: number
    precision: number
    recall: number
    cv_accuracy_mean: number
    calibration_error: number | null
  }
  performance?: {
    total_predictions: number
    wins: number
    losses: number
    win_rate: number
    total_pnl: number
  }
}

interface Feature {
  rank: number
  name: string
  importance: number
  importance_pct: number
  meaning: string
}

interface Log {
  id: number
  timestamp: string
  log_type: string
  action: string
  ml_score: number | null
  recommendation: string | null
  reasoning: string | null
  trade_id: string | null
  details: any
}

interface TrainingHistory {
  training_id: string
  training_date: string
  accuracy: number
  precision_score: number
  cv_accuracy_mean: number
  is_calibrated: boolean
  model_version: string
  total_samples: number
}

export default function PrometheusPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'features' | 'performance' | 'logs' | 'training' | 'strategy'>('overview')
  const [training, setTraining] = useState(false)
  const [logFilter, setLogFilter] = useState<string>('')

  // SWR hooks for data fetching
  const { data: statusData, isLoading: statusLoading, mutate: mutateStatus } = useSWR<MLStatus>(
    '/api/prometheus/status',
    fetcher,
    { refreshInterval: 30000 }
  )

  const { data: featuresData, mutate: mutateFeatures } = useSWR<{ features: Feature[] }>(
    activeTab === 'features' ? '/api/prometheus/feature-importance' : null,
    fetcher
  )

  const { data: logsData, mutate: mutateLogs } = useSWR<{ logs: Log[] }>(
    activeTab === 'logs' ? '/api/prometheus/logs?limit=100' : null,
    fetcher,
    { refreshInterval: 10000 }
  )

  const { data: trainingHistoryData } = useSWR<{ history: TrainingHistory[] }>(
    activeTab === 'training' ? '/api/prometheus/training-history' : null,
    fetcher
  )

  const { data: performanceData } = useSWR(
    activeTab === 'performance' ? '/api/prometheus/performance' : null,
    fetcher
  )

  const { data: strategyData } = useSWR(
    activeTab === 'strategy' ? '/api/ml/strategy-explanation' : null,
    fetcher
  )

  const status = statusData
  const features = featuresData?.features || []
  const logs = logsData?.logs || []
  const trainingHistory = trainingHistoryData?.history || []
  const strategy = strategyData?.data

  const handleTrain = async () => {
    setTraining(true)
    try {
      await api.post('/api/prometheus/train', { min_samples: 30, calibrate: true })
      mutateStatus()
      mutateFeatures()
    } catch (e) {
      console.error('Training failed:', e)
    }
    setTraining(false)
  }

  const handleRefresh = () => {
    mutateStatus()
    if (activeTab === 'logs') mutateLogs()
    if (activeTab === 'features') mutateFeatures()
  }

  const getRecommendationStyle = (rec: string) => {
    switch (rec) {
      case 'STRONG_TRADE':
        return 'bg-green-900/50 text-green-300 border-green-700'
      case 'TRADE':
        return 'bg-blue-900/50 text-blue-300 border-blue-700'
      case 'NEUTRAL':
        return 'bg-yellow-900/50 text-yellow-300 border-yellow-700'
      case 'CAUTION':
        return 'bg-orange-900/50 text-orange-300 border-orange-700'
      case 'SKIP':
        return 'bg-red-900/50 text-red-300 border-red-700'
      default:
        return 'bg-gray-800 text-gray-300 border-gray-700'
    }
  }

  const getLogTypeStyle = (type: string) => {
    switch (type) {
      case 'PREDICTION':
        return 'bg-purple-900/50 text-purple-300'
      case 'TRAINING':
        return 'bg-blue-900/50 text-blue-300'
      case 'OUTCOME':
        return 'bg-green-900/50 text-green-300'
      case 'ERROR':
        return 'bg-red-900/50 text-red-300'
      default:
        return 'bg-gray-800 text-gray-300'
    }
  }

  const filteredLogs = logs.filter(log => {
    if (!logFilter) return true
    return (
      log.log_type.toLowerCase().includes(logFilter.toLowerCase()) ||
      log.action.toLowerCase().includes(logFilter.toLowerCase()) ||
      (log.reasoning && log.reasoning.toLowerCase().includes(logFilter.toLowerCase()))
    )
  })

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8 pt-20">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8 flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                <Flame className="w-8 h-8 text-orange-400" />
                PROMETHEUS
              </h1>
              <p className="text-gray-400">
                Predictive Risk Optimization Through Machine Evaluation & Training for Honest Earnings Utility System
              </p>
              {status?.model_version && (
                <p className="text-sm text-purple-400 mt-1 flex items-center gap-2">
                  <Shield className="w-4 h-4" />
                  Model: {status.model_version}
                  {status.is_calibrated && (
                    <span className="bg-green-900/50 text-green-300 text-xs px-2 py-0.5 rounded">
                      Calibrated
                    </span>
                  )}
                </p>
              )}
            </div>
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400"
            >
              <RefreshCw className={`w-5 h-5 ${statusLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-6 flex-wrap">
            {[
              { id: 'overview', label: 'Overview', icon: Target },
              { id: 'features', label: 'Features', icon: BarChart3 },
              { id: 'performance', label: 'Performance', icon: Activity },
              { id: 'training', label: 'Training', icon: Zap },
              { id: 'logs', label: 'Logs', icon: FileText },
              { id: 'strategy', label: 'Strategy', icon: Brain }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-orange-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>

          {statusLoading && !status ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-orange-500"></div>
            </div>
          ) : (
            <>
              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Status Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    {/* ML Status */}
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
                        {status?.model_trained ? 'Trained & Ready' : 'Not Trained'}
                      </p>
                      {status?.is_calibrated && (
                        <p className="text-sm text-purple-400 mt-1">Probabilities Calibrated</p>
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

                    {/* Accuracy */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        <Target className="w-6 h-6 text-purple-400" />
                        <h3 className="text-lg font-semibold text-white">Accuracy</h3>
                      </div>
                      <p className="text-2xl font-bold text-white">
                        {status?.training_metrics?.accuracy
                          ? `${(status.training_metrics.accuracy * 100).toFixed(1)}%`
                          : 'N/A'}
                      </p>
                      {status?.training_metrics?.cv_accuracy_mean && (
                        <p className="text-sm text-gray-400">
                          CV: {(status.training_metrics.cv_accuracy_mean * 100).toFixed(1)}%
                        </p>
                      )}
                    </div>

                    {/* Win Rate */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        <TrendingUp className="w-6 h-6 text-green-400" />
                        <h3 className="text-lg font-semibold text-white">Win Rate</h3>
                      </div>
                      <p className="text-2xl font-bold text-white">
                        {status?.performance?.win_rate
                          ? `${(status.performance.win_rate * 100).toFixed(1)}%`
                          : 'N/A'}
                      </p>
                      <p className="text-sm text-gray-400">
                        {status?.performance?.wins || 0}W / {status?.performance?.losses || 0}L
                      </p>
                    </div>
                  </div>

                  {/* Honest Assessment */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Eye className="w-5 h-5 text-orange-400" />
                      Honest Assessment
                    </h3>
                    <p className="text-gray-300 text-lg">{status?.honest_assessment}</p>
                  </div>

                  {/* What ML Can/Cannot Do */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-gray-800 rounded-lg p-6 border border-green-900/50">
                      <h3 className="text-lg font-semibold text-green-400 mb-4 flex items-center gap-2">
                        <CheckCircle className="w-5 h-5" />
                        What Prometheus CAN Do
                      </h3>
                      <ul className="space-y-2">
                        {status?.what_ml_can_do?.map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-gray-300">
                            <ChevronRight className="w-4 h-4 text-green-400 mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-red-900/50">
                      <h3 className="text-lg font-semibold text-red-400 mb-4 flex items-center gap-2">
                        <XCircle className="w-5 h-5" />
                        What Prometheus CANNOT Do
                      </h3>
                      <ul className="space-y-2">
                        {status?.what_ml_cannot_do?.map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-gray-300">
                            <ChevronRight className="w-4 h-4 text-red-400 mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Train Button */}
                  {status?.can_train && (
                    <div className="flex justify-center">
                      <button
                        onClick={handleTrain}
                        disabled={training}
                        className="px-8 py-4 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 text-white font-medium rounded-lg flex items-center gap-3 text-lg"
                      >
                        {training ? (
                          <>
                            <RefreshCw className="w-6 h-6 animate-spin" />
                            Training Prometheus...
                          </>
                        ) : (
                          <>
                            <Flame className="w-6 h-6" />
                            Train Prometheus Model
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Features Tab */}
              {activeTab === 'features' && (
                <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                  <h3 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-orange-400" />
                    Feature Importance Analysis
                  </h3>
                  {features.length > 0 ? (
                    <div className="space-y-4">
                      {features.map((feature, i) => (
                        <div key={i} className="space-y-2">
                          <div className="flex justify-between items-center">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-500 text-sm w-6">#{feature.rank}</span>
                              <span className="text-white font-medium">{feature.name}</span>
                            </div>
                            <span className="text-orange-400 font-bold">
                              {feature.importance_pct.toFixed(1)}%
                            </span>
                          </div>
                          <div className="w-full bg-gray-700 rounded-full h-3">
                            <div
                              className="bg-gradient-to-r from-orange-600 to-orange-400 h-3 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(feature.importance_pct * 2, 100)}%` }}
                            />
                          </div>
                          <p className="text-sm text-gray-400 pl-8">{feature.meaning}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-400">Train the model to see feature importance</p>
                  )}
                </div>
              )}

              {/* Performance Tab */}
              {activeTab === 'performance' && (
                <div className="space-y-6">
                  {/* Performance Summary */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <p className="text-gray-400 text-sm mb-1">Total Predictions</p>
                      <p className="text-3xl font-bold text-white">
                        {performanceData?.total_predictions || status?.performance?.total_predictions || 0}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <p className="text-gray-400 text-sm mb-1">Prediction Accuracy</p>
                      <p className="text-3xl font-bold text-green-400">
                        {performanceData?.prediction_accuracy
                          ? `${(performanceData.prediction_accuracy * 100).toFixed(1)}%`
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <p className="text-gray-400 text-sm mb-1">Total P&L</p>
                      <p className={`text-3xl font-bold ${
                        (performanceData?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        ${(performanceData?.total_pnl || status?.performance?.total_pnl || 0).toLocaleString()}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <p className="text-gray-400 text-sm mb-1">Calibration Error</p>
                      <p className="text-3xl font-bold text-purple-400">
                        {performanceData?.calibration_error
                          ? `${(performanceData.calibration_error * 100).toFixed(2)}%`
                          : 'N/A'}
                      </p>
                    </div>
                  </div>

                  {/* Calibration Chart Placeholder */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Activity className="w-5 h-5 text-orange-400" />
                      Probability Calibration
                    </h3>
                    <p className="text-gray-400">
                      Calibration shows how well predicted probabilities match actual outcomes.
                      A well-calibrated model should have predictions close to the diagonal line.
                    </p>
                    <div className="mt-4 p-4 bg-gray-900 rounded-lg">
                      <p className="text-sm text-gray-500">
                        {status?.is_calibrated
                          ? 'Model is calibrated using isotonic regression.'
                          : 'Model uses raw probabilities (not calibrated).'}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Training History Tab */}
              {activeTab === 'training' && (
                <div className="space-y-6">
                  <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                    <div className="p-4 border-b border-gray-700">
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <Zap className="w-5 h-5 text-orange-400" />
                        Training History
                      </h3>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="bg-gray-900">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Date</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Version</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Samples</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Accuracy</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">CV Score</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Calibrated</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-700">
                          {trainingHistory.length > 0 ? (
                            trainingHistory.map((training, i) => (
                              <tr key={i} className="hover:bg-gray-700/50">
                                <td className="px-4 py-3 text-sm text-gray-300">
                                  {new Date(training.training_date).toLocaleDateString()}
                                </td>
                                <td className="px-4 py-3 text-sm text-purple-400">
                                  {training.model_version}
                                </td>
                                <td className="px-4 py-3 text-sm text-white">
                                  {training.total_samples}
                                </td>
                                <td className="px-4 py-3 text-sm text-green-400">
                                  {(training.accuracy * 100).toFixed(1)}%
                                </td>
                                <td className="px-4 py-3 text-sm text-blue-400">
                                  {(training.cv_accuracy_mean * 100).toFixed(1)}%
                                </td>
                                <td className="px-4 py-3">
                                  {training.is_calibrated ? (
                                    <CheckCircle className="w-4 h-4 text-green-400" />
                                  ) : (
                                    <XCircle className="w-4 h-4 text-gray-500" />
                                  )}
                                </td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                                No training history yet
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Training Metrics Details */}
                  {status?.training_metrics && (
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h3 className="text-lg font-semibold text-white mb-4">Current Model Metrics</h3>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div>
                          <p className="text-gray-400 text-sm">Accuracy</p>
                          <p className="text-xl font-bold text-white">
                            {(status.training_metrics.accuracy * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Precision</p>
                          <p className="text-xl font-bold text-white">
                            {(status.training_metrics.precision * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Recall</p>
                          <p className="text-xl font-bold text-white">
                            {(status.training_metrics.recall * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">CV Score</p>
                          <p className="text-xl font-bold text-white">
                            {(status.training_metrics.cv_accuracy_mean * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Calibration Error</p>
                          <p className="text-xl font-bold text-white">
                            {status.training_metrics.calibration_error
                              ? `${(status.training_metrics.calibration_error * 100).toFixed(2)}%`
                              : 'N/A'}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Logs Tab */}
              {activeTab === 'logs' && (
                <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                  <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                    <div>
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <FileText className="w-5 h-5 text-orange-400" />
                        Decision Logs
                      </h3>
                      <p className="text-sm text-gray-400">Complete transparency on all ML decisions</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <Filter className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                        <input
                          type="text"
                          placeholder="Filter logs..."
                          value={logFilter}
                          onChange={(e) => setLogFilter(e.target.value)}
                          className="pl-10 pr-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-orange-500"
                        />
                      </div>
                      <button
                        onClick={() => mutateLogs()}
                        className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-400"
                      >
                        <RefreshCw className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="max-h-[600px] overflow-y-auto">
                    <table className="w-full">
                      <thead className="bg-gray-900 sticky top-0">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Time</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Type</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Action</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Score</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Recommendation</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Details</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {filteredLogs.length > 0 ? (
                          filteredLogs.map((log) => (
                            <tr key={log.id} className="hover:bg-gray-700/50">
                              <td className="px-4 py-3 text-sm text-gray-400">
                                {new Date(log.timestamp).toLocaleString()}
                              </td>
                              <td className="px-4 py-3">
                                <span className={`px-2 py-1 rounded text-xs font-medium ${getLogTypeStyle(log.log_type)}`}>
                                  {log.log_type}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-sm text-white">
                                {log.action}
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
                                  <span className={`px-2 py-1 rounded text-xs font-medium border ${getRecommendationStyle(log.recommendation)}`}>
                                    {log.recommendation}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-400 max-w-xs truncate">
                                {log.reasoning || '-'}
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                              No logs yet. Train the model or run predictions to generate logs.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Strategy Tab */}
              {activeTab === 'strategy' && (
                <div className="space-y-6">
                  {strategy ? (
                    <>
                      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                        <h3 className="text-xl font-semibold text-white mb-2">{strategy.strategy}</h3>

                        {/* Why It Works */}
                        <div className="mt-6">
                          <h4 className="text-lg font-medium text-green-400 mb-4 flex items-center gap-2">
                            <TrendingUp className="w-5 h-5" />
                            Why It Works
                          </h4>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {Object.entries(strategy.why_it_works || {}).map(([key, value]: [string, any]) => (
                              <div key={key} className="bg-gray-900 rounded-lg p-4 border border-green-900/30">
                                <h5 className="text-white font-medium mb-2 capitalize">
                                  {key.replace(/_/g, ' ')}
                                </h5>
                                <p className="text-gray-400 text-sm">{value.explanation}</p>
                                <p className="text-green-400 text-sm mt-2">{value.you_benefit}</p>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Why It Can Fail */}
                        <div className="mt-6">
                          <h4 className="text-lg font-medium text-red-400 mb-4 flex items-center gap-2">
                            <TrendingDown className="w-5 h-5" />
                            Why It Can Fail
                          </h4>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {Object.entries(strategy.why_it_can_fail || {}).map(([key, value]: [string, any]) => (
                              <div key={key} className="bg-gray-900 rounded-lg p-4 border border-red-900/30">
                                <h5 className="text-white font-medium mb-2 capitalize">
                                  {key.replace(/_/g, ' ')}
                                </h5>
                                <p className="text-gray-400 text-sm">{value.explanation}</p>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Realistic Expectations */}
                        <div className="mt-6">
                          <h4 className="text-lg font-medium text-blue-400 mb-4 flex items-center gap-2">
                            <Target className="w-5 h-5" />
                            Realistic Expectations
                          </h4>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {Object.entries(strategy.realistic_expectations || {}).map(([key, value]) => (
                              <div key={key} className="bg-gray-900 rounded-lg p-4 text-center">
                                <p className="text-gray-400 text-sm capitalize">{key.replace(/_/g, ' ')}</p>
                                <p className="text-white font-bold text-lg mt-1">{String(value)}</p>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Bottom Line */}
                        <div className="mt-6 bg-orange-900/30 rounded-lg p-4 border border-orange-700">
                          <p className="text-gray-200">{strategy.bottom_line}</p>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="bg-gray-800 rounded-lg p-8 border border-gray-700 text-center">
                      <Brain className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                      <p className="text-gray-400">Loading strategy explanation...</p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
