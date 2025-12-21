'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  TestTube, TrendingUp, TrendingDown, Activity, BarChart3, PlayCircle,
  RefreshCw, AlertTriangle, Calendar, Clock, Loader2, CheckCircle,
  Settings, DollarSign, Target, Layers, ChevronDown, ChevronUp,
  Download, FileSpreadsheet, LineChart, PieChart, ArrowUpDown,
  Database, Info, Percent, Shield, Zap, Search
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import EnhancedEquityCurve from '@/components/backtest/EnhancedEquityCurve'
import { apiClient } from '@/lib/api'
import {
  LineChart as RechartsLine, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, BarChart, Bar, Cell, AreaChart, Area, ComposedChart
} from 'recharts'

interface BacktestConfig {
  start_date: string
  end_date: string
  initial_capital: number
  spread_width: number
  sd_multiplier: number
  risk_per_trade_pct: number
  ticker: string
  strategy: string
  // New enhanced parameters
  strategy_type: string
  // Strike selection method
  strike_selection: 'sd' | 'fixed' | 'delta'
  fixed_strike_distance: number
  target_delta: number
  min_vix: number | null
  max_vix: number | null
  stop_loss_pct: number | null
  profit_target_pct: number | null
  trade_monday: boolean
  trade_tuesday: boolean
  trade_wednesday: boolean
  trade_thursday: boolean
  trade_friday: boolean
  max_contracts_override: number | null
  commission_per_leg: number | null
  slippage_per_spread: number | null
  hold_days: number
  wall_proximity_pct: number
}

interface BacktestJob {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  progress_message: string
  result: any
  error: string | null
  created_at: string
  completed_at: string | null
}

interface Strategy {
  id: string
  name: string
  description: string
  features: string[]
  recommended_settings: {
    risk_per_trade_pct: number
    sd_multiplier: number
    spread_width: number
  }
}

interface StrategyType {
  id: string
  name: string
  description: string
  legs: number
  direction: string
  credit: boolean
  warning?: string
}

interface Tier {
  name: string
  equity_range: string
  options_dte: string
  sd_days: number
  max_contracts: number
  trades_per_week: number
  description: string
}

interface BacktestResult {
  id: number
  job_id: string
  created_at: string
  strategy: string
  ticker: string
  start_date: string
  end_date: string
  initial_capital: number
  final_equity: number
  total_pnl: number
  total_return_pct: number
  avg_monthly_return_pct: number
  max_drawdown_pct: number
  total_trades: number
  win_rate: number
  profit_factor: number
  total_costs: number
  tier_stats: any
  monthly_returns: any
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function ZeroDTEBacktestPage() {
  // Configuration state
  const [config, setConfig] = useState<BacktestConfig>({
    start_date: '2022-01-01',
    end_date: '2025-12-01',
    initial_capital: 1000000,
    spread_width: 10,
    sd_multiplier: 1.0,
    risk_per_trade_pct: 5.0,
    ticker: 'SPX',
    strategy: 'hybrid_fixed',
    // New parameters
    strategy_type: 'iron_condor',
    // Strike selection
    strike_selection: 'sd',
    fixed_strike_distance: 50,
    target_delta: 0.16,
    min_vix: null,
    max_vix: null,
    stop_loss_pct: null,
    profit_target_pct: null,
    trade_monday: true,
    trade_tuesday: true,
    trade_wednesday: true,
    trade_thursday: true,
    trade_friday: true,
    max_contracts_override: null,
    commission_per_leg: null,
    slippage_per_spread: null,
    hold_days: 1,
    wall_proximity_pct: 1.0,
  })

  // UI state
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [strategyTypes, setStrategyTypes] = useState<StrategyType[]>([])
  const [tiers, setTiers] = useState<Tier[]>([])
  const [results, setResults] = useState<BacktestResult[]>([])
  const [presets, setPresets] = useState<any[]>([])
  const [savedStrategies, setSavedStrategies] = useState<any[]>([])
  const [selectedResult, setSelectedResult] = useState<BacktestResult | null>(null)
  const [liveJobResult, setLiveJobResult] = useState<any>(null)

  // Job state
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  const [completedJobId, setCompletedJobId] = useState<string | null>(null)  // Keep job_id for exports
  const [jobStatus, setJobStatus] = useState<BacktestJob | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // UI toggles
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showTiers, setShowTiers] = useState(false)
  const [showRiskSettings, setShowRiskSettings] = useState(false)
  const [showDataInfo, setShowDataInfo] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'charts' | 'trades' | 'compare' | 'analytics'>('overview')

  // Analytics state
  const [analyticsData, setAnalyticsData] = useState<any>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [selectedTradeForInspection, setSelectedTradeForInspection] = useState<number | null>(null)
  const [tradeInspectorData, setTradeInspectorData] = useState<any>(null)

  // Backend connection status
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'error'>('checking')
  const [oratDataInfo, setOratDataInfo] = useState<any>(null)

  // Comparison state
  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([])

  // Oracle AI state
  const [oracleStatus, setOracleStatus] = useState<any>(null)
  const [oracleLogs, setOracleLogs] = useState<any[]>([])
  const [showOracleLogs, setShowOracleLogs] = useState(false)

  // Natural Language Backtest state
  const [nlQuery, setNlQuery] = useState('')
  const [nlParsedConfig, setNlParsedConfig] = useState<any>(null)
  const [showNlInput, setShowNlInput] = useState(false)

  // Preset application feedback
  const [presetAppliedMessage, setPresetAppliedMessage] = useState<string | null>(null)

