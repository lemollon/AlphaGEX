'use client'

import { useState } from 'react'
import { Target, TrendingUp, TrendingDown, Activity, DollarSign, CheckCircle, Clock, RefreshCw, BarChart3, ChevronDown, ChevronUp, Play, Settings, FileText, Zap, Brain, Crosshair, ScrollText } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  useATHENAStatus,
  useATHENAPositions,
  useATHENASignals,
  useATHENAPerformance,
  useATHENAOracleAdvice,
  useATHENAMLSignal,
  useATHENALogs,
  useATHENADecisions
} from '@/lib/hooks/useMarketData'

interface Heartbeat {
  last_scan: string | null
  last_scan_iso: string | null
  status: string
  scan_count_today: number
  details: Record<string, any>
}

interface ATHENAStatus {
  mode: string
  capital: number
  open_positions: number
  closed_today: number
  daily_trades: number
  daily_pnl: number
  oracle_available: boolean
  kronos_available: boolean
  tradier_available: boolean
  gex_ml_available: boolean
  is_active: boolean
  scan_interval_minutes?: number
  heartbeat?: Heartbeat
  config?: {
    risk_per_trade: number
    spread_width: number
    wall_filter_pct: number
    ticker: string
    max_daily_trades: number
  }
}

interface SpreadPosition {
  position_id: string
  spread_type: string
  ticker: string
  long_strike: number
  short_strike: number
  expiration: string
  entry_price: number
  contracts: number
  max_profit: number
  max_loss: number
  spot_at_entry: number
  gex_regime: string
  oracle_confidence: number
  status: string
  exit_price: number
  exit_reason: string
  realized_pnl: number
  created_at: string
  exit_time: string | null
}

interface Signal {
  id: number
  created_at: string
  ticker: string
  direction: string
  confidence: number
  oracle_advice: string
  gex_regime: string
  call_wall: number
  put_wall: number
  spot_price: number
  spread_type: string
  reasoning: string
  status: string
}

interface LogEntry {
  id: number
  created_at: string
  level: string
  message: string
  details: Record<string, any> | null
}

interface OracleAdvice {
  advice: string
  win_probability: number
  confidence: number
  reasoning: string
  suggested_call_strike: number | null
  use_gex_walls: boolean
}

interface MLSignal {
  advice: string
  spread_type: string
  confidence: number
  win_probability: number
  expected_volatility: number
  suggested_strikes: { entry_strike: number, exit_strike: number }
  reasoning: string
  model_predictions: {
    direction: string
    flip_gravity: number
    magnet_attraction: number
    pin_zone: number
    volatility: number
  }
  gex_context: {
    spot_price: number
    regime: string
    call_wall: number
    put_wall: number
    net_gex: number
  }
}

interface PerformanceData {
  summary: {
    total_trades: number
    total_wins: number
    total_pnl: number
    avg_win_rate: number
    bullish_count: number
    bearish_count: number
  }
  daily: {
    date: string
    trades: number
    wins: number
    net_pnl: number
    win_rate: number
  }[]
}

interface DecisionLog {
  decision_id: string
  bot_name: string
  symbol: string
  decision_type: string
  action: string
  what: string
  why: string
  how: string
  timestamp: string
  actual_pnl?: number
  outcome_notes?: string
  underlying_price_at_entry?: number
  underlying_price_at_exit?: number

  // Trade legs with Greeks
  legs?: Array<{
    leg_id: number
    action: string
    option_type: string
    strike: number
    expiration: string
    entry_price: number
    exit_price: number
    contracts: number
    // Greeks
    delta?: number
    gamma?: number
    theta?: number
    vega?: number
    iv?: number
    realized_pnl?: number
  }>

  // ML Predictions (ATHENA primary signal source)
  ml_predictions?: {
    direction: string
    direction_probability: number
    advice: string
    suggested_spread_type: string
    flip_gravity: number
    magnet_attraction: number
    pin_zone_probability: number
    expected_volatility: number
    ml_confidence: number
    win_probability: number
    suggested_entry_strike: number
    suggested_exit_strike: number
    ml_reasoning: string
    model_version: string
    models_used: string[]
  }

  // Oracle/ML advice (Oracle fallback)
  oracle_advice?: {
    advice: string
    win_probability: number
    confidence: number
    suggested_risk_pct: number
    reasoning: string
    suggested_sd_multiplier?: number
    use_gex_walls?: boolean
    suggested_call_strike?: number
    top_factors?: Array<{ factor: string; importance: number }>
    model_version?: string
    claude_analysis?: {
      analysis: string
      confidence_adjustment?: number
      risk_factors: string[]
      opportunities?: string[]
      recommendation?: string
    }
  }

  // GEX context (extended)
  gex_context?: {
    net_gex: number
    gex_normalized?: number
    call_wall: number
    put_wall: number
    flip_point: number
    distance_to_flip_pct?: number
    regime: string
    between_walls: boolean
  }

  // Market context (extended)
  market_context?: {
    spot_price: number
    vix: number
    vix_percentile?: number
    expected_move?: number
    trend?: string
    day_of_week?: number
    days_to_opex?: number
  }

  // Backtest stats
  backtest_stats?: {
    strategy_name: string
    win_rate: number
    expectancy: number
    avg_win: number
    avg_loss: number
    sharpe_ratio: number
    max_drawdown: number
    total_trades: number
    uses_real_data: boolean
    backtest_period: string
  }

  // Position sizing (extended)
  position_sizing?: {
    contracts: number
    position_dollars: number
    max_risk_dollars: number
    sizing_method?: string
    target_profit_pct?: number
    stop_loss_pct?: number
    probability_of_profit: number
  }

  // Risk checks
  risk_checks?: Array<{
    check: string
    passed: boolean
    value?: string
    threshold?: string
  }>
  passed_risk_checks?: boolean

  // Alternatives (extended)
  alternatives?: {
    primary_reason: string
    supporting_factors: string[]
    risk_factors: string[]
    alternatives_considered?: string[]
    why_not_alternatives?: string[]
  }
}

