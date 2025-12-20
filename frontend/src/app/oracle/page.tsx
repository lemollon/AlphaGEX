'use client'

import { useState, useEffect, useCallback } from 'react'
import { Eye, Brain, Activity, RefreshCw, Trash2, CheckCircle, XCircle, AlertCircle, Sparkles, FileText, History, TrendingUp, BarChart3, Download, Zap, Bot, MessageSquare, Settings, Play, Clock, Target, ChevronDown, ChevronUp } from 'lucide-react'
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

interface TrainingStatus {
  model_trained: boolean
  model_version: string
  pending_outcomes: number
  total_outcomes: number
  last_trained: string | null
  threshold_for_retrain: number
  needs_training: boolean
  training_metrics: any
  claude_available: boolean
  model_source: 'database' | 'local_file' | 'none'
  db_persistence: boolean
  persistence_status: string
}

interface LogEntry {
  timestamp: string
  type: string
  message: string
  data?: any
}

interface BotInteraction {
  source: string
  id: number
  trade_date: string
  bot_name: string
  timestamp: string
  action: string
  win_probability?: number
  confidence?: number
  reasoning?: string
  spot_price?: number
  vix?: number
  gex_regime?: string
  claude_analysis?: any
  actual_outcome?: string
  actual_pnl?: number
}

