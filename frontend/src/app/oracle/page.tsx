'use client'

import { useState, useEffect, useCallback } from 'react'
import { Eye, Brain, Activity, RefreshCw, Trash2, Play, CheckCircle, XCircle, AlertCircle, Sparkles, FileText, History, TrendingUp, BarChart3, Download, CloudDownload, Zap } from 'lucide-react'
import Navigation from '@/components/Navigation'
import DecisionLogViewer from '@/components/trader/DecisionLogViewer'
import { apiClient } from '@/lib/api'
import { useOracleStatus, useOracleLogs } from '@/lib/hooks/useMarketData'

interface OracleStatus {
  model_trained: boolean
  model_version: string
  claude_available: boolean
  claude_model: string
  high_confidence_threshold: number
  low_confidence_threshold: number
}

interface LogEntry {
  timestamp: string
  type: string
  message: string
  data?: any
}

interface Prediction {
  bot_name: string
  advice: string
  win_probability: number
  confidence: number
  suggested_risk_pct: number
  reasoning: string
  model_version: string
  top_factors: [string, number][]
}

interface StoredPrediction {
  id: number
  trade_date: string
  bot_name: string
  advice: string
  win_probability: number
  confidence: number
  suggested_risk_pct: number
  reasoning: string
  model_version: string
  top_factors: any
  actual_outcome: string | null
  actual_pnl: number | null
  created_at: string
}

interface OracleFormData {
  spot_price: number
  vix: number
  gex_regime: string
  day_of_week: number
  vix_1d_change: number
  normalized_gex: number
  distance_to_call_wall: number
  distance_to_put_wall: number
  bot_name: string
}

// Helper function to format timestamp in Texas Central Time
function formatTexasCentralTime(isoTimestamp: string): string {
  try {
    const date = new Date(isoTimestamp)
    return date.toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    })
  } catch {
    return isoTimestamp
  }
}

// Helper function to format full date in Texas Central Time
function formatTexasCentralDateTime(isoTimestamp: string): string {
  try {
    const date = new Date(isoTimestamp)
    return date.toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    })
  } catch {
    return isoTimestamp
  }
}