export default function ATHENAPage() {
  // SWR hooks for data fetching with caching
  const { data: statusRes, error: statusError, isLoading: statusLoading, isValidating: statusValidating, mutate: mutateStatus } = useATHENAStatus()
  const { data: positionsRes, isValidating: posValidating, mutate: mutatePositions } = useATHENAPositions()
  const { data: signalsRes, isValidating: signalsValidating, mutate: mutateSignals } = useATHENASignals(20)
  const { data: performanceRes, isValidating: perfValidating, mutate: mutatePerf } = useATHENAPerformance(30)
  const { data: adviceRes, isValidating: adviceValidating, mutate: mutateAdvice } = useATHENAOracleAdvice()
  const { data: mlSignalRes, isValidating: mlValidating, mutate: mutateML } = useATHENAMLSignal()
  const { data: logsRes, isValidating: logsValidating, mutate: mutateLogs } = useATHENALogs(undefined, 50)
  const { data: decisionsRes, isValidating: decisionsValidating, mutate: mutateDecisions } = useATHENADecisions(100)

  // Extract data from responses
  const status = statusRes?.data as ATHENAStatus | undefined
  const positions = (positionsRes?.data || []) as SpreadPosition[]
  const signals = (signalsRes?.data || []) as Signal[]
  const performance = performanceRes?.data as PerformanceData | undefined
  const oracleAdvice = adviceRes?.data as OracleAdvice | undefined
  const mlSignal = mlSignalRes?.data as MLSignal | undefined
  const logs = (logsRes?.data || []) as LogEntry[]
  const decisions = (decisionsRes?.data || []) as DecisionLog[]

  const loading = statusLoading && !status
  const error = statusError?.message || null
  const isRefreshing = statusValidating || posValidating || signalsValidating || perfValidating || adviceValidating || mlValidating || logsValidating || decisionsValidating

  // UI State - default to expanded for better visibility
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'signals' | 'logs'>('overview')
  const [showClosedPositions, setShowClosedPositions] = useState(true)
  const [runningCycle, setRunningCycle] = useState(false)
  const [expandedDecision, setExpandedDecision] = useState<string | null>(null)

  // Manual refresh function
  const fetchData = () => {
    mutateStatus()
    mutatePositions()
    mutateSignals()
    mutatePerf()
    mutateAdvice()
    mutateML()
    mutateLogs()
    mutateDecisions()
  }

  // Helper functions for decision display
  const getDecisionTypeBadge = (type: string) => {
    switch (type) {
      case 'ENTRY_SIGNAL': return { bg: 'bg-green-900/50', text: 'text-green-400' }
      case 'EXIT_SIGNAL': return { bg: 'bg-red-900/50', text: 'text-red-400' }
      case 'NO_TRADE': return { bg: 'bg-gray-700', text: 'text-gray-400' }
      default: return { bg: 'bg-gray-700', text: 'text-gray-400' }
    }
  }

  const getActionColor = (action: string) => {
    switch (action?.toUpperCase()) {
      case 'BUY': return 'text-green-400'
      case 'SELL': return 'text-red-400'
      case 'CLOSE': return 'text-yellow-400'
      case 'SKIP': return 'text-gray-400'
      default: return 'text-gray-400'
    }
  }

  const runCycle = async () => {
    setRunningCycle(true)
    try {
      const res = await apiClient.runATHENACycle()
      if (res.data?.success) {
        fetchData()
      }
    } catch (err) {
      console.error('Failed to run cycle:', err)
    } finally {
      setRunningCycle(false)
    }
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value)
  }

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
  }

  // Build equity curve from closed positions
  const buildEquityCurve = () => {
    const closedPositions = positions.filter(p => p.status === 'closed' && p.exit_time)
    if (closedPositions.length === 0) return []

    // Sort by close date
    const sorted = [...closedPositions].sort((a, b) =>
      new Date(a.exit_time!).getTime() - new Date(b.exit_time!).getTime()
    )

    // Group by date
    const byDate: Record<string, number> = {}
    sorted.forEach(pos => {
      const date = new Date(pos.exit_time!).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      byDate[date] = (byDate[date] || 0) + (pos.realized_pnl || 0)
    })

    // Build cumulative equity
    const startingCapital = status?.capital || 100000
    let cumPnl = 0
    return Object.keys(byDate).map(date => {
      cumPnl += byDate[date]
      return {
        date,
        equity: startingCapital + cumPnl,
        daily_pnl: byDate[date],
        pnl: cumPnl
      }
    })
  }

  const equityData = buildEquityCurve()
  const closedPositions = positions.filter(p => p.status === 'closed')
  const totalPnl = closedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0)

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-16 pt-24">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Target className="w-8 h-8 text-orange-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">ATHENA</h1>
                <p className="text-gray-400 text-sm">Directional Spread Trading Bot</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-gray-500 text-sm">
                Auto-refresh 30s • Cached
              </span>
              <button
                onClick={fetchData}
                disabled={isRefreshing}
                className="p-2 bg-gray-800 rounded-lg hover:bg-gray-700 transition disabled:opacity-50"
              >
                <RefreshCw className={`w-5 h-5 text-gray-400 ${isRefreshing ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={runCycle}
                disabled={runningCycle}
                className="flex items-center gap-2 px-4 py-2 bg-orange-600 rounded-lg hover:bg-orange-500 transition disabled:opacity-50"
              >
                <Play className={`w-4 h-4 ${runningCycle ? 'animate-pulse' : ''}`} />
                <span className="text-white text-sm">Run Cycle</span>
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-6">
            {(['overview', 'positions', 'signals', 'logs'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-lg capitalize transition ${
                  activeTab === tab
                    ? 'bg-orange-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Heartbeat Status Bar */}
          <div className="mb-4 bg-gray-800/50 rounded-lg p-3 border border-gray-700">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${
                    status?.heartbeat?.status === 'TRADED' ? 'bg-green-500 animate-pulse' :
                    status?.heartbeat?.status === 'SCAN_COMPLETE' ? 'bg-blue-500' :
                    status?.heartbeat?.status === 'ERROR' ? 'bg-red-500' :
                    status?.heartbeat?.status === 'MARKET_CLOSED' ? 'bg-yellow-500' :
                    'bg-gray-500'
                  }`} />
                  <span className="text-gray-400 text-sm">Heartbeat</span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Last Scan: </span>
                  <span className={`font-mono ${status?.heartbeat?.last_scan ? 'text-white' : 'text-gray-500'}`}>
                    {status?.heartbeat?.last_scan || 'Never'}
                  </span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Status: </span>
                  <span className={`font-medium ${
                    status?.heartbeat?.status === 'TRADED' ? 'text-green-400' :
                    status?.heartbeat?.status === 'SCAN_COMPLETE' ? 'text-blue-400' :
                    status?.heartbeat?.status === 'ERROR' ? 'text-red-400' :
                    'text-gray-400'
                  }`}>
                    {status?.heartbeat?.status?.replace(/_/g, ' ') || 'Unknown'}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Scans Today: </span>
                  <span className="text-white font-bold">{status?.heartbeat?.scan_count_today || 0}</span>
                </div>
                <div>
                  <span className="text-gray-500">Interval: </span>
                  <span className="text-cyan-400">{status?.scan_interval_minutes || 5} min</span>
                </div>
                <Clock className="w-4 h-4 text-gray-500" />
              </div>
            </div>
          </div>

          {error && (
            <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 mb-6">
              <p className="text-red-400">{error}</p>
            </div>
          )}

          {activeTab === 'overview' && (
            <>
              {/* Status Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <DollarSign className="w-5 h-5 text-green-500" />
                    <span className="text-gray-400 text-sm">Capital</span>
                  </div>
                  <p className="text-2xl font-bold text-white">
                    {status ? formatCurrency(status.capital) : '--'}
                  </p>
                  <p className="text-sm text-gray-500">
                    Mode: <span className={status?.mode === 'paper' ? 'text-yellow-400' : 'text-green-400'}>
                      {status?.mode?.toUpperCase() || 'PAPER'}
                    </span>
                  </p>
                </div>

                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="w-5 h-5 text-blue-500" />
                    <span className="text-gray-400 text-sm">Positions</span>
                  </div>
                  <p className="text-2xl font-bold text-white">
                    {status?.open_positions || 0} open
                  </p>
                  <p className="text-sm text-gray-500">
                    {status?.closed_today || 0} closed today
                  </p>
                </div>

                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 className="w-5 h-5 text-purple-500" />
                    <span className="text-gray-400 text-sm">Daily P&L</span>
                  </div>
                  <p className={`text-2xl font-bold ${(status?.daily_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {status ? formatCurrency(status.daily_pnl) : '--'}
                  </p>
                  <p className="text-sm text-gray-500">
                    {status?.daily_trades || 0} trades today
                  </p>
                </div>

                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle className="w-5 h-5 text-emerald-500" />
                    <span className="text-gray-400 text-sm">Systems</span>
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${status?.gex_ml_available ? 'bg-green-500' : 'bg-red-500'}`} />
                      <span className="text-sm text-gray-300">GEX ML</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${status?.oracle_available ? 'bg-green-500' : 'bg-red-500'}`} />
                      <span className="text-sm text-gray-300">Oracle</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${status?.kronos_available ? 'bg-green-500' : 'bg-red-500'}`} />
                      <span className="text-sm text-gray-300">Kronos</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${status?.tradier_available ? 'bg-green-500' : 'bg-red-500'}`} />
                      <span className="text-sm text-gray-300">Tradier</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Live GEX Context Panel */}
              <div className="bg-gray-800 rounded-xl p-6 border border-purple-700/50 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Crosshair className="w-5 h-5 text-purple-500" />
                    <h2 className="text-lg font-semibold text-white">Live GEX Context</h2>
                    <span className="px-2 py-0.5 text-xs bg-purple-900/50 text-purple-400 rounded">REAL-TIME</span>
                  </div>
                  {status?.heartbeat?.details?.gex_context && (
                    <span className="text-xs text-gray-500">
                      Updated: {status.heartbeat.last_scan}
                    </span>
                  )}
                </div>

                {mlSignal?.gex_context || status?.heartbeat?.details?.gex_context ? (
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">SPY Price</p>
                      <p className="text-2xl font-bold text-white">
                        ${(mlSignal?.gex_context?.spot_price || status?.heartbeat?.details?.gex_context?.spot_price || 0).toFixed(2)}
                      </p>
                    </div>
                    <div className="bg-green-900/20 border border-green-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Put Wall (Support)</p>
                      <p className="text-2xl font-bold text-green-400">
                        ${(mlSignal?.gex_context?.put_wall || status?.heartbeat?.details?.gex_context?.put_wall || 0).toFixed(0)}
                      </p>
                    </div>
                    <div className="bg-red-900/20 border border-red-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Call Wall (Resistance)</p>
                      <p className="text-2xl font-bold text-red-400">
                        ${(mlSignal?.gex_context?.call_wall || status?.heartbeat?.details?.gex_context?.call_wall || 0).toFixed(0)}
                      </p>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">GEX Regime</p>
                      <p className={`text-xl font-bold ${
                        (mlSignal?.gex_context?.regime || status?.heartbeat?.details?.gex_context?.regime) === 'POSITIVE'
                          ? 'text-green-400'
                          : 'text-red-400'
                      }`}>
                        {mlSignal?.gex_context?.regime || status?.heartbeat?.details?.gex_context?.regime || 'N/A'}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {(mlSignal?.gex_context?.regime || status?.heartbeat?.details?.gex_context?.regime) === 'POSITIVE'
                          ? 'Dealers hedge → mean reversion'
                          : 'Dealers amplify → momentum'}
                      </p>
                    </div>
                    <div className="bg-purple-900/20 border border-purple-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Net GEX</p>
                      <p className="text-xl font-bold text-purple-400">
                        {((mlSignal?.gex_context?.net_gex || status?.heartbeat?.details?.gex_context?.net_gex || 0) / 1e9).toFixed(2)}B
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {(mlSignal?.gex_context?.net_gex || 0) > 0 ? 'Bullish gamma pressure' : 'Bearish gamma pressure'}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-4 text-gray-500">
                    <p>No GEX data available</p>
                    <p className="text-xs mt-1">GEX context will appear after ATHENA runs a scan during market hours</p>
                  </div>
                )}

                {/* Visual Range Bar */}
                {mlSignal?.gex_context?.spot_price && mlSignal?.gex_context?.put_wall && mlSignal?.gex_context?.call_wall && (
                  <div className="mt-4 pt-4 border-t border-gray-700">
                    <div className="flex items-center justify-between text-xs text-gray-500 mb-2">
                      <span>Put Wall ${mlSignal.gex_context.put_wall.toFixed(0)}</span>
                      <span className="text-white font-medium">SPY ${mlSignal.gex_context.spot_price.toFixed(2)}</span>
                      <span>Call Wall ${mlSignal.gex_context.call_wall.toFixed(0)}</span>
                    </div>
                    <div className="relative h-3 bg-gray-700 rounded-full overflow-hidden">
                      {/* Range background gradient */}
                      <div className="absolute inset-0 bg-gradient-to-r from-green-600/30 via-gray-600/30 to-red-600/30" />
                      {/* SPY position marker */}
                      {(() => {
                        const range = mlSignal.gex_context.call_wall - mlSignal.gex_context.put_wall
                        const position = ((mlSignal.gex_context.spot_price - mlSignal.gex_context.put_wall) / range) * 100
                        const clampedPosition = Math.max(0, Math.min(100, position))
                        return (
                          <div
                            className="absolute top-0 bottom-0 w-1 bg-white shadow-lg shadow-white/50"
                            style={{ left: `${clampedPosition}%` }}
                          />
                        )
                      })()}
                    </div>
                    <div className="flex justify-between text-xs mt-1">
                      <span className="text-green-400">Support Zone</span>
                      <span className="text-gray-400">
                        {(() => {
                          const range = mlSignal.gex_context.call_wall - mlSignal.gex_context.put_wall
                          const position = ((mlSignal.gex_context.spot_price - mlSignal.gex_context.put_wall) / range) * 100
                          if (position < 30) return 'Near Put Wall - Bullish Setup'
                          if (position > 70) return 'Near Call Wall - Bearish Setup'
                          return 'Between Walls - Range Bound'
                        })()}
                      </span>
                      <span className="text-red-400">Resistance Zone</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Equity Curve */}
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-orange-500" />
                    <h2 className="text-lg font-semibold text-white">Equity Curve</h2>
                  </div>
                  {totalPnl !== 0 && (
                    <span className={`text-sm font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {totalPnl >= 0 ? '+' : ''}{formatCurrency(totalPnl)}
                    </span>
                  )}
                </div>
                <div className="h-48 bg-gray-900/50 rounded-lg p-2">
                  {equityData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={equityData}>
                        <defs>
                          <linearGradient id="athenaEquity" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#F97316" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#F97316" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis
                          dataKey="date"
                          tick={{ fill: '#9CA3AF', fontSize: 12 }}
                          axisLine={{ stroke: '#374151' }}
                        />
                        <YAxis
                          tick={{ fill: '#9CA3AF', fontSize: 12 }}
                          axisLine={{ stroke: '#374151' }}
                          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                        />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }}
                          formatter={(value: number, name: string) => {
                            if (name === 'equity') return [formatCurrency(value), 'Equity']
                            if (name === 'daily_pnl') return [formatCurrency(value), 'Daily P&L']
                            if (name === 'pnl') return [formatCurrency(value), 'Total P&L']
                            return [value, name]
                          }}
                          labelFormatter={(label) => `Date: ${label}`}
                        />
                        <Area type="monotone" dataKey="equity" stroke="#F97316" strokeWidth={2} fill="url(#athenaEquity)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                      No equity data yet - chart appears after first closed trade
                    </div>
                  )}
                </div>
                {closedPositions.length > 0 && (
                  <div className="mt-4 grid grid-cols-3 gap-4 text-center border-t border-gray-700 pt-4">
                    <div>
                      <p className="text-gray-400 text-xs">Total Trades</p>
                      <p className="text-white font-bold">{closedPositions.length}</p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-xs">Win Rate</p>
                      <p className="text-white font-bold">
                        {closedPositions.length > 0
                          ? `${((closedPositions.filter(p => (p.realized_pnl || 0) > 0).length / closedPositions.length) * 100).toFixed(0)}%`
                          : '--'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-xs">Avg Trade</p>
                      <p className={`font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {closedPositions.length > 0
                          ? formatCurrency(totalPnl / closedPositions.length)
                          : '--'}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* ML Signal Card (Primary Signal Source) */}
              <div className="bg-gray-800 rounded-xl p-6 border border-orange-700/50 mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <Activity className="w-5 h-5 text-orange-500" />
                  <h2 className="text-lg font-semibold text-white">GEX ML Signal</h2>
                  <span className="px-2 py-0.5 text-xs bg-orange-900/50 text-orange-400 rounded">PRIMARY</span>
                </div>
                {mlSignal ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      <div>
                        <p className="text-gray-400 text-sm mb-1">Recommendation</p>
                        <p className={`text-xl font-bold ${
                          mlSignal.advice === 'LONG' ? 'text-green-400' :
                          mlSignal.advice === 'SHORT' ? 'text-red-400' :
                          'text-gray-400'
                        }`}>
                          {mlSignal.advice}
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-sm mb-1">Spread Type</p>
                        <p className={`text-lg font-semibold ${
                          mlSignal.spread_type === 'BULL_CALL_SPREAD' ? 'text-green-400' :
                          mlSignal.spread_type === 'BEAR_CALL_SPREAD' ? 'text-red-400' :
                          'text-gray-400'
                        }`}>
                          {mlSignal.spread_type?.replace('_', ' ') || 'NONE'}
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-sm mb-1">Confidence</p>
                        <p className="text-xl font-bold text-white">
                          {(mlSignal.confidence * 100).toFixed(1)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-sm mb-1">Win Probability</p>
                        <p className="text-xl font-bold text-white">
                          {(mlSignal.win_probability * 100).toFixed(1)}%
                        </p>
                      </div>
                    </div>

                    {mlSignal.model_predictions && (
                      <div className="pt-4 border-t border-gray-700">
                        <p className="text-gray-400 text-sm mb-2">Model Predictions</p>
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                          <div className="bg-gray-900 rounded p-2">
                            <p className="text-xs text-gray-500">Direction</p>
                            <p className={`text-sm font-medium ${
                              mlSignal.model_predictions.direction === 'UP' ? 'text-green-400' :
                              mlSignal.model_predictions.direction === 'DOWN' ? 'text-red-400' :
                              'text-gray-400'
                            }`}>{mlSignal.model_predictions.direction}</p>
                          </div>
                          <div className="bg-gray-900 rounded p-2">
                            <p className="text-xs text-gray-500">Flip Gravity</p>
                            <p className="text-sm font-medium text-white">{(mlSignal.model_predictions.flip_gravity * 100).toFixed(0)}%</p>
                          </div>
                          <div className="bg-gray-900 rounded p-2">
                            <p className="text-xs text-gray-500">Magnet Attraction</p>
                            <p className="text-sm font-medium text-white">{(mlSignal.model_predictions.magnet_attraction * 100).toFixed(0)}%</p>
                          </div>
                          <div className="bg-gray-900 rounded p-2">
                            <p className="text-xs text-gray-500">Pin Zone</p>
                            <p className="text-sm font-medium text-white">{(mlSignal.model_predictions.pin_zone * 100).toFixed(0)}%</p>
                          </div>
                          <div className="bg-gray-900 rounded p-2">
                            <p className="text-xs text-gray-500">Exp. Volatility</p>
                            <p className="text-sm font-medium text-white">{mlSignal.model_predictions.volatility?.toFixed(2)}%</p>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="pt-3">
                      <p className="text-gray-400 text-sm mb-1">Reasoning</p>
                      <p className="text-gray-300 text-sm">{mlSignal.reasoning}</p>
                    </div>
                  </div>
                ) : (
                  <p className="text-gray-500">No ML signal available (train models with train_gex_probability_models.py)</p>
                )}
              </div>

              {/* Oracle Advice Card (Fallback) */}
              <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <Zap className="w-5 h-5 text-yellow-500" />
                  <h2 className="text-lg font-semibold text-white">Oracle Advice</h2>
                  <span className="px-2 py-0.5 text-xs bg-gray-700 text-gray-400 rounded">FALLBACK</span>
                </div>
                {oracleAdvice ? (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Advice</p>
                      <p className={`text-xl font-bold ${
                        oracleAdvice.advice === 'TRADE_FULL' ? 'text-green-400' :
                        oracleAdvice.advice === 'TRADE_REDUCED' ? 'text-yellow-400' :
                        'text-red-400'
                      }`}>
                        {oracleAdvice.advice}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Win Probability</p>
                      <p className="text-xl font-bold text-white">
                        {(oracleAdvice.win_probability * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Confidence</p>
                      <p className="text-xl font-bold text-white">
                        {oracleAdvice.confidence.toFixed(1)}%
                      </p>
                    </div>
                    <div className="md:col-span-3">
                      <p className="text-gray-400 text-sm mb-1">Reasoning</p>
                      <p className="text-gray-300 text-sm">{oracleAdvice.reasoning}</p>
                    </div>
                  </div>
                ) : (
                  <p className="text-gray-500">No Oracle advice available (market may be closed)</p>
                )}
              </div>

              {/* Performance Chart */}
              {performance && performance.daily.length > 0 && (
                <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-6">
                  <h2 className="text-lg font-semibold text-white mb-4">Daily Performance</h2>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={performance.daily.slice().reverse()}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
                        <YAxis stroke="#9CA3AF" fontSize={12} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                          labelStyle={{ color: '#9CA3AF' }}
                        />
                        <Bar
                          dataKey="net_pnl"
                          fill="#F97316"
                          radius={[4, 4, 0, 0]}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-gray-700">
                    <div>
                      <p className="text-gray-400 text-sm">Total P&L</p>
                      <p className={`text-lg font-bold ${performance.summary.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(performance.summary.total_pnl)}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm">Win Rate</p>
                      <p className="text-lg font-bold text-white">
                        {performance.summary.avg_win_rate.toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm">Total Trades</p>
                      <p className="text-lg font-bold text-white">{performance.summary.total_trades}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Decision Log Panel */}
              <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
                <div className="p-4 border-b border-gray-700 flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <ScrollText className="w-5 h-5 text-orange-400" />
                      <h2 className="text-lg font-semibold text-white">Decision Log</h2>
                      <span className="text-sm text-gray-400">
                        {decisions.length} decisions
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mt-1">
                      Full audit trail: What, Why, How for every trading decision
                    </p>
                  </div>
                </div>

                <div className="p-4 space-y-3 max-h-[800px] overflow-y-auto">
                  {decisions.length > 0 ? (
                    decisions.map((decision) => {
                      const badge = getDecisionTypeBadge(decision.decision_type)
                      const isExpanded = expandedDecision === decision.decision_id

                      return (
                        <div
                          key={decision.decision_id}
                          className={`bg-gray-900/50 rounded-lg border transition-all ${
                            isExpanded ? 'border-orange-500/50' : 'border-gray-700 hover:border-gray-600'
                          }`}
                        >
                          {/* Decision Header */}
                          <div
                            className="p-3 cursor-pointer"
                            onClick={() => setExpandedDecision(isExpanded ? null : decision.decision_id)}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap mb-1">
                                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.bg} ${badge.text}`}>
                                    {decision.decision_type?.replace(/_/g, ' ')}
                                  </span>
                                  <span className={`text-sm font-medium ${getActionColor(decision.action)}`}>
                                    {decision.action}
                                  </span>
                                  {decision.symbol && (
                                    <span className="text-xs text-gray-400 font-mono">{decision.symbol}</span>
                                  )}
                                  {decision.actual_pnl !== undefined && decision.actual_pnl !== 0 && (
                                    <span className={`text-xs font-bold ${decision.actual_pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                      {decision.actual_pnl > 0 ? '+' : ''}{formatCurrency(decision.actual_pnl)}
                                    </span>
                                  )}
                                </div>
                                <p className="text-sm text-white truncate">
                                  <span className="text-gray-500">WHAT: </span>
                                  {decision.what}
                                </p>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="text-xs text-gray-500 whitespace-nowrap">
                                  {new Date(decision.timestamp).toLocaleString('en-US', {
                                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                                  })}
                                </span>
                                {isExpanded ? (
                                  <ChevronUp className="w-4 h-4 text-gray-400" />
                                ) : (
                                  <ChevronDown className="w-4 h-4 text-gray-400" />
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Expanded Details */}
                          {isExpanded && (
                            <div className="px-3 pb-3 space-y-3 border-t border-gray-700/50 pt-3">
                              {/* WHY Section */}
                              <div className="bg-yellow-900/10 border-l-2 border-yellow-500 pl-3 py-2">
                                <span className="text-yellow-400 text-xs font-bold">WHY:</span>
                                <p className="text-sm text-gray-300 mt-1">{decision.why || 'Not specified'}</p>
                                {decision.alternatives?.supporting_factors && decision.alternatives.supporting_factors.length > 0 && (
                                  <div className="mt-2 flex flex-wrap gap-1">
                                    {decision.alternatives.supporting_factors.map((f, i) => (
                                      <span key={i} className="px-2 py-0.5 bg-yellow-900/30 rounded text-xs text-yellow-300">{f}</span>
                                    ))}
                                  </div>
                                )}
                              </div>

                              {/* HOW Section */}
                              {decision.how && (
                                <div className="bg-blue-900/10 border-l-2 border-blue-500 pl-3 py-2">
                                  <span className="text-blue-400 text-xs font-bold">HOW:</span>
                                  <p className="text-sm text-gray-300 mt-1">{decision.how}</p>
                                </div>
                              )}

                              {/* Market Context & GEX */}
                              <div className="grid grid-cols-2 gap-3">
                                {/* Market Context (Extended) */}
                                <div className="bg-gray-800/50 rounded p-2">
                                  <span className="text-cyan-400 text-xs font-bold">MARKET AT DECISION:</span>
                                  <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
                                    <div>
                                      <span className="text-gray-500">{decision.symbol}:</span>
                                      <span className="text-white ml-1">${(decision.market_context?.spot_price || 0).toFixed(2)}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500">VIX:</span>
                                      <span className="text-yellow-400 ml-1">{(decision.market_context?.vix || 0).toFixed(1)}</span>
                                      {decision.market_context?.vix_percentile !== undefined && (
                                        <span className="text-gray-500 ml-1">({decision.market_context.vix_percentile}th %ile)</span>
                                      )}
                                    </div>
                                    {decision.market_context?.expected_move !== undefined && (
                                      <div>
                                        <span className="text-gray-500">Exp Move:</span>
                                        <span className="text-white ml-1">{decision.market_context.expected_move.toFixed(2)}%</span>
                                      </div>
                                    )}
                                    {decision.market_context?.trend && (
                                      <div>
                                        <span className="text-gray-500">Trend:</span>
                                        <span className={`ml-1 ${
                                          decision.market_context.trend === 'BULLISH' ? 'text-green-400' :
                                          decision.market_context.trend === 'BEARISH' ? 'text-red-400' : 'text-gray-400'
                                        }`}>{decision.market_context.trend}</span>
                                      </div>
                                    )}
                                    {decision.market_context?.days_to_opex !== undefined && (
                                      <div>
                                        <span className="text-gray-500">Days to OPEX:</span>
                                        <span className="text-white ml-1">{decision.market_context.days_to_opex}</span>
                                      </div>
                                    )}
                                  </div>
                                </div>

                                {/* GEX Context (Extended) */}
                                <div className="bg-purple-900/20 border border-purple-700/30 rounded p-2">
                                  <div className="flex items-center gap-1 mb-2">
                                    <Crosshair className="w-3 h-3 text-purple-400" />
                                    <span className="text-purple-400 text-xs font-bold">GEX LEVELS:</span>
                                  </div>
                                  <div className="grid grid-cols-2 gap-2 text-xs">
                                    <div>
                                      <span className="text-gray-500">Put Wall:</span>
                                      <span className="text-green-400 ml-1">${decision.gex_context?.put_wall || '-'}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500">Call Wall:</span>
                                      <span className="text-red-400 ml-1">${decision.gex_context?.call_wall || '-'}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500">Flip:</span>
                                      <span className="text-white ml-1">${decision.gex_context?.flip_point || '-'}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500">Regime:</span>
                                      <span className={`ml-1 ${decision.gex_context?.regime === 'POSITIVE' ? 'text-green-400' : decision.gex_context?.regime === 'NEGATIVE' ? 'text-red-400' : 'text-gray-400'}`}>
                                        {decision.gex_context?.regime || '-'}
                                      </span>
                                    </div>
                                    {decision.gex_context?.net_gex !== undefined && (
                                      <div className="col-span-2">
                                        <span className="text-gray-500">Net GEX:</span>
                                        <span className="text-white ml-1">{(decision.gex_context.net_gex / 1e9).toFixed(2)}B</span>
                                        {decision.gex_context?.between_walls && (
                                          <span className="ml-2 px-1 py-0.5 bg-purple-900/50 rounded text-purple-300">In Pin Zone</span>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>

                              {/* ML Predictions (ATHENA Primary) */}
                              {decision.ml_predictions && (
                                <div className="bg-orange-900/20 border border-orange-700/30 rounded p-2">
                                  <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                      <Zap className="w-4 h-4 text-orange-400" />
                                      <span className="text-orange-400 text-xs font-bold">GEX ML PREDICTIONS:</span>
                                    </div>
                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                      decision.ml_predictions.advice === 'LONG' ? 'bg-green-900/50 text-green-400' :
                                      decision.ml_predictions.advice === 'SHORT' ? 'bg-red-900/50 text-red-400' :
                                      'bg-gray-700 text-gray-400'
                                    }`}>
                                      {decision.ml_predictions.advice}
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-4 gap-2 text-xs mb-2">
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Direction</span>
                                      <span className={`font-bold ${
                                        decision.ml_predictions.direction === 'UP' ? 'text-green-400' :
                                        decision.ml_predictions.direction === 'DOWN' ? 'text-red-400' : 'text-gray-400'
                                      }`}>
                                        {decision.ml_predictions.direction} ({(decision.ml_predictions.direction_probability * 100).toFixed(0)}%)
                                      </span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Flip Gravity</span>
                                      <span className="text-purple-400 font-bold">{(decision.ml_predictions.flip_gravity * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Magnet</span>
                                      <span className="text-blue-400 font-bold">{(decision.ml_predictions.magnet_attraction * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Pin Zone</span>
                                      <span className="text-cyan-400 font-bold">{(decision.ml_predictions.pin_zone_probability * 100).toFixed(0)}%</span>
                                    </div>
                                  </div>
                                  <div className="grid grid-cols-3 gap-2 text-xs">
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Exp Volatility</span>
                                      <span className="text-yellow-400 font-bold">{(decision.ml_predictions.expected_volatility).toFixed(2)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">ML Confidence</span>
                                      <span className="text-white font-bold">{(decision.ml_predictions.ml_confidence * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Win Prob</span>
                                      <span className="text-green-400 font-bold">{(decision.ml_predictions.win_probability * 100).toFixed(0)}%</span>
                                    </div>
                                  </div>
                                  <div className="mt-2">
                                    <span className="text-gray-500 text-xs">Suggested: </span>
                                    <span className="text-orange-300 text-xs font-medium">{decision.ml_predictions.suggested_spread_type?.replace(/_/g, ' ')}</span>
                                  </div>
                                  {decision.ml_predictions.ml_reasoning && (
                                    <p className="text-xs text-gray-400 mt-2 italic">{decision.ml_predictions.ml_reasoning}</p>
                                  )}
                                </div>
                              )}

                              {/* Oracle/ML Advice (Fallback) */}
                              {decision.oracle_advice && (
                                <div className="bg-green-900/20 border border-green-700/30 rounded p-2">
                                  <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                      <Brain className="w-4 h-4 text-green-400" />
                                      <span className="text-green-400 text-xs font-bold">ORACLE PREDICTION:</span>
                                    </div>
                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                      decision.oracle_advice.advice?.includes('TRADE') ? 'bg-green-900/50 text-green-400' :
                                      decision.oracle_advice.advice?.includes('LONG') || decision.oracle_advice.advice?.includes('SHORT') ? 'bg-green-900/50 text-green-400' :
                                      'bg-red-900/50 text-red-400'
                                    }`}>
                                      {decision.oracle_advice.advice?.replace(/_/g, ' ')}
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-3 gap-2 text-xs mb-2">
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Win Prob</span>
                                      <span className="text-green-400 font-bold">{((decision.oracle_advice.win_probability || 0) * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Confidence</span>
                                      <span className="text-white font-bold">{((decision.oracle_advice.confidence || 0) * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Risk %</span>
                                      <span className="text-yellow-400 font-bold">{(decision.oracle_advice.suggested_risk_pct || 0).toFixed(1)}%</span>
                                    </div>
                                  </div>
                                  {decision.oracle_advice.reasoning && (
                                    <p className="text-xs text-gray-400 mt-2 italic">{decision.oracle_advice.reasoning}</p>
                                  )}
                                  {decision.oracle_advice.claude_analysis && (
                                    <div className="mt-2 pt-2 border-t border-green-700/30">
                                      <span className="text-xs text-green-300 font-medium">Claude AI Analysis:</span>
                                      <p className="text-xs text-gray-400 mt-1">{decision.oracle_advice.claude_analysis.analysis}</p>
                                      {decision.oracle_advice.claude_analysis.risk_factors?.length > 0 && (
                                        <div className="flex flex-wrap gap-1 mt-1">
                                          {decision.oracle_advice.claude_analysis.risk_factors.map((rf, i) => (
                                            <span key={i} className="px-1.5 py-0.5 bg-red-900/30 rounded text-xs text-red-400">{rf}</span>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* Backtest Stats */}
                              {decision.backtest_stats && decision.backtest_stats.win_rate > 0 && (
                                <div className="bg-blue-900/20 border border-blue-700/30 rounded p-2">
                                  <div className="flex items-center gap-2 mb-2">
                                    <BarChart3 className="w-4 h-4 text-blue-400" />
                                    <span className="text-blue-400 text-xs font-bold">BACKTEST BACKING:</span>
                                    {decision.backtest_stats.uses_real_data && (
                                      <span className="px-1.5 py-0.5 bg-green-900/30 rounded text-xs text-green-400">Real Data</span>
                                    )}
                                  </div>
                                  <div className="grid grid-cols-4 gap-2 text-xs">
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Win Rate</span>
                                      <span className="text-green-400 font-bold">{decision.backtest_stats.win_rate.toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Expectancy</span>
                                      <span className="text-white font-bold">${decision.backtest_stats.expectancy.toFixed(0)}</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Sharpe</span>
                                      <span className="text-cyan-400 font-bold">{decision.backtest_stats.sharpe_ratio.toFixed(2)}</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Trades</span>
                                      <span className="text-white font-bold">{decision.backtest_stats.total_trades}</span>
                                    </div>
                                  </div>
                                  {decision.backtest_stats.backtest_period && (
                                    <p className="text-xs text-gray-500 mt-2">Period: {decision.backtest_stats.backtest_period}</p>
                                  )}
                                </div>
                              )}

                              {/* Position Sizing (Extended) */}
                              {decision.position_sizing && (decision.position_sizing.contracts > 0 || decision.position_sizing.position_dollars > 0) && (
                                <div className="bg-gray-800/50 rounded p-2">
                                  <div className="flex items-center gap-2 mb-2">
                                    <DollarSign className="w-4 h-4 text-yellow-400" />
                                    <span className="text-yellow-400 text-xs font-bold">POSITION SIZING:</span>
                                  </div>
                                  <div className="grid grid-cols-4 gap-2 text-xs">
                                    <div>
                                      <span className="text-gray-500">Contracts:</span>
                                      <span className="text-white ml-1 font-bold">{decision.position_sizing.contracts}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500">Premium:</span>
                                      <span className="text-green-400 ml-1">${(decision.position_sizing.position_dollars || 0).toLocaleString()}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500">Max Risk:</span>
                                      <span className="text-red-400 ml-1">${(decision.position_sizing.max_risk_dollars || 0).toLocaleString()}</span>
                                    </div>
                                    {decision.position_sizing.probability_of_profit > 0 && (
                                      <div>
                                        <span className="text-gray-500">POP:</span>
                                        <span className="text-white ml-1">{(decision.position_sizing.probability_of_profit * 100).toFixed(0)}%</span>
                                      </div>
                                    )}
                                  </div>
                                  {(decision.position_sizing.target_profit_pct || decision.position_sizing.stop_loss_pct) && (
                                    <div className="grid grid-cols-2 gap-2 text-xs mt-2">
                                      {decision.position_sizing.target_profit_pct !== undefined && (
                                        <div>
                                          <span className="text-gray-500">Target:</span>
                                          <span className="text-green-400 ml-1">{decision.position_sizing.target_profit_pct}%</span>
                                        </div>
                                      )}
                                      {decision.position_sizing.stop_loss_pct !== undefined && (
                                        <div>
                                          <span className="text-gray-500">Stop:</span>
                                          <span className="text-red-400 ml-1">{decision.position_sizing.stop_loss_pct}%</span>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* Trade Legs with Greeks */}
                              {decision.legs && decision.legs.length > 0 && (
                                <div className="bg-gray-800/50 rounded p-2">
                                  <span className="text-cyan-400 text-xs font-bold">TRADE LEGS ({decision.legs.length}):</span>
                                  <div className="mt-2 overflow-x-auto">
                                    <table className="w-full text-xs">
                                      <thead>
                                        <tr className="text-gray-500">
                                          <th className="text-left py-1">Leg</th>
                                          <th className="text-left py-1">Type</th>
                                          <th className="text-right py-1">Strike</th>
                                          <th className="text-right py-1">Entry</th>
                                          {decision.legs?.some(l => l.delta) && <th className="text-right py-1">Delta</th>}
                                          {decision.legs?.some(l => l.theta) && <th className="text-right py-1">Theta</th>}
                                          {decision.legs?.some(l => l.iv) && <th className="text-right py-1">IV</th>}
                                          {decision.legs?.some(l => l.realized_pnl) && <th className="text-right py-1">P&L</th>}
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {decision.legs?.map((leg, i) => (
                                          <tr key={i} className="border-t border-gray-700/50">
                                            <td className="py-1">
                                              <span className={`${leg.action === 'BUY' ? 'text-green-400' : 'text-red-400'} font-medium`}>
                                                {leg.action}
                                              </span>
                                            </td>
                                            <td className="py-1 text-gray-400">{leg.contracts}x {leg.option_type?.toUpperCase()}</td>
                                            <td className="py-1 text-right text-white">${leg.strike}</td>
                                            <td className="py-1 text-right text-green-400">${leg.entry_price?.toFixed(2) || '-'}</td>
                                            {decision.legs?.some(l => l.delta) && (
                                              <td className="py-1 text-right text-blue-400">{leg.delta?.toFixed(2) || '-'}</td>
                                            )}
                                            {decision.legs?.some(l => l.theta) && (
                                              <td className="py-1 text-right text-purple-400">{leg.theta?.toFixed(3) || '-'}</td>
                                            )}
                                            {decision.legs?.some(l => l.iv) && (
                                              <td className="py-1 text-right text-yellow-400">{leg.iv ? (leg.iv * 100).toFixed(0) + '%' : '-'}</td>
                                            )}
                                            {decision.legs?.some(l => l.realized_pnl) && (
                                              <td className={`py-1 text-right font-bold ${(leg.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                {leg.realized_pnl ? `$${leg.realized_pnl.toFixed(0)}` : '-'}
                                              </td>
                                            )}
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              )}

                              {/* Risk Checks */}
                              {decision.risk_checks && decision.risk_checks.length > 0 && (
                                <div className="bg-gray-800/50 rounded p-2">
                                  <div className="flex items-center justify-between mb-2">
                                    <span className="text-cyan-400 text-xs font-bold">RISK CHECKS:</span>
                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                      decision.passed_risk_checks ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                                    }`}>
                                      {decision.passed_risk_checks ? 'ALL PASSED' : 'SOME FAILED'}
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-2 gap-2">
                                    {decision.risk_checks.map((check, i) => (
                                      <div key={i} className="flex items-center gap-2 text-xs">
                                        <span className={check.passed ? 'text-green-400' : 'text-red-400'}>
                                          {check.passed ? '✓' : '✗'}
                                        </span>
                                        <span className="text-gray-400">{check.check}:</span>
                                        <span className="text-white">{check.value || '-'}</span>
                                        {check.threshold && (
                                          <span className="text-gray-500">({check.threshold})</span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Alternatives Considered */}
                              {decision.alternatives?.alternatives_considered && decision.alternatives.alternatives_considered.length > 0 && (
                                <div className="bg-gray-800/50 rounded p-2">
                                  <span className="text-gray-400 text-xs font-bold">ALTERNATIVES CONSIDERED:</span>
                                  <div className="mt-2 space-y-1">
                                    {decision.alternatives.alternatives_considered.map((alt, i) => (
                                      <div key={i} className="flex items-start gap-2 text-xs">
                                        <span className="text-red-400">✗</span>
                                        <span className="text-gray-400">{alt}</span>
                                        {decision.alternatives?.why_not_alternatives?.[i] && (
                                          <span className="text-gray-500">- {decision.alternatives.why_not_alternatives[i]}</span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Risk Factors */}
                              {decision.alternatives?.risk_factors && decision.alternatives.risk_factors.length > 0 && (
                                <div className="flex flex-wrap gap-1">
                                  <span className="text-gray-500 text-xs">Risks:</span>
                                  {decision.alternatives.risk_factors.map((rf, i) => (
                                    <span key={i} className="px-1.5 py-0.5 bg-red-900/30 rounded text-xs text-red-400">{rf}</span>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })
                  ) : (
                    <div className="text-center py-8 text-gray-500">
                      No decisions logged yet. Decisions will appear here when ATHENA makes trading decisions.
                    </div>
                  )}
                </div>
              </div>
            </>
          )}

          {activeTab === 'positions' && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                <h2 className="text-lg font-semibold text-white">Positions</h2>
                <button
                  onClick={() => setShowClosedPositions(!showClosedPositions)}
                  className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition"
                >
                  {showClosedPositions ? 'Hide' : 'Show'} Closed
                  {showClosedPositions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-900">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">ID</th>
                      <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Type</th>
                      <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Strikes</th>
                      <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Contracts</th>
                      <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Entry</th>
                      <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Regime</th>
                      <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Status</th>
                      <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">P&L</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-700">
                    {positions
                      .filter(p => showClosedPositions || p.status === 'open')
                      .map((pos) => (
                        <tr key={pos.position_id} className="hover:bg-gray-700/50">
                          <td className="px-4 py-3 text-sm text-gray-300 font-mono">
                            {pos.position_id.slice(-8)}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 rounded text-xs font-medium ${
                              pos.spread_type === 'BULL_CALL_SPREAD'
                                ? 'bg-green-900/50 text-green-400'
                                : 'bg-red-900/50 text-red-400'
                            }`}>
                              {pos.spread_type === 'BULL_CALL_SPREAD' ? 'BULL CALL' : 'BEAR CALL'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-300">
                            ${pos.long_strike} / ${pos.short_strike}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-300">{pos.contracts}</td>
                          <td className="px-4 py-3 text-sm text-gray-300">${pos.entry_price.toFixed(2)}</td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 rounded text-xs ${
                              pos.gex_regime === 'POSITIVE'
                                ? 'bg-blue-900/50 text-blue-400'
                                : 'bg-orange-900/50 text-orange-400'
                            }`}>
                              {pos.gex_regime}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 rounded text-xs ${
                              pos.status === 'open'
                                ? 'bg-yellow-900/50 text-yellow-400'
                                : 'bg-gray-700 text-gray-400'
                            }`}>
                              {pos.status}
                            </span>
                          </td>
                          <td className={`px-4 py-3 text-sm font-medium ${
                            pos.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {pos.status === 'closed' ? formatCurrency(pos.realized_pnl) : '--'}
                          </td>
                        </tr>
                      ))}
                    {positions.length === 0 && (
                      <tr>
                        <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                          No positions found
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'signals' && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="p-4 border-b border-gray-700">
                <h2 className="text-lg font-semibold text-white">Recent Signals</h2>
              </div>
              <div className="divide-y divide-gray-700">
                {signals.map((signal) => (
                  <div key={signal.id} className="p-4 hover:bg-gray-700/50">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          signal.direction === 'BULLISH'
                            ? 'bg-green-900/50 text-green-400'
                            : signal.direction === 'BEARISH'
                            ? 'bg-red-900/50 text-red-400'
                            : 'bg-gray-700 text-gray-400'
                        }`}>
                          {signal.direction}
                        </span>
                        <span className="text-gray-400 text-sm">
                          {new Date(signal.created_at).toLocaleString()}
                        </span>
                      </div>
                      <span className={`px-2 py-1 rounded text-xs ${
                        signal.oracle_advice === 'TRADE_FULL'
                          ? 'bg-green-900/50 text-green-400'
                          : signal.oracle_advice === 'TRADE_REDUCED'
                          ? 'bg-yellow-900/50 text-yellow-400'
                          : 'bg-red-900/50 text-red-400'
                      }`}>
                        {signal.oracle_advice}
                      </span>
                    </div>
                    <div className="grid grid-cols-4 gap-4 text-sm mb-2">
                      <div>
                        <span className="text-gray-500">Confidence:</span>
                        <span className="text-white ml-2">{signal.confidence.toFixed(1)}%</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Spot:</span>
                        <span className="text-white ml-2">${signal.spot_price.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Call Wall:</span>
                        <span className="text-white ml-2">${signal.call_wall.toFixed(0)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Put Wall:</span>
                        <span className="text-white ml-2">${signal.put_wall.toFixed(0)}</span>
                      </div>
                    </div>
                    <p className="text-gray-400 text-sm">{signal.reasoning}</p>
                  </div>
                ))}
                {signals.length === 0 && (
                  <div className="p-8 text-center text-gray-500">
                    No signals found
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                <h2 className="text-lg font-semibold text-white">Recent Activity Logs</h2>
                <a href="/athena/logs" className="text-sm text-orange-400 hover:underline">View all logs →</a>
              </div>
              <div className="divide-y divide-gray-700 max-h-[600px] overflow-y-auto">
                {logs.map((log) => (
                  <div key={log.id} className={`p-3 ${
                    log.level === 'ERROR' ? 'bg-red-900/20' :
                    log.level === 'WARNING' ? 'bg-yellow-900/20' :
                    ''
                  }`}>
                    <div className="flex items-center gap-3 mb-1">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                        log.level === 'ERROR' ? 'bg-red-900 text-red-300' :
                        log.level === 'WARNING' ? 'bg-yellow-900 text-yellow-300' :
                        log.level === 'INFO' ? 'bg-blue-900 text-blue-300' :
                        'bg-gray-700 text-gray-300'
                      }`}>
                        {log.level}
                      </span>
                      <span className="text-xs text-gray-500">
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-gray-200 text-sm">{log.message}</p>
                    {log.details && (
                      <details className="mt-2">
                        <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400">
                          View details
                        </summary>
                        <pre className="mt-2 text-xs text-gray-400 bg-gray-900 rounded p-2 overflow-x-auto">
                          {JSON.stringify(log.details, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                ))}
                {logs.length === 0 && (
                  <div className="p-8 text-center text-gray-500">
                    No logs found
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
