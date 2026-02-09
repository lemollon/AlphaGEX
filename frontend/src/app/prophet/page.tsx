'use client'

import { useState, useEffect, useCallback, Component, ErrorInfo, ReactNode } from 'react'
import { Eye, Brain, Activity, RefreshCw, Trash2, CheckCircle, XCircle, AlertCircle, AlertTriangle, ShieldAlert, Sparkles, FileText, History, TrendingUp, BarChart3, Download, Zap, Bot, MessageSquare, Settings, Play, Clock, Target, ChevronDown, ChevronUp, Crosshair } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import DecisionLogViewer from '@/components/trader/DecisionLogViewer'
import EquityCurveChart from '@/components/charts/EquityCurveChart'
import { apiClient } from '@/lib/api'
import { useProphetStatus, useProphetLogs, useProphetFullTransparency } from '@/lib/hooks/useMarketData'

// Error Boundary for Prophet component-level errors
interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

class ProphetErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Prophet Error Boundary caught error:', error, errorInfo)
    this.setState({ errorInfo })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <div className="p-6 bg-red-500/10 border border-red-500/30 rounded-lg m-4">
          <div className="flex items-center gap-3 mb-4">
            <AlertTriangle className="w-6 h-6 text-red-400" />
            <h3 className="text-lg font-semibold text-red-400">Component Error</h3>
          </div>
          <p className="text-text-secondary mb-4">
            An error occurred while rendering this section. Please try refreshing the page.
          </p>
          {process.env.NODE_ENV === 'development' && this.state.error && (
            <div className="bg-gray-900 rounded p-3 mb-4">
              <pre className="text-xs text-red-300 whitespace-pre-wrap">
                {this.state.error.message}
              </pre>
            </div>
          )}
          <button
            onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

// Safe array access helper - returns typed array or empty array
function safeArray<T = unknown>(arr: T[] | null | undefined): T[] {
  return Array.isArray(arr) ? arr : []
}

// Safe string array helper for common use case
function safeStringArray(arr: string[] | null | undefined | unknown): string[] {
  if (!Array.isArray(arr)) return []
  return arr.map(item => String(item ?? ''))
}

// Safe number formatting helper
function safeNumber(val: number | null | undefined, decimals: number = 2): string {
  if (val == null || isNaN(val)) return 'N/A'
  return val.toFixed(decimals)
}

// Safe percentage formatting helper
function safePercent(val: number | null | undefined, decimals: number = 1): string {
  if (val == null || isNaN(val)) return 'N/A'
  return `${(val * 100).toFixed(decimals)}%`
}

// Safe object check helper - verifies value is a non-null object (not array)
function isPlainObject(val: unknown): val is Record<string, unknown> {
  return val !== null && typeof val === 'object' && !Array.isArray(val)
}

// Safe object entries helper - returns entries only for valid objects
function safeObjectEntries<T>(obj: T | null | undefined): [string, T[keyof T & string]][] {
  if (!isPlainObject(obj)) return []
  return Object.entries(obj) as [string, T[keyof T & string]][]
}

// Safe object keys helper - returns keys only for valid objects
function safeObjectKeys(obj: unknown): string[] {
  if (!isPlainObject(obj)) return []
  return Object.keys(obj)
}

interface BotHeartbeat {
  last_scan: string | null
  last_scan_iso: string | null
  status: string
  scan_count_today: number
  details: Record<string, any>
}

interface ProphetStatus {
  model_trained: boolean
  model_version: string
  claude_available: boolean
  claude_model: string
  high_confidence_threshold: number
  low_confidence_threshold: number
}

interface ProphetStatusResponse {
  success: boolean
  prophet?: ProphetStatus
  bot_heartbeats?: Record<string, BotHeartbeat>
  error?: string
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
  // Model staleness metrics (Issue #4 - end-to-end visibility)
  hours_since_training?: number
  is_model_fresh?: boolean
  freshness_warning?: string | null
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
  gex_net?: number
  gex_call_wall?: number
  gex_put_wall?: number
  gex_flip_point?: number
  day_of_week?: number
  // NEUTRAL Regime Analysis fields
  neutral_derived_direction?: string
  neutral_confidence?: number
  neutral_reasoning?: string
  ic_suitability?: number
  bullish_suitability?: number
  bearish_suitability?: number
  recommended_strategy?: string
  trend_direction?: string
  trend_strength?: number
  position_in_range_pct?: number
  is_contained?: boolean
  wall_filter_passed?: boolean
  suggested_risk_pct?: number
  suggested_sd_multiplier?: number
  use_gex_walls?: boolean
  suggested_put_strike?: number
  suggested_call_strike?: number
  model_version?: string
  top_factors?: Record<string, number>
  claude_analysis?: any
  actual_outcome?: string
  actual_pnl?: number
  outcome_date?: string
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
function formatTexasCentralTime(isoTimestamp: string | null | undefined): string {
  if (!isoTimestamp) return 'N/A'
  try {
    const date = new Date(isoTimestamp)
    if (isNaN(date.getTime())) return 'Invalid'
    return date.toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    })
  } catch {
    return String(isoTimestamp)
  }
}

// Helper function to format full date in Texas Central Time
function formatTexasCentralDateTime(isoTimestamp: string | null | undefined): string {
  if (!isoTimestamp) return 'N/A'
  try {
    const date = new Date(isoTimestamp)
    if (isNaN(date.getTime())) return 'Invalid Date'
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
    return String(isoTimestamp)
  }
}

