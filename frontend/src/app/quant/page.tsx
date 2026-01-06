'use client'

import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '@/lib/api'
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
  BarChart3,
  Clock,
  AlertTriangle
} from 'lucide-react'

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
}

interface QuantStats {
  days: number
  by_type: { model: string; count: number; avg_confidence: number }[]
  by_day: { date: string; count: number }[]
  by_value: { value: string; count: number }[]
}

export default function QuantPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'predictions' | 'logs' | 'stats'>('overview')
  const [status, setStatus] = useState<QuantStatus | null>(null)
  const [logs, setLogs] = useState<PredictionLog[]>([])
  const [stats, setStats] = useState<QuantStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Prediction state
  const [predicting, setPredicting] = useState(false)
  const [regimePrediction, setRegimePrediction] = useState<Record<string, unknown> | null>(null)
  const [directionalPrediction, setDirectionalPrediction] = useState<Record<string, unknown> | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/quant/status')
      setStatus(res.data)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch Quant status:', err)
      setError('Failed to load Quant status')
    }
  }, [])

  const fetchLogs = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/quant/logs', { params: { limit: 50 } })
      setLogs(res.data?.logs || [])
    } catch (err) {
      console.error('Failed to fetch logs:', err)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/quant/logs/stats', { params: { days: 7 } })
      setStats(res.data)
    } catch (err) {
      console.error('Failed to fetch stats:', err)
    }
  }, [])

  const runPredictions = useCallback(async () => {
    setPredicting(true)
    try {
      // Get current market data
      const gexRes = await apiClient.getGEX('SPY').catch(() => null)
      const vixRes = await apiClient.getVIXCurrent().catch(() => null)

      const spotPrice = gexRes?.data?.data?.spot_price || 585
      const vix = vixRes?.data?.data?.vix_spot || 15
      const netGex = gexRes?.data?.data?.net_gex || 0
      const flipPoint = gexRes?.data?.data?.flip_point || spotPrice
      const callWall = gexRes?.data?.data?.call_wall || spotPrice + 5
      const putWall = gexRes?.data?.data?.put_wall || spotPrice - 5

      // Run regime prediction
      const regimeRes = await apiClient.post('/api/quant/predict/regime', {
        spot_price: spotPrice,
        vix: vix,
        net_gex: netGex,
        flip_point: flipPoint,
        iv_rank: 50
      }).catch(() => null)

      if (regimeRes?.data) {
        setRegimePrediction(regimeRes.data)
      }

      // Run directional prediction
      const dirRes = await apiClient.post('/api/quant/predict/direction', {
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

      // Refresh logs after predictions
      await fetchLogs()
    } catch (err) {
      console.error('Prediction failed:', err)
    } finally {
      setPredicting(false)
    }
  }, [fetchLogs])

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await Promise.all([fetchStatus(), fetchLogs(), fetchStats()])
      setLoading(false)
    }
    loadData()

    // Auto-refresh every 30 seconds
    const interval = setInterval(() => {
      fetchStatus()
      if (activeTab === 'logs') fetchLogs()
      if (activeTab === 'stats') fetchStats()
    }, 30000)

    return () => clearInterval(interval)
  }, [fetchStatus, fetchLogs, fetchStats, activeTab])

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

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 p-6 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 text-blue-400 animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading Quant ML Models...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-900 p-6">
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
      <div className="flex gap-2 mb-6 border-b border-gray-700 pb-2">
        {[
          { id: 'overview', label: 'Overview', icon: Brain },
          { id: 'predictions', label: 'Live Predictions', icon: Zap },
          { id: 'logs', label: 'Prediction Logs', icon: Clock },
          { id: 'stats', label: 'Statistics', icon: BarChart3 },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`flex items-center gap-2 px-4 py-2 rounded-t-lg transition-colors ${
              activeTab === tab.id
                ? 'bg-gray-800 text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && status && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
              <div className="text-gray-400 text-sm mb-1">Last Updated</div>
              <div className="text-lg text-gray-300">
                {new Date(status.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </div>

          {/* Models Grid */}
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

      {/* Predictions Tab */}
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
            {/* Regime Classifier */}
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
                  {regimePrediction.probabilities && (
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

            {/* Directional ML */}
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

      {/* Logs Tab */}
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
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-gray-700/50">
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {new Date(log.timestamp).toLocaleString()}
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Stats Tab */}
      {activeTab === 'stats' && stats && (
        <div className="space-y-6">
          <h2 className="text-xl text-white font-semibold">Prediction Statistics (Last {stats.days} days)</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* By Model Type */}
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

            {/* By Predicted Value */}
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

          {/* By Day */}
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
  )
}
