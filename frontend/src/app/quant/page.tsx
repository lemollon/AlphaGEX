'use client'

import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '@/lib/api'
import Navigation from '@/components/Navigation'
import {
  Calculator,
  TrendingUp,
  TrendingDown,
  Activity,
  CheckCircle,
  XCircle,
  RefreshCw,
  Brain,
  Zap,
  Target,
  Clock,
  AlertTriangle,
  Bell,
  Award,
  GitCompare,
  GraduationCap,
  ThumbsUp,
  ThumbsDown,
  Eye,
  Check,
  X
} from 'lucide-react'

// ============================================================================
// INTERFACES
// ============================================================================

interface QuantModule {
  name: string
  available: boolean
  is_trained?: boolean
  model_version?: string
  description?: string
  error?: string
}

interface QuantStatus {
  models: QuantModule[]
  total_predictions_24h: number
  timestamp: string
}

interface PredictionLog {
  id: number
  timestamp: string
  symbol: string
  prediction_type: string
  predicted_value: string
  confidence: number
  features: Record<string, unknown>
  outcome_correct?: boolean | null
  outcome_pnl?: number | null
  used_by_bot?: string | null
}

interface QuantStats {
  days: number
  by_type: { model: string; count: number; avg_confidence: number }[]
  by_day: { date: string; count: number }[]
  by_value: { value: string; count: number }[]
}

interface QuantAlert {
  id: number
  timestamp: string
  alert_type: string
  severity: string
  title: string
  message: string
  symbol: string
  previous_value?: string
  current_value?: string
  confidence?: number
  model_name?: string
  acknowledged: boolean
}

interface ModelPerformance {
  model_name: string
  total_predictions: number
  correct_predictions: number
  incorrect_predictions: number
  pending_predictions: number
  accuracy: number
  avg_confidence: number
  total_pnl: number
}

interface PerformanceSummary {
  period: string
  models: ModelPerformance[]
  overall_accuracy: number
  overall_predictions: number
  best_model: string
}

interface TrainingHistory {
  id: number
  timestamp: string
  model_name: string
  training_samples: number
  accuracy_before: number
  accuracy_after: number
  status: string
  duration_seconds: number
  triggered_by: string
}

interface ModelComparison {
  timestamp: string
  models: {
    name: string
    prediction: string
    confidence: number
    accuracy_7d: number
  }[]
  agreement: boolean
  consensus_prediction?: string
}

