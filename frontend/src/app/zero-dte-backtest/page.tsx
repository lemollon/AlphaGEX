'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  TestTube, TrendingUp, TrendingDown, Activity, BarChart3, PlayCircle,
  RefreshCw, AlertTriangle, Calendar, Clock, Loader2, CheckCircle,
  Settings, DollarSign, Target, Layers, ChevronDown, ChevronUp,
  Download, FileSpreadsheet, LineChart, PieChart, ArrowUpDown,
  Database, Info, Percent, Shield, Zap
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
  const [activeTab, setActiveTab] = useState<'overview' | 'charts' | 'trades' | 'compare'>('overview')

  // Backend connection status
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'error'>('checking')
  const [oratDataInfo, setOratDataInfo] = useState<any>(null)

  // Comparison state
  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([])

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

  // Load strategies and tiers on mount
  useEffect(() => {
    checkBackendHealth()
    loadStrategies()
    loadStrategyTypes()
    loadTiers()
    loadResults()
    loadPresets()
    loadSavedStrategies()
  }, [])

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

  // Poll job status
  useEffect(() => {
    if (!currentJobId || !running) return

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/api/zero-dte/job/${currentJobId}`)

        // Handle HTTP errors
        if (!response.ok) {
          console.error(`Job poll failed: HTTP ${response.status}`)
          if (response.status === 404) {
            setRunning(false)
            setCurrentJobId(null)
            setError('Job not found - backend may have restarted. Please try again.')
          }
          return
        }

        const data = await response.json()

        if (data.job) {
          setJobStatus(data.job)

          if (data.job.status === 'completed') {
            setRunning(false)
            setCompletedJobId(currentJobId)  // Save for export buttons
            setCurrentJobId(null)
            setLiveJobResult(data.job.result)
            loadResults()
          } else if (data.job.status === 'failed') {
            setRunning(false)
            setCurrentJobId(null)
            setError(data.job.error || 'Backtest failed')
          }
        }
      } catch (err) {
        console.error('Failed to poll job status:', err)
        // Network error - show user-friendly message
        setError('Lost connection to backend - check if server is running at ' + API_URL)
        setRunning(false)
        setCurrentJobId(null)
      }
    }, 2000)

    return () => clearInterval(interval)
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

      <main className="pt-16">
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

          {/* Strategy Selection */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {strategies.map(strategy => (
              <div
                key={strategy.id}
                onClick={() => selectStrategy(strategy.id)}
                className={`bg-gray-900 border rounded-lg p-4 cursor-pointer transition-all ${
                  config.strategy === strategy.id
                    ? 'border-blue-500 ring-2 ring-blue-500/20'
                    : 'border-gray-800 hover:border-gray-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-bold">{strategy.name}</h3>
                  {config.strategy === strategy.id && (
                    <CheckCircle className="w-5 h-5 text-blue-400" />
                  )}
                </div>
                <p className="text-sm text-gray-400 mb-3">{strategy.description}</p>
                <div className="flex flex-wrap gap-1">
                  {strategy.features.slice(0, 2).map((f, i) => (
                    <span key={i} className="px-2 py-0.5 bg-gray-800 rounded text-xs text-gray-300">
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            ))}
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

              {/* Strategy Type */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Strategy Type</label>
                <select
                  value={config.strategy_type}
                  onChange={e => setConfig(prev => ({ ...prev, strategy_type: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                >
                  {strategyTypes.map(st => (
                    <option key={st.id} value={st.id}>{st.name}</option>
                  ))}
                </select>
                {config.strategy_type === 'gex_protected_iron_condor' && (
                  <p className="mt-1 text-xs text-emerald-400">
                    Uses GEX walls for strike protection, falls back to SD when unavailable
                  </p>
                )}
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
                </div>
              </div>
            )}

            {/* Run Button */}
            <div className="mt-6 flex items-center gap-4">
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
                {['overview', 'charts', 'trades', 'compare'].map(tab => (
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

              {/* Compare Tab */}
              {activeTab === 'compare' && (
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="font-bold mb-4">Compare Backtests</h3>
                  <p className="text-gray-400 mb-4">
                    Run multiple backtests with different parameters, then compare them here.
                  </p>

                  {/* Results History */}
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
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
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