export default function OraclePage() {
  // SWR hooks for data fetching with caching
  const { data: statusRes, error: statusError, isLoading: statusLoading, isValidating: statusValidating, mutate: mutateStatus } = useOracleStatus()
  const { data: logsRes, isValidating: logsValidating, mutate: mutateLogs } = useOracleLogs()

  // Extract data from responses
  const status = statusRes?.oracle as OracleStatus | undefined
  const logs = (logsRes?.logs || []) as LogEntry[]

  const loading = statusLoading && !status
  const isRefreshing = statusValidating || logsValidating

  // Local state for UI and form
  const [analyzing, setAnalyzing] = useState(false)
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [claudeExplanation, setClaudeExplanation] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'test' | 'history' | 'decisions'>('test')
  const [storedPredictions, setStoredPredictions] = useState<StoredPrediction[]>([])
  const [historyDays, setHistoryDays] = useState(30)
  const [loadingLiveData, setLoadingLiveData] = useState(false)

  // Form state for test prediction - default empty to encourage loading live data
  const [formData, setFormData] = useState({
    spot_price: 0,
    vix: 0,
    gex_regime: 'NEUTRAL',
    day_of_week: new Date().getDay(),
    vix_1d_change: 0,
    normalized_gex: 0,
    distance_to_call_wall: 0,
    distance_to_put_wall: 0,
    bot_name: 'ARES'
  })

  // Load live market data into form
  const loadLiveMarketData = async () => {
    setLoadingLiveData(true)
    try {
      // Fetch GEX and VIX data in parallel
      const [gexRes, vixRes] = await Promise.all([
        apiClient.getGEX('SPY'),
        apiClient.getVIXCurrent()
      ])

      const gexData = gexRes.data?.data || gexRes.data
      const vixData = vixRes.data?.data || vixRes.data

      // Determine GEX regime based on net_gex
      let gexRegime = 'NEUTRAL'
      if (gexData?.net_gex > 0) {
        gexRegime = 'POSITIVE'
      } else if (gexData?.net_gex < 0) {
        gexRegime = 'NEGATIVE'
      }

      // Calculate normalized GEX (simplified - between -1 and 1)
      const normalizedGex = gexData?.net_gex
        ? Math.max(-1, Math.min(1, gexData.net_gex / 5000000000)) // Normalize to billions
        : 0

      // Calculate distance to walls if available
      const spotPrice = gexData?.spot_price || 0
      const callWall = gexData?.call_wall || gexData?.levels?.call_wall || 0
      const putWall = gexData?.put_wall || gexData?.levels?.put_wall || 0

      const distanceToCallWall = callWall && spotPrice
        ? ((callWall - spotPrice) / spotPrice) * 100
        : 0
      const distanceToPutWall = putWall && spotPrice
        ? ((spotPrice - putWall) / spotPrice) * 100
        : 0

      setFormData((prev: OracleFormData) => ({
        ...prev,
        spot_price: Math.round(spotPrice * 100) / 100 || 0,
        vix: vixData?.vix || vixData?.current_vix || 0,
        gex_regime: gexRegime,
        day_of_week: new Date().getDay(),
        vix_1d_change: vixData?.change_1d || 0,
        normalized_gex: Math.round(normalizedGex * 100) / 100,
        distance_to_call_wall: Math.round(distanceToCallWall * 10) / 10,
        distance_to_put_wall: Math.round(distanceToPutWall * 10) / 10
      }))
    } catch (err) {
      console.error('Failed to load live market data:', err)
      setError('Failed to load live market data. Please enter values manually.')
    } finally {
      setLoadingLiveData(false)
    }
  }

  // Export logs to JSON
  const exportLogsJSON = () => {
    const exportData = logs.map(log => ({
      ...log,
      timestamp_ct: formatTexasCentralDateTime(log.timestamp)
    }))
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `oracle_logs_${new Date().toISOString().split('T')[0]}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Export logs to CSV
  const exportLogsCSV = () => {
    const headers = ['Timestamp (CT)', 'Type', 'Message', 'Data']
    const rows = logs.map(log => [
      formatTexasCentralDateTime(log.timestamp),
      log.type,
      log.message,
      log.data ? JSON.stringify(log.data) : ''
    ])
    const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `oracle_logs_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const fetchStatus = useCallback(() => {
    mutateStatus()
  }, [mutateStatus])

  const fetchLogs = useCallback(() => {
    mutateLogs()
  }, [mutateLogs])

  const clearLogs = async () => {
    try {
      await apiClient.clearOracleLogs()
      mutateLogs()
    } catch (err: any) {
      console.error('Failed to clear logs:', err)
    }
  }

  const fetchPredictionHistory = useCallback(async () => {
    try {
      const response = await apiClient.getOraclePredictions({ days: historyDays, limit: 100 })
      if (response.data?.success) {
        setStoredPredictions(response.data.data?.predictions || [])
      }
    } catch (err: any) {
      console.error('Failed to fetch prediction history:', err)
    }
  }, [historyDays])

  const runAnalysis = async () => {
    setAnalyzing(true)
    setError(null)
    setPrediction(null)
    setClaudeExplanation(null)

    try {
      const response = await apiClient.oracleAnalyze(formData)
      if (response.data?.success) {
        setPrediction(response.data.prediction)
        setClaudeExplanation(response.data.claude_explanation)
        // Refresh logs after analysis
        fetchLogs()
      } else {
        setError(response.data?.error || 'Analysis failed')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to run analysis')
    } finally {
      setAnalyzing(false)
    }
  }

  // Load prediction history on mount (SWR handles status and logs)
  useEffect(() => {
    fetchPredictionHistory()
  }, [fetchPredictionHistory])

  const getAdviceColor = (advice: string) => {
    switch (advice) {
      case 'TRADE_FULL': return 'text-green-400'
      case 'TRADE_REDUCED': return 'text-yellow-400'
      case 'SKIP': return 'text-red-400'
      default: return 'text-gray-400'
    }
  }

  const getLogTypeColor = (type: string) => {
    switch (type) {
      case 'INIT': return 'bg-blue-500/20 text-blue-400'
      case 'PREDICT': return 'bg-green-500/20 text-green-400'
      case 'CLAUDE_VALIDATE': return 'bg-purple-500/20 text-purple-400'
      case 'CLAUDE_EXPLAIN': return 'bg-indigo-500/20 text-indigo-400'
      case 'ERROR': return 'bg-red-500/20 text-red-400'
      default: return 'bg-gray-500/20 text-gray-400'
    }
  }

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-2">
              <Eye className="w-8 h-8 text-purple-400" />
              <h1 className="text-3xl font-bold text-text-primary">Oracle AI</h1>
            </div>
            <p className="text-text-secondary">
              Claude-powered ML prediction validation and trade analysis for ARES, ATLAS, and PHOENIX
            </p>
          </div>

          {/* Status Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            {/* Claude Status */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-text-secondary text-sm">Claude AI</span>
                {status?.claude_available ? (
                  <CheckCircle className="w-5 h-5 text-green-400" />
                ) : (
                  <XCircle className="w-5 h-5 text-red-400" />
                )}
              </div>
              <p className={`text-lg font-semibold ${status?.claude_available ? 'text-green-400' : 'text-red-400'}`}>
                {status?.claude_available ? 'Connected' : 'Unavailable'}
              </p>
              {status?.claude_model && (
                <p className="text-text-muted text-xs mt-1">{status.claude_model}</p>
              )}
            </div>

            {/* ML Model Status */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-text-secondary text-sm">ML Model</span>
                <Brain className="w-5 h-5 text-purple-400" />
              </div>
              <p className={`text-lg font-semibold ${status?.model_trained ? 'text-green-400' : 'text-yellow-400'}`}>
                {status?.model_trained ? 'Trained' : 'Not Trained'}
              </p>
              <p className="text-text-muted text-xs mt-1">v{status?.model_version || '0.0.0'}</p>
              {!status?.model_trained && (
                <p className="text-yellow-400/70 text-xs mt-2">
                  Train from KRONOS backtests
                </p>
              )}
            </div>

            {/* High Confidence Threshold */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-text-secondary text-sm">High Confidence</span>
                <Activity className="w-5 h-5 text-green-400" />
              </div>
              <p className="text-lg font-semibold text-text-primary">
                {((status?.high_confidence_threshold || 0.7) * 100).toFixed(0)}%
              </p>
              <p className="text-text-muted text-xs mt-1">Full trade threshold</p>
            </div>

            {/* Low Confidence Threshold */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-text-secondary text-sm">Low Confidence</span>
                <AlertCircle className="w-5 h-5 text-yellow-400" />
              </div>
              <p className="text-lg font-semibold text-text-primary">
                {((status?.low_confidence_threshold || 0.55) * 100).toFixed(0)}%
              </p>
              <p className="text-text-muted text-xs mt-1">Skip trade threshold</p>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-6">
            <button
              onClick={() => setActiveTab('test')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'test' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <Play className="w-4 h-4" />
              Test Prediction
            </button>
            <button
              onClick={() => setActiveTab('history')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'history' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <History className="w-4 h-4" />
              Prediction History ({storedPredictions.length})
            </button>
            <button
              onClick={() => setActiveTab('decisions')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'decisions' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <FileText className="w-4 h-4" />
              Decision Log
            </button>
          </div>

          {/* Test Tab */}
          {activeTab === 'test' && (
          <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Test Prediction Form */}
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-purple-400" />
                  Test Oracle Prediction
                </h2>
                <button
                  onClick={loadLiveMarketData}
                  disabled={loadingLiveData}
                  className="btn-secondary text-sm flex items-center gap-2"
                  title="Load current market data from GEX and VIX APIs"
                >
                  {loadingLiveData ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      Load Live Data
                    </>
                  )}
                </button>
              </div>

              {formData.spot_price === 0 && (
                <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-400 text-sm">
                  Click "Load Live Data" to populate form with current market data, or enter values manually.
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <label className="block text-text-secondary text-sm mb-1">Spot Price</label>
                  <input
                    type="number"
                    value={formData.spot_price}
                    onChange={(e) => setFormData({ ...formData, spot_price: Number(e.target.value) })}
                    className="input w-full"
                  />
                </div>
                <div>
                  <label className="block text-text-secondary text-sm mb-1">VIX</label>
                  <input
                    type="number"
                    value={formData.vix}
                    onChange={(e) => setFormData({ ...formData, vix: Number(e.target.value) })}
                    className="input w-full"
                  />
                </div>
                <div>
                  <label className="block text-text-secondary text-sm mb-1">GEX Regime</label>
                  <select
                    value={formData.gex_regime}
                    onChange={(e) => setFormData({ ...formData, gex_regime: e.target.value })}
                    className="input w-full"
                  >
                    <option value="POSITIVE">POSITIVE</option>
                    <option value="NEGATIVE">NEGATIVE</option>
                    <option value="NEUTRAL">NEUTRAL</option>
                  </select>
                </div>
                <div>
                  <label className="block text-text-secondary text-sm mb-1">Day of Week</label>
                  <select
                    value={formData.day_of_week}
                    onChange={(e) => setFormData({ ...formData, day_of_week: Number(e.target.value) })}
                    className="input w-full"
                  >
                    <option value={0}>Sunday</option>
                    <option value={1}>Monday</option>
                    <option value={2}>Tuesday</option>
                    <option value={3}>Wednesday</option>
                    <option value={4}>Thursday</option>
                    <option value={5}>Friday</option>
                    <option value={6}>Saturday</option>
                  </select>
                </div>
                <div>
                  <label className="block text-text-secondary text-sm mb-1">VIX 1D Change</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.vix_1d_change}
                    onChange={(e) => setFormData({ ...formData, vix_1d_change: Number(e.target.value) })}
                    className="input w-full"
                  />
                </div>
                <div>
                  <label className="block text-text-secondary text-sm mb-1">Normalized GEX</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.normalized_gex}
                    onChange={(e) => setFormData({ ...formData, normalized_gex: Number(e.target.value) })}
                    className="input w-full"
                  />
                </div>
              </div>

              {/* Bot Selector */}
              <div className="mb-6">
                <label className="block text-text-secondary text-sm mb-2">Select Bot Strategy</label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, bot_name: 'ARES' })}
                    className={`p-3 rounded-lg border transition-colors ${
                      formData.bot_name === 'ARES'
                        ? 'border-red-500 bg-red-500/20 text-red-400'
                        : 'border-border bg-background-hover text-text-secondary hover:border-red-500/50'
                    }`}
                  >
                    <div className="font-semibold">ARES</div>
                    <div className="text-xs opacity-70">Iron Condor</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, bot_name: 'ATLAS' })}
                    className={`p-3 rounded-lg border transition-colors ${
                      formData.bot_name === 'ATLAS'
                        ? 'border-blue-500 bg-blue-500/20 text-blue-400'
                        : 'border-border bg-background-hover text-text-secondary hover:border-blue-500/50'
                    }`}
                  >
                    <div className="font-semibold">ATLAS</div>
                    <div className="text-xs opacity-70">Wheel Strategy</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, bot_name: 'PHOENIX' })}
                    className={`p-3 rounded-lg border transition-colors ${
                      formData.bot_name === 'PHOENIX'
                        ? 'border-orange-500 bg-orange-500/20 text-orange-400'
                        : 'border-border bg-background-hover text-text-secondary hover:border-orange-500/50'
                    }`}
                  >
                    <div className="font-semibold">PHOENIX</div>
                    <div className="text-xs opacity-70">Directional Calls</div>
                  </button>
                </div>
              </div>

              <button
                onClick={runAnalysis}
                disabled={analyzing || !status?.claude_available || formData.spot_price === 0}
                className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {analyzing ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    Run Oracle Analysis
                  </>
                )}
              </button>

              {error && (
                <div className="mt-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400 text-sm">
                  {error}
                </div>
              )}
            </div>

            {/* Live Logs */}
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <Activity className="w-5 h-5 text-blue-400" />
                  Live Logs
                </h2>
                <div className="flex gap-2">
                  <button
                    onClick={exportLogsJSON}
                    className="p-2 rounded-lg bg-background-hover hover:bg-background-deep transition-colors"
                    title="Export logs as JSON"
                    disabled={logs.length === 0}
                  >
                    <Download className="w-4 h-4 text-text-secondary" />
                  </button>
                  <button
                    onClick={exportLogsCSV}
                    className="p-2 rounded-lg bg-background-hover hover:bg-background-deep transition-colors"
                    title="Export logs as CSV"
                    disabled={logs.length === 0}
                  >
                    <FileText className="w-4 h-4 text-text-secondary" />
                  </button>
                  <button
                    onClick={fetchLogs}
                    className="p-2 rounded-lg bg-background-hover hover:bg-background-deep transition-colors"
                    title="Refresh logs"
                  >
                    <RefreshCw className="w-4 h-4 text-text-secondary" />
                  </button>
                  <button
                    onClick={clearLogs}
                    className="p-2 rounded-lg bg-background-hover hover:bg-red-500/20 transition-colors"
                    title="Clear logs"
                  >
                    <Trash2 className="w-4 h-4 text-text-secondary hover:text-red-400" />
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between mb-2">
                <span className="text-text-muted text-xs">Timestamps in Texas Central Time (CT)</span>
                <span className="text-text-muted text-xs">{logs.length} entries</span>
              </div>
              <div className="h-80 overflow-y-auto space-y-2 bg-background-deep rounded-lg p-3">
                {logs.length === 0 ? (
                  <p className="text-text-muted text-sm text-center py-4">No logs yet. Run an analysis to see Oracle activity.</p>
                ) : (
                  logs.slice().reverse().map((log, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs">
                      <span className="text-text-muted whitespace-nowrap" title="Texas Central Time">
                        {formatTexasCentralTime(log.timestamp)}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${getLogTypeColor(log.type)}`}>
                        {log.type}
                      </span>
                      <span className="text-text-secondary flex-1">{log.message}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Prediction Results */}
          {prediction && (
            <div className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Prediction Summary */}
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Prediction Result</h2>

                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                    <span className="text-text-secondary">Advice</span>
                    <span className={`font-bold text-lg ${getAdviceColor(prediction.advice)}`}>
                      {prediction.advice}
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                    <span className="text-text-secondary">Win Probability</span>
                    <span className="font-bold text-lg text-text-primary">
                      {(prediction.win_probability * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                    <span className="text-text-secondary">Confidence</span>
                    <span className="font-bold text-lg text-text-primary">
                      {prediction.confidence.toFixed(1)}%
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                    <span className="text-text-secondary">Suggested Risk</span>
                    <span className="font-bold text-lg text-text-primary">
                      {prediction.suggested_risk_pct}%
                    </span>
                  </div>

                  {prediction.top_factors && prediction.top_factors.length > 0 && (
                    <div className="p-3 bg-background-hover rounded-lg">
                      <span className="text-text-secondary text-sm block mb-2">Top Factors</span>
                      <div className="space-y-1">
                        {prediction.top_factors.map(([factor, weight], idx) => (
                          <div key={idx} className="flex items-center justify-between text-sm">
                            <span className="text-text-primary">{factor}</span>
                            <span className="text-purple-400">{(weight * 100).toFixed(0)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="p-3 bg-background-hover rounded-lg">
                    <span className="text-text-secondary text-sm block mb-2">ML Reasoning</span>
                    <p className="text-text-primary text-sm">{prediction.reasoning}</p>
                  </div>
                </div>
              </div>

              {/* Claude Explanation */}
              {claudeExplanation && (
                <div className="card">
                  <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-purple-400" />
                    Claude AI Explanation
                  </h2>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <div
                      className="text-text-secondary whitespace-pre-wrap"
                      dangerouslySetInnerHTML={{
                        __html: claudeExplanation
                          .replace(/^# (.*$)/gm, '<h3 class="text-lg font-bold text-text-primary mt-4 mb-2">$1</h3>')
                          .replace(/^\*\*(.*?)\*\*/gm, '<strong class="text-text-primary">$1</strong>')
                          .replace(/\*\*(.*?)\*\*/g, '<strong class="text-text-primary">$1</strong>')
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
          </>
          )}

          {/* Info Section - always visible */}
          <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="card bg-purple-500/5 border border-purple-500/20">
              <div className="flex items-start gap-3">
                <Brain className="w-5 h-5 text-purple-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">ML Predictions</h3>
                  <p className="text-text-secondary text-sm">
                    Machine learning model trained on KRONOS backtest data to predict Iron Condor outcomes
                  </p>
                </div>
              </div>
            </div>

            <div className="card bg-blue-500/5 border border-blue-500/20">
              <div className="flex items-start gap-3">
                <Eye className="w-5 h-5 text-blue-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">Claude Validation</h3>
                  <p className="text-text-secondary text-sm">
                    Claude Haiku 4.5 validates predictions and adjusts confidence based on market context
                  </p>
                </div>
              </div>
            </div>

            <div className="card bg-green-500/5 border border-green-500/20">
              <div className="flex items-start gap-3">
                <Sparkles className="w-5 h-5 text-green-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">Natural Language</h3>
                  <p className="text-text-secondary text-sm">
                    Get trader-friendly explanations of why Oracle recommends specific actions
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* History Tab */}
          {activeTab === 'history' && (
            <div className="space-y-6">
              {/* Time Filter */}
              <div className="flex items-center gap-4">
                <select
                  value={historyDays}
                  onChange={(e) => setHistoryDays(Number(e.target.value))}
                  className="input"
                >
                  <option value={7}>Last 7 Days</option>
                  <option value={30}>Last 30 Days</option>
                  <option value={90}>Last 90 Days</option>
                </select>
                <button
                  onClick={fetchPredictionHistory}
                  className="btn-secondary flex items-center gap-2"
                >
                  <RefreshCw className="w-4 h-4" />
                  Refresh
                </button>
              </div>

              {/* Prediction History Table */}
              <div className="card overflow-hidden">
                <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                  <History className="w-5 h-5 text-purple-400" />
                  Stored Predictions
                </h3>
                {storedPredictions.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-background-deep">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Date</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Bot</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Advice</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Win Prob</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Confidence</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Outcome</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">P&L</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Reasoning</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {storedPredictions.map((pred) => (
                          <tr key={pred.id} className="hover:bg-background-hover">
                            <td className="px-4 py-3 text-sm text-text-secondary">
                              {new Date(pred.trade_date).toLocaleDateString()}
                            </td>
                            <td className="px-4 py-3">
                              <span className="px-2 py-1 rounded text-xs font-medium bg-purple-500/20 text-purple-300">
                                {pred.bot_name}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span className={`font-semibold ${getAdviceColor(pred.advice)}`}>
                                {pred.advice}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-sm text-text-primary">
                              {pred.win_probability ? `${(pred.win_probability * 100).toFixed(1)}%` : '-'}
                            </td>
                            <td className="px-4 py-3 text-sm text-text-primary">
                              {pred.confidence ? `${pred.confidence.toFixed(1)}%` : '-'}
                            </td>
                            <td className="px-4 py-3">
                              {pred.actual_outcome ? (
                                <span className={`px-2 py-1 rounded text-xs font-medium ${
                                  pred.actual_outcome.includes('MAX_PROFIT') || pred.actual_outcome === 'WIN'
                                    ? 'bg-green-500/20 text-green-300'
                                    : 'bg-red-500/20 text-red-300'
                                }`}>
                                  {pred.actual_outcome}
                                </span>
                              ) : (
                                <span className="text-text-muted text-sm">Pending</span>
                              )}
                            </td>
                            <td className={`px-4 py-3 text-sm font-medium ${
                              pred.actual_pnl != null
                                ? pred.actual_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                                : 'text-text-muted'
                            }`}>
                              {pred.actual_pnl != null ? `$${pred.actual_pnl.toFixed(2)}` : '-'}
                            </td>
                            <td className="px-4 py-3 text-sm text-text-secondary max-w-xs truncate">
                              {pred.reasoning || '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-text-muted text-center py-8">
                    No predictions stored yet. Run predictions through the bots to see history here.
                  </p>
                )}
              </div>

              {/* Stats Summary */}
              {storedPredictions.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="card">
                    <p className="text-text-secondary text-sm mb-1">Total Predictions</p>
                    <p className="text-2xl font-bold text-text-primary">{storedPredictions.length}</p>
                  </div>
                  <div className="card">
                    <p className="text-text-secondary text-sm mb-1">With Outcomes</p>
                    <p className="text-2xl font-bold text-text-primary">
                      {storedPredictions.filter(p => p.actual_outcome).length}
                    </p>
                  </div>
                  <div className="card">
                    <p className="text-text-secondary text-sm mb-1">Correct Predictions</p>
                    <p className="text-2xl font-bold text-green-400">
                      {storedPredictions.filter(p =>
                        p.actual_outcome && (p.actual_outcome.includes('MAX_PROFIT') || p.actual_outcome === 'WIN')
                      ).length}
                    </p>
                  </div>
                  <div className="card">
                    <p className="text-text-secondary text-sm mb-1">Total P&L</p>
                    <p className={`text-2xl font-bold ${
                      storedPredictions.reduce((sum, p) => sum + (p.actual_pnl || 0), 0) >= 0
                        ? 'text-green-400' : 'text-red-400'
                    }`}>
                      ${storedPredictions.reduce((sum, p) => sum + (p.actual_pnl || 0), 0).toFixed(2)}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Decisions Tab */}
          {activeTab === 'decisions' && (
            <div className="card">
              <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                <FileText className="w-5 h-5 text-green-500" />
                ORACLE Decision Log
              </h3>
              <DecisionLogViewer defaultBot="ORACLE" />
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