type TabType = 'overview' | 'predictions' | 'logs' | 'outcomes' | 'alerts' | 'performance' | 'training' | 'compare' | 'stats'

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function QuantPage() {
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [status, setStatus] = useState<QuantStatus | null>(null)
  const [logs, setLogs] = useState<PredictionLog[]>([])
  const [stats, setStats] = useState<QuantStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Prediction state
  const [predicting, setPredicting] = useState(false)
  const [regimePrediction, setRegimePrediction] = useState<Record<string, unknown> | null>(null)
  const [directionalPrediction, setDirectionalPrediction] = useState<Record<string, unknown> | null>(null)

  // New feature states
  const [pendingOutcomes, setPendingOutcomes] = useState<PredictionLog[]>([])
  const [alerts, setAlerts] = useState<QuantAlert[]>([])
  const [performanceSummary, setPerformanceSummary] = useState<PerformanceSummary | null>(null)
  const [trainingHistory, setTrainingHistory] = useState<TrainingHistory[]>([])
  const [modelComparison, setModelComparison] = useState<ModelComparison | null>(null)
  const [botUsageStats, setBotUsageStats] = useState<Record<string, unknown> | null>(null)

  // ============================================================================
  // DATA FETCHING
  // ============================================================================

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiClient.getQuantStatus()
      setStatus(res.data)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch Quant status:', err)
      setError('Failed to load Quant status')
    }
  }, [])

  const fetchLogs = useCallback(async () => {
    try {
      const res = await apiClient.getQuantLogs(50)
      setLogs(res.data?.logs || [])
    } catch (err) {
      console.error('Failed to fetch logs:', err)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const res = await apiClient.getQuantLogsStats(7)
      setStats(res.data)
    } catch (err) {
      console.error('Failed to fetch stats:', err)
    }
  }, [])

  const fetchPendingOutcomes = useCallback(async () => {
    try {
      const res = await apiClient.getQuantPendingOutcomes(20)
      setPendingOutcomes(res.data?.predictions || [])
    } catch (err) {
      console.error('Failed to fetch pending outcomes:', err)
    }
  }, [])

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await apiClient.getQuantAlerts(50, false)
      setAlerts(res.data?.alerts || [])
    } catch (err) {
      console.error('Failed to fetch alerts:', err)
    }
  }, [])

  const fetchPerformance = useCallback(async () => {
    try {
      const res = await apiClient.getQuantPerformanceSummary(7)
      setPerformanceSummary(res.data)
    } catch (err) {
      console.error('Failed to fetch performance:', err)
    }
  }, [])

  const fetchTrainingHistory = useCallback(async () => {
    try {
      const res = await apiClient.getQuantTrainingHistory(20)
      setTrainingHistory(res.data?.history || [])
    } catch (err) {
      console.error('Failed to fetch training history:', err)
    }
  }, [])

  const fetchComparison = useCallback(async () => {
    try {
      const res = await apiClient.getQuantComparison()
      setModelComparison(res.data)
    } catch (err) {
      console.error('Failed to fetch comparison:', err)
    }
  }, [])

  const fetchBotUsage = useCallback(async () => {
    try {
      const res = await apiClient.getQuantBotUsage(7)
      setBotUsageStats(res.data)
    } catch (err) {
      console.error('Failed to fetch bot usage:', err)
    }
  }, [])

  // ============================================================================
  // ACTIONS
  // ============================================================================

  const runPredictions = useCallback(async () => {
    setPredicting(true)
    try {
      const gexRes = await apiClient.getGEX('SPY').catch(() => null)
      const vixRes = await apiClient.getVIXCurrent().catch(() => null)

      const spotPrice = gexRes?.data?.data?.spot_price || 585
      const vix = vixRes?.data?.data?.vix_spot || 15
      const netGex = gexRes?.data?.data?.net_gex || 0
      const flipPoint = gexRes?.data?.data?.flip_point || spotPrice
      const callWall = gexRes?.data?.data?.call_wall || spotPrice + 5
      const putWall = gexRes?.data?.data?.put_wall || spotPrice - 5

      const regimeRes = await apiClient.predictRegime({
        spot_price: spotPrice,
        vix: vix,
        net_gex: netGex,
        flip_point: flipPoint,
        iv_rank: 50
      }).catch(() => null)

      if (regimeRes?.data) {
        setRegimePrediction(regimeRes.data)
      }

      const dirRes = await apiClient.predictDirection({
        net_gex: netGex,
        call_wall: callWall,
        put_wall: putWall,
        flip_point: flipPoint,
        spot_price: spotPrice,
        vix: vix
      }).catch(() => null)

      if (dirRes?.data) {
        setDirectionalPrediction(dirRes.data)
      }

      await fetchLogs()
      await fetchComparison()
    } catch (err) {
      console.error('Prediction failed:', err)
    } finally {
      setPredicting(false)
    }
  }, [fetchLogs, fetchComparison])

  const recordOutcome = useCallback(async (predictionId: number, correct: boolean, pnl?: number) => {
    try {
      await apiClient.recordQuantOutcome({
        prediction_id: predictionId,
        correct: correct,
        pnl: pnl,
        notes: `Manually marked as ${correct ? 'correct' : 'incorrect'}`
      })
      await fetchPendingOutcomes()
      await fetchPerformance()
    } catch (err) {
      console.error('Failed to record outcome:', err)
    }
  }, [fetchPendingOutcomes, fetchPerformance])

  const acknowledgeAlert = useCallback(async (alertId: number) => {
    try {
      await apiClient.acknowledgeQuantAlert(alertId)
      await fetchAlerts()
    } catch (err) {
      console.error('Failed to acknowledge alert:', err)
    }
  }, [fetchAlerts])

  // ============================================================================
  // EFFECTS
  // ============================================================================

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await Promise.all([fetchStatus(), fetchLogs(), fetchStats()])
      setLoading(false)
    }
    loadData()

    const interval = setInterval(() => {
      fetchStatus()
      if (activeTab === 'logs') fetchLogs()
      if (activeTab === 'stats') fetchStats()
      if (activeTab === 'outcomes') fetchPendingOutcomes()
      if (activeTab === 'alerts') fetchAlerts()
      if (activeTab === 'performance') fetchPerformance()
      if (activeTab === 'training') fetchTrainingHistory()
      if (activeTab === 'compare') fetchComparison()
    }, 30000)

    return () => clearInterval(interval)
  }, [fetchStatus, fetchLogs, fetchStats, fetchPendingOutcomes, fetchAlerts, fetchPerformance, fetchTrainingHistory, fetchComparison, activeTab])

  useEffect(() => {
    if (activeTab === 'outcomes') fetchPendingOutcomes()
    if (activeTab === 'alerts') fetchAlerts()
    if (activeTab === 'performance') {
      fetchPerformance()
      fetchBotUsage()
    }
    if (activeTab === 'training') fetchTrainingHistory()
    if (activeTab === 'compare') fetchComparison()
  }, [activeTab, fetchPendingOutcomes, fetchAlerts, fetchPerformance, fetchBotUsage, fetchTrainingHistory, fetchComparison])

  // ============================================================================
  // HELPERS
  // ============================================================================

  const getActionColor = (action: string) => {
    switch (action) {
      case 'SELL_PREMIUM':
      case 'STAY_FLAT':
        return 'text-yellow-400'
      case 'BUY_CALLS':
      case 'BULLISH':
        return 'text-green-400'
      case 'BUY_PUTS':
      case 'BEARISH':
        return 'text-red-400'
      case 'FLAT':
        return 'text-gray-400'
      default:
        return 'text-gray-300'
    }
  }

  const getActionIcon = (action: string) => {
    switch (action) {
      case 'SELL_PREMIUM':
        return <Target className="h-5 w-5 text-yellow-400" />
      case 'BUY_CALLS':
      case 'BULLISH':
        return <TrendingUp className="h-5 w-5 text-green-400" />
      case 'BUY_PUTS':
      case 'BEARISH':
        return <TrendingDown className="h-5 w-5 text-red-400" />
      case 'STAY_FLAT':
      case 'FLAT':
        return <Activity className="h-5 w-5 text-gray-400" />
      default:
        return <Brain className="h-5 w-5 text-blue-400" />
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
        return 'bg-red-900/50 border-red-500 text-red-300'
      case 'WARNING':
        return 'bg-yellow-900/50 border-yellow-500 text-yellow-300'
      default:
        return 'bg-blue-900/50 border-blue-500 text-blue-300'
    }
  }

  const formatTimestamp = (ts: string) => {
    return new Date(ts).toLocaleString()
  }

  // ============================================================================
  // RENDER
  // ============================================================================

  if (loading) {
    return (
      <>
        <Navigation />
        <main className="min-h-screen bg-black text-white px-4 pb-4 md:px-6 md:pb-6 pt-28">
          <div className="flex items-center justify-center h-[60vh]">
            <div className="text-center">
              <RefreshCw className="h-8 w-8 text-blue-400 animate-spin mx-auto mb-4" />
              <p className="text-gray-400">Loading Quant ML Models...</p>
            </div>
          </div>
        </main>
      </>
    )
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: Brain },
    { id: 'predictions', label: 'Live', icon: Zap },
    { id: 'logs', label: 'Logs', icon: Clock },
    { id: 'outcomes', label: 'Outcomes', icon: ThumbsUp },
    { id: 'alerts', label: 'Alerts', icon: Bell },
    { id: 'performance', label: 'Performance', icon: Award },
    { id: 'training', label: 'Training', icon: GraduationCap },
    { id: 'compare', label: 'Compare', icon: GitCompare },
  ] as const

  const unackedAlertCount = alerts.filter(a => !a.acknowledged).length

  return (
    <>
      <Navigation />
      <main className="min-h-screen bg-black text-white px-4 pb-4 md:px-6 md:pb-6 pt-28">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Header */}
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-2">
              <Calculator className="h-8 w-8 text-blue-400" />
              <h1 className="text-2xl font-bold text-white">QUANT - ML Models Dashboard</h1>
            </div>
            <p className="text-gray-400">
              Quantitative ML models for market regime classification, direction prediction, and signal ensemble
            </p>
          </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 bg-red-900/30 border border-red-500 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-red-400" />
          <span className="text-red-300">{error}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 mb-6 border-b border-gray-700 pb-2">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-3 py-2 rounded-t-lg transition-colors text-sm ${
              activeTab === tab.id
                ? 'bg-gray-800 text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
            {tab.id === 'alerts' && unackedAlertCount > 0 && (
              <span className="bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">
                {unackedAlertCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ======================================================================== */}
      {/* OVERVIEW TAB */}
      {/* ======================================================================== */}
      {activeTab === 'overview' && status && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-gray-400 text-sm mb-1">Models Available</div>
              <div className="text-2xl font-bold text-green-400">
                {status.models.filter(m => m.available).length} / {status.models.length}
              </div>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-gray-400 text-sm mb-1">Predictions (24h)</div>
              <div className="text-2xl font-bold text-blue-400">
                {status.total_predictions_24h}
              </div>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-gray-400 text-sm mb-1">Unread Alerts</div>
              <div className={`text-2xl font-bold ${unackedAlertCount > 0 ? 'text-red-400' : 'text-gray-400'}`}>
                {unackedAlertCount}
              </div>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-gray-400 text-sm mb-1">Last Updated</div>
              <div className="text-lg text-gray-300">
                {new Date(status.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {status.models.map((model, idx) => (
              <div
                key={idx}
                className={`bg-gray-800 rounded-lg p-4 border ${
                  model.available ? 'border-green-500/30' : 'border-gray-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-white font-semibold">{model.name}</h3>
                  {model.available ? (
                    <CheckCircle className="h-5 w-5 text-green-400" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-400" />
                  )}
                </div>
                <p className="text-gray-400 text-sm mb-3">{model.description || 'No description'}</p>
                {model.available && (
                  <div className="flex flex-wrap gap-2">
                    {model.is_trained !== undefined && (
                      <span className={`px-2 py-1 rounded text-xs ${
                        model.is_trained ? 'bg-green-900/50 text-green-300' : 'bg-yellow-900/50 text-yellow-300'
                      }`}>
                        {model.is_trained ? 'Trained' : 'Untrained'}
                      </span>
                    )}
                    {model.model_version && (
                      <span className="px-2 py-1 rounded text-xs bg-blue-900/50 text-blue-300">
                        v{model.model_version}
                      </span>
                    )}
                  </div>
                )}
                {model.error && (
                  <p className="text-red-400 text-xs mt-2">{model.error}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ======================================================================== */}
      {/* PREDICTIONS TAB */}
      {/* ======================================================================== */}
      {activeTab === 'predictions' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl text-white font-semibold">Live Predictions</h2>
            <button
              onClick={runPredictions}
              disabled={predicting}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg text-white transition-colors"
            >
              {predicting ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Zap className="h-4 w-4" />
              )}
              {predicting ? 'Running...' : 'Run Predictions'}
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Brain className="h-5 w-5 text-purple-400" />
                ML Regime Classifier
              </h3>
              {regimePrediction ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    {getActionIcon(regimePrediction.action as string)}
                    <span className={`text-2xl font-bold ${getActionColor(regimePrediction.action as string)}`}>
                      {regimePrediction.action as string}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-gray-400 text-sm">Confidence</div>
                      <div className="text-xl text-white">{(regimePrediction.confidence as number)?.toFixed(1)}%</div>
                    </div>
                    <div>
                      <div className="text-gray-400 text-sm">Model Status</div>
                      <div className={`text-sm ${regimePrediction.is_trained ? 'text-green-400' : 'text-yellow-400'}`}>
                        {regimePrediction.is_trained ? 'Trained' : 'Untrained'}
                      </div>
                    </div>
                  </div>
                  {(regimePrediction.probabilities as Record<string, number> | undefined) && (
                    <div className="mt-4">
                      <div className="text-gray-400 text-sm mb-2">Probabilities</div>
                      <div className="space-y-1">
                        {Object.entries(regimePrediction.probabilities as Record<string, number>).map(([action, prob]) => (
                          <div key={action} className="flex justify-between text-sm">
                            <span className={getActionColor(action)}>{action}</span>
                            <span className="text-gray-300">{(prob * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-gray-500">Click &quot;Run Predictions&quot; to get regime classification</p>
              )}
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-cyan-400" />
                GEX Directional ML
              </h3>
              {directionalPrediction ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    {getActionIcon(directionalPrediction.direction as string)}
                    <span className={`text-2xl font-bold ${getActionColor(directionalPrediction.direction as string)}`}>
                      {directionalPrediction.direction as string}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-gray-400 text-sm">Confidence</div>
                      <div className="text-xl text-white">
                        {((directionalPrediction.confidence as number) * 100)?.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-400 text-sm">Timestamp</div>
                      <div className="text-sm text-gray-300">
                        {new Date(directionalPrediction.timestamp as string).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-gray-500">Click &quot;Run Predictions&quot; to get direction prediction</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ======================================================================== */}
      {/* LOGS TAB */}
      {/* ======================================================================== */}
      {activeTab === 'logs' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl text-white font-semibold">Prediction Logs</h2>
            <button
              onClick={fetchLogs}
              className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-sm"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>

          {logs.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <Clock className="h-12 w-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">No prediction logs yet</p>
              <p className="text-gray-500 text-sm">Run predictions to start logging</p>
            </div>
          ) : (
            <div className="bg-gray-800 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-700">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Time</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Model</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Prediction</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Confidence</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Outcome</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Bot</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-gray-700/50">
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-300">
                        {log.prediction_type}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`flex items-center gap-2 ${getActionColor(log.predicted_value)}`}>
                          {getActionIcon(log.predicted_value)}
                          {log.predicted_value}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-300">
                        {log.confidence?.toFixed(1)}%
                      </td>
                      <td className="px-4 py-3">
                        {log.outcome_correct === null || log.outcome_correct === undefined ? (
                          <span className="text-gray-500 text-sm">Pending</span>
                        ) : log.outcome_correct ? (
                          <CheckCircle className="h-4 w-4 text-green-400" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-400" />
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {log.used_by_bot || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ======================================================================== */}
      {/* OUTCOMES TAB */}
      {/* ======================================================================== */}
      {activeTab === 'outcomes' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl text-white font-semibold">Pending Outcomes</h2>
            <button
              onClick={fetchPendingOutcomes}
              className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-sm"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>

          <p className="text-gray-400 text-sm">
            Mark predictions as correct or incorrect to track model accuracy. These are predictions that haven&apos;t been evaluated yet.
          </p>

          {pendingOutcomes.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <ThumbsUp className="h-12 w-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">No pending outcomes</p>
              <p className="text-gray-500 text-sm">All predictions have been evaluated</p>
            </div>
          ) : (
            <div className="space-y-3">
              {pendingOutcomes.map((pred) => (
                <div key={pred.id} className="bg-gray-800 rounded-lg p-4 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="text-sm text-gray-500">
                      {formatTimestamp(pred.timestamp)}
                    </div>
                    <div className="text-gray-300">{pred.prediction_type}</div>
                    <div className={`flex items-center gap-2 font-semibold ${getActionColor(pred.predicted_value)}`}>
                      {getActionIcon(pred.predicted_value)}
                      {pred.predicted_value}
                    </div>
                    <div className="text-gray-400 text-sm">
                      {pred.confidence?.toFixed(1)}% confidence
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => recordOutcome(pred.id, true)}
                      className="flex items-center gap-1 px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded text-white text-sm"
                    >
                      <ThumbsUp className="h-4 w-4" />
                      Correct
                    </button>
                    <button
                      onClick={() => recordOutcome(pred.id, false)}
                      className="flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-white text-sm"
                    >
                      <ThumbsDown className="h-4 w-4" />
                      Incorrect
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ======================================================================== */}
      {/* ALERTS TAB */}
      {/* ======================================================================== */}
      {activeTab === 'alerts' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl text-white font-semibold">Model Alerts</h2>
            <button
              onClick={fetchAlerts}
              className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-sm"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>

          <p className="text-gray-400 text-sm">
            Alerts for regime changes, high-confidence predictions, model disagreements, and prediction streaks.
          </p>

          {alerts.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <Bell className="h-12 w-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">No alerts yet</p>
              <p className="text-gray-500 text-sm">Alerts will appear when models detect important events</p>
            </div>
          ) : (
            <div className="space-y-3">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={`rounded-lg p-4 border ${getSeverityColor(alert.severity)} ${
                    alert.acknowledged ? 'opacity-60' : ''
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          alert.severity === 'CRITICAL' ? 'bg-red-500/30' :
                          alert.severity === 'WARNING' ? 'bg-yellow-500/30' :
                          'bg-blue-500/30'
                        }`}>
                          {alert.severity}
                        </span>
                        <span className="text-xs text-gray-400">{alert.alert_type}</span>
                        <span className="text-xs text-gray-500">{formatTimestamp(alert.timestamp)}</span>
                      </div>
                      <h4 className="font-semibold text-white mb-1">{alert.title}</h4>
                      <p className="text-sm text-gray-300">{alert.message}</p>
                      {alert.previous_value && alert.current_value && (
                        <div className="mt-2 text-sm">
                          <span className="text-gray-400">Changed: </span>
                          <span className={getActionColor(alert.previous_value)}>{alert.previous_value}</span>
                          <span className="text-gray-500 mx-2">→</span>
                          <span className={getActionColor(alert.current_value)}>{alert.current_value}</span>
                        </div>
                      )}
                    </div>
                    {!alert.acknowledged && (
                      <button
                        onClick={() => acknowledgeAlert(alert.id)}
                        className="flex items-center gap-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-sm ml-4"
                      >
                        <Eye className="h-4 w-4" />
                        Acknowledge
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ======================================================================== */}
      {/* PERFORMANCE TAB */}
      {/* ======================================================================== */}
      {activeTab === 'performance' && (
        <div className="space-y-6">
          <h2 className="text-xl text-white font-semibold">Model Performance (Last 7 Days)</h2>

          {performanceSummary ? (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-gray-800 rounded-lg p-4">
                  <div className="text-gray-400 text-sm mb-1">Overall Accuracy</div>
                  <div className={`text-2xl font-bold ${
                    performanceSummary.overall_accuracy >= 60 ? 'text-green-400' :
                    performanceSummary.overall_accuracy >= 50 ? 'text-yellow-400' :
                    'text-red-400'
                  }`}>
                    {performanceSummary.overall_accuracy?.toFixed(1)}%
                  </div>
                </div>
                <div className="bg-gray-800 rounded-lg p-4">
                  <div className="text-gray-400 text-sm mb-1">Total Predictions</div>
                  <div className="text-2xl font-bold text-blue-400">
                    {performanceSummary.overall_predictions}
                  </div>
                </div>
                <div className="bg-gray-800 rounded-lg p-4">
                  <div className="text-gray-400 text-sm mb-1">Best Model</div>
                  <div className="text-xl font-semibold text-green-400">
                    {performanceSummary.best_model || 'N/A'}
                  </div>
                </div>
                <div className="bg-gray-800 rounded-lg p-4">
                  <div className="text-gray-400 text-sm mb-1">Period</div>
                  <div className="text-lg text-gray-300">
                    {performanceSummary.period}
                  </div>
                </div>
              </div>

              {/* Per-Model Performance */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {performanceSummary.models?.map((model, idx) => (
                  <div key={idx} className="bg-gray-800 rounded-lg p-4">
                    <h3 className="text-white font-semibold mb-4">{model.model_name}</h3>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Accuracy</span>
                        <span className={`font-semibold ${
                          model.accuracy >= 60 ? 'text-green-400' :
                          model.accuracy >= 50 ? 'text-yellow-400' :
                          'text-red-400'
                        }`}>
                          {model.accuracy?.toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Total</span>
                        <span className="text-gray-300">{model.total_predictions}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Correct</span>
                        <span className="text-green-400">{model.correct_predictions}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Incorrect</span>
                        <span className="text-red-400">{model.incorrect_predictions}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Pending</span>
                        <span className="text-gray-500">{model.pending_predictions}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Avg Confidence</span>
                        <span className="text-blue-400">{model.avg_confidence?.toFixed(1)}%</span>
                      </div>
                      {model.total_pnl !== undefined && model.total_pnl !== 0 && (
                        <div className="flex justify-between">
                          <span className="text-gray-400">Total PnL</span>
                          <span className={model.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                            ${model.total_pnl?.toFixed(2)}
                          </span>
                        </div>
                      )}
                      {/* Accuracy Bar */}
                      <div className="mt-2">
                        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${
                              model.accuracy >= 60 ? 'bg-green-500' :
                              model.accuracy >= 50 ? 'bg-yellow-500' :
                              'bg-red-500'
                            }`}
                            style={{ width: `${Math.min(model.accuracy || 0, 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Bot Usage Stats */}
              {botUsageStats && (
                <div className="bg-gray-800 rounded-lg p-4">
                  <h3 className="text-white font-semibold mb-4">Bot Usage of Predictions</h3>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    {Object.entries(botUsageStats as Record<string, number>).map(([bot, count]) => (
                      <div key={bot} className="text-center">
                        <div className="text-2xl font-bold text-blue-400">{count as number}</div>
                        <div className="text-sm text-gray-400">{bot}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <Award className="h-12 w-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">No performance data available</p>
              <p className="text-gray-500 text-sm">Record some outcomes to see performance metrics</p>
            </div>
          )}
        </div>
      )}

      {/* ======================================================================== */}
      {/* TRAINING TAB */}
      {/* ======================================================================== */}
      {activeTab === 'training' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl text-white font-semibold">Model Training</h2>
            <button
              onClick={fetchTrainingHistory}
              className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-sm"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>

          {/* Automated Training Schedule Info */}
          <div className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 border border-purple-500/30 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-purple-500/20 rounded-lg">
                <Clock className="h-5 w-5 text-purple-400" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Automated Training Schedule</h3>
                <p className="text-gray-400 text-sm mt-1">
                  ML models are automatically retrained every <span className="text-purple-400 font-medium">Sunday at 5:00 PM CT</span> when markets are closed.
                </p>
                <div className="flex flex-wrap gap-2 mt-2">
                  <span className="px-2 py-1 bg-gray-700 rounded text-xs text-gray-300">GEX_DIRECTIONAL</span>
                </div>
              </div>
            </div>
          </div>

          {/* Training History */}
          <h3 className="text-lg text-white font-semibold">Training History</h3>

          {trainingHistory.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <GraduationCap className="h-12 w-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">No training history</p>
              <p className="text-gray-500 text-sm">Model training runs will appear here</p>
            </div>
          ) : (
            <div className="bg-gray-800 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-700">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Time</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Model</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Samples</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Before</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">After</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Status</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Duration</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-300">Triggered By</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {trainingHistory.map((run) => (
                    <tr key={run.id} className="hover:bg-gray-700/50">
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {formatTimestamp(run.timestamp)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-300">
                        {run.model_name}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-300">
                        {run.training_samples?.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {run.accuracy_before?.toFixed(1)}%
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span className={
                          run.accuracy_after > run.accuracy_before ? 'text-green-400' :
                          run.accuracy_after < run.accuracy_before ? 'text-red-400' :
                          'text-gray-300'
                        }>
                          {run.accuracy_after?.toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {run.status === 'COMPLETED' ? (
                          <span className="flex items-center gap-1 text-green-400 text-sm">
                            <Check className="h-4 w-4" />
                            Completed
                          </span>
                        ) : run.status === 'FAILED' ? (
                          <span className="flex items-center gap-1 text-red-400 text-sm">
                            <X className="h-4 w-4" />
                            Failed
                          </span>
                        ) : (
                          <span className="text-yellow-400 text-sm">{run.status}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {run.duration_seconds}s
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {run.triggered_by}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ======================================================================== */}
      {/* COMPARE TAB */}
      {/* ======================================================================== */}
      {activeTab === 'compare' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl text-white font-semibold">Model Comparison</h2>
            <button
              onClick={fetchComparison}
              className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-sm"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>

          <p className="text-gray-400 text-sm">
            Compare predictions across all models to see when they agree or disagree.
          </p>

          {modelComparison ? (
            <>
              {/* Agreement Status */}
              <div className={`rounded-lg p-6 border ${
                modelComparison.agreement
                  ? 'bg-green-900/20 border-green-500/30'
                  : 'bg-yellow-900/20 border-yellow-500/30'
              }`}>
                <div className="flex items-center gap-3 mb-2">
                  {modelComparison.agreement ? (
                    <CheckCircle className="h-8 w-8 text-green-400" />
                  ) : (
                    <AlertTriangle className="h-8 w-8 text-yellow-400" />
                  )}
                  <div>
                    <h3 className={`text-xl font-semibold ${
                      modelComparison.agreement ? 'text-green-400' : 'text-yellow-400'
                    }`}>
                      {modelComparison.agreement ? 'Models Agree' : 'Models Disagree'}
                    </h3>
                    <p className="text-gray-400 text-sm">
                      {modelComparison.agreement
                        ? `Consensus: ${modelComparison.consensus_prediction}`
                        : 'Different models are predicting different outcomes'
                      }
                    </p>
                  </div>
                </div>
              </div>

              {/* Model Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {modelComparison.models?.map((model, idx) => (
                  <div key={idx} className="bg-gray-800 rounded-lg p-4">
                    <h3 className="text-white font-semibold mb-4">{model.name}</h3>
                    <div className="space-y-3">
                      <div>
                        <div className="text-gray-400 text-sm mb-1">Current Prediction</div>
                        <div className={`flex items-center gap-2 text-xl font-bold ${getActionColor(model.prediction)}`}>
                          {getActionIcon(model.prediction)}
                          {model.prediction}
                        </div>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Confidence</span>
                        <span className="text-blue-400">{(model.confidence * 100).toFixed(1)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">7-Day Accuracy</span>
                        <span className={
                          model.accuracy_7d >= 60 ? 'text-green-400' :
                          model.accuracy_7d >= 50 ? 'text-yellow-400' :
                          'text-red-400'
                        }>
                          {model.accuracy_7d?.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="text-gray-500 text-sm">
                Last updated: {formatTimestamp(modelComparison.timestamp)}
              </div>
            </>
          ) : (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <GitCompare className="h-12 w-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">No comparison data available</p>
              <p className="text-gray-500 text-sm">Run predictions to compare model outputs</p>
            </div>
          )}
        </div>
      )}

      {/* ======================================================================== */}
      {/* STATS TAB (Legacy) */}
      {/* ======================================================================== */}
      {activeTab === 'stats' && stats && (
        <div className="space-y-6">
          <h2 className="text-xl text-white font-semibold">Prediction Statistics (Last {stats.days} days)</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg text-white mb-4">By Model</h3>
              {stats.by_type.length === 0 ? (
                <p className="text-gray-500">No data yet</p>
              ) : (
                <div className="space-y-3">
                  {stats.by_type.map((item, idx) => (
                    <div key={idx} className="flex justify-between items-center">
                      <span className="text-gray-300">{item.model}</span>
                      <div className="text-right">
                        <span className="text-blue-400 font-semibold">{item.count}</span>
                        <span className="text-gray-500 text-sm ml-2">
                          ({item.avg_confidence?.toFixed(0)}% avg)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg text-white mb-4">By Prediction</h3>
              {stats.by_value.length === 0 ? (
                <p className="text-gray-500">No data yet</p>
              ) : (
                <div className="space-y-3">
                  {stats.by_value.map((item, idx) => (
                    <div key={idx} className="flex justify-between items-center">
                      <span className={getActionColor(item.value)}>{item.value}</span>
                      <span className="text-gray-300">{item.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {stats.by_day.length > 0 && (
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg text-white mb-4">Daily Volume</h3>
              <div className="flex items-end gap-1 h-32">
                {stats.by_day.map((day, idx) => {
                  const maxCount = Math.max(...stats.by_day.map(d => d.count))
                  const height = maxCount > 0 ? (day.count / maxCount) * 100 : 0
                  return (
                    <div
                      key={idx}
                      className="flex-1 bg-blue-500/50 hover:bg-blue-500 transition-colors rounded-t"
                      style={{ height: `${height}%` }}
                      title={`${day.date}: ${day.count} predictions`}
                    />
                  )
                })}
              </div>
              <div className="flex justify-between text-xs text-gray-500 mt-2">
                <span>{stats.by_day[0]?.date}</span>
                <span>{stats.by_day[stats.by_day.length - 1]?.date}</span>
              </div>
            </div>
          )}
        </div>
      )}
        </div>
      </main>
    </>
  )
}
