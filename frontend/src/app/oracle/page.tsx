'use client'

import { useState, useEffect, useCallback } from 'react'
import { Eye, Brain, Activity, RefreshCw, Trash2, Play, CheckCircle, XCircle, AlertCircle, Sparkles, FileText } from 'lucide-react'
import Navigation from '@/components/Navigation'
import DecisionLogViewer from '@/components/trader/DecisionLogViewer'
import { apiClient } from '@/lib/api'

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

export default function OraclePage() {
  const [status, setStatus] = useState<OracleStatus | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [claudeExplanation, setClaudeExplanation] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Form state for test prediction
  const [formData, setFormData] = useState({
    spot_price: 5900,
    vix: 18,
    gex_regime: 'POSITIVE',
    day_of_week: new Date().getDay(),
    vix_1d_change: 0,
    normalized_gex: 0.5,
    distance_to_call_wall: 50,
    distance_to_put_wall: 50
  })

  const fetchStatus = useCallback(async () => {
    try {
      const response = await apiClient.getOracleStatus()
      if (response.data?.success) {
        setStatus(response.data.oracle)
      }
    } catch (err: any) {
      console.error('Failed to fetch Oracle status:', err)
    }
  }, [])

  const fetchLogs = useCallback(async () => {
    try {
      const response = await apiClient.getOracleLogs()
      if (response.data?.success) {
        setLogs(response.data.logs || [])
      }
    } catch (err: any) {
      console.error('Failed to fetch Oracle logs:', err)
    }
  }, [])

  const clearLogs = async () => {
    try {
      await apiClient.clearOracleLogs()
      setLogs([])
    } catch (err: any) {
      console.error('Failed to clear logs:', err)
    }
  }

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

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await Promise.all([fetchStatus(), fetchLogs()])
      setLoading(false)
    }
    loadData()

    // Auto-refresh logs every 5 seconds
    const interval = setInterval(fetchLogs, 5000)
    return () => clearInterval(interval)
  }, [fetchStatus, fetchLogs])

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

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Test Prediction Form */}
            <div className="card">
              <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-purple-400" />
                Test Oracle Prediction
              </h2>

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

              <button
                onClick={runAnalysis}
                disabled={analyzing || !status?.claude_available}
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

              <div className="h-80 overflow-y-auto space-y-2 bg-background-deep rounded-lg p-3">
                {logs.length === 0 ? (
                  <p className="text-text-muted text-sm text-center py-4">No logs yet</p>
                ) : (
                  logs.slice().reverse().map((log, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs">
                      <span className="text-text-muted whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleTimeString()}
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

          {/* Info Section */}
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
        </div>

        {/* ORACLE Decision Log */}
        <div className="card mt-6">
          <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
            <FileText className="w-5 h-5 text-green-500" />
            ORACLE Decision Log
          </h3>
          <DecisionLogViewer defaultBot="ORACLE" />
        </div>
      </main>
    </div>
  )
}