// Expandable Claude Analysis Component with FULL TRANSPARENCY
function ClaudeAnalysisPanel({ analysis }: { analysis: any }) {
  const [expanded, setExpanded] = useState(false)
  const [showRawPrompt, setShowRawPrompt] = useState(false)
  const [showRawResponse, setShowRawResponse] = useState(false)

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
              <p className="text-text-primary font-bold">{analysis.recommendation}</p>
            </div>
          )}
          {analysis.confidence_adjustment != null && (
            <div>
              <span className="text-text-muted">Confidence Adjustment:</span>
              <span className={`ml-2 font-medium ${analysis.confidence_adjustment >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {analysis.confidence_adjustment > 0 ? '+' : ''}{(analysis.confidence_adjustment * 100).toFixed(1)}%
              </span>
            </div>
          )}
          {safeStringArray(analysis.risk_factors).length > 0 && (
            <div>
              <span className="text-text-muted">Risk Factors:</span>
              <ul className="mt-1 space-y-1">
                {safeStringArray(analysis.risk_factors).map((risk, idx) => (
                  <li key={idx} className="text-red-300 flex items-start gap-2">
                    <AlertCircle className="w-3 h-3 mt-1 flex-shrink-0" />
                    {risk || 'Unknown risk'}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {safeStringArray(analysis.opportunities).length > 0 && (
            <div>
              <span className="text-text-muted">Opportunities:</span>
              <ul className="mt-1 space-y-1">
                {safeStringArray(analysis.opportunities).map((opp, idx) => (
                  <li key={idx} className="text-green-300 flex items-start gap-2">
                    <CheckCircle className="w-3 h-3 mt-1 flex-shrink-0" />
                    {opp || 'Unknown opportunity'}
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

          {/* RAW PROMPT/RESPONSE TRANSPARENCY */}
          {analysis.raw_prompt && (
            <div className="border-t border-border pt-3 mt-3">
              <button
                onClick={() => setShowRawPrompt(!showRawPrompt)}
                className="flex items-center gap-2 text-blue-400 hover:text-blue-300 text-xs font-medium"
              >
                <MessageSquare className="w-3 h-3" />
                {showRawPrompt ? 'Hide' : 'Show'} Raw Prompt Sent to Claude
                {showRawPrompt ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
              {showRawPrompt && (
                <div className="mt-2 bg-gray-900 rounded-lg p-3 max-h-60 overflow-y-auto">
                  <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">{analysis.raw_prompt}</pre>
                </div>
              )}
            </div>
          )}

          {analysis.raw_response && (
            <div className="pt-2">
              <button
                onClick={() => setShowRawResponse(!showRawResponse)}
                className="flex items-center gap-2 text-purple-400 hover:text-purple-300 text-xs font-medium"
              >
                <Bot className="w-3 h-3" />
                {showRawResponse ? 'Hide' : 'Show'} Raw Response from Claude
                {showRawResponse ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
              {showRawResponse && (
                <div className="mt-2 bg-purple-900/20 rounded-lg p-3 max-h-60 overflow-y-auto">
                  <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">{analysis.raw_response}</pre>
                </div>
              )}
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

export default function ProphetPage() {
  const sidebarPadding = useSidebarPadding()

  // SWR hooks for data fetching with caching
  const { data: statusRes, error: statusError, isLoading: statusLoading, isValidating: statusValidating, mutate: mutateStatus } = useProphetStatus()
  const { data: logsRes, isValidating: logsValidating, mutate: mutateLogs } = useProphetLogs()
  const { data: transparencyRes, isValidating: transparencyValidating, mutate: mutateTransparency } = useProphetFullTransparency()

  // Extract data from responses
  const status = statusRes?.prophet as ProphetStatus | undefined
  const botHeartbeats = (statusRes?.bot_heartbeats || {}) as Record<string, BotHeartbeat>
  const logs = (logsRes?.logs || []) as LogEntry[]
  const dataFlows = (transparencyRes?.data_flows || []) as any[]
  const claudeExchanges = (transparencyRes?.claude_exchanges || []) as any[]

  const loading = statusLoading && !status
  const isRefreshing = statusValidating || logsValidating || transparencyValidating

  // Local state
  const [activeTab, setActiveTab] = useState<'interactions' | 'performance' | 'training' | 'logs' | 'decisions' | 'dataflow' | 'formulas'>('interactions')
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
      const response = await apiClient.getProphetBotInteractions({
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
      const response = await apiClient.getProphetTrainingStatus()
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
      const response = await apiClient.getProphetPerformance(90)
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
      const response = await apiClient.triggerProphetTraining(force)
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
    a.download = `prophet_interactions_${new Date().toISOString().split('T')[0]}.json`
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
      i.actual_pnl != null ? `$${i.actual_pnl.toFixed(2)}` : '',
      i.reasoning || ''
    ])
    const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `prophet_interactions_${new Date().toISOString().split('T')[0]}.csv`
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
    a.download = `prophet_logs_${new Date().toISOString().split('T')[0]}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const clearLogs = async () => {
    try {
      await apiClient.clearProphetLogs()
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

  // Auto-refresh interactions every 30 seconds when tab is active
  useEffect(() => {
    if (activeTab !== 'interactions') return

    const interval = setInterval(() => {
      fetchBotInteractions()
    }, 30000) // 30 seconds

    return () => clearInterval(interval)
  }, [activeTab, fetchBotInteractions])

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
      case 'FORTRESS': return 'text-red-400 bg-red-500/20 border-red-500/30'
      case 'CORNERSTONE': return 'text-indigo-400 bg-indigo-500/20 border-indigo-500/30'
      case 'LAZARUS': return 'text-rose-400 bg-rose-500/20 border-rose-500/30'
      case 'SOLOMON': return 'text-purple-400 bg-purple-500/20 border-purple-500/30'
      case 'ANCHOR': return 'text-blue-400 bg-blue-500/20 border-blue-500/30'
      case 'GIDEON': return 'text-orange-400 bg-orange-500/20 border-orange-500/30'
      case 'SAMSON': return 'text-teal-400 bg-teal-500/20 border-teal-500/30'
      case 'PROPHET': return 'text-cyan-400 bg-cyan-500/20 border-cyan-500/30'
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
      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-2">
              <Eye className="w-8 h-8 text-purple-400" />
              <h1 className="text-3xl font-bold text-text-primary">Prophet Knowledge Base</h1>
            </div>
            <p className="text-text-secondary">
              Centralized intelligence hub for all trading bots (FORTRESS, SOLOMON, ANCHOR, LAZARUS, CORNERSTONE, GIDEON, SAMSON) - All bot interactions, Claude AI reasoning, and ML predictions
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

          {/* Bot Heartbeats Section */}
          <div className="mb-6 bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-5 h-5 text-purple-400" />
              <h3 className="text-lg font-semibold text-white">Bot Heartbeats</h3>
              <span className="text-xs text-gray-500">(5-min scan intervals)</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {['FORTRESS', 'SOLOMON', 'ANCHOR', 'LAZARUS', 'CORNERSTONE', 'GIDEON', 'SAMSON'].map((botName) => {
                const hb = botHeartbeats[botName]
                const statusColor = hb?.status === 'TRADED' ? 'bg-green-500' :
                                   hb?.status === 'SCAN_COMPLETE' ? 'bg-blue-500' :
                                   hb?.status === 'ERROR' ? 'bg-red-500' :
                                   hb?.status === 'MARKET_CLOSED' ? 'bg-yellow-500' :
                                   'bg-gray-500'
                return (
                  <div key={botName} className="bg-gray-900/50 rounded-lg p-3 border border-gray-600">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${statusColor} ${hb?.status === 'TRADED' ? 'animate-pulse' : ''}`} />
                        <span className="text-white font-bold">{botName}</span>
                      </div>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                        hb?.status === 'TRADED' ? 'bg-green-900/50 text-green-400' :
                        hb?.status === 'SCAN_COMPLETE' ? 'bg-blue-900/50 text-blue-400' :
                        hb?.status === 'ERROR' ? 'bg-red-900/50 text-red-400' :
                        'bg-gray-700 text-gray-400'
                      }`}>
                        {hb?.status?.replace(/_/g, ' ') || 'Never Run'}
                      </span>
                    </div>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="text-gray-500">Last Scan:</span>
                        <span className="text-gray-300 font-mono">{hb?.last_scan || 'Never'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Scans Today:</span>
                        <span className="text-cyan-400 font-bold">{hb?.scan_count_today || 0}</span>
                      </div>
                    </div>
                  </div>
                )
              })}
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
            <button
              onClick={() => setActiveTab('dataflow')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'dataflow' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <Eye className="w-4 h-4" />
              Data Flow
              {(dataFlows.length > 0 || claudeExchanges.length > 0) && (
                <span className="text-xs bg-green-500/30 text-green-300 px-1.5 py-0.5 rounded">
                  {dataFlows.length + claudeExchanges.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab('formulas')}
              className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
                activeTab === 'formulas' ? 'bg-purple-600 text-white' : 'bg-background-card text-text-secondary hover:bg-background-hover'
              }`}
            >
              <Sparkles className="w-4 h-4" />
              Decision Formulas
            </button>
          </div>

          {/* Bot Interactions Tab */}
          {activeTab === 'interactions' && (
            <ProphetErrorBoundary>
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
                    <option value="FORTRESS">FORTRESS</option>
                    <option value="SOLOMON">SOLOMON</option>
                    <option value="ANCHOR">ANCHOR</option>
                    <option value="LAZARUS">LAZARUS</option>
                    <option value="CORNERSTONE">CORNERSTONE</option>
                    <option value="GIDEON">GIDEON</option>
                    <option value="SAMSON">SAMSON</option>
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
                    <p className="text-text-muted text-sm mt-1">Interactions will appear as bots consult Prophet for trading decisions.</p>
                  </div>
                ) : (
                  botInteractions.map((interaction) => (
                    <div key={`${interaction.source}-${interaction.id}`} className="card">
                      {/* Header Row */}
                      <div className="flex flex-wrap items-start justify-between gap-4 mb-3">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className={`px-3 py-1 rounded-lg text-sm font-semibold border ${getBotColor(interaction.bot_name)}`}>
                            {interaction.bot_name}
                          </span>
                          <span className={`px-2 py-1 rounded text-xs font-medium ${getAdviceColor(interaction.action)}`}>
                            {interaction.action}
                          </span>
                          {interaction.actual_outcome && (
                            <span className={`px-2 py-1 rounded text-xs font-medium ${
                              (typeof interaction.actual_outcome === 'string' && interaction.actual_outcome.includes('MAX_PROFIT')) || interaction.actual_outcome === 'WIN'
                                ? 'bg-green-500/20 text-green-300'
                                : 'bg-red-500/20 text-red-300'
                            }`}>
                              {String(interaction.actual_outcome)}
                            </span>
                          )}
                          {interaction.model_version && (
                            <span className="px-2 py-1 rounded text-xs font-medium bg-indigo-500/20 text-indigo-300">
                              v{interaction.model_version}
                            </span>
                          )}
                          {interaction.use_gex_walls && (
                            <span className="px-2 py-1 rounded text-xs font-medium bg-cyan-500/20 text-cyan-300">
                              GEX Walls
                            </span>
                          )}
                        </div>
                        <div className="text-right">
                          <p className="text-text-primary font-medium">
                            {formatTexasCentralDateTime(interaction.timestamp || interaction.trade_date)}
                          </p>
                          <p className="text-text-muted text-xs">
                            CT {interaction.day_of_week != null && `• ${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][interaction.day_of_week]}`}
                          </p>
                        </div>
                      </div>

                      {/* Primary Metrics Row */}
                      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-3">
                        {interaction.win_probability != null && (
                          <div className="bg-background-deep rounded p-2">
                            <p className="text-text-muted text-xs">Win Prob</p>
                            <p className="text-text-primary font-semibold">{(interaction.win_probability * 100).toFixed(1)}%</p>
                          </div>
                        )}
                        {interaction.confidence != null && (
                          <div className="bg-background-deep rounded p-2">
                            <p className="text-text-muted text-xs">Confidence</p>
                            <p className="text-text-primary font-semibold">{interaction.confidence.toFixed(1)}%</p>
                          </div>
                        )}
                        {interaction.spot_price != null && (
                          <div className="bg-background-deep rounded p-2">
                            <p className="text-text-muted text-xs">Spot Price</p>
                            <p className="text-text-primary font-semibold">${interaction.spot_price.toFixed(2)}</p>
                          </div>
                        )}
                        {interaction.vix != null && (
                          <div className="bg-background-deep rounded p-2">
                            <p className="text-text-muted text-xs">VIX</p>
                            <p className="text-text-primary font-semibold">{interaction.vix.toFixed(2)}</p>
                          </div>
                        )}
                        {interaction.gex_regime && (
                          <div className="bg-background-deep rounded p-2">
                            <p className="text-text-muted text-xs">GEX Regime</p>
                            <p className={`font-semibold ${
                              interaction.gex_regime === 'POSITIVE' ? 'text-green-400' :
                              interaction.gex_regime === 'NEGATIVE' ? 'text-red-400' : 'text-yellow-400'
                            }`}>{interaction.gex_regime}</p>
                          </div>
                        )}
                        {interaction.actual_pnl != null && (
                          <div className="bg-background-deep rounded p-2">
                            <p className="text-text-muted text-xs">P&L</p>
                            <p className={`font-semibold ${interaction.actual_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              ${interaction.actual_pnl.toFixed(2)}
                            </p>
                          </div>
                        )}
                      </div>

                      {/* GEX Details Row */}
                      {(interaction.gex_net != null || interaction.gex_call_wall != null || interaction.gex_put_wall != null || interaction.gex_flip_point != null) && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 p-3 bg-cyan-500/5 border border-cyan-500/20 rounded-lg">
                          <div className="text-xs">
                            <span className="text-cyan-400 font-medium">GEX Details</span>
                          </div>
                          {interaction.gex_net != null && (
                            <div className="text-xs">
                              <span className="text-text-muted">Net GEX:</span>
                              <span className={`ml-1 font-medium ${interaction.gex_net >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {(interaction.gex_net / 1e9).toFixed(2)}B
                              </span>
                            </div>
                          )}
                          {interaction.gex_call_wall != null && (
                            <div className="text-xs">
                              <span className="text-text-muted">Call Wall:</span>
                              <span className="text-text-primary ml-1 font-medium">${interaction.gex_call_wall.toFixed(0)}</span>
                            </div>
                          )}
                          {interaction.gex_put_wall != null && (
                            <div className="text-xs">
                              <span className="text-text-muted">Put Wall:</span>
                              <span className="text-text-primary ml-1 font-medium">${interaction.gex_put_wall.toFixed(0)}</span>
                            </div>
                          )}
                          {interaction.gex_flip_point != null && (
                            <div className="text-xs">
                              <span className="text-text-muted">Flip Point:</span>
                              <span className="text-text-primary ml-1 font-medium">${interaction.gex_flip_point.toFixed(0)}</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Enhanced Prophet Analysis Display - Shows for any regime when data available */}
                      {(interaction.trend_direction || interaction.ic_suitability != null || interaction.position_in_range_pct != null || interaction.neutral_derived_direction) && (
                        <div className="mb-3 space-y-3">
                          {/* TREND ANALYSIS Section */}
                          {interaction.trend_direction && (
                            <div className="p-3 bg-blue-500/5 border border-blue-500/20 rounded-lg">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-blue-400 text-xs font-medium flex items-center gap-1">
                                  <TrendingUp className="w-3 h-3" />
                                  TREND ANALYSIS
                                </span>
                              </div>
                              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                                <div className="text-xs">
                                  <span className="text-text-muted">Direction:</span>
                                  <span className={`ml-1 font-bold ${
                                    interaction.trend_direction === 'UPTREND' ? 'text-green-400' :
                                    interaction.trend_direction === 'DOWNTREND' ? 'text-red-400' : 'text-yellow-400'
                                  }`}>
                                    {interaction.trend_direction === 'UPTREND' ? '↑ ' : interaction.trend_direction === 'DOWNTREND' ? '↓ ' : '→ '}
                                    {interaction.trend_direction}
                                  </span>
                                  {interaction.trend_strength != null && (
                                    <span className="text-text-muted ml-1">(strength: {(interaction.trend_strength * 100).toFixed(1)}%)</span>
                                  )}
                                </div>
                                {interaction.spot_price != null && interaction.gex_put_wall != null && interaction.gex_call_wall != null && (
                                  <div className="text-xs col-span-2">
                                    <span className="text-text-muted">Price Range:</span>
                                    <span className="text-text-primary ml-1">
                                      ${interaction.gex_put_wall?.toFixed(0)} → ${interaction.spot_price?.toFixed(2)} → ${interaction.gex_call_wall?.toFixed(0)}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* WALL POSITION Section - Visual Bar */}
                          {interaction.gex_put_wall != null && interaction.gex_call_wall != null && interaction.spot_price != null && (
                            <div className="p-3 bg-purple-500/5 border border-purple-500/20 rounded-lg">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-purple-400 text-xs font-medium flex items-center gap-1">
                                  <Crosshair className="w-3 h-3" />
                                  WALL POSITION
                                </span>
                                {interaction.is_contained != null && (
                                  <span className={`text-xs px-2 py-0.5 rounded ${
                                    interaction.is_contained ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                                  }`}>
                                    Status: {interaction.is_contained ? 'CONTAINED ✓' : 'OUTSIDE RANGE'}
                                  </span>
                                )}
                              </div>
                              <div className="space-y-2">
                                {/* Visual Wall Bar */}
                                <div className="flex items-center gap-2 text-xs">
                                  <span className="text-red-400 font-mono w-16">Put ${interaction.gex_put_wall?.toFixed(0)}</span>
                                  <div className="flex-1 relative h-6 bg-gray-800 rounded overflow-hidden">
                                    {/* Put side gradient */}
                                    <div className="absolute left-0 top-0 bottom-0 w-1/3 bg-gradient-to-r from-red-500/30 to-transparent" />
                                    {/* Call side gradient */}
                                    <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-green-500/30 to-transparent" />
                                    {/* Current price marker */}
                                    {(() => {
                                      const putWall = interaction.gex_put_wall || 0
                                      const callWall = interaction.gex_call_wall || 0
                                      const spotPrice = interaction.spot_price || 0
                                      const range = callWall - putWall
                                      const position = range > 0 ? ((spotPrice - putWall) / range) * 100 : 50
                                      return (
                                        <div
                                          className="absolute top-0 bottom-0 w-0.5 bg-cyan-400"
                                          style={{ left: `${Math.min(Math.max(position, 5), 95)}%` }}
                                        >
                                          <div className="absolute -top-0.5 left-1/2 -translate-x-1/2 w-2 h-2 bg-cyan-400 rounded-full" />
                                          <div className="absolute top-6 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] text-cyan-400">
                                            ${spotPrice.toFixed(0)}
                                          </div>
                                        </div>
                                      )
                                    })()}
                                  </div>
                                  <span className="text-green-400 font-mono w-16 text-right">Call ${interaction.gex_call_wall?.toFixed(0)}</span>
                                </div>
                                {/* Position percentage */}
                                {interaction.position_in_range_pct != null && (
                                  <div className="text-center text-xs text-text-muted">
                                    <span className={`font-medium ${
                                      interaction.position_in_range_pct > 60 ? 'text-green-400' :
                                      interaction.position_in_range_pct < 40 ? 'text-red-400' : 'text-yellow-400'
                                    }`}>
                                      {interaction.position_in_range_pct.toFixed(0)}% of range
                                    </span>
                                    {interaction.position_in_range_pct > 50 ? ' (closer to call wall)' : ' (closer to put wall)'}
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* STRATEGY SUITABILITY Section - Progress Bars */}
                          {(interaction.ic_suitability != null || interaction.bullish_suitability != null || interaction.bearish_suitability != null) && (
                            <div className="p-3 bg-cyan-500/5 border border-cyan-500/20 rounded-lg">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-cyan-400 text-xs font-medium">STRATEGY SUITABILITY</span>
                                {interaction.recommended_strategy && (
                                  <span className="text-xs px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-400">
                                    Recommended: {interaction.recommended_strategy}
                                  </span>
                                )}
                              </div>
                              <div className="space-y-2">
                                {interaction.ic_suitability != null && (
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs text-text-muted w-24">Iron Condor</span>
                                    <div className="flex-1 h-4 bg-gray-800 rounded overflow-hidden">
                                      <div
                                        className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 transition-all"
                                        style={{ width: `${Math.min(interaction.ic_suitability, 100)}%` }}
                                      />
                                    </div>
                                    <span className="text-xs font-mono text-cyan-400 w-10 text-right">{interaction.ic_suitability.toFixed(0)}%</span>
                                  </div>
                                )}
                                {interaction.bullish_suitability != null && (
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs text-text-muted w-24">Bull Spread</span>
                                    <div className="flex-1 h-4 bg-gray-800 rounded overflow-hidden">
                                      <div
                                        className="h-full bg-gradient-to-r from-green-600 to-green-400 transition-all"
                                        style={{ width: `${Math.min(interaction.bullish_suitability, 100)}%` }}
                                      />
                                    </div>
                                    <span className="text-xs font-mono text-green-400 w-10 text-right">{interaction.bullish_suitability.toFixed(0)}%</span>
                                  </div>
                                )}
                                {interaction.bearish_suitability != null && (
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs text-text-muted w-24">Bear Spread</span>
                                    <div className="flex-1 h-4 bg-gray-800 rounded overflow-hidden">
                                      <div
                                        className="h-full bg-gradient-to-r from-red-600 to-red-400 transition-all"
                                        style={{ width: `${Math.min(interaction.bearish_suitability, 100)}%` }}
                                      />
                                    </div>
                                    <span className="text-xs font-mono text-red-400 w-10 text-right">{interaction.bearish_suitability.toFixed(0)}%</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* NEUTRAL REGIME DECISION Section */}
                          {interaction.gex_regime === 'NEUTRAL' && (interaction.neutral_derived_direction || interaction.neutral_reasoning) && (
                            <div className="p-3 bg-yellow-500/5 border border-yellow-500/20 rounded-lg">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-yellow-400 text-xs font-medium">NEUTRAL REGIME DECISION</span>
                                {interaction.wall_filter_passed != null && (
                                  <span className={`text-xs px-2 py-0.5 rounded ${
                                    interaction.wall_filter_passed ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                                  }`}>
                                    Wall Filter: {interaction.wall_filter_passed ? 'PASSED ✓' : 'FAILED ✗'}
                                  </span>
                                )}
                              </div>
                              <div className="space-y-2">
                                {interaction.neutral_derived_direction && (
                                  <div className="flex items-center gap-2">
                                    <span className="text-text-muted text-xs">Derived Direction:</span>
                                    <span className={`text-sm font-bold ${
                                      interaction.neutral_derived_direction === 'BULLISH' ? 'text-green-400' :
                                      interaction.neutral_derived_direction === 'BEARISH' ? 'text-red-400' : 'text-yellow-400'
                                    }`}>
                                      {interaction.neutral_derived_direction}
                                    </span>
                                    {interaction.neutral_confidence != null && (
                                      <span className="text-text-muted text-xs">({(interaction.neutral_confidence * 100).toFixed(0)}% confidence)</span>
                                    )}
                                  </div>
                                )}
                                {interaction.neutral_reasoning && (
                                  <div className="text-xs text-text-secondary bg-yellow-500/10 rounded p-2">
                                    <span className="text-yellow-400">Reasoning:</span> "{interaction.neutral_reasoning}"
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* ML REASONING Section */}
                          {(interaction.win_probability != null || interaction.wall_filter_passed != null) && interaction.reasoning && (
                            <div className="p-3 bg-indigo-500/5 border border-indigo-500/20 rounded-lg">
                              <span className="text-indigo-400 text-xs font-medium">ML REASONING</span>
                              <div className="mt-2 space-y-1 text-xs">
                                {interaction.wall_filter_passed != null && (
                                  <div className="flex items-center gap-2">
                                    {interaction.wall_filter_passed ? (
                                      <CheckCircle className="w-3 h-3 text-green-400" />
                                    ) : (
                                      <XCircle className="w-3 h-3 text-red-400" />
                                    )}
                                    <span className="text-text-muted">Wall filter</span>
                                    <span className={interaction.wall_filter_passed ? 'text-green-400' : 'text-red-400'}>
                                      {interaction.wall_filter_passed ? 'PASSED' : 'FAILED'}
                                    </span>
                                  </div>
                                )}
                                {interaction.neutral_derived_direction && (
                                  <div className="flex items-center gap-2">
                                    <CheckCircle className="w-3 h-3 text-green-400" />
                                    <span className="text-text-muted">Direction:</span>
                                    <span className={`${
                                      interaction.neutral_derived_direction === 'BULLISH' ? 'text-green-400' :
                                      interaction.neutral_derived_direction === 'BEARISH' ? 'text-red-400' : 'text-yellow-400'
                                    }`}>
                                      {interaction.neutral_derived_direction} (from trend analysis)
                                    </span>
                                  </div>
                                )}
                                {interaction.win_probability != null && (
                                  <div className="flex items-center gap-2">
                                    <CheckCircle className="w-3 h-3 text-green-400" />
                                    <span className="text-text-muted">Win Prob:</span>
                                    <span className="text-text-primary">
                                      {(interaction.win_probability * 100).toFixed(0)}%
                                      {interaction.confidence != null && ` (base ${(interaction.win_probability * 100 - 10).toFixed(0)}% + trend ${interaction.trend_strength ? (interaction.trend_strength * 10).toFixed(0) : '0'}%)`}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Suggested Strikes Row */}
                      {(interaction.suggested_put_strike != null || interaction.suggested_call_strike != null || interaction.suggested_risk_pct != null || interaction.suggested_sd_multiplier != null) && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 p-3 bg-purple-500/5 border border-purple-500/20 rounded-lg">
                          <div className="text-xs">
                            <span className="text-purple-400 font-medium">Suggested Setup</span>
                          </div>
                          {interaction.suggested_put_strike != null && (
                            <div className="text-xs">
                              <span className="text-text-muted">Put Strike:</span>
                              <span className="text-red-400 ml-1 font-medium">${interaction.suggested_put_strike.toFixed(0)}</span>
                            </div>
                          )}
                          {interaction.suggested_call_strike != null && (
                            <div className="text-xs">
                              <span className="text-text-muted">Call Strike:</span>
                              <span className="text-green-400 ml-1 font-medium">${interaction.suggested_call_strike.toFixed(0)}</span>
                            </div>
                          )}
                          {interaction.suggested_risk_pct != null && (
                            <div className="text-xs">
                              <span className="text-text-muted">Risk %:</span>
                              <span className="text-text-primary ml-1 font-medium">{interaction.suggested_risk_pct.toFixed(1)}%</span>
                            </div>
                          )}
                          {interaction.suggested_sd_multiplier != null && (
                            <div className="text-xs">
                              <span className="text-text-muted">SD Mult:</span>
                              <span className="text-text-primary ml-1 font-medium">{interaction.suggested_sd_multiplier.toFixed(2)}x</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Top Factors */}
                      {isPlainObject(interaction.top_factors) && safeObjectKeys(interaction.top_factors).length > 0 && (
                        <div className="mb-3 p-3 bg-yellow-500/5 border border-yellow-500/20 rounded-lg">
                          <p className="text-yellow-400 text-xs font-medium mb-2">Top Decision Factors</p>
                          <div className="flex flex-wrap gap-2">
                            {safeObjectEntries(interaction.top_factors).slice(0, 5).map(([factor, weight]) => (
                              <span key={factor} className="px-2 py-1 bg-yellow-500/10 rounded text-xs text-text-secondary">
                                {factor}: <span className="text-yellow-400 font-medium">{typeof weight === 'number' ? weight.toFixed(2) : String(weight ?? '')}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

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
            </ProphetErrorBoundary>
          )}

          {/* Performance Tab */}
          {activeTab === 'performance' && (
            <ProphetErrorBoundary>
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-text-primary">Prophet Prediction Performance (90 Days)</h3>
                <button
                  onClick={fetchPerformance}
                  className="btn-secondary flex items-center gap-2"
                >
                  <RefreshCw className="w-4 h-4" />
                  Refresh
                </button>
              </div>

              {/* Enhanced Equity Curve with Event Markers */}
              <EquityCurveChart
                title="Combined Bot Performance"
                defaultDays={90}
                height={400}
                showDrawdown={true}
              />

              {performance?.overall ? (
                <>
                  {/* Overall Stats */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="card">
                      <p className="text-text-secondary text-sm mb-1">Total Predictions</p>
                      <p className="text-3xl font-bold text-text-primary">{performance.total_predictions ?? 0}</p>
                    </div>
                    <div className="card">
                      <p className="text-text-secondary text-sm mb-1">Win Rate</p>
                      <p className="text-3xl font-bold text-green-400">{((performance.overall.win_rate ?? 0) * 100).toFixed(1)}%</p>
                      <p className="text-text-muted text-xs">
                        {performance.overall.wins ?? 0}W / {performance.overall.losses ?? 0}L
                      </p>
                    </div>
                    <div className="card">
                      <p className="text-text-secondary text-sm mb-1">Calibration Error</p>
                      <p className={`text-3xl font-bold ${(performance.overall.calibration_error ?? 1) < 0.05 ? 'text-green-400' : (performance.overall.calibration_error ?? 1) < 0.1 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {((performance.overall.calibration_error ?? 0) * 100).toFixed(1)}%
                      </p>
                      <p className="text-text-muted text-xs">Predicted vs Actual</p>
                    </div>
                    <div className="card">
                      <p className="text-text-secondary text-sm mb-1">Total P&L</p>
                      <p className={`text-3xl font-bold ${(performance.overall.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${(performance.overall.total_pnl ?? 0).toFixed(0)}
                      </p>
                    </div>
                  </div>

                  {/* By Bot */}
                  {isPlainObject(performance.by_bot) && safeObjectKeys(performance.by_bot).length > 0 && (
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
                            {safeObjectEntries(performance.by_bot).map(([bot, data]) => (
                              <tr key={bot} className="hover:bg-background-hover">
                                <td className="px-4 py-3">
                                  <span className={`px-2 py-1 rounded text-xs font-medium ${getBotColor(bot)}`}>
                                    {bot}
                                  </span>
                                </td>
                                <td className="px-4 py-3 text-text-primary">{data.total ?? 0}</td>
                                <td className="px-4 py-3 text-green-400">{data.wins ?? 0}</td>
                                <td className="px-4 py-3 text-text-primary">{((data.win_rate ?? 0) * 100).toFixed(1)}%</td>
                                <td className="px-4 py-3 text-text-primary">{((data.avg_predicted_prob ?? 0) * 100).toFixed(1)}%</td>
                                <td className={`px-4 py-3 font-medium ${(data.pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  ${(data.pnl ?? 0).toFixed(0)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="card text-center py-12">
                  <BarChart3 className="w-12 h-12 mx-auto text-text-muted mb-3" />
                  <p className="text-text-secondary">No performance data available yet.</p>
                  <p className="text-text-muted text-sm mt-1">Performance metrics will appear once predictions have outcomes.</p>
                </div>
              )}
            </div>
            </ProphetErrorBoundary>
          )}

          {/* Training Tab */}
          {activeTab === 'training' && (
            <ProphetErrorBoundary>
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
                      {/* Model Age with freshness indicator (Issue #4) */}
                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Model Age</span>
                        <span className={`font-bold ${
                          trainingStatus.is_model_fresh === false ? 'text-red-400' :
                          (trainingStatus.hours_since_training ?? 0) > 12 ? 'text-yellow-400' : 'text-green-400'
                        }`}>
                          {trainingStatus.hours_since_training != null
                            ? `${trainingStatus.hours_since_training.toFixed(1)}h`
                            : 'Unknown'}
                          {trainingStatus.is_model_fresh === false && ' (STALE)'}
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
                      {/* Staleness warning (Issue #4 - end-to-end visibility) */}
                      {trainingStatus.is_model_fresh === false && (
                        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                          MODEL IS STALE ({trainingStatus.hours_since_training?.toFixed(1)}h old) - Predictions may be outdated. Retraining recommended.
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
                        Prophet automatically trains weekly (Sunday midnight CT) and when 100+ new outcomes are available.
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
                                <span className="text-text-primary ml-2">{((trainingResult.training_metrics.accuracy ?? 0) * 100).toFixed(1)}%</span>
                              </div>
                              <div>
                                <span className="text-text-muted">AUC-ROC:</span>
                                <span className="text-text-primary ml-2">{(trainingResult.training_metrics.auc_roc ?? 0).toFixed(3)}</span>
                              </div>
                              <div>
                                <span className="text-text-muted">Samples:</span>
                                <span className="text-text-primary ml-2">{trainingResult.training_metrics.total_samples ?? 0}</span>
                              </div>
                              <div>
                                <span className="text-text-muted">Method:</span>
                                <span className="text-text-primary ml-2">{trainingResult.method ?? 'N/A'}</span>
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
                            <span className="text-text-primary">{((trainingStatus.training_metrics.accuracy ?? 0) * 100).toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Precision:</span>
                            <span className="text-text-primary">{((trainingStatus.training_metrics.precision ?? 0) * 100).toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Recall:</span>
                            <span className="text-text-primary">{((trainingStatus.training_metrics.recall ?? 0) * 100).toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">F1 Score:</span>
                            <span className="text-text-primary">{((trainingStatus.training_metrics.f1_score ?? 0) * 100).toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">AUC-ROC:</span>
                            <span className="text-text-primary">{(trainingStatus.training_metrics.auc_roc ?? 0).toFixed(3)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Brier Score:</span>
                            <span className="text-text-primary">{(trainingStatus.training_metrics.brier_score ?? 0).toFixed(4)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Samples:</span>
                            <span className="text-text-primary">{trainingStatus.training_metrics.total_samples ?? 0}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-muted">Win Rate:</span>
                            <span className="text-text-primary">{((trainingStatus.training_metrics.win_rate_actual ?? 0) * 100).toFixed(1)}%</span>
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
            </ProphetErrorBoundary>
          )}

          {/* Live Logs Tab */}
          {activeTab === 'logs' && (
            <ProphetErrorBoundary>
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <Activity className="w-5 h-5 text-blue-400" />
                  Live Prophet Logs
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
                  <p className="text-text-muted text-sm text-center py-4">No logs yet. Prophet activity will appear here.</p>
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
                      {isPlainObject(log.data) && safeObjectKeys(log.data).length > 0 && (
                        <span className="text-text-muted" title={JSON.stringify(log.data, null, 2)}>
                          [data]
                        </span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
            </ProphetErrorBoundary>
          )}

          {/* Decision Log Tab */}
          {activeTab === 'decisions' && (
            <ProphetErrorBoundary>
            <div className="card">
              <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                <FileText className="w-5 h-5 text-green-500" />
                PROPHET Decision Log
              </h3>
              <DecisionLogViewer defaultBot="PROPHET" />
            </div>
            </ProphetErrorBoundary>
          )}

          {/* Data Flow Tab - FULL TRANSPARENCY */}
          {activeTab === 'dataflow' && (
            <ProphetErrorBoundary>
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
                    <Eye className="w-5 h-5 text-cyan-400" />
                    Prophet Data Flow - Full Transparency
                  </h3>
                  <p className="text-text-muted text-sm mt-1">
                    Complete visibility into all data passing through Prophet - inputs, ML outputs, Claude exchanges, and final decisions
                  </p>
                </div>
                <button
                  onClick={() => mutateTransparency()}
                  disabled={transparencyValidating}
                  className="btn-secondary flex items-center gap-2"
                >
                  <RefreshCw className={`w-4 h-4 ${transparencyValidating ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>

              {/* Claude AI Exchanges - Full Prompt/Response */}
              <div className="card">
                <h4 className="text-md font-semibold text-purple-300 mb-4 flex items-center gap-2">
                  <Sparkles className="w-5 h-5" />
                  Claude AI Exchanges ({claudeExchanges.length})
                  <span className="text-xs text-text-muted font-normal ml-2">Full prompt/response pairs</span>
                </h4>
                {claudeExchanges.length === 0 ? (
                  <div className="text-center py-8 text-text-muted">
                    <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p>No Claude AI exchanges recorded yet.</p>
                    <p className="text-xs mt-1">Exchanges will appear when bots consult Claude for validation.</p>
                  </div>
                ) : (
                  <div className="space-y-4 max-h-[600px] overflow-y-auto">
                    {claudeExchanges.slice().reverse().map((exchange: any, idx: number) => (
                      <div key={idx} className="bg-gray-900/50 rounded-lg border border-purple-500/20 overflow-hidden">
                        {/* Header */}
                        <div className="px-4 py-2 bg-purple-500/10 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <span className={`px-2 py-1 rounded text-xs font-bold ${getBotColor(exchange.bot_name)}`}>
                              {exchange.bot_name}
                            </span>
                            <span className="text-text-muted text-xs">
                              {formatTexasCentralDateTime(exchange.timestamp)}
                            </span>
                            {/* Hallucination Risk Badge */}
                            <span className={`px-2 py-1 rounded text-xs font-medium flex items-center gap-1 ${
                              exchange.hallucination_risk === 'LOW'
                                ? 'bg-green-500/20 text-green-400'
                                : exchange.hallucination_risk === 'MEDIUM'
                                  ? 'bg-yellow-500/20 text-yellow-400'
                                  : 'bg-red-500/20 text-red-400'
                            }`}>
                              {exchange.hallucination_risk === 'LOW' ? (
                                <CheckCircle className="w-3 h-3" />
                              ) : (
                                <AlertTriangle className="w-3 h-3" />
                              )}
                              {exchange.hallucination_risk === 'LOW' ? 'Verified' :
                               exchange.hallucination_risk === 'MEDIUM' ? 'Caution' : 'Risk'}
                            </span>
                          </div>
                          <div className="flex items-center gap-4 text-xs text-text-muted">
                            <span>{exchange.tokens_used} tokens</span>
                            <span>{exchange.response_time_ms}ms</span>
                            <span className="text-purple-400">{exchange.model}</span>
                          </div>
                        </div>

                        {/* Hallucination Warnings (if any) */}
                        {exchange.hallucination_risk !== 'LOW' && safeStringArray(exchange.hallucination_warnings).length > 0 && (
                          <div className={`px-4 py-3 border-b border-gray-700 ${
                            exchange.hallucination_risk === 'HIGH' ? 'bg-red-900/10' : 'bg-yellow-900/10'
                          }`}>
                            <p className={`text-xs font-semibold mb-2 flex items-center gap-2 ${
                              exchange.hallucination_risk === 'HIGH' ? 'text-red-400' : 'text-yellow-400'
                            }`}>
                              <AlertTriangle className="w-3 h-3" />
                              HALLUCINATION WARNINGS:
                            </p>
                            <ul className={`text-xs list-disc list-inside space-y-1 ${
                              exchange.hallucination_risk === 'HIGH' ? 'text-red-300/80' : 'text-yellow-300/80'
                            }`}>
                              {safeStringArray(exchange.hallucination_warnings).map((warning, wIdx) => (
                                <li key={wIdx}>{warning || 'Unknown warning'}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Data Citations (if verified) */}
                        {exchange.hallucination_risk === 'LOW' && safeStringArray(exchange.data_citations).length > 0 && (
                          <div className="px-4 py-3 border-b border-gray-700 bg-green-900/10">
                            <p className="text-xs text-green-400 font-semibold mb-2 flex items-center gap-2">
                              <CheckCircle className="w-3 h-3" />
                              DATA CITATIONS (VERIFIED):
                            </p>
                            <div className="flex flex-wrap gap-1">
                              {safeStringArray(exchange.data_citations).map((citation, cIdx) => (
                                <span key={cIdx} className="text-xs bg-green-500/20 text-green-300 px-2 py-0.5 rounded">
                                  {citation || 'Unknown citation'}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Market Context */}
                        <div className="px-4 py-3 border-b border-gray-700">
                          <p className="text-xs text-cyan-400 font-semibold mb-2">MARKET CONTEXT:</p>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                            <div>
                              <span className="text-text-muted">Spot:</span>
                              <span className="ml-1 text-text-primary">
                                {exchange.market_context?.spot_price != null
                                  ? `$${safeNumber(exchange.market_context.spot_price)}`
                                  : 'N/A'}
                              </span>
                            </div>
                            <div>
                              <span className="text-text-muted">VIX:</span>
                              <span className="ml-1 text-text-primary">
                                {safeNumber(exchange.market_context?.vix)}
                              </span>
                            </div>
                            <div>
                              <span className="text-text-muted">GEX Regime:</span>
                              <span className={`ml-1 font-medium ${
                                exchange.market_context?.gex_regime === 'POSITIVE' ? 'text-green-400' :
                                exchange.market_context?.gex_regime === 'NEGATIVE' ? 'text-red-400' : 'text-yellow-400'
                              }`}>{exchange.market_context?.gex_regime || 'N/A'}</span>
                            </div>
                            <div>
                              <span className="text-text-muted">Between Walls:</span>
                              <span className={`ml-1 ${exchange.market_context?.gex_between_walls ? 'text-green-400' : 'text-red-400'}`}>
                                {exchange.market_context?.gex_between_walls != null
                                  ? (exchange.market_context.gex_between_walls ? 'Yes' : 'No')
                                  : 'N/A'}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* ML Prediction */}
                        <div className="px-4 py-3 border-b border-gray-700">
                          <p className="text-xs text-yellow-400 font-semibold mb-2">ML PREDICTION:</p>
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <div>
                              <span className="text-text-muted">Win Probability:</span>
                              <span className="ml-1 text-text-primary font-bold">
                                {exchange.ml_prediction?.win_probability != null
                                  ? safePercent(exchange.ml_prediction.win_probability)
                                  : 'N/A'}
                              </span>
                            </div>
                            <div>
                              <span className="text-text-muted">Top Factors:</span>
                              <span className="ml-1 text-text-primary">
                                {(() => {
                                  try {
                                    const factors = exchange.ml_prediction?.top_factors
                                    // Handle array format: [["factor1", 0.5], ["factor2", 0.3]]
                                    if (Array.isArray(factors) && factors.length > 0) {
                                      return factors.slice(0, 3).map((f: unknown) => {
                                        if (typeof f === 'string') return f
                                        if (Array.isArray(f) && f.length > 0) return String(f[0])
                                        if (typeof f === 'object' && f !== null) return String((f as Record<string, unknown>)[0] || 'Unknown')
                                        return String(f)
                                      }).join(', ')
                                    }
                                    // Handle object format: { factor1: 0.5, factor2: 0.3 }
                                    if (isPlainObject(factors)) {
                                      const keys = safeObjectKeys(factors)
                                      if (keys.length === 0) return 'N/A'
                                      return keys.slice(0, 3).join(', ')
                                    }
                                    return 'N/A'
                                  } catch {
                                    return 'N/A'
                                  }
                                })()}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Full Prompt */}
                        <div className="px-4 py-3 border-b border-gray-700">
                          <p className="text-xs text-blue-400 font-semibold mb-2">PROMPT SENT TO CLAUDE:</p>
                          <div className="bg-gray-900 rounded p-3 max-h-40 overflow-y-auto">
                            <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">
                              {exchange.prompt_sent}
                            </pre>
                          </div>
                        </div>

                        {/* Full Response */}
                        <div className="px-4 py-3">
                          <p className="text-xs text-purple-400 font-semibold mb-2">RESPONSE FROM CLAUDE:</p>
                          <div className="bg-purple-900/20 rounded p-3 max-h-40 overflow-y-auto">
                            <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">
                              {exchange.response_received}
                            </pre>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Data Flow Records */}
              <div className="card">
                <h4 className="text-md font-semibold text-cyan-300 mb-4 flex items-center gap-2">
                  <Activity className="w-5 h-5" />
                  Data Flow Pipeline ({dataFlows.length})
                  <span className="text-xs text-text-muted font-normal ml-2">INPUT → ML_OUTPUT → DECISION stages</span>
                </h4>
                {dataFlows.length === 0 ? (
                  <div className="text-center py-8 text-text-muted">
                    <TrendingUp className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p>No data flows recorded yet.</p>
                    <p className="text-xs mt-1">Data will appear when Prophet processes predictions.</p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[400px] overflow-y-auto">
                    {dataFlows.slice().reverse().map((flow: any, idx: number) => (
                      <div key={idx} className="flex items-start gap-4 p-3 bg-gray-900/30 rounded-lg hover:bg-gray-900/50 transition-colors">
                        <div className="flex-shrink-0">
                          <span className={`px-2 py-1 rounded text-xs font-bold ${getBotColor(flow.bot_name)}`}>
                            {flow.bot_name}
                          </span>
                        </div>
                        <div className="flex-shrink-0">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            flow.stage === 'INPUT' ? 'bg-cyan-500/20 text-cyan-400' :
                            flow.stage === 'ML_OUTPUT' ? 'bg-yellow-500/20 text-yellow-400' :
                            flow.stage === 'DECISION' ? 'bg-green-500/20 text-green-400' :
                            'bg-gray-500/20 text-gray-400'
                          }`}>
                            {flow.stage}
                          </span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs text-text-muted mb-1">
                            {formatTexasCentralDateTime(flow.timestamp)}
                          </div>
                          <pre className="text-xs text-text-secondary whitespace-pre-wrap overflow-x-auto">
                            {JSON.stringify(flow.data, null, 2)}
                          </pre>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Summary Stats */}
              {transparencyRes?.summary && (
                <div className="grid grid-cols-3 gap-4">
                  <div className="card text-center">
                    <p className="text-text-muted text-sm">Total Logs</p>
                    <p className="text-2xl font-bold text-text-primary">{transparencyRes.summary.total_logs ?? 0}</p>
                  </div>
                  <div className="card text-center">
                    <p className="text-text-muted text-sm">Data Flows</p>
                    <p className="text-2xl font-bold text-cyan-400">{transparencyRes.summary.total_data_flows ?? 0}</p>
                  </div>
                  <div className="card text-center">
                    <p className="text-text-muted text-sm">Claude Exchanges</p>
                    <p className="text-2xl font-bold text-purple-400">{transparencyRes.summary.total_claude_exchanges ?? 0}</p>
                  </div>
                </div>
              )}
            </div>
            </ProphetErrorBoundary>
          )}

          {/* Decision Formulas Tab */}
          {activeTab === 'formulas' && (
            <div className="space-y-6">
              <div className="card">
                <h3 className="text-lg font-semibold text-purple-400 mb-4 flex items-center gap-2">
                  <Sparkles className="w-5 h-5" />
                  Prophet Decision Formulas
                </h3>
                <p className="text-text-secondary mb-6">
                  Complete reference of all formulas and thresholds Prophet uses to make trading decisions.
                </p>

                {/* Win Probability Thresholds */}
                <div className="mb-8">
                  <h4 className="text-md font-semibold text-green-400 mb-3 flex items-center gap-2">
                    <Target className="w-4 h-4" />
                    Win Probability → Trading Decision
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-green-400 font-bold">TRADE_FULL</span>
                        <span className="text-gray-400 ml-2">Full position size</span>
                      </div>
                      <code className="bg-green-900/30 text-green-300 px-3 py-1 rounded font-mono text-sm">
                        win_probability ≥ 70%
                      </code>
                    </div>
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-yellow-400 font-bold">TRADE_REDUCED</span>
                        <span className="text-gray-400 ml-2">Scaled position</span>
                      </div>
                      <code className="bg-yellow-900/30 text-yellow-300 px-3 py-1 rounded font-mono text-sm">
                        55% ≤ win_probability &lt; 70%
                      </code>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-red-400 font-bold">SKIP_TODAY</span>
                        <span className="text-gray-400 ml-2">No trade</span>
                      </div>
                      <code className="bg-red-900/30 text-red-300 px-3 py-1 rounded font-mono text-sm">
                        win_probability &lt; 55%
                      </code>
                    </div>
                  </div>
                </div>

                {/* Risk Percentage Formula */}
                <div className="mb-8">
                  <h4 className="text-md font-semibold text-blue-400 mb-3 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4" />
                    Risk Percentage Formula (for TRADE_REDUCED)
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <code className="block bg-blue-900/30 text-blue-300 p-4 rounded font-mono text-sm mb-3">
                      risk% = 3.0 + ((win_prob - 0.55) / 0.15) × 5.0
                    </code>
                    <div className="text-sm text-gray-400 space-y-1">
                      <p>• At 55% win probability → <span className="text-white">3% risk</span></p>
                      <p>• At 62.5% win probability → <span className="text-white">5.5% risk</span></p>
                      <p>• At 70% win probability → <span className="text-white">8% risk</span></p>
                      <p>• Above 70% (TRADE_FULL) → <span className="text-white">10% risk</span></p>
                    </div>
                  </div>
                </div>

                {/* VIX Skip Rules */}
                <div className="mb-8">
                  <h4 className="text-md font-semibold text-red-400 mb-3 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" />
                    VIX Skip Rules (Automatic SKIP_TODAY)
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-red-400 font-bold">Hard VIX Skip</span>
                        <span className="text-gray-400 ml-2">Any day</span>
                      </div>
                      <code className="bg-red-900/30 text-red-300 px-3 py-1 rounded font-mono text-sm">
                        VIX &gt; 32 → SKIP
                      </code>
                    </div>
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-orange-400 font-bold">Monday/Friday Skip</span>
                        <span className="text-gray-400 ml-2">Higher risk days</span>
                      </div>
                      <code className="bg-orange-900/30 text-orange-300 px-3 py-1 rounded font-mono text-sm">
                        VIX &gt; 30 on Mon/Fri → SKIP
                      </code>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-yellow-400 font-bold">Streak Skip</span>
                        <span className="text-gray-400 ml-2">After 2+ losses</span>
                      </div>
                      <code className="bg-yellow-900/30 text-yellow-300 px-3 py-1 rounded font-mono text-sm">
                        VIX &gt; 28 + recent_losses ≥ 2 → SKIP
                      </code>
                    </div>
                  </div>
                </div>

                {/* GEX Adjustments */}
                <div className="mb-8">
                  <h4 className="text-md font-semibold text-cyan-400 mb-3 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4" />
                    GEX-Based Win Probability Adjustments
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-green-400 font-bold">Inside GEX Walls</span>
                        <span className="text-gray-400 ml-2">Protected zone</span>
                      </div>
                      <code className="bg-green-900/30 text-green-300 px-3 py-1 rounded font-mono text-sm">
                        win_probability += 3%
                      </code>
                    </div>
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-yellow-400 font-bold">Near Wall (&lt;0.5%)</span>
                        <span className="text-gray-400 ml-2">Breakout risk</span>
                      </div>
                      <code className="bg-yellow-900/30 text-yellow-300 px-3 py-1 rounded font-mono text-sm">
                        win_probability -= 5%
                      </code>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-red-400 font-bold">Outside Walls</span>
                        <span className="text-gray-400 ml-2">Unprotected</span>
                      </div>
                      <code className="bg-red-900/30 text-red-300 px-3 py-1 rounded font-mono text-sm">
                        win_probability -= 3%
                      </code>
                    </div>
                  </div>
                </div>

                {/* SD Multiplier Logic */}
                <div className="mb-8">
                  <h4 className="text-md font-semibold text-purple-400 mb-3 flex items-center gap-2">
                    <Crosshair className="w-4 h-4" />
                    Strike Distance (SD Multiplier)
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-green-400 font-bold">High Confidence</span>
                        <span className="text-gray-400 ml-2">win_prob ≥ 70%</span>
                      </div>
                      <code className="bg-green-900/30 text-green-300 px-3 py-1 rounded font-mono text-sm">
                        SD = 1.0 (at expected move)
                      </code>
                    </div>
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-yellow-400 font-bold">Medium Confidence</span>
                        <span className="text-gray-400 ml-2">60% ≤ win_prob &lt; 70%</span>
                      </div>
                      <code className="bg-yellow-900/30 text-yellow-300 px-3 py-1 rounded font-mono text-sm">
                        SD = 1.1 (wider strikes)
                      </code>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-red-400 font-bold">Low Confidence</span>
                        <span className="text-gray-400 ml-2">win_prob &lt; 60%</span>
                      </div>
                      <code className="bg-red-900/30 text-red-300 px-3 py-1 rounded font-mono text-sm">
                        SD = 1.2 (widest strikes)
                      </code>
                    </div>
                  </div>
                </div>

                {/* Hallucination Risk Penalties */}
                <div className="mb-8">
                  <h4 className="text-md font-semibold text-orange-400 mb-3 flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4" />
                    Claude Hallucination Risk Penalties
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-gray-700 pb-2">
                      <div>
                        <span className="text-red-400 font-bold">HIGH Risk</span>
                        <span className="text-gray-400 ml-2">Unreliable analysis</span>
                      </div>
                      <code className="bg-red-900/30 text-red-300 px-3 py-1 rounded font-mono text-sm">
                        win_probability -= 10%
                      </code>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-yellow-400 font-bold">MEDIUM Risk</span>
                        <span className="text-gray-400 ml-2">Uncertain analysis</span>
                      </div>
                      <code className="bg-yellow-900/30 text-yellow-300 px-3 py-1 rounded font-mono text-sm">
                        win_probability -= 5%
                      </code>
                    </div>
                  </div>
                </div>

                {/* ML Feature Columns */}
                <div className="mb-8">
                  <h4 className="text-md font-semibold text-indigo-400 mb-3 flex items-center gap-2">
                    <Brain className="w-4 h-4" />
                    ML Model Features
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                      {[
                        'vix', 'vix_percentile_30d', 'vix_change_1d',
                        'day_of_week', 'hour', 'days_to_expiry',
                        'gex_normalized', 'gex_regime_encoded', 'put_wall_distance',
                        'call_wall_distance', 'is_between_walls'
                      ].map((feature) => (
                        <code key={feature} className="bg-indigo-900/30 text-indigo-300 px-2 py-1 rounded text-xs font-mono">
                          {feature}
                        </code>
                      ))}
                    </div>
                  </div>
                </div>

                {/* SOLOMON Direction Override */}
                <div className="mb-8">
                  <h4 className="text-md font-semibold text-pink-400 mb-3 flex items-center gap-2">
                    <Zap className="w-4 h-4" />
                    SOLOMON Prophet Direction Override
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <code className="block bg-pink-900/30 text-pink-300 p-4 rounded font-mono text-sm mb-3">
                      IF oracle_confidence ≥ 85% AND oracle_win_prob ≥ 60%{'\n'}
                      THEN use Prophet direction instead of wall direction
                    </code>
                    <p className="text-sm text-gray-400">
                      Prophet can override wall-based direction when it has very high confidence in its prediction.
                    </p>
                  </div>
                </div>

                {/* Top Factors Adjustments */}
                <div>
                  <h4 className="text-md font-semibold text-emerald-400 mb-3 flex items-center gap-2">
                    <Activity className="w-4 h-4" />
                    Top Factors Confidence Adjustments
                  </h4>
                  <div className="bg-gray-900/50 rounded-lg p-4 space-y-3">
                    <div className="border-b border-gray-700 pb-2">
                      <span className="text-emerald-400 font-bold">VIX Factor High Importance (&gt;20%)</span>
                      <div className="text-sm text-gray-400 mt-1 space-y-1">
                        <p>• VIX &gt; 25: <code className="bg-red-900/30 text-red-300 px-1 rounded">-up to 8%</code></p>
                        <p>• VIX &lt; 14: <code className="bg-green-900/30 text-green-300 px-1 rounded">+up to 5%</code></p>
                      </div>
                    </div>
                    <div className="border-b border-gray-700 pb-2">
                      <span className="text-emerald-400 font-bold">GEX Regime Factor High Importance (&gt;15%)</span>
                      <div className="text-sm text-gray-400 mt-1 space-y-1">
                        <p>• NEGATIVE regime: <code className="bg-red-900/30 text-red-300 px-1 rounded">-5%</code> (for ICs)</p>
                        <p>• POSITIVE regime: <code className="bg-green-900/30 text-green-300 px-1 rounded">+3%</code></p>
                      </div>
                    </div>
                    <div>
                      <span className="text-emerald-400 font-bold">Day of Week Factor High Importance (&gt;15%)</span>
                      <div className="text-sm text-gray-400 mt-1 space-y-1">
                        <p>• Monday/Tuesday: <code className="bg-green-900/30 text-green-300 px-1 rounded">+3%</code></p>
                        <p>• Friday: <code className="bg-red-900/30 text-red-300 px-1 rounded">-3%</code></p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Info Section - All 6 Trading Bots */}
          <div className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="card bg-red-500/5 border border-red-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-red-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">FORTRESS</h3>
                  <p className="text-text-secondary text-sm">0DTE SPY Iron Condors with GEX-protected strikes</p>
                </div>
              </div>
            </div>

            <div className="card bg-cyan-500/5 border border-cyan-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">SOLOMON</h3>
                  <p className="text-text-secondary text-sm">GEX-based directional spreads trading</p>
                </div>
              </div>
            </div>

            <div className="card bg-blue-500/5 border border-blue-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-blue-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">ANCHOR</h3>
                  <p className="text-text-secondary text-sm">SPX Iron Condors with Prophet intelligence</p>
                </div>
              </div>
            </div>

            <div className="card bg-rose-500/5 border border-rose-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-rose-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">LAZARUS</h3>
                  <p className="text-text-secondary text-sm">Momentum continuation with GEX-confirmed bias</p>
                </div>
              </div>
            </div>

            <div className="card bg-indigo-500/5 border border-indigo-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-indigo-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">CORNERSTONE</h3>
                  <p className="text-text-secondary text-sm">Mean-reversion trading at key GEX levels</p>
                </div>
              </div>
            </div>

            <div className="card bg-orange-500/5 border border-orange-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-orange-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">GIDEON</h3>
                  <p className="text-text-secondary text-sm">Aggressive GEX-based directional spreads</p>
                </div>
              </div>
            </div>

            <div className="card bg-teal-500/5 border border-teal-500/20">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-teal-400 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-text-primary mb-1">SAMSON</h3>
                  <p className="text-text-secondary text-sm">Aggressive SPX Iron Condors with $12 spreads</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