  // Check backend health on mount
  const checkBackendHealth = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/health`)
      if (response.ok) {
        const data = await response.json()
        setBackendStatus('connected')
        if (data.orat_data?.status === 'available') {
          setOratDataInfo(data.orat_data)
        }
      } else {
        setBackendStatus('error')
        setError(`Backend returned HTTP ${response.status}`)
      }
    } catch (err) {
      setBackendStatus('error')
      setError(`Cannot connect to backend at ${API_URL}. Start it with: python backend/main.py`)
    }
  }

  // Load Oracle status
  const loadOracleStatus = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/oracle/status`)
      if (response.ok) {
        const data = await response.json()
        if (data.success) {
          setOracleStatus(data.oracle)
        }
      }
    } catch (err) {
      console.error('Failed to load Oracle status:', err)
    }
  }

  // Load Oracle logs
  const loadOracleLogs = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/oracle/logs?limit=20`)
      if (response.ok) {
        const data = await response.json()
        if (data.success) {
          setOracleLogs(data.logs || [])
        }
      }
    } catch (err) {
      console.error('Failed to load Oracle logs:', err)
    }
  }

  // PERFORMANCE FIX: Single consolidated init call instead of 8+ separate calls
  const loadKronosInit = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/init`)
      if (response.ok) {
        const data = await response.json()
        if (data.success) {
          // Set all data from single response
          if (data.health?.status === 'ok') {
            setBackendStatus('connected')
          } else if (data.health?.status === 'degraded') {
            setBackendStatus('connected')
          }
          if (data.strategies) setStrategies(data.strategies)
          if (data.strategy_types) setStrategyTypes(data.strategy_types)
          if (data.tiers) setTiers(data.tiers)
          if (data.presets) setPresets(data.presets)
          if (data.saved_strategies) setSavedStrategies(data.saved_strategies)
          if (data.oracle) setOracleStatus(data.oracle)
          // Load full results separately (init only returns summary)
          loadResults()
          return
        }
      }
      // Fallback to individual calls if init fails
      console.warn('Init endpoint failed, falling back to individual calls')
      checkBackendHealth()
      loadStrategies()
      loadStrategyTypes()
      loadTiers()
      loadResults()
      loadPresets()
      loadSavedStrategies()
      loadOracleStatus()
    } catch (err) {
      console.error('Init failed, using fallback:', err)
      checkBackendHealth()
      loadStrategies()
      loadStrategyTypes()
      loadTiers()
      loadResults()
      loadPresets()
      loadSavedStrategies()
      loadOracleStatus()
    }
  }

  // Load all data on mount using consolidated endpoint
  useEffect(() => {
    loadKronosInit()
  }, [])

  // Auto-refresh Oracle logs when panel is open
  useEffect(() => {
    if (showOracleLogs) {
      loadOracleLogs()
      const interval = setInterval(loadOracleLogs, 3000) // Refresh every 3s
      return () => clearInterval(interval)
    }
  }, [showOracleLogs])

  const loadPresets = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/presets`)
      if (!response.ok) {
        console.error(`Failed to load presets: HTTP ${response.status}`)
        return
      }
      const data = await response.json()
      if (data.presets) {
        setPresets(data.presets)
      }
    } catch (err) {
      console.error('Failed to load presets:', err)
    }
  }

  const loadSavedStrategies = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/saved-strategies`)
      if (!response.ok) {
        console.error(`Failed to load saved strategies: HTTP ${response.status}`)
        return
      }
      const data = await response.json()
      if (data.strategies) {
        setSavedStrategies(data.strategies)
      }
    } catch (err) {
      console.error('Failed to load saved strategies:', err)
    }
  }

  const applyPreset = (presetId: string) => {
    const preset = presets.find(p => p.id === presetId) || savedStrategies.find(s => s.id === presetId)
    if (preset && preset.config) {
      setConfig(prev => ({
        ...prev,
        ...preset.config,
        // Preserve date range and capital
        start_date: prev.start_date,
        end_date: prev.end_date,
        initial_capital: prev.initial_capital,
      }))
      // Show feedback message
      setPresetAppliedMessage(`Applied preset: ${preset.name}`)
      setTimeout(() => setPresetAppliedMessage(null), 3000)
    }
  }

  const saveCurrentStrategy = async () => {
    const name = prompt('Enter a name for this strategy:')
    if (!name) return

    const description = prompt('Enter a description (optional):') || ''

    try {
      const response = await fetch(`${API_URL}/api/zero-dte/saved-strategies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          description,
          config: config,
          tags: []
        })
      })

      if (response.ok) {
        alert('Strategy saved successfully!')
        loadSavedStrategies()
      } else {
        alert('Failed to save strategy')
      }
    } catch (err) {
      console.error('Failed to save strategy:', err)
      alert('Failed to save strategy')
    }
  }

  // PERFORMANCE FIX: Use WebSocket -> SSE -> Polling cascade for real-time progress
  useEffect(() => {
    if (!currentJobId || !running) return

    let websocket: WebSocket | null = null
    let eventSource: EventSource | null = null
    let fallbackInterval: NodeJS.Timeout | null = null
    let connectionMethod = 'none'

    // Handle job update from any source
    function handleJobUpdate(data: any) {
      setJobStatus(prev => ({
        ...prev,
        job_id: data.job_id || currentJobId,
        status: data.status,
        progress: data.progress,
        progress_message: data.progress_message || '',
        result: null,
        error: data.error || null,
        created_at: prev?.created_at || new Date().toISOString(),
        completed_at: data.status === 'completed' ? new Date().toISOString() : null,
      }))

      if (data.status === 'completed') {
        setRunning(false)
        setCompletedJobId(currentJobId)
        setCurrentJobId(null)
        // Fetch full result
        fetch(`${API_URL}/api/zero-dte/job/${currentJobId}`)
          .then(res => res.json())
          .then(fullData => {
            if (fullData.job?.result) {
              setLiveJobResult(fullData.job.result)
            }
          })
        loadResults()
        cleanup()
      } else if (data.status === 'failed') {
        setRunning(false)
        setCurrentJobId(null)
        setError(data.error || 'Backtest failed')
        cleanup()
      } else if (data.status === 'not_found') {
        setRunning(false)
        setCurrentJobId(null)
        setError('Job not found - backend may have restarted.')
        cleanup()
      }
    }

    function cleanup() {
      websocket?.close()
      eventSource?.close()
      if (fallbackInterval) clearInterval(fallbackInterval)
    }

    // 1. Try WebSocket first (fastest, bidirectional)
    function tryWebSocket() {
      try {
        const wsUrl = API_URL.replace('http://', 'ws://').replace('https://', 'wss://')
        websocket = new WebSocket(`${wsUrl}/ws/kronos/job/${currentJobId}`)

        websocket.onopen = () => {
          connectionMethod = 'websocket'
          console.log('KRONOS: Connected via WebSocket')
        }

        websocket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.type === 'job_update' || data.type === 'job_complete') {
              handleJobUpdate(data)
            }
          } catch (e) {
            console.error('WebSocket message parse error:', e)
          }
        }

        websocket.onerror = () => {
          console.warn('WebSocket failed, trying SSE...')
          websocket?.close()
          websocket = null
          trySSE()
        }

        websocket.onclose = () => {
          if (connectionMethod === 'websocket' && running) {
            // Unexpected close, try SSE
            trySSE()
          }
        }
      } catch (e) {
        console.warn('WebSocket not available, trying SSE...')
        trySSE()
      }
    }

    // 2. Try SSE as fallback (one-way, simpler)
    function trySSE() {
      if (connectionMethod !== 'none' && connectionMethod !== 'websocket') return

      try {
        eventSource = new EventSource(`${API_URL}/api/zero-dte/job/${currentJobId}/stream`)

        eventSource.onopen = () => {
          connectionMethod = 'sse'
          console.log('KRONOS: Connected via SSE')
        }

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            handleJobUpdate(data)
          } catch (e) {
            console.error('SSE message parse error:', e)
          }
        }

        eventSource.onerror = () => {
          console.warn('SSE failed, falling back to polling...')
          eventSource?.close()
          eventSource = null
          startFallbackPolling()
        }
      } catch (e) {
        console.warn('SSE not available, using polling...')
        startFallbackPolling()
      }
    }

    // 3. Polling as last resort
    function startFallbackPolling() {
      if (fallbackInterval) return
      connectionMethod = 'polling'
      console.log('KRONOS: Using polling fallback')

      fallbackInterval = setInterval(async () => {
        try {
          const response = await fetch(`${API_URL}/api/zero-dte/job/${currentJobId}`)
          if (!response.ok) {
            if (response.status === 404) {
              handleJobUpdate({ status: 'not_found' })
            }
            return
          }
          const data = await response.json()
          if (data.job) {
            handleJobUpdate({
              status: data.job.status,
              progress: data.job.progress,
              progress_message: data.job.progress_message,
              error: data.job.error,
            })
            if (data.job.status === 'completed') {
              setLiveJobResult(data.job.result)
            }
          }
        } catch (err) {
          console.error('Polling failed:', err)
        }
      }, 2000)
    }

    // Start connection cascade
    tryWebSocket()

    return cleanup
  }, [currentJobId, running])

  const loadStrategies = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/strategies`)
      if (!response.ok) {
        console.error(`Failed to load strategies: HTTP ${response.status}`)
        return
      }
      const data = await response.json()
      if (data.strategies) {
        setStrategies(data.strategies)
      }
    } catch (err) {
      console.error('Failed to load strategies:', err)
    }
  }

  const loadStrategyTypes = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/strategy-types`)
      if (!response.ok) {
        console.error(`Failed to load strategy types: HTTP ${response.status}`)
        return
      }
      const data = await response.json()
      if (data.strategy_types) {
        setStrategyTypes(data.strategy_types)
      }
    } catch (err) {
      console.error('Failed to load strategy types:', err)
    }
  }

  const loadTiers = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/tiers`)
      if (!response.ok) {
        console.error(`Failed to load tiers: HTTP ${response.status}`)
        return
      }
      const data = await response.json()
      if (data.tiers) {
        setTiers(data.tiers)
      }
    } catch (err) {
      console.error('Failed to load tiers:', err)
    }
  }

  const loadResults = async () => {
    try {
      const response = await fetch(`${API_URL}/api/zero-dte/results`)
      if (!response.ok) {
        console.error(`Failed to load results: HTTP ${response.status}`)
        return
      }
      const data = await response.json()
      if (data.results) {
        setResults(data.results)
        if (data.results.length > 0 && !selectedResult) {
          setSelectedResult(data.results[0])
        }
      }
    } catch (err) {
      console.error('Failed to load results:', err)
    }
  }

  const runBacktest = async () => {
    // Prevent double-clicks
    if (running) return

    // Validation
    const validationErrors: string[] = []

    // Check date range
    if (config.start_date >= config.end_date) {
      validationErrors.push('Start date must be before end date')
    }

    // Check at least one trading day is selected
    const tradingDaysSelected = [
      config.trade_monday,
      config.trade_tuesday,
      config.trade_wednesday,
      config.trade_thursday,
      config.trade_friday
    ].some(day => day)

    if (!tradingDaysSelected) {
      validationErrors.push('At least one trading day must be selected')
    }

    // Check VIX filter is valid
    if (config.min_vix !== null && config.max_vix !== null && config.min_vix >= config.max_vix) {
      validationErrors.push('Min VIX must be less than Max VIX')
    }

    // Check risk per trade is reasonable
    if (config.risk_per_trade_pct <= 0 || config.risk_per_trade_pct > 100) {
      validationErrors.push('Risk per trade must be between 0 and 100%')
    }

    if (validationErrors.length > 0) {
      setError(validationErrors.join('. '))
      return
    }

    setRunning(true)
    setError(null)
    setJobStatus(null)
    setLiveJobResult(null)
    setCompletedJobId(null)  // Clear old completed job

    try {
      const response = await fetch(`${API_URL}/api/zero-dte/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      })

      // Handle HTTP errors before trying to parse JSON
      if (!response.ok) {
        let errorMessage = `Server error: HTTP ${response.status}`
        try {
          const errorData = await response.json()
          errorMessage = errorData.detail || errorData.error || errorMessage
        } catch {
          // If response isn't JSON, use status text
          errorMessage = `Server error: ${response.status} ${response.statusText}`
        }
        setError(errorMessage)
        setRunning(false)
        return
      }

      const data = await response.json()

      if (data.job_id) {
        setCurrentJobId(data.job_id)
        setJobStatus({
          job_id: data.job_id,
          status: 'pending',
          progress: 0,
          progress_message: 'Job queued...',
          result: null,
          error: null,
          created_at: new Date().toISOString(),
          completed_at: null
        })
      } else {
        setError(data.error || 'Failed to start backtest - no job_id returned')
        setRunning(false)
      }
    } catch (err: any) {
      // Network error or backend not running
      setError(`Cannot connect to backend at ${API_URL}. Is the server running?`)
      setRunning(false)
    }
  }

  // Natural Language Backtest with Claude
  const runNaturalLanguageBacktest = async () => {
    if (!nlQuery.trim() || running) return

    setRunning(true)
    setError(null)
    setJobStatus(null)
    setLiveJobResult(null)
    setCompletedJobId(null)
    setNlParsedConfig(null)

    try {
      const response = await fetch(`${API_URL}/api/zero-dte/natural-language`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: nlQuery })
      })

      if (!response.ok) {
        let errorMessage = `Server error: HTTP ${response.status}`
        try {
          const errorData = await response.json()
          errorMessage = errorData.detail || errorData.error || errorMessage
        } catch {
          errorMessage = `Server error: ${response.status} ${response.statusText}`
        }
        setError(errorMessage)
        setRunning(false)
        return
      }

      const data = await response.json()

      if (data.success && data.job_id) {
        setNlParsedConfig({
          parsing_method: data.parsing_method,
          parsed: data.parsed_config,
          full: data.full_config
        })
        setCurrentJobId(data.job_id)
        setJobStatus({
          job_id: data.job_id,
          status: 'pending',
          progress: 0,
          progress_message: `Parsed using ${data.parsing_method}: starting backtest...`,
          result: null,
          error: null,
          created_at: new Date().toISOString(),
          completed_at: null
        })
      } else {
        setError(data.error || 'Failed to parse natural language request')
        setRunning(false)
      }
    } catch (err: any) {
      setError(`Cannot connect to backend at ${API_URL}. Is the server running?`)
      setRunning(false)
    }
  }

  const selectStrategy = (strategyId: string) => {
    const strategy = strategies.find(s => s.id === strategyId)
    if (strategy) {
      setConfig(prev => ({
        ...prev,
        strategy: strategyId,
        ...strategy.recommended_settings
      }))
    }
  }

  const exportTrades = async (jobId: string) => {
    window.open(`${API_URL}/api/zero-dte/export/trades/${jobId}`, '_blank')
  }

  const exportSummary = async (jobId: string) => {
    window.open(`${API_URL}/api/zero-dte/export/summary/${jobId}`, '_blank')
  }

  const exportEquityCurve = async (jobId: string) => {
    window.open(`${API_URL}/api/zero-dte/export/equity-curve/${jobId}`, '_blank')
  }

  // Export individual result by ID
  const exportResultById = async (resultId: number) => {
    window.open(`${API_URL}/api/zero-dte/export/result/${resultId}`, '_blank')
  }

  // Export all results as CSV
  const exportAllResults = async () => {
    window.open(`${API_URL}/api/zero-dte/export/all-results`, '_blank')
  }

  // Get current result (live or selected)
  const currentResult = liveJobResult || selectedResult

  // Helper to check if result has valid data
  const hasValidResult = (result: any): boolean => {
    if (!result) return false
    // Check for live job result structure
    if (result.summary && result.trades) {
      return result.trades.total > 0
    }
    // Check for saved result structure
    if (result.total_trades !== undefined) {
      return result.total_trades > 0
    }
    return false
  }

  // Format monthly returns for chart
  const monthlyChartData = currentResult?.monthly_returns
    ? Object.entries(currentResult.monthly_returns).map(([month, pct]) => ({
        month,
        return_pct: typeof pct === 'number' ? pct : parseFloat(String(pct))
      }))
    : []

  // Format equity curve for chart
  const equityCurveData = liveJobResult?.equity_curve || []

  // Format day of week performance
  const dayOfWeekData = liveJobResult?.day_of_week_performance
    ? Object.entries(liveJobResult.day_of_week_performance).map(([day, stats]: [string, any]) => ({
        day,
        trades: stats.trades,
        pnl: stats.pnl,
        win_rate: stats.win_rate,
        avg_pnl: stats.avg_pnl
      }))
    : []

  // Format VIX performance
  const vixPerformanceData = liveJobResult?.vix_performance
    ? Object.entries(liveJobResult.vix_performance).map(([level, stats]: [string, any]) => ({
        level: level.charAt(0).toUpperCase() + level.slice(1),
        trades: stats.trades,
        pnl: stats.pnl,
        win_rate: stats.win_rate,
        avg_pnl: stats.avg_pnl
      }))
    : []

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <Navigation />

      <main className="pt-24">
        <div className="container mx-auto px-4 py-8 space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-3">
                <Clock className="w-8 h-8 text-blue-400" />
                KRONOS - 0DTE Iron Condor Backtest
              </h1>
              <p className="text-gray-400 mt-1">
                God of Time Decay - Hybrid scaling strategy with automatic tier transitions
              </p>
            </div>
            <div className="flex items-center gap-4">
              {/* Backend Status Indicator */}
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs ${
                backendStatus === 'connected' ? 'bg-green-900/50 text-green-400' :
                backendStatus === 'error' ? 'bg-red-900/50 text-red-400' :
                'bg-yellow-900/50 text-yellow-400'
              }`}>
                <div className={`w-2 h-2 rounded-full ${
                  backendStatus === 'connected' ? 'bg-green-400' :
                  backendStatus === 'error' ? 'bg-red-400' :
                  'bg-yellow-400 animate-pulse'
                }`} />
                {backendStatus === 'connected' ? 'Backend Connected' :
                 backendStatus === 'error' ? 'Backend Offline' :
                 'Checking...'}
              </div>
              {/* Oracle AI Status Indicator */}
              {oracleStatus && (
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs ${
                  oracleStatus.claude_available ? 'bg-purple-900/50 text-purple-400' : 'bg-gray-800 text-gray-400'
                }`}>
                  <div className={`w-2 h-2 rounded-full ${
                    oracleStatus.claude_available ? 'bg-purple-400' : 'bg-gray-500'
                  }`} />
                  Claude AI: {oracleStatus.claude_available ? 'Active' : 'Offline'}
                </div>
              )}
              <button
                onClick={() => setShowOracleLogs(!showOracleLogs)}
                className="flex items-center gap-2 px-4 py-2 bg-purple-900/30 hover:bg-purple-900/50 rounded-lg text-sm text-purple-300"
              >
                <Activity className="w-4 h-4" />
                Oracle Logs
                {showOracleLogs ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
              <button
                onClick={() => setShowDataInfo(!showDataInfo)}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm"
              >
                <Database className="w-4 h-4" />
                Data Sources
                {showDataInfo ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Oracle Live Logs Panel */}
          {showOracleLogs && (
            <div className="bg-purple-900/20 border border-purple-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-bold text-purple-300 flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  Oracle AI Live Logs
                </h3>
                <div className="flex items-center gap-2">
                  {oracleStatus && (
                    <span className="text-xs text-gray-400">
                      Model: {oracleStatus.claude_model || 'N/A'} | Version: {oracleStatus.model_version}
                    </span>
                  )}
                  <button
                    onClick={loadOracleLogs}
                    className="p-1 hover:bg-purple-800/50 rounded"
                  >
                    <RefreshCw className="w-4 h-4 text-purple-400" />
                  </button>
                </div>
              </div>
              <div className="bg-black/30 rounded-lg p-3 max-h-48 overflow-y-auto font-mono text-xs">
                {oracleLogs.length === 0 ? (
                  <div className="text-gray-500 text-center py-4">
                    No Oracle logs yet. Run a backtest or make a prediction to see Claude AI activity.
                  </div>
                ) : (
                  oracleLogs.slice().reverse().map((log, idx) => (
                    <div key={idx} className={`py-1 border-b border-gray-800 last:border-0 ${
                      log.type === 'ERROR' ? 'text-red-400' :
                      log.type === 'WARN' ? 'text-yellow-400' :
                      log.type?.includes('DONE') ? 'text-green-400' :
                      'text-purple-300'
                    }`}>
                      <span className="text-gray-500">{log.timestamp?.split('T')[1]?.split('.')[0] || ''}</span>
                      {' '}
                      <span className="text-purple-500">[{log.type}]</span>
                      {' '}
                      {log.message}
                      {log.data && (
                        <span className="text-gray-500 ml-2">
                          {JSON.stringify(log.data).slice(0, 80)}...
                        </span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Backend Error Banner */}
          {backendStatus === 'error' && (
            <div className="bg-red-900/30 border border-red-800 rounded-lg p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-red-400" />
                <div>
                  <div className="font-bold text-red-300">Backend Not Connected</div>
                  <div className="text-sm text-red-400">
                    Start the backend with: <code className="bg-red-900/50 px-2 py-0.5 rounded">python backend/main.py</code>
                  </div>
                </div>
              </div>
              <button
                onClick={checkBackendHealth}
                className="px-4 py-2 bg-red-800 hover:bg-red-700 rounded-lg text-sm flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                Retry
              </button>
            </div>
          )}

          {/* Data Sources Info Panel */}
          {showDataInfo && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <h3 className="font-bold mb-4 flex items-center gap-2">
                <Info className="w-5 h-5 text-blue-400" />
                Data Sources & Limitations
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-gray-800 rounded-lg p-4">
                  <h4 className="font-bold text-green-400 mb-2">ORAT Options Data</h4>
                  <p className="text-sm text-gray-400 mb-2">End-of-day options data including Greeks, IV, bid/ask</p>
                  <ul className="text-xs text-gray-500 space-y-1">
                    <li>- SPX, SPXW, SPY tickers</li>
                    <li>- 2021-01-01 to present</li>
                    <li>- EOD snapshots only</li>
                  </ul>
                </div>
                <div className="bg-gray-800 rounded-lg p-4">
                  <h4 className="font-bold text-yellow-400 mb-2">Yahoo Finance</h4>
                  <p className="text-sm text-gray-400 mb-2">Free OHLC data for underlying and VIX</p>
                  <ul className="text-xs text-gray-500 space-y-1">
                    <li>- S&P 500 daily OHLC</li>
                    <li>- VIX daily close</li>
                    <li>- Fetched on-demand</li>
                  </ul>
                </div>
                <div className="bg-gray-800 rounded-lg p-4">
                  <h4 className="font-bold text-gray-400 mb-2">Limitations</h4>
                  <ul className="text-xs text-gray-500 space-y-1">
                    <li>- No intraday data (stops approximate)</li>
                    <li>- Greeks are EOD snapshot</li>
                    <li>- Settlement uses daily OHLC</li>
                    <li>- No tick data for slippage</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Strategy Type Selection - PRIMARY (what type of options strategy to trade) */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold flex items-center gap-2">
                  <Target className="w-5 h-5 text-blue-400" />
                  Strategy Type
                </h2>
                <p className="text-sm text-gray-400 mt-1">Select the options strategy structure to backtest</p>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {strategyTypes.map(st => (
                <div
                  key={st.id}
                  onClick={() => setConfig(prev => ({ ...prev, strategy_type: st.id }))}
                  className={`border rounded-lg p-3 cursor-pointer transition-all ${
                    config.strategy_type === st.id
                      ? 'border-blue-500 bg-blue-900/20 ring-2 ring-blue-500/20'
                      : 'border-gray-700 hover:border-gray-600 bg-gray-800/50'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-sm">{st.name}</span>
                    {config.strategy_type === st.id && (
                      <CheckCircle className="w-4 h-4 text-blue-400" />
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs mb-1">
                    <span className={`px-1.5 py-0.5 rounded ${st.credit ? 'bg-green-900/50 text-green-400' : 'bg-yellow-900/50 text-yellow-400'}`}>
                      {st.credit ? 'Credit' : 'Debit'}
                    </span>
                    <span className="text-gray-500">{st.legs} legs</span>
                  </div>
                  <p className="text-xs text-gray-400 line-clamp-2">{st.description}</p>
                </div>
              ))}
            </div>
            {/* Strategy-specific notes */}
            {config.strategy_type === 'gex_protected_iron_condor' && (
              <div className="mt-3 p-3 bg-emerald-900/20 border border-emerald-800 rounded-lg text-sm text-emerald-300">
                <strong>GEX-Protected:</strong> Places strikes outside GEX walls (call wall/put wall) for additional protection. Falls back to SD method when GEX data is unavailable.
              </div>
            )}
            {config.strategy_type === 'apache_directional' && (
              <div className="mt-3 p-3 bg-orange-900/20 border border-orange-800 rounded-lg text-sm text-orange-300">
                <strong>Apache GEX Directional:</strong> DEBIT SPREADS ONLY. Opens Bull Call spreads when price is near put wall (support), Bear Put spreads when near call wall (resistance). Skips trades when not near walls. Adjust "Wall Proximity %" in Advanced settings.
              </div>
            )}
            {(config.strategy_type === 'diagonal_call' || config.strategy_type === 'diagonal_put') && (
              <div className="mt-3 p-3 bg-purple-900/20 border border-purple-800 rounded-lg text-sm text-purple-300">
                <strong>Diagonal Spread:</strong> Poor Man's Covered {config.strategy_type === 'diagonal_call' ? 'Call' : 'Put'}. Sells near-term OTM option and buys longer-term option. Short strike placed at configured SD multiplier distance.
              </div>
            )}
          </div>

          {/* Risk Profile Selection - SECONDARY (how aggressive to trade) */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-bold text-sm flex items-center gap-2">
                  <Shield className="w-4 h-4 text-gray-400" />
                  Risk Profile
                  <span className="text-xs text-gray-500 font-normal">(Account scaling behavior)</span>
                </h3>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {strategies.map(strategy => (
                <div
                  key={strategy.id}
                  onClick={() => selectStrategy(strategy.id)}
                  className={`border rounded-lg p-3 cursor-pointer transition-all ${
                    config.strategy === strategy.id
                      ? 'border-purple-500 bg-purple-900/20'
                      : 'border-gray-700 hover:border-gray-600 bg-gray-800/30'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="font-bold text-sm">{strategy.name}</h4>
                    {config.strategy === strategy.id && (
                      <CheckCircle className="w-4 h-4 text-purple-400" />
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mb-2">{strategy.description}</p>
                  <div className="flex flex-wrap gap-1">
                    {strategy.features.slice(0, 2).map((f, i) => (
                      <span key={i} className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-400">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Configuration Panel */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Settings className="w-5 h-5 text-gray-400" />
                Backtest Configuration
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowRiskSettings(!showRiskSettings)}
                  className="text-sm text-purple-400 hover:text-purple-300 flex items-center gap-1"
                >
                  <Shield className="w-4 h-4" />
                  {showRiskSettings ? 'Hide' : 'Show'} Risk
                </button>
                <button
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
                >
                  {showAdvanced ? 'Hide' : 'Show'} Advanced
                  {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Basic Settings */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {/* Date Range */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Start Date</label>
                <input
                  type="date"
                  value={config.start_date}
                  onChange={e => setConfig(prev => ({ ...prev, start_date: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">End Date</label>
                <input
                  type="date"
                  value={config.end_date}
                  onChange={e => setConfig(prev => ({ ...prev, end_date: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                />
              </div>

              {/* Capital */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Initial Capital</label>
                <div className="relative">
                  <DollarSign className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
                  <input
                    type="number"
                    value={config.initial_capital}
                    onChange={e => setConfig(prev => ({ ...prev, initial_capital: Number(e.target.value) }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded pl-8 pr-3 py-2 text-sm"
                  />
                </div>
              </div>

              {/* Risk */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Risk Per Trade (%)</label>
                <input
                  type="number"
                  step="0.5"
                  value={config.risk_per_trade_pct}
                  onChange={e => setConfig(prev => ({ ...prev, risk_per_trade_pct: Number(e.target.value) }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                />
              </div>

              {/* Strategy Preset */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Strategy Preset
                  <span className="text-gray-600 ml-1">(Quick Start)</span>
                </label>
                <select
                  value=""
                  onChange={e => e.target.value && applyPreset(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                >
                  <option value="">Select a preset...</option>
                  <optgroup label="Built-in Presets">
                    {presets.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </optgroup>
                  {savedStrategies.filter(s => !s.is_preset).length > 0 && (
                    <optgroup label="Saved Strategies">
                      {savedStrategies.filter(s => !s.is_preset).map(s => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </div>

            </div>

            {/* Risk Management Settings */}
            {showRiskSettings && (
              <div className="mt-4 pt-4 border-t border-gray-800">
                <h3 className="text-sm font-bold text-purple-400 mb-3 flex items-center gap-2">
                  <Shield className="w-4 h-4" />
                  Risk Management & Filters
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                  {/* VIX Filter */}
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Min VIX</label>
                    <input
                      type="number"
                      step="1"
                      value={config.min_vix || ''}
                      placeholder="None"
                      onChange={e => setConfig(prev => ({ ...prev, min_vix: e.target.value ? Number(e.target.value) : null }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Max VIX</label>
                    <input
                      type="number"
                      step="1"
                      value={config.max_vix || ''}
                      placeholder="None"
                      onChange={e => setConfig(prev => ({ ...prev, max_vix: e.target.value ? Number(e.target.value) : null }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                    />
                  </div>

                  {/* Stop Loss / Profit Target */}
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Stop Loss %</label>
                    <input
                      type="number"
                      step="10"
                      value={config.stop_loss_pct || ''}
                      placeholder="None"
                      onChange={e => setConfig(prev => ({ ...prev, stop_loss_pct: e.target.value ? Number(e.target.value) : null }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Profit Target %</label>
                    <input
                      type="number"
                      step="10"
                      value={config.profit_target_pct || ''}
                      placeholder="None"
                      onChange={e => setConfig(prev => ({ ...prev, profit_target_pct: e.target.value ? Number(e.target.value) : null }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                    />
                  </div>

                  {/* Max Contracts Override */}
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Max Contracts</label>
                    <input
                      type="number"
                      value={config.max_contracts_override || ''}
                      placeholder="Auto"
                      onChange={e => setConfig(prev => ({ ...prev, max_contracts_override: e.target.value ? Number(e.target.value) : null }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                    />
                  </div>
                </div>

                {/* Trading Days */}
                <div className="mt-4">
                  <label className="block text-sm text-gray-400 mb-2">Trading Days</label>
                  <div className="flex gap-4">
                    {[
                      { key: 'trade_monday', label: 'Mon' },
                      { key: 'trade_tuesday', label: 'Tue' },
                      { key: 'trade_wednesday', label: 'Wed' },
                      { key: 'trade_thursday', label: 'Thu' },
                      { key: 'trade_friday', label: 'Fri' },
                    ].map(day => (
                      <label key={day.key} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config[day.key as keyof BacktestConfig] as boolean}
                          onChange={e => setConfig(prev => ({ ...prev, [day.key]: e.target.checked }))}
                          className="w-4 h-4 rounded bg-gray-800 border-gray-600"
                        />
                        <span className="text-sm">{day.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Advanced Options */}
            {showAdvanced && (
              <div className="mt-4 pt-4 border-t border-gray-800 space-y-4">
                {/* Strike Selection Method */}
                <div>
                  <h3 className="text-sm font-bold text-cyan-400 mb-3 flex items-center gap-2">
                    <Target className="w-4 h-4" />
                    Strike Selection Method
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                      <label className="block text-sm text-gray-400 mb-1">Method</label>
                      <select
                        value={config.strike_selection}
                        onChange={e => setConfig(prev => ({ ...prev, strike_selection: e.target.value as 'sd' | 'fixed' | 'delta' }))}
                        className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                      >
                        <option value="sd">Standard Deviation (SD)</option>
                        <option value="fixed">Fixed Distance</option>
                        <option value="delta">Target Delta</option>
                      </select>
                    </div>
                    {config.strike_selection === 'sd' && (
                      <div>
                        <label className="block text-sm text-gray-400 mb-1">SD Multiplier</label>
                        <input
                          type="number"
                          step="0.1"
                          value={config.sd_multiplier}
                          onChange={e => setConfig(prev => ({ ...prev, sd_multiplier: Number(e.target.value) }))}
                          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                        />
                        <p className="text-xs text-gray-500 mt-1">Strike = Price ± (SD × Expected Move)</p>
                      </div>
                    )}
                    {config.strike_selection === 'fixed' && (
                      <div>
                        <label className="block text-sm text-gray-400 mb-1">Fixed Distance ($)</label>
                        <input
                          type="number"
                          step="5"
                          value={config.fixed_strike_distance}
                          onChange={e => setConfig(prev => ({ ...prev, fixed_strike_distance: Number(e.target.value) }))}
                          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                        />
                        <p className="text-xs text-gray-500 mt-1">Fixed points from current price</p>
                      </div>
                    )}
                    {config.strike_selection === 'delta' && (
                      <div>
                        <label className="block text-sm text-gray-400 mb-1">Target Delta</label>
                        <input
                          type="number"
                          step="0.01"
                          min="0.01"
                          max="0.50"
                          value={config.target_delta}
                          onChange={e => setConfig(prev => ({ ...prev, target_delta: Number(e.target.value) }))}
                          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                        />
                        <p className="text-xs text-gray-500 mt-1">e.g., 0.16 = 16 delta</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Other Advanced Settings */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Spread Width ($)</label>
                  <input
                    type="number"
                    value={config.spread_width}
                    onChange={e => setConfig(prev => ({ ...prev, spread_width: Number(e.target.value) }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Ticker</label>
                  <select
                    value={config.ticker}
                    onChange={e => setConfig(prev => ({ ...prev, ticker: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  >
                    <option value="SPX">SPX</option>
                    <option value="SPXW">SPXW</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Commission/Leg ($)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={config.commission_per_leg || ''}
                    placeholder="Default"
                    onChange={e => setConfig(prev => ({ ...prev, commission_per_leg: e.target.value ? Number(e.target.value) : null }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Slippage/Spread ($)</label>
                  <input
                    type="number"
                    step="0.05"
                    value={config.slippage_per_spread || ''}
                    placeholder="Default"
                    onChange={e => setConfig(prev => ({ ...prev, slippage_per_spread: e.target.value ? Number(e.target.value) : null }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Hold Duration</label>
                  <select
                    value={config.hold_days}
                    onChange={e => setConfig(prev => ({ ...prev, hold_days: Number(e.target.value) }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  >
                    <option value={1}>Day Trade (exit same day)</option>
                    <option value={2}>Swing 2 Days</option>
                    <option value={3}>Swing 3 Days</option>
                    <option value={5}>Swing 5 Days (1 week)</option>
                  </select>
                </div>
                <div>
                  <label className={`block text-sm mb-1 ${config.strategy_type === 'apache_directional' ? 'text-orange-400' : 'text-gray-400'}`}>
                    Wall Proximity % (Apache)
                  </label>
                  <select
                    value={config.wall_proximity_pct}
                    onChange={e => setConfig(prev => ({ ...prev, wall_proximity_pct: Number(e.target.value) }))}
                    className={`w-full border rounded px-3 py-2 text-sm ${
                      config.strategy_type === 'apache_directional'
                        ? 'bg-orange-900/20 border-orange-700'
                        : 'bg-gray-800 border-gray-700'
                    }`}
                  >
                    <option value={0.5}>0.5% (very tight)</option>
                    <option value={1.0}>1.0% (default)</option>
                    <option value={1.5}>1.5%</option>
                    <option value={2.0}>2.0%</option>
                    <option value={3.0}>3.0% (loose)</option>
                    <option value={5.0}>5.0% (very loose)</option>
                  </select>
                  {config.strategy_type === 'apache_directional' && (
                    <p className="text-xs text-orange-400 mt-1">Apache uses this to detect proximity to GEX walls</p>
                  )}
                </div>
                </div>
              </div>
            )}

            {/* Natural Language Backtest Input */}
            <div className="mt-6 pt-4 border-t border-gray-800">
              <button
                onClick={() => setShowNlInput(!showNlInput)}
                className="text-sm text-purple-400 hover:text-purple-300 flex items-center gap-2 mb-3"
              >
                <Activity className="w-4 h-4" />
                {showNlInput ? 'Hide' : 'Show'} Natural Language Backtest (Claude AI)
                {showNlInput ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>

              {showNlInput && (
                <div className="bg-purple-900/20 border border-purple-800 rounded-lg p-4 mb-4">
                  <h4 className="text-sm font-bold text-purple-300 mb-2">Describe your backtest in plain English:</h4>
                  <div className="flex gap-3">
                    <input
                      type="text"
                      value={nlQuery}
                      onChange={(e) => setNlQuery(e.target.value)}
                      placeholder="e.g., Run aggressive iron condors for 2023 with VIX > 20"
                      className="flex-1 bg-gray-900 border border-purple-700 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none"
                      onKeyDown={(e) => e.key === 'Enter' && runNaturalLanguageBacktest()}
                    />
                    <button
                      onClick={runNaturalLanguageBacktest}
                      disabled={!nlQuery.trim() || running || backendStatus !== 'connected'}
                      className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm"
                    >
                      <Zap className="w-4 h-4" />
                      Run with AI
                    </button>
                  </div>
                  <p className="text-xs text-gray-400 mt-2">
                    Examples: "Test GEX-protected IC from Jan 2022 to Dec 2023" | "Backtest conservative strategy in high VIX (VIX &gt; 25)" | "Run 1.5 SD iron condor for 2024"
                  </p>
                  {nlParsedConfig && (
                    <div className="mt-3 p-2 bg-black/30 rounded text-xs">
                      <span className="text-purple-400">Parsed ({nlParsedConfig.parsing_method}):</span>
                      <span className="text-gray-300 ml-2">
                        {Object.entries(nlParsedConfig.parsed || {}).map(([k, v]) => `${k}=${v}`).join(', ') || 'defaults used'}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Run Button */}
            <div className="mt-4 flex items-center gap-4">
              <button
                onClick={runBacktest}
                disabled={running || backendStatus !== 'connected'}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                title={backendStatus !== 'connected' ? 'Backend not connected' : undefined}
              >
                {running ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Running Backtest...
                  </>
                ) : backendStatus !== 'connected' ? (
                  <>
                    <AlertTriangle className="w-5 h-5" />
                    Backend Offline
                  </>
                ) : (
                  <>
                    <PlayCircle className="w-5 h-5" />
                    Run Backtest
                  </>
                )}
              </button>

              <button
                onClick={saveCurrentStrategy}
                className="px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg font-medium flex items-center gap-2 text-sm"
                title="Save current configuration as a strategy preset"
              >
                <Download className="w-4 h-4" />
                Save Strategy
              </button>

              {error && !error.includes('Backend') && (
                <div className="flex items-center gap-2 text-red-400">
                  <AlertTriangle className="w-5 h-5" />
                  {error}
                </div>
              )}

              {presetAppliedMessage && (
                <div className="flex items-center gap-2 text-green-400 animate-pulse">
                  <CheckCircle className="w-5 h-5" />
                  {presetAppliedMessage}
                </div>
              )}
            </div>

            {/* Progress Bar */}
            {running && jobStatus && (
              <div className="mt-4 bg-gray-800 rounded-lg p-4">
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-gray-400">{jobStatus.progress_message}</span>
                  <span className="text-blue-400">{jobStatus.progress}%</span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${jobStatus.progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Scaling Tiers Info */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
            <button
              onClick={() => setShowTiers(!showTiers)}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-800/50"
            >
              <div className="flex items-center gap-2">
                <Layers className="w-5 h-5 text-purple-400" />
                <span className="font-bold">Scaling Tiers</span>
                <span className="text-sm text-gray-400">- How the strategy adapts as your account grows</span>
              </div>
              {showTiers ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </button>

            {showTiers && (
              <div className="px-6 pb-6">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  {tiers.map((tier, i) => (
                    <div key={tier.name} className="bg-gray-800 rounded-lg p-4">
                      <div className="text-purple-400 font-bold mb-2">Tier {i + 1}</div>
                      <div className="text-lg font-bold mb-1">{tier.equity_range}</div>
                      <div className="text-sm text-gray-400 mb-3">{tier.description}</div>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-gray-500">Options:</span>
                          <span>{tier.options_dte}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">SD Days:</span>
                          <span>{tier.sd_days}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Max Contracts:</span>
                          <span>{tier.max_contracts}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Trades/Week:</span>
                          <span>{tier.trades_per_week}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Results Section */}
          {(hasValidResult(liveJobResult) || results.length > 0) && (
            <>
              {/* Tabs */}
              <div className="flex gap-2 border-b border-gray-800 pb-2">
                {['overview', 'charts', 'trades', 'analytics', 'compare'].map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab as any)}
                    className={`px-4 py-2 rounded-t-lg transition-colors ${
                      activeTab === tab
                        ? 'bg-gray-800 text-white'
                        : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>

              {/* Overview Tab */}
              {activeTab === 'overview' && hasValidResult(currentResult) && (
                <>
                  {/* Summary Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400 mb-1">Final Equity</div>
                      <div className="text-2xl font-bold text-green-400">
                        ${(liveJobResult?.summary?.final_equity || currentResult.final_equity)?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                    </div>
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400 mb-1">Total Return</div>
                      <div className={`text-2xl font-bold ${(liveJobResult?.summary?.total_return_pct || currentResult.total_return_pct) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {(liveJobResult?.summary?.total_return_pct || currentResult.total_return_pct)?.toFixed(1)}%
                      </div>
                    </div>
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400 mb-1">Avg Monthly</div>
                      <div className={`text-2xl font-bold ${(liveJobResult?.summary?.avg_monthly_return_pct || currentResult.avg_monthly_return_pct) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {(liveJobResult?.summary?.avg_monthly_return_pct || currentResult.avg_monthly_return_pct)?.toFixed(2)}%
                      </div>
                    </div>
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400 mb-1">Win Rate</div>
                      <div className="text-2xl font-bold text-blue-400">
                        {(liveJobResult?.trades?.win_rate || currentResult.win_rate)?.toFixed(1)}%
                      </div>
                    </div>
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400 mb-1">Max Drawdown</div>
                      <div className="text-2xl font-bold text-red-400">
                        {(liveJobResult?.summary?.max_drawdown_pct || currentResult.max_drawdown_pct)?.toFixed(1)}%
                      </div>
                    </div>
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                      <div className="text-sm text-gray-400 mb-1">Profit Factor</div>
                      <div className="text-2xl font-bold text-purple-400">
                        {(liveJobResult?.trades?.profit_factor || currentResult.profit_factor)?.toFixed(2)}
                      </div>
                    </div>
                  </div>

                  {/* Risk Metrics */}
                  {liveJobResult?.risk_metrics && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">Sharpe Ratio</div>
                        <div className="text-xl font-bold text-cyan-400">
                          {liveJobResult.risk_metrics.sharpe_ratio?.toFixed(2)}
                        </div>
                      </div>
                      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">Sortino Ratio</div>
                        <div className="text-xl font-bold text-cyan-400">
                          {liveJobResult.risk_metrics.sortino_ratio?.toFixed(2)}
                        </div>
                      </div>
                      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">Max Consecutive Losses</div>
                        <div className="text-xl font-bold text-orange-400">
                          {liveJobResult.risk_metrics.max_consecutive_losses}
                        </div>
                      </div>
                      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">VIX Filter Skips</div>
                        <div className="text-xl font-bold text-gray-400">
                          {liveJobResult.risk_metrics.vix_filter_skips}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* GEX-Protected Strategy Stats */}
                  {liveJobResult?.gex_stats && (
                    <div className="bg-gray-900 border border-emerald-800 rounded-lg p-6">
                      <h3 className="font-bold mb-4 flex items-center gap-2 text-emerald-400">
                        <Zap className="w-5 h-5" />
                        GEX-Protected Strategy Stats
                      </h3>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                        <div className="bg-gray-800 rounded-lg p-4">
                          <div className="text-sm text-gray-400 mb-1">GEX Wall Trades</div>
                          <div className="text-xl font-bold text-emerald-400">
                            {liveJobResult.gex_stats.trades_with_gex_walls}
                          </div>
                          <div className="text-xs text-gray-500">
                            {((liveJobResult.gex_stats.trades_with_gex_walls /
                              (liveJobResult.gex_stats.trades_with_gex_walls + liveJobResult.gex_stats.trades_with_sd_fallback)) * 100).toFixed(1)}%
                            of trades
                          </div>
                        </div>
                        <div className="bg-gray-800 rounded-lg p-4">
                          <div className="text-sm text-gray-400 mb-1">SD Fallback Trades</div>
                          <div className="text-xl font-bold text-yellow-400">
                            {liveJobResult.gex_stats.trades_with_sd_fallback}
                          </div>
                          <div className="text-xs text-gray-500">
                            GEX data unavailable
                          </div>
                        </div>
                        <div className="bg-gray-800 rounded-lg p-4">
                          <div className="text-sm text-gray-400 mb-1">GEX Unavailable Days</div>
                          <div className="text-xl font-bold text-gray-400">
                            {liveJobResult.gex_stats.gex_unavailable_days}
                          </div>
                          <div className="text-xs text-gray-500">
                            Used SD multiplier instead
                          </div>
                        </div>
                      </div>
                      <p className="text-xs text-gray-500 mt-4">
                        GEX walls provide support/resistance levels for strike selection. When GEX data is unavailable, the strategy falls back to SD-based strike selection.
                      </p>
                    </div>
                  )}

                  {/* Exit Type Stats (for intraday exit strategies) */}
                  {liveJobResult?.intraday_exit_stats && Object.keys(liveJobResult.intraday_exit_stats).length > 0 && (
                    <div className="bg-gray-900 border border-amber-800 rounded-lg p-6">
                      <h3 className="font-bold mb-4 flex items-center gap-2 text-amber-400">
                        <Clock className="w-5 h-5" />
                        Exit Type Breakdown
                      </h3>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        {liveJobResult.intraday_exit_stats.held_to_close !== undefined && liveJobResult.intraday_exit_stats.held_to_close > 0 && (
                          <div className="bg-gray-800 rounded-lg p-4">
                            <div className="text-sm text-gray-400 mb-1">Held to Close</div>
                            <div className="text-xl font-bold text-gray-300">
                              {liveJobResult.intraday_exit_stats.held_to_close}
                            </div>
                            <div className="text-xs text-gray-500">EOD settlement</div>
                          </div>
                        )}
                        {liveJobResult.intraday_exit_stats.take_profit_exits !== undefined && liveJobResult.intraday_exit_stats.take_profit_exits > 0 && (
                          <div className="bg-gray-800 rounded-lg p-4">
                            <div className="text-sm text-gray-400 mb-1">Take Profit</div>
                            <div className="text-xl font-bold text-green-400">
                              {liveJobResult.intraday_exit_stats.take_profit_exits}
                            </div>
                            <div className="text-xs text-gray-500">Hit profit target</div>
                          </div>
                        )}
                        {liveJobResult.intraday_exit_stats.stop_loss_exits !== undefined && liveJobResult.intraday_exit_stats.stop_loss_exits > 0 && (
                          <div className="bg-gray-800 rounded-lg p-4">
                            <div className="text-sm text-gray-400 mb-1">Stop Loss</div>
                            <div className="text-xl font-bold text-red-400">
                              {liveJobResult.intraday_exit_stats.stop_loss_exits}
                            </div>
                            <div className="text-xs text-gray-500">Hit stop loss</div>
                          </div>
                        )}
                        {liveJobResult.intraday_exit_stats.wall_break_exits !== undefined && liveJobResult.intraday_exit_stats.wall_break_exits > 0 && (
                          <div className="bg-gray-800 rounded-lg p-4">
                            <div className="text-sm text-gray-400 mb-1">Wall Break</div>
                            <div className="text-xl font-bold text-purple-400">
                              {liveJobResult.intraday_exit_stats.wall_break_exits}
                            </div>
                            <div className="text-xs text-gray-500">GEX wall breached</div>
                          </div>
                        )}
                        {liveJobResult.intraday_exit_stats.time_based_exits !== undefined && liveJobResult.intraday_exit_stats.time_based_exits > 0 && (
                          <div className="bg-gray-800 rounded-lg p-4">
                            <div className="text-sm text-gray-400 mb-1">Time Exits</div>
                            <div className="text-xl font-bold text-blue-400">
                              {liveJobResult.intraday_exit_stats.time_based_exits}
                            </div>
                            <div className="text-xs text-gray-500">Time-based exit</div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Export Buttons */}
                  {completedJobId && liveJobResult && (
                    <div className="flex gap-4">
                      <button
                        onClick={() => exportTrades(completedJobId)}
                        className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm"
                      >
                        <FileSpreadsheet className="w-4 h-4" />
                        Export Trades CSV
                      </button>
                      <button
                        onClick={() => exportSummary(completedJobId)}
                        className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm"
                      >
                        <Download className="w-4 h-4" />
                        Export Summary CSV
                      </button>
                      <button
                        onClick={() => exportEquityCurve(completedJobId)}
                        className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm"
                      >
                        <LineChart className="w-4 h-4" />
                        Export Equity Curve
                      </button>
                    </div>
                  )}

                  {/* Monthly Returns Chart */}
                  {monthlyChartData.length > 0 && (
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                      <h3 className="font-bold mb-4">Monthly Returns</h3>
                      <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={monthlyChartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis
                              dataKey="month"
                              stroke="#9CA3AF"
                              fontSize={10}
                              angle={-45}
                              textAnchor="end"
                              height={60}
                            />
                            <YAxis
                              stroke="#9CA3AF"
                              fontSize={12}
                              tickFormatter={(v) => `${v}%`}
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                              formatter={(value: number) => [`${value.toFixed(2)}%`, 'Return']}
                            />
                            <Bar dataKey="return_pct" name="Return %">
                              {monthlyChartData.map((entry, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={entry.return_pct >= 0 ? '#22C55E' : '#EF4444'}
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Charts Tab */}
              {activeTab === 'charts' && liveJobResult && (
                <div className="space-y-6">
                  {/* Enhanced Equity Curve with Annotations */}
                  <EnhancedEquityCurve
                    equityCurve={equityCurveData}
                    tierTransitions={liveJobResult?.tier_transitions || []}
                    allTrades={liveJobResult?.all_trades || []}
                    initialCapital={config.initial_capital}
                  />

                  {/* Drawdown Chart */}
                  {equityCurveData.length > 0 && (
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                      <h3 className="font-bold mb-4">Drawdown Over Time</h3>
                      <div className="h-60">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={equityCurveData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis
                              dataKey="date"
                              stroke="#9CA3AF"
                              fontSize={10}
                              tickFormatter={(date) => date?.slice(2, 7)}
                            />
                            <YAxis
                              stroke="#9CA3AF"
                              fontSize={12}
                              tickFormatter={(v) => `-${v.toFixed(1)}%`}
                              reversed
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                              formatter={(value: number) => [`-${value.toFixed(2)}%`, 'Drawdown']}
                            />
                            <Area
                              type="monotone"
                              dataKey="drawdown_pct"
                              stroke="#EF4444"
                              fill="#EF4444"
                              fillOpacity={0.3}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}

                  {/* Day of Week Performance */}
                  {dayOfWeekData.length > 0 && (
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                      <h3 className="font-bold mb-4">P&L by Day of Week</h3>
                      <div className="h-60">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={dayOfWeekData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="day" stroke="#9CA3AF" fontSize={12} />
                            <YAxis
                              stroke="#9CA3AF"
                              fontSize={12}
                              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                              formatter={(value: number, name: string) => {
                                if (name === 'pnl') return [`$${value.toLocaleString()}`, 'P&L']
                                if (name === 'win_rate') return [`${value.toFixed(1)}%`, 'Win Rate']
                                return [value, name]
                              }}
                            />
                            <Bar dataKey="pnl" name="P&L">
                              {dayOfWeekData.map((entry, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={entry.pnl >= 0 ? '#22C55E' : '#EF4444'}
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}

                  {/* VIX Level Performance */}
                  {vixPerformanceData.length > 0 && (
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                      <h3 className="font-bold mb-4">P&L by VIX Level</h3>
                      <div className="h-60">
                        <ResponsiveContainer width="100%" height="100%">
                          <ComposedChart data={vixPerformanceData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="level" stroke="#9CA3AF" fontSize={12} />
                            <YAxis
                              yAxisId="left"
                              stroke="#9CA3AF"
                              fontSize={12}
                              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                            />
                            <YAxis
                              yAxisId="right"
                              orientation="right"
                              stroke="#9CA3AF"
                              fontSize={12}
                              tickFormatter={(v) => `${v}%`}
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                            />
                            <Bar yAxisId="left" dataKey="pnl" name="P&L" fill="#8B5CF6" />
                            <Line
                              yAxisId="right"
                              type="monotone"
                              dataKey="win_rate"
                              name="Win Rate"
                              stroke="#22C55E"
                              strokeWidth={2}
                            />
                          </ComposedChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Trades Tab */}
              {activeTab === 'trades' && liveJobResult?.all_trades && (
                <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                  <div className="px-6 py-4 border-b border-gray-800 flex justify-between items-center">
                    <h3 className="font-bold">Trade Log ({liveJobResult.all_trades.length} trades)</h3>
                  </div>
                  <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-950 sticky top-0">
                        <tr>
                          <th className="text-left p-3">#</th>
                          <th className="text-left p-3">Date</th>
                          <th className="text-left p-3">Tier</th>
                          <th className="text-right p-3">VIX</th>
                          <th className="text-right p-3">Put Strike</th>
                          <th className="text-right p-3">Call Strike</th>
                          <th className="text-right p-3">Contracts</th>
                          <th className="text-right p-3">P&L</th>
                          <th className="text-left p-3">Outcome</th>
                        </tr>
                      </thead>
                      <tbody>
                        {liveJobResult.all_trades.slice(0, 100).map((trade: any) => (
                          <tr key={trade.trade_number} className="border-b border-gray-800 hover:bg-gray-800/50">
                            <td className="p-3">{trade.trade_number}</td>
                            <td className="p-3">{trade.trade_date}</td>
                            <td className="p-3 text-purple-400">{trade.tier_name.replace('TIER_', '')}</td>
                            <td className="p-3 text-right">{trade.vix?.toFixed(1)}</td>
                            <td className="p-3 text-right">{trade.put_short_strike?.toFixed(0)}</td>
                            <td className="p-3 text-right">{trade.call_short_strike?.toFixed(0)}</td>
                            <td className="p-3 text-right">{trade.contracts}</td>
                            <td className={`p-3 text-right font-mono ${trade.net_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              ${trade.net_pnl?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </td>
                            <td className={`p-3 ${
                              trade.outcome === 'MAX_PROFIT' ? 'text-green-400' :
                              trade.outcome === 'DOUBLE_BREACH' ? 'text-red-400' : 'text-yellow-400'
                            }`}>
                              {trade.outcome}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {liveJobResult.all_trades.length > 100 && (
                      <div className="p-4 text-center text-gray-400">
                        Showing first 100 of {liveJobResult.all_trades.length} trades. Export CSV for full list.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Analytics Tab */}
              {activeTab === 'analytics' && completedJobId && (
                <div className="space-y-6">
                  {/* Load Analytics Button */}
                  {!analyticsData && (
                    <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 text-center">
                      <h3 className="font-bold mb-4">Advanced Analytics</h3>
                      <p className="text-gray-400 mb-4">
                        Analyze your backtest with VIX regime breakdown, day-of-week performance,
                        Monte Carlo simulation, and trade-by-trade inspection.
                      </p>
                      <button
                        onClick={async () => {
                          setAnalyticsLoading(true)
                          try {
                            const response = await fetch(`${API_URL}/api/zero-dte/analytics/comprehensive/${completedJobId}`)
                            const data = await response.json()
                            if (data.success) {
                              setAnalyticsData(data)
                            }
                          } catch (err) {
                            console.error('Failed to load analytics:', err)
                          }
                          setAnalyticsLoading(false)
                        }}
                        disabled={analyticsLoading}
                        className="px-6 py-3 bg-purple-600 hover:bg-purple-700 rounded-lg font-semibold disabled:opacity-50 flex items-center gap-2 mx-auto"
                      >
                        {analyticsLoading ? (
                          <>
                            <Loader2 className="w-5 h-5 animate-spin" />
                            Loading Analytics...
                          </>
                        ) : (
                          <>
                            <Activity className="w-5 h-5" />
                            Load Comprehensive Analytics
                          </>
                        )}
                      </button>
                    </div>
                  )}

                  {/* Analytics Results */}
                  {analyticsData && (
                    <>
                      {/* Recommendations */}
                      {analyticsData.recommendations && analyticsData.recommendations.length > 0 && (
                        <div className="bg-gray-900 border border-purple-800 rounded-lg p-4">
                          <h3 className="font-bold mb-3 flex items-center gap-2 text-purple-400">
                            <Zap className="w-5 h-5" />
                            AI Recommendations
                          </h3>
                          <div className="space-y-2">
                            {analyticsData.recommendations.map((rec: any, i: number) => (
                              <div key={i} className={`p-3 rounded-lg border ${
                                rec.priority === 'HIGH' ? 'border-red-800 bg-red-900/20' :
                                rec.priority === 'MEDIUM' ? 'border-yellow-800 bg-yellow-900/20' :
                                'border-green-800 bg-green-900/20'
                              }`}>
                                <div className="flex items-center gap-2 mb-1">
                                  <span className={`px-2 py-0.5 rounded text-xs ${
                                    rec.priority === 'HIGH' ? 'bg-red-800 text-red-200' :
                                    rec.priority === 'MEDIUM' ? 'bg-yellow-800 text-yellow-200' :
                                    'bg-green-800 text-green-200'
                                  }`}>{rec.type}</span>
                                  <span className="text-sm font-medium">{rec.message}</span>
                                </div>
                                <p className="text-xs text-gray-400">{rec.action}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* VIX Regime Analysis */}
                      {analyticsData.analytics?.vix_regime && (
                        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                          <h3 className="font-bold mb-4 flex items-center gap-2">
                            <TrendingUp className="w-5 h-5 text-orange-400" />
                            VIX Regime Performance
                          </h3>
                          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                            {analyticsData.analytics.vix_regime.regimes?.map((regime: any) => (
                              <div
                                key={regime.regime}
                                className={`p-3 rounded-lg border ${
                                  regime.regime === analyticsData.analytics.vix_regime.optimal_regime
                                    ? 'border-green-500 bg-green-900/20'
                                    : 'border-gray-700 bg-gray-800'
                                }`}
                              >
                                <div className="text-xs text-gray-400 mb-1">{regime.label}</div>
                                <div className="text-lg font-bold" style={{ color: regime.color }}>
                                  {regime.win_rate}%
                                </div>
                                <div className="text-xs text-gray-500">
                                  {regime.trade_count} trades • ${regime.avg_pnl.toFixed(0)} avg
                                </div>
                              </div>
                            ))}
                          </div>
                          {analyticsData.analytics.vix_regime.recommendation && (
                            <p className="mt-3 text-sm text-orange-400">
                              {analyticsData.analytics.vix_regime.recommendation}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Day of Week Analysis */}
                      {analyticsData.analytics?.day_of_week && (
                        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                          <h3 className="font-bold mb-4 flex items-center gap-2">
                            <Calendar className="w-5 h-5 text-blue-400" />
                            Day of Week Performance
                          </h3>
                          <div className="grid grid-cols-5 gap-3">
                            {analyticsData.analytics.day_of_week.days?.map((day: any) => (
                              <div
                                key={day.name}
                                className={`p-4 rounded-lg border text-center ${
                                  day.name === analyticsData.analytics.day_of_week.best_day
                                    ? 'border-green-500 bg-green-900/20'
                                    : day.name === analyticsData.analytics.day_of_week.worst_day
                                    ? 'border-red-500 bg-red-900/20'
                                    : 'border-gray-700 bg-gray-800'
                                }`}
                              >
                                <div className="font-bold" style={{ color: day.color }}>{day.name}</div>
                                <div className="text-2xl font-bold mt-1" style={{ color: day.color }}>
                                  {day.win_rate}%
                                </div>
                                <div className="text-xs text-gray-400 mt-1">
                                  {day.trade_count} trades
                                </div>
                                <div className={`text-sm font-medium ${day.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  ${day.avg_pnl?.toFixed(0)} avg
                                </div>
                              </div>
                            ))}
                          </div>
                          {analyticsData.analytics.day_of_week.recommendation && (
                            <p className="mt-3 text-sm text-blue-400">
                              {analyticsData.analytics.day_of_week.recommendation}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Monte Carlo Simulation */}
                      {analyticsData.analytics?.monte_carlo && (
                        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                          <h3 className="font-bold mb-4 flex items-center gap-2">
                            <BarChart3 className="w-5 h-5 text-cyan-400" />
                            Monte Carlo Simulation ({analyticsData.analytics.monte_carlo.simulations} runs)
                          </h3>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                            <div className="bg-gray-800 rounded-lg p-4">
                              <div className="text-xs text-gray-400 mb-1">Verdict</div>
                              <div className={`text-xl font-bold ${
                                analyticsData.analytics.monte_carlo.verdict === 'ROBUST' ? 'text-green-400' :
                                analyticsData.analytics.monte_carlo.verdict === 'MODERATE' ? 'text-yellow-400' :
                                'text-red-400'
                              }`}>
                                {analyticsData.analytics.monte_carlo.verdict}
                              </div>
                            </div>
                            <div className="bg-gray-800 rounded-lg p-4">
                              <div className="text-xs text-gray-400 mb-1">Profit Probability</div>
                              <div className="text-xl font-bold text-green-400">
                                {analyticsData.analytics.monte_carlo.probabilities?.profit}%
                              </div>
                            </div>
                            <div className="bg-gray-800 rounded-lg p-4">
                              <div className="text-xs text-gray-400 mb-1">Median Return</div>
                              <div className="text-xl font-bold text-cyan-400">
                                {analyticsData.analytics.monte_carlo.monte_carlo?.return_pct?.median}%
                              </div>
                            </div>
                            <div className="bg-gray-800 rounded-lg p-4">
                              <div className="text-xs text-gray-400 mb-1">95% CI Range</div>
                              <div className="text-sm font-bold text-purple-400">
                                {analyticsData.analytics.monte_carlo.confidence_interval?.return_range?.[0]}% to {analyticsData.analytics.monte_carlo.confidence_interval?.return_range?.[1]}%
                              </div>
                            </div>
                          </div>
                          <div className="grid grid-cols-3 gap-4">
                            <div className="bg-gray-800 rounded-lg p-3">
                              <div className="text-xs text-gray-400">P(Double Money)</div>
                              <div className="text-lg font-bold">{analyticsData.analytics.monte_carlo.probabilities?.double_money}%</div>
                            </div>
                            <div className="bg-gray-800 rounded-lg p-3">
                              <div className="text-xs text-gray-400">P(Lose 50%)</div>
                              <div className="text-lg font-bold text-red-400">{analyticsData.analytics.monte_carlo.probabilities?.lose_50_pct}%</div>
                            </div>
                            <div className="bg-gray-800 rounded-lg p-3">
                              <div className="text-xs text-gray-400">P(DD &gt; 50%)</div>
                              <div className="text-lg font-bold text-orange-400">{analyticsData.analytics.monte_carlo.probabilities?.drawdown_over_50}%</div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Monthly Performance & Streaks */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Monthly */}
                        {analyticsData.analytics?.monthly && (
                          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                            <h3 className="font-bold mb-4 flex items-center gap-2">
                              <Calendar className="w-5 h-5 text-green-400" />
                              Monthly Performance
                            </h3>
                            <div className="flex justify-between items-center mb-4">
                              <div>
                                <div className="text-3xl font-bold text-green-400">
                                  {analyticsData.analytics.monthly.monthly_win_rate}%
                                </div>
                                <div className="text-sm text-gray-400">Profitable Months</div>
                              </div>
                              <div className="text-right">
                                <div className="text-sm text-gray-400">
                                  {analyticsData.analytics.monthly.profitable_months}/{analyticsData.analytics.monthly.total_months} months
                                </div>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {analyticsData.analytics.monthly.months?.slice(-12).map((m: any) => (
                                <div
                                  key={m.month}
                                  title={`${m.month}: $${m.total_pnl.toFixed(0)}`}
                                  className={`w-6 h-6 rounded flex items-center justify-center text-xs ${
                                    m.is_profitable ? 'bg-green-900 text-green-400' : 'bg-red-900 text-red-400'
                                  }`}
                                >
                                  {m.is_profitable ? '+' : '-'}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Streaks */}
                        {analyticsData.analytics?.streaks && (
                          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                            <h3 className="font-bold mb-4 flex items-center gap-2">
                              <TrendingUp className="w-5 h-5 text-yellow-400" />
                              Win/Loss Streaks
                            </h3>
                            <div className="grid grid-cols-2 gap-4">
                              <div className="bg-green-900/20 border border-green-800 rounded-lg p-3 text-center">
                                <div className="text-3xl font-bold text-green-400">
                                  {analyticsData.analytics.streaks.max_win_streak}
                                </div>
                                <div className="text-xs text-gray-400">Max Win Streak</div>
                                <div className="text-xs text-green-400">
                                  Avg: {analyticsData.analytics.streaks.avg_win_streak}
                                </div>
                              </div>
                              <div className="bg-red-900/20 border border-red-800 rounded-lg p-3 text-center">
                                <div className="text-3xl font-bold text-red-400">
                                  {analyticsData.analytics.streaks.max_loss_streak}
                                </div>
                                <div className="text-xs text-gray-400">Max Loss Streak</div>
                                <div className="text-xs text-red-400">
                                  Avg: {analyticsData.analytics.streaks.avg_loss_streak}
                                </div>
                              </div>
                            </div>
                            <div className="mt-3 text-center text-sm">
                              <span className={analyticsData.analytics.streaks.current_streak?.type === 'WIN' ? 'text-green-400' : 'text-red-400'}>
                                Current: {analyticsData.analytics.streaks.current_streak?.count} {analyticsData.analytics.streaks.current_streak?.type?.toLowerCase()}s
                              </span>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Trade Inspector */}
                      {liveJobResult?.all_trades && (
                        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                          <h3 className="font-bold mb-4 flex items-center gap-2">
                            <Search className="w-5 h-5 text-purple-400" />
                            Trade Inspector
                          </h3>
                          <div className="flex gap-4 mb-4">
                            <select
                              value={selectedTradeForInspection || ''}
                              onChange={(e) => {
                                const num = Number(e.target.value)
                                setSelectedTradeForInspection(num || null)
                                setTradeInspectorData(null)
                              }}
                              className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2"
                            >
                              <option value="">Select a trade to inspect...</option>
                              {liveJobResult.all_trades.slice(0, 100).map((trade: any) => (
                                <option key={trade.trade_number} value={trade.trade_number}>
                                  #{trade.trade_number} - {trade.trade_date} - {trade.outcome} (${trade.net_pnl?.toFixed(0)})
                                </option>
                              ))}
                            </select>
                            <button
                              onClick={async () => {
                                if (!selectedTradeForInspection || !completedJobId) return
                                try {
                                  const response = await fetch(`${API_URL}/api/zero-dte/analytics/trade/${completedJobId}/${selectedTradeForInspection}`)
                                  const data = await response.json()
                                  if (data.success) {
                                    setTradeInspectorData(data)
                                  }
                                } catch (err) {
                                  console.error('Failed to load trade details:', err)
                                }
                              }}
                              disabled={!selectedTradeForInspection}
                              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg disabled:opacity-50"
                            >
                              Inspect
                            </button>
                          </div>

                          {tradeInspectorData && (
                            <div className="border border-purple-800 rounded-lg p-4 bg-purple-900/10">
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                                <div>
                                  <div className="text-xs text-gray-400">Entry Price</div>
                                  <div className="font-bold">${tradeInspectorData.context?.entry_price?.toFixed(2)}</div>
                                </div>
                                <div>
                                  <div className="text-xs text-gray-400">Put Short Strike</div>
                                  <div className="font-bold text-red-400">${tradeInspectorData.context?.put_short_strike}</div>
                                  <div className="text-xs text-gray-500">{tradeInspectorData.context?.put_distance_pct}% OTM</div>
                                </div>
                                <div>
                                  <div className="text-xs text-gray-400">Call Short Strike</div>
                                  <div className="font-bold text-green-400">${tradeInspectorData.context?.call_short_strike}</div>
                                  <div className="text-xs text-gray-500">{tradeInspectorData.context?.call_distance_pct}% OTM</div>
                                </div>
                                <div>
                                  <div className="text-xs text-gray-400">VIX</div>
                                  <div className="font-bold">{tradeInspectorData.market_conditions?.vix?.toFixed(1)}</div>
                                </div>
                              </div>
                              {tradeInspectorData.context?.gex_put_wall && (
                                <div className="grid grid-cols-2 gap-4 mb-4 p-3 bg-emerald-900/20 rounded-lg">
                                  <div>
                                    <div className="text-xs text-gray-400">GEX Put Wall</div>
                                    <div className="font-bold text-emerald-400">${tradeInspectorData.context.gex_put_wall}</div>
                                    <div className="text-xs text-gray-500">
                                      Strike is {tradeInspectorData.context.put_strike_vs_wall} wall ({tradeInspectorData.context.put_wall_cushion_pct}% cushion)
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-xs text-gray-400">GEX Call Wall</div>
                                    <div className="font-bold text-emerald-400">${tradeInspectorData.context.gex_call_wall}</div>
                                    <div className="text-xs text-gray-500">
                                      Strike is {tradeInspectorData.context.call_strike_vs_wall} wall ({tradeInspectorData.context.call_wall_cushion_pct}% cushion)
                                    </div>
                                  </div>
                                </div>
                              )}
                              <div className="flex items-center justify-between">
                                <div>
                                  <span className={`px-3 py-1 rounded-full text-sm ${
                                    tradeInspectorData.outcome_analysis?.outcome === 'WIN' ? 'bg-green-900 text-green-400' : 'bg-red-900 text-red-400'
                                  }`}>
                                    {tradeInspectorData.outcome_analysis?.outcome}
                                  </span>
                                  <span className="ml-2 text-sm text-gray-400">
                                    Exit: {tradeInspectorData.outcome_analysis?.exit_type}
                                  </span>
                                </div>
                                <div className={`text-xl font-bold ${tradeInspectorData.outcome_analysis?.net_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  ${tradeInspectorData.outcome_analysis?.net_pnl?.toFixed(2)}
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Compare Tab */}
              {activeTab === 'compare' && (
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="flex justify-between items-center mb-4">
                    <div>
                      <h3 className="font-bold">Backtest History</h3>
                      <p className="text-gray-400 text-sm">
                        {results.length} saved backtest{results.length !== 1 ? 's' : ''}. Click a row to view details.
                      </p>
                    </div>
                    {results.length > 0 && (
                      <button
                        onClick={exportAllResults}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium"
                      >
                        <Download className="w-4 h-4" />
                        Export All CSV
                      </button>
                    )}
                  </div>

                  {results.length === 0 ? (
                    <div className="text-center py-8 text-gray-400">
                      <Database className="w-12 h-12 mx-auto mb-3 opacity-50" />
                      <p>No saved backtests yet. Run a backtest to see results here.</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="bg-gray-950 text-sm text-gray-400">
                          <tr>
                            <th className="text-left p-4">Date</th>
                            <th className="text-left p-4">Strategy</th>
                            <th className="text-left p-4">Period</th>
                            <th className="text-right p-4">Initial</th>
                            <th className="text-right p-4">Final</th>
                            <th className="text-right p-4">Return</th>
                            <th className="text-right p-4">Monthly Avg</th>
                            <th className="text-right p-4">Win Rate</th>
                            <th className="text-right p-4">Trades</th>
                            <th className="text-center p-4">Export</th>
                          </tr>
                        </thead>
                        <tbody>
                          {results.map(result => (
                            <tr
                              key={result.id}
                              onClick={() => setSelectedResult(result)}
                              className={`border-b border-gray-800 cursor-pointer hover:bg-gray-800/50 ${
                                selectedResult?.id === result.id ? 'bg-blue-900/20' : ''
                              }`}
                            >
                              <td className="p-4 text-sm text-gray-400">
                                {new Date(result.created_at).toLocaleDateString()}
                              </td>
                              <td className="p-4 font-medium">{result.strategy}</td>
                              <td className="p-4 text-sm text-gray-400">
                                {result.start_date} - {result.end_date}
                              </td>
                              <td className="p-4 text-right">
                                ${result.initial_capital?.toLocaleString()}
                              </td>
                              <td className="p-4 text-right font-bold text-green-400">
                                ${result.final_equity?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                              </td>
                              <td className={`p-4 text-right font-bold ${result.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {result.total_return_pct?.toFixed(1)}%
                              </td>
                              <td className={`p-4 text-right ${result.avg_monthly_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {result.avg_monthly_return_pct?.toFixed(2)}%
                              </td>
                              <td className="p-4 text-right text-blue-400">
                                {result.win_rate?.toFixed(1)}%
                              </td>
                              <td className="p-4 text-right">{result.total_trades}</td>
                              <td className="p-4 text-center">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    exportResultById(result.id)
                                  }}
                                  className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                                  title="Export this result"
                                >
                                  <Download className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* Empty State */}
          {!hasValidResult(liveJobResult) && results.length === 0 && !running && (
            <div className="bg-gray-900 border-2 border-dashed border-gray-700 rounded-xl p-12 text-center">
              <TestTube className="w-16 h-16 mx-auto mb-4 text-gray-600" />
              <h2 className="text-2xl font-bold mb-2">No Backtest Results Yet</h2>
              <p className="text-gray-400 mb-6 max-w-lg mx-auto">
                Configure your strategy parameters above and click "Run Backtest" to analyze the
                0DTE Iron Condor hybrid scaling strategy with your ORAT historical data.
              </p>
              {error && (
                <div className="mt-4 p-4 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm max-w-lg mx-auto">
                  <AlertTriangle className="w-5 h-5 inline mr-2" />
                  {error}
                </div>
              )}
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