interface PerformanceData {
  total_predictions: number
  days: number
  overall: {
    wins: number
    losses: number
    win_rate: number
    avg_predicted_win_prob: number
    calibration_error: number
    total_pnl: number
  }
  by_bot: Record<string, {
    total: number
    wins: number
    pnl: number
    win_rate: number
    avg_predicted_prob: number
  }>
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

// Expandable Claude Analysis Component
function ClaudeAnalysisPanel({ analysis }: { analysis: any }) {
  const [expanded, setExpanded] = useState(false)

  if (!analysis) return null

  return (
    <div className="mt-3 border border-purple-500/30 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-2 bg-purple-500/10 flex items-center justify-between text-sm"
      >
        <span className="flex items-center gap-2 text-purple-300">
          <Sparkles className="w-4 h-4" />
          Claude AI Analysis
        </span>
        {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>
      {expanded && (
        <div className="p-4 space-y-3 text-sm">
          {analysis.recommendation && (
            <div>
              <span className="text-text-muted">Recommendation:</span>
              <p className="text-text-primary">{analysis.recommendation}</p>
            </div>
          )}
          {analysis.confidence_adjustment !== undefined && (
            <div>
              <span className="text-text-muted">Confidence Adjustment:</span>
              <span className={`ml-2 font-medium ${analysis.confidence_adjustment >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {analysis.confidence_adjustment > 0 ? '+' : ''}{(analysis.confidence_adjustment * 100).toFixed(1)}%
              </span>
            </div>
          )}
          {analysis.risk_factors && analysis.risk_factors.length > 0 && (
            <div>
              <span className="text-text-muted">Risk Factors:</span>
              <ul className="mt-1 space-y-1">
                {analysis.risk_factors.map((risk: string, idx: number) => (
                  <li key={idx} className="text-red-300 flex items-start gap-2">
                    <AlertCircle className="w-3 h-3 mt-1 flex-shrink-0" />
                    {risk}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {analysis.opportunities && analysis.opportunities.length > 0 && (
            <div>
              <span className="text-text-muted">Opportunities:</span>
              <ul className="mt-1 space-y-1">
                {analysis.opportunities.map((opp: string, idx: number) => (
                  <li key={idx} className="text-green-300 flex items-start gap-2">
                    <CheckCircle className="w-3 h-3 mt-1 flex-shrink-0" />
                    {opp}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {analysis.analysis && (
            <div>
              <span className="text-text-muted">Full Analysis:</span>
              <p className="text-text-secondary mt-1 whitespace-pre-wrap">{analysis.analysis}</p>
            </div>
          )}
          {analysis.tokens_used && (
            <div className="text-text-muted text-xs border-t border-border pt-2 mt-2">
              Tokens: {analysis.input_tokens} in / {analysis.output_tokens} out |
              Response: {analysis.response_time_ms}ms |
              Model: {analysis.model_used}
            </div>
          )}
        </div>
      )}
    </div>
  )
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

  // Local state
  const [activeTab, setActiveTab] = useState<'interactions' | 'performance' | 'training' | 'logs' | 'decisions'>('interactions')
  const [botInteractions, setBotInteractions] = useState<BotInteraction[]>([])
  const [trainingStatus, setTrainingStatus] = useState<TrainingStatus | null>(null)
  const [performance, setPerformance] = useState<PerformanceData | null>(null)
  const [selectedBot, setSelectedBot] = useState<string>('ALL')
  const [interactionDays, setInteractionDays] = useState(7)
  const [loadingInteractions, setLoadingInteractions] = useState(false)
  const [loadingTraining, setLoadingTraining] = useState(false)
  const [triggeringTraining, setTriggeringTraining] = useState(false)
  const [trainingResult, setTrainingResult] = useState<any>(null)

  // Fetch bot interactions
  const fetchBotInteractions = useCallback(async () => {
    setLoadingInteractions(true)
    try {
      const botParam = selectedBot === 'ALL' ? undefined : selectedBot
      const response = await apiClient.getOracleBotInteractions({
        days: interactionDays,
        limit: 200,
        bot_name: botParam
      })
      if (response.data?.success) {
        setBotInteractions(response.data.interactions || [])
      }
    } catch (err) {
      console.error('Failed to fetch interactions:', err)
    } finally {
      setLoadingInteractions(false)
    }
  }, [interactionDays, selectedBot])

  // Fetch training status
  const fetchTrainingStatus = useCallback(async () => {
    setLoadingTraining(true)
    try {
      const response = await apiClient.getOracleTrainingStatus()
      if (response.data?.success) {
        setTrainingStatus(response.data)
      }
    } catch (err) {
      console.error('Failed to fetch training status:', err)
    } finally {
      setLoadingTraining(false)
    }
  }, [])

  // Fetch performance data
  const fetchPerformance = useCallback(async () => {
    try {
      const response = await apiClient.getOraclePerformance(90)
      if (response.data?.success) {
        setPerformance(response.data)
      }
    } catch (err) {
      console.error('Failed to fetch performance:', err)
    }
  }, [])

  // Trigger training
  const triggerTraining = async (force: boolean = false) => {
    setTriggeringTraining(true)
    setTrainingResult(null)
    try {
      const response = await apiClient.triggerOracleTraining(force)
      setTrainingResult(response.data)
      if (response.data?.success) {
        fetchTrainingStatus()
        mutateStatus()
      }
    } catch (err: any) {
      setTrainingResult({ success: false, error: err.message })
    } finally {
      setTriggeringTraining(false)
    }
  }

  // Export interactions to JSON
  const exportInteractionsJSON = () => {
    const exportData = botInteractions.map(i => ({
      ...i,
      timestamp_ct: formatTexasCentralDateTime(i.timestamp || i.trade_date)
    }))
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `oracle_interactions_${new Date().toISOString().split('T')[0]}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Export interactions to CSV
  const exportInteractionsCSV = () => {
    const headers = ['Timestamp (CT)', 'Bot', 'Action', 'Win Prob', 'Confidence', 'VIX', 'GEX Regime', 'Outcome', 'P&L', 'Reasoning']
    const rows = botInteractions.map(i => [
      formatTexasCentralDateTime(i.timestamp || i.trade_date),
      i.bot_name,
      i.action,
      i.win_probability ? `${(i.win_probability * 100).toFixed(1)}%` : '',
      i.confidence ? `${i.confidence.toFixed(1)}%` : '',
      i.vix || '',
      i.gex_regime || '',
      i.actual_outcome || 'Pending',
      i.actual_pnl !== undefined ? `$${i.actual_pnl.toFixed(2)}` : '',
      i.reasoning || ''
    ])
    const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `oracle_interactions_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Export logs
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

  const clearLogs = async () => {
    try {
      await apiClient.clearOracleLogs()
      mutateLogs()
    } catch (err: any) {
      console.error('Failed to clear logs:', err)
    }
  }

  // Load data on mount and tab change
  useEffect(() => {
    if (activeTab === 'interactions') fetchBotInteractions()
    if (activeTab === 'training') fetchTrainingStatus()
    if (activeTab === 'performance') fetchPerformance()
  }, [activeTab, fetchBotInteractions, fetchTrainingStatus, fetchPerformance])

  const getAdviceColor = (advice: string) => {
    switch (advice) {
      case 'TRADE_FULL': return 'text-green-400 bg-green-500/20'
      case 'TRADE_REDUCED': return 'text-yellow-400 bg-yellow-500/20'
      case 'SKIP': case 'SKIP_TODAY': return 'text-red-400 bg-red-500/20'
      default: return 'text-gray-400 bg-gray-500/20'
    }
  }

  const getBotColor = (bot: string) => {
    switch (bot) {
      case 'ARES': return 'text-red-400 bg-red-500/20 border-red-500/30'
      case 'ATLAS': return 'text-blue-400 bg-blue-500/20 border-blue-500/30'
      case 'PHOENIX': return 'text-orange-400 bg-orange-500/20 border-orange-500/30'
      case 'ATHENA': return 'text-purple-400 bg-purple-500/20 border-purple-500/30'
      case 'ORACLE': return 'text-indigo-400 bg-indigo-500/20 border-indigo-500/30'
      default: return 'text-gray-400 bg-gray-500/20 border-gray-500/30'
    }
  }

  const getLogTypeColor = (type: string) => {
    switch (type) {
      case 'INIT': return 'bg-blue-500/20 text-blue-400'
      case 'PREDICT': return 'bg-green-500/20 text-green-400'
      case 'CLAUDE_VALIDATE': return 'bg-purple-500/20 text-purple-400'
      case 'CLAUDE_EXPLAIN': return 'bg-indigo-500/20 text-indigo-400'
      case 'TRAIN_START': case 'TRAIN_DONE': return 'bg-yellow-500/20 text-yellow-400'
      case 'AUTO_TRAIN_CHECK': case 'AUTO_TRAIN_START': case 'AUTO_TRAIN_SUCCESS': return 'bg-cyan-500/20 text-cyan-400'
      case 'ERROR': case 'TRAIN_ERROR': case 'AUTO_TRAIN_FAIL': return 'bg-red-500/20 text-red-400'
      case 'OUTCOME': return 'bg-emerald-500/20 text-emerald-400'
      default: return 'bg-gray-500/20 text-gray-400'
    }
  }

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-24 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-2">
              <Eye className="w-8 h-8 text-purple-400" />
              <h1 className="text-3xl font-bold text-text-primary">Oracle Knowledge Base</h1>
            </div>
            <p className="text-text-secondary">
              Centralized intelligence hub for ARES, ATLAS, PHOENIX, and ATHENA - All bot interactions, Claude AI reasoning, and ML predictions
            </p>
          </div>

          {/* Status Cards */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
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

            {/* Pending Outcomes */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-text-secondary text-sm">Pending Outcomes</span>
                <Clock className="w-5 h-5 text-blue-400" />
              </div>
              <p className="text-lg font-semibold text-text-primary">
                {trainingStatus?.pending_outcomes ?? '-'}
              </p>
              <p className="text-text-muted text-xs mt-1">of {trainingStatus?.threshold_for_retrain ?? 100} for retrain</p>
            </div>

            {/* High Confidence Threshold */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-text-secondary text-sm">High Confidence</span>
                <Target className="w-5 h-5 text-green-400" />
              </div>
              <p className="text-lg font-semibold text-text-primary">
                {((status?.high_confidence_threshold || 0.7) * 100).toFixed(0)}%
              </p>
              <p className="text-text-muted text-xs mt-1">Full trade threshold</p>
            </div>

            {/* Total Interactions */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-text-secondary text-sm">Interactions</span>
                <MessageSquare className="w-5 h-5 text-indigo-400" />
              </div>
              <p className="text-lg font-semibold text-text-primary">
                {botInteractions.length}
              </p>
              <p className="text-text-muted text-xs mt-1">Last {interactionDays} days</p>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex flex-wrap gap-2 mb-6">
            <button
              onClick={() => setActiveTab('interactions')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'interactions' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <Bot className="w-4 h-4" />
              Bot Interactions
            </button>
            <button
              onClick={() => setActiveTab('performance')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'performance' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              Performance
            </button>
            <button
              onClick={() => setActiveTab('training')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'training' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <Settings className="w-4 h-4" />
              Training
            </button>
            <button
              onClick={() => setActiveTab('logs')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'logs' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <Activity className="w-4 h-4" />
              Live Logs ({logs.length})
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

          {/* Bot Interactions Tab */}
          {activeTab === 'interactions' && (
            <div className="space-y-6">
              {/* Filters */}
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-text-secondary text-sm">Bot:</span>
                  <select
                    value={selectedBot}
                    onChange={(e) => setSelectedBot(e.target.value)}
                    className="input"
                  >
                    <option value="ALL">All Bots</option>
                    <option value="ARES">ARES</option>
                    <option value="ATLAS">ATLAS</option>
                    <option value="PHOENIX">PHOENIX</option>
                    <option value="ATHENA">ATHENA</option>
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-text-secondary text-sm">Days:</span>
                  <select
                    value={interactionDays}
                    onChange={(e) => setInteractionDays(Number(e.target.value))}
                    className="input"
                  >
                    <option value={1}>Last 24 Hours</option>
                    <option value={7}>Last 7 Days</option>
                    <option value={30}>Last 30 Days</option>
                    <option value={90}>Last 90 Days</option>
                  </select>
                </div>
                <button
                  onClick={fetchBotInteractions}
                  disabled={loadingInteractions}
                  className="btn-secondary flex items-center gap-2"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingInteractions ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
                <div className="flex-1" />
                <button
                  onClick={exportInteractionsJSON}
                  disabled={botInteractions.length === 0}
                  className="btn-secondary flex items-center gap-2"
                  title="Export as JSON"
                >
                  <Download className="w-4 h-4" />
                  JSON
                </button>
                <button
                  onClick={exportInteractionsCSV}
                  disabled={botInteractions.length === 0}
                  className="btn-secondary flex items-center gap-2"
                  title="Export as CSV"
                >
                  <FileText className="w-4 h-4" />
                  CSV
                </button>
              </div>

              {/* Interactions List */}
              <div className="space-y-4">
                {loadingInteractions ? (
                  <div className="card text-center py-12">
                    <RefreshCw className="w-8 h-8 animate-spin mx-auto text-purple-400 mb-3" />
                    <p className="text-text-secondary">Loading interactions...</p>
                  </div>
                ) : botInteractions.length === 0 ? (
                  <div className="card text-center py-12">
                    <Bot className="w-12 h-12 mx-auto text-text-muted mb-3" />
                    <p className="text-text-secondary">No bot interactions found for the selected period.</p>
                    <p className="text-text-muted text-sm mt-1">Interactions will appear as bots consult Oracle for trading decisions.</p>
                  </div>
                ) : (
                  botInteractions.map((interaction) => (
                    <div key={`${interaction.source}-${interaction.id}`} className="card">
                      <div className="flex flex-wrap items-start justify-between gap-4 mb-3">
                        <div className="flex items-center gap-3">
                          <span className={`px-3 py-1 rounded-lg text-sm font-semibold border ${getBotColor(interaction.bot_name)}`}>
                            {interaction.bot_name}
                          </span>
                          <span className={`px-2 py-1 rounded text-xs font-medium ${getAdviceColor(interaction.action)}`}>
                            {interaction.action}
                          </span>
                          {interaction.actual_outcome && (
                            <span className={`px-2 py-1 rounded text-xs font-medium ${
                              interaction.actual_outcome.includes('MAX_PROFIT') || interaction.actual_outcome === 'WIN'
                                ? 'bg-green-500/20 text-green-300'
                                : 'bg-red-500/20 text-red-300'
                            }`}>
                              {interaction.actual_outcome}
                            </span>
                          )}
                        </div>
                        <div className="text-right">
                          <p className="text-text-primary font-medium">
                            {formatTexasCentralDateTime(interaction.timestamp || interaction.trade_date)}
                          </p>
                          <p className="text-text-muted text-xs">CT</p>
                        </div>
                      </div>

                      {/* Metrics Row */}
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-3">
                        {interaction.win_probability !== undefined && (
                          <div>
                            <p className="text-text-muted text-xs">Win Probability</p>
                            <p className="text-text-primary font-semibold">{(interaction.win_probability * 100).toFixed(1)}%</p>
                          </div>
                        )}
                        {interaction.confidence !== undefined && (
                          <div>
                            <p className="text-text-muted text-xs">Confidence</p>
                            <p className="text-text-primary font-semibold">{interaction.confidence.toFixed(1)}%</p>
                          </div>
                        )}
                        {interaction.vix !== undefined && (
                          <div>
                            <p className="text-text-muted text-xs">VIX</p>
                            <p className="text-text-primary font-semibold">{interaction.vix.toFixed(2)}</p>
                          </div>
                        )}
                        {interaction.gex_regime && (
                          <div>
                            <p className="text-text-muted text-xs">GEX Regime</p>
                            <p className={`font-semibold ${
                              interaction.gex_regime === 'POSITIVE' ? 'text-green-400' :
                              interaction.gex_regime === 'NEGATIVE' ? 'text-red-400' : 'text-yellow-400'
                            }`}>{interaction.gex_regime}</p>
                          </div>
                        )}
                        {interaction.actual_pnl !== undefined && (
                          <div>
                            <p className="text-text-muted text-xs">P&L</p>
                            <p className={`font-semibold ${interaction.actual_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              ${interaction.actual_pnl.toFixed(2)}
                            </p>
                          </div>
                        )}
                      </div>

                      {/* Reasoning */}
                      {interaction.reasoning && (
                        <div className="bg-background-deep rounded-lg p-3 mb-3">
                          <p className="text-text-muted text-xs mb-1">ML Reasoning</p>
                          <p className="text-text-secondary text-sm">{interaction.reasoning}</p>
                        </div>
                      )}

                      {/* Claude Analysis */}
                      <ClaudeAnalysisPanel analysis={interaction.claude_analysis} />
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Performance Tab */}
          {activeTab === 'performance' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-text-primary">Oracle Prediction Performance (90 Days)</h3>
                <button
                  onClick={fetchPerformance}
                  className="btn-secondary flex items-center gap-2"
                >
                  <RefreshCw className="w-4 h-4" />
                  Refresh
                </button>
              </div>

              {performance ? (
                <>
                  {/* Overall Stats */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="card">
                      <p className="text-text-secondary text-sm mb-1">Total Predictions</p>
                      <p className="text-3xl font-bold text-text-primary">{performance.total_predictions}</p>
                    </div>
                    <div className="card">
                      <p className="text-text-secondary text-sm mb-1">Win Rate</p>
                      <p className="text-3xl font-bold text-green-400">{(performance.overall.win_rate * 100).toFixed(1)}%</p>
                      <p className="text-text-muted text-xs">
                        {performance.overall.wins}W / {performance.overall.losses}L
                      </p>
                    </div>
                    <div className="card">
                      <p className="text-text-secondary text-sm mb-1">Calibration Error</p>
                      <p className={`text-3xl font-bold ${performance.overall.calibration_error < 0.05 ? 'text-green-400' : performance.overall.calibration_error < 0.1 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {(performance.overall.calibration_error * 100).toFixed(1)}%
                      </p>
                      <p className="text-text-muted text-xs">Predicted vs Actual</p>
                    </div>
                    <div className="card">
                      <p className="text-text-secondary text-sm mb-1">Total P&L</p>
                      <p className={`text-3xl font-bold ${performance.overall.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${performance.overall.total_pnl.toFixed(0)}
                      </p>
                    </div>
                  </div>

                  {/* By Bot */}
                  <div className="card">
                    <h4 className="text-lg font-semibold text-text-primary mb-4">Performance by Bot</h4>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="bg-background-deep">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Bot</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Predictions</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Wins</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Win Rate</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">Avg Predicted</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-text-muted">P&L</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {Object.entries(performance.by_bot).map(([bot, data]) => (
                            <tr key={bot} className="hover:bg-background-hover">
                              <td className="px-4 py-3">
                                <span className={`px-2 py-1 rounded text-xs font-medium ${getBotColor(bot)}`}>
                                  {bot}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-text-primary">{data.total}</td>
                              <td className="px-4 py-3 text-green-400">{data.wins}</td>
                              <td className="px-4 py-3 text-text-primary">{(data.win_rate * 100).toFixed(1)}%</td>
                              <td className="px-4 py-3 text-text-primary">{(data.avg_predicted_prob * 100).toFixed(1)}%</td>
                              <td className={`px-4 py-3 font-medium ${data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                ${data.pnl.toFixed(0)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              ) : (
                <div className="card text-center py-12">
                  <BarChart3 className="w-12 h-12 mx-auto text-text-muted mb-3" />
                  <p className="text-text-secondary">No performance data available yet.</p>
                  <p className="text-text-muted text-sm mt-1">Performance metrics will appear once predictions have outcomes.</p>
                </div>
              )}
            </div>
          )}

          {/* Training Tab */}
          {activeTab === 'training' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-text-primary">ML Model Training</h3>
                <button
                  onClick={fetchTrainingStatus}
                  disabled={loadingTraining}
                  className="btn-secondary flex items-center gap-2"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingTraining ? 'animate-spin' : ''}`} />
                  Refresh Status
                </button>
              </div>

              {trainingStatus ? (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Status Card */}
                  <div className="card">
                    <h4 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <Brain className="w-5 h-5 text-purple-400" />
                      Model Status
                    </h4>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Status</span>
                        <span className={`font-bold ${trainingStatus.model_trained ? 'text-green-400' : 'text-yellow-400'}`}>
                          {trainingStatus.model_trained ? 'Trained' : 'Not Trained'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Version</span>
                        <span className="text-text-primary font-medium">{trainingStatus.model_version}</span>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Last Trained</span>
                        <span className="text-text-primary">
                          {trainingStatus.last_trained ? formatTexasCentralDateTime(trainingStatus.last_trained) : 'Never'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Pending Outcomes</span>
                        <span className={`font-bold ${trainingStatus.pending_outcomes >= trainingStatus.threshold_for_retrain ? 'text-yellow-400' : 'text-text-primary'}`}>
                          {trainingStatus.pending_outcomes} / {trainingStatus.threshold_for_retrain}
                        </span>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Total Outcomes</span>
                        <span className="text-text-primary font-medium">{trainingStatus.total_outcomes}</span>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Model Source</span>
                        <span className={`font-bold ${trainingStatus.db_persistence ? 'text-green-400' : 'text-yellow-400'}`}>
                          {trainingStatus.model_source === 'database' ? 'Database' :
                           trainingStatus.model_source === 'local_file' ? 'Local File' : 'None'}
                        </span>
                      </div>
                      {trainingStatus.db_persistence ? (
                        <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm">
                          Model saved in database - survives restarts
                        </div>
                      ) : trainingStatus.model_trained ? (
                        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                          WARNING: Model NOT in database - will be lost on restart! Re-train to save.
                        </div>
                      ) : null}
                      {trainingStatus.needs_training && (
                        <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-400 text-sm">
                          Model needs retraining - threshold reached or model not trained
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Training Actions */}
                  <div className="card">
                    <h4 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <Zap className="w-5 h-5 text-yellow-400" />
                      Training Actions
                    </h4>
                    <div className="space-y-4">
                      <p className="text-text-secondary text-sm">
                        Oracle automatically trains weekly (Sunday midnight CT) and when 100+ new outcomes are available.
                        You can also trigger training manually.
                      </p>
                      <div className="flex gap-4">
                        <button
                          onClick={() => triggerTraining(false)}
                          disabled={triggeringTraining}
                          className="btn-secondary flex items-center gap-2 flex-1"
                        >
                          {triggeringTraining ? (
                            <RefreshCw className="w-4 h-4 animate-spin" />
                          ) : (
                            <Play className="w-4 h-4" />
                          )}
                          Auto Train
                        </button>
                        <button
                          onClick={() => triggerTraining(true)}
                          disabled={triggeringTraining}
                          className="btn-primary flex items-center gap-2 flex-1"
                        >
                          {triggeringTraining ? (
                            <RefreshCw className="w-4 h-4 animate-spin" />
                          ) : (
                            <Zap className="w-4 h-4" />
                          )}
                          Force Train
                        </button>
                      </div>

                      {trainingResult && (
                        <div className={`p-4 rounded-lg ${trainingResult.success ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
                          <p className={`font-medium ${trainingResult.success ? 'text-green-400' : 'text-red-400'}`}>
                            {trainingResult.success ? 'Training Successful' : 'Training Failed'}
                          </p>
                          <p className="text-text-secondary text-sm mt-1">
                            {trainingResult.reason || trainingResult.error}
                          </p>
                          {trainingResult.training_metrics && (
                            <div className="mt-3 pt-3 border-t border-border grid grid-cols-2 gap-2 text-sm">
                              <div>
                                <span className="text-text-muted">Accuracy:</span>
                                <span className="text-text-primary ml-2">{(trainingResult.training_metrics.accuracy * 100).toFixed(1)}%</span>
                              </div>
                              <div>
                                <span className="text-text-muted">AUC-ROC:</span>
                                <span className="text-text-primary ml-2">{trainingResult.training_metrics.auc_roc.toFixed(3)}</span>
                              </div>
                              <div>
                                <span className="text-text-muted">Samples:</span>
                                <span className="text-text-primary ml-2">{trainingResult.training_metrics.total_samples}</span>
                              </div>
                              <div>
                                <span className="text-text-muted">Method:</span>
                                <span className="text-text-primary ml-2">{trainingResult.method}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Training Metrics */}
                    {trainingStatus.training_metrics && (
                      <div className="mt-6 pt-4 border-t border-border">
                        <h5 className="text-sm font-medium text-text-primary mb-3">Current Model Metrics</h5>
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div className="flex justify-between">
                            <span className="text-text-muted">Accuracy:</span>
                            <span className="text-text-primary">{(trainingStatus.training_metrics.accuracy * 100).toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Precision:</span>
                            <span className="text-text-primary">{(trainingStatus.training_metrics.precision * 100).toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Recall:</span>
                            <span className="text-text-primary">{(trainingStatus.training_metrics.recall * 100).toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">F1 Score:</span>
                            <span className="text-text-primary">{(trainingStatus.training_metrics.f1_score * 100).toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">AUC-ROC:</span>
                            <span className="text-text-primary">{trainingStatus.training_metrics.auc_roc.toFixed(3)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Brier Score:</span>
                            <span className="text-text-primary">{trainingStatus.training_metrics.brier_score.toFixed(4)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Samples:</span>
                            <span className="text-text-primary">{trainingStatus.training_metrics.total_samples}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Win Rate:</span>
                            <span className="text-text-primary">{(trainingStatus.training_metrics.win_rate_actual * 100).toFixed(1)}%</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="card text-center py-12">
                  <Settings className="w-12 h-12 mx-auto text-text-muted mb-3 animate-spin" />
                  <p className="text-text-secondary">Loading training status...</p>
                </div>
              )}
            </div>
          )}

          {/* Live Logs Tab */}
          {activeTab === 'logs' && (
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <Activity className="w-5 h-5 text-blue-400" />
                  Live Oracle Logs
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
                    onClick={() => mutateLogs()}
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
              <div className="h-[500px] overflow-y-auto space-y-2 bg-background-deep rounded-lg p-3">
                {logs.length === 0 ? (
                  <p className="text-text-muted text-sm text-center py-4">No logs yet. Oracle activity will appear here.</p>
                ) : (
                  logs.slice().reverse().map((log, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs py-1 hover:bg-background-hover rounded px-2">
                      <span className="text-text-muted whitespace-nowrap" title="Texas Central Time">
                        {formatTexasCentralTime(log.timestamp)}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${getLogTypeColor(log.type)}`}>
                        {log.type}
                      </span>
                      <span className="text-text-secondary flex-1">{log.message}</span>
                      {log.data && Object.keys(log.data).length > 0 && (
                        <span className="text-text-muted" title={JSON.stringify(log.data, null, 2)}>
                          [data]
                        </span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Decision Log Tab */}
          {activeTab === 'decisions' && (
            <div className="card">
              <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                <FileText className="w-5 h-5 text-green-500" />
                ORACLE Decision Log
              </h3>
              <DecisionLogViewer defaultBot="ORACLE" />
            </div>
          )}

          {/* Info Section */}
          <div className="mt-8 grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="card bg-red-500/5 border border-red-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-red-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">ARES</h3>
                  <p className="text-text-secondary text-sm">0DTE Iron Condors with GEX-protected strikes</p>
                </div>
              </div>
            </div>

            <div className="card bg-blue-500/5 border border-blue-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-blue-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">ATLAS</h3>
                  <p className="text-text-secondary text-sm">Wheel strategy for consistent premium</p>
                </div>
              </div>
            </div>

            <div className="card bg-orange-500/5 border border-orange-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-orange-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">PHOENIX</h3>
                  <p className="text-text-secondary text-sm">Directional calls for momentum plays</p>
                </div>
              </div>
            </div>

            <div className="card bg-purple-500/5 border border-purple-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-purple-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">ATHENA</h3>
                  <p className="text-text-secondary text-sm">Pattern recognition and signals</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
