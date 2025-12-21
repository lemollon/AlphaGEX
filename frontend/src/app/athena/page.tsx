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
  // Trade legs
  legs?: Array<{
    leg_id: number
    action: string
    option_type: string
    strike: number
    expiration: string
    entry_price: number
    exit_price: number
    contracts: number
  }>
  // Oracle/ML advice
  oracle_advice?: {
    advice: string
    win_probability: number
    confidence: number
    suggested_risk_pct: number
    reasoning: string
    claude_analysis?: {
      analysis: string
      risk_factors: string[]
    }
  }
  // GEX context
  gex_context?: {
    net_gex: number
    call_wall: number
    put_wall: number
    flip_point: number
    regime: string
    between_walls: boolean
  }
  // Market context
  market_context?: {
    spot_price: number
    vix: number
  }
  // Position sizing
  position_sizing?: {
    contracts: number
    position_dollars: number
    max_risk_dollars: number
    probability_of_profit: number
  }
  // Alternatives
  alternatives?: {
    primary_reason: string
    supporting_factors: string[]
    risk_factors: string[]
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

  // UI State
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'signals' | 'logs'>('overview')
  const [showClosedPositions, setShowClosedPositions] = useState(false)
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
                                  <div className="mt-2">
                                    <span className="text-xs text-gray-500">Supporting Factors:</span>
                                    <ul className="list-disc list-inside text-xs text-gray-400 mt-1">
                                      {decision.alternatives.supporting_factors.map((f, i) => (
                                        <li key={i}>{f}</li>
                                      ))}
                                    </ul>
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
                                {/* Market Context */}
                                <div className="bg-gray-800/50 rounded p-2">
                                  <span className="text-cyan-400 text-xs font-bold">MARKET AT DECISION:</span>
                                  <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
                                    <div>
                                      <span className="text-gray-500">{decision.symbol}:</span>
                                      <span className="text-white ml-1">${(decision.market_context?.spot_price || 0).toLocaleString()}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-500">VIX:</span>
                                      <span className="text-yellow-400 ml-1">{(decision.market_context?.vix || 0).toFixed(1)}</span>
                                    </div>
                                  </div>
                                </div>

                                {/* GEX Context */}
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
                                  </div>
                                </div>
                              </div>

                              {/* Oracle/ML Advice */}
                              {decision.oracle_advice && (
                                <div className="bg-green-900/20 border border-green-700/30 rounded p-2">
                                  <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                      <Brain className="w-4 h-4 text-green-400" />
                                      <span className="text-green-400 text-xs font-bold">ML/ORACLE PREDICTION:</span>
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

                              {/* Position Sizing */}
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
                                </div>
                              )}

                              {/* Trade Legs */}
                              {decision.legs && decision.legs.length > 0 && (
                                <div className="bg-gray-800/50 rounded p-2">
                                  <span className="text-cyan-400 text-xs font-bold">TRADE LEGS:</span>
                                  <div className="mt-2 space-y-1">
                                    {decision.legs.map((leg, i) => (
                                      <div key={i} className="flex items-center gap-2 text-xs">
                                        <span className={`${leg.action === 'BUY' ? 'text-green-400' : 'text-red-400'} font-medium w-10`}>
                                          {leg.action}
                                        </span>
                                        <span className="text-white">{leg.contracts}x</span>
                                        <span className="text-gray-400">{leg.option_type?.toUpperCase()}</span>
                                        <span className="text-white">${leg.strike}</span>
                                        <span className="text-gray-500">{leg.expiration}</span>
                                        {leg.entry_price && (
                                          <span className="text-green-400">@ ${leg.entry_price.toFixed(2)}</span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
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
