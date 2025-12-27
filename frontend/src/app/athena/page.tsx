'use client'

import React, { useState, useMemo } from 'react'
import { Target, TrendingUp, TrendingDown, Activity, DollarSign, CheckCircle, Clock, RefreshCw, BarChart3, ChevronDown, ChevronUp, ChevronRight, Play, Settings, FileText, Zap, Brain, Crosshair, ScrollText, Wallet } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useToast } from '@/components/ui/Toast'
import {
  useATHENAStatus,
  useATHENAPositions,
  useATHENASignals,
  useATHENAPerformance,
  useATHENAOracleAdvice,
  useATHENAMLSignal,
  useATHENALogs,
  useATHENADecisions,
  useScanActivityAthena,
  useATHENALivePnL
} from '@/lib/hooks/useMarketData'
import ScanActivityFeed from '@/components/ScanActivityFeed'
import { EquityDataPoint, LivePnLData } from '@/components/trader/LivePortfolio'
import {
  BotStatusBanner,
  WhyNotTrading,
  TodayReportCard,
  ActivityTimeline,
  RiskMetrics,
  PositionDetailModal,
  AllOpenPositions,
  LiveEquityCurve,
  TradeStoryCard,
  LastScanSummary,
  SignalConflictTracker,
  PositionEntryContext
} from '@/components/trader'
import type { TradeDecision } from '@/components/trader'
import EquityCurveChart from '@/components/charts/EquityCurveChart'

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

interface PositionGreeks {
  net_delta: number
  net_gamma: number
  net_theta: number
  long_delta: number
  short_delta: number
}

interface SpreadPosition {
  position_id: string
  spread_type: string
  ticker: string
  long_strike: number
  short_strike: number
  spread_width?: number
  expiration: string
  is_0dte?: boolean
  entry_price: number
  contracts: number
  max_profit: number
  max_loss: number
  breakeven?: number
  spot_at_entry: number
  gex_regime: string
  oracle_confidence: number
  oracle_reasoning?: string
  greeks?: PositionGreeks
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

  // SIGNAL SOURCE & OVERRIDE TRACKING
  signal_source?: string  // "ML", "Oracle", "Oracle (override ML)", etc.
  override_occurred?: boolean
  override_details?: {
    overridden_signal?: string
    overridden_advice?: string
    override_reason?: string
    override_by?: string
    oracle_advice?: string
    oracle_confidence?: number
    oracle_win_probability?: number
    ml_was_saying?: string
  }

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

// ==================== TODAY'S STATUS CARD ====================
interface ATHENATodaySummaryProps {
  tradedToday: boolean
  openPosition: SpreadPosition | null
  lastDecision: DecisionLog | null
  oracleAdvice: OracleAdvice | undefined
  mlSignal: MLSignal | undefined
  gexContext: { regime: string; put_wall: number; call_wall: number; net_gex: number } | undefined
  spotPrice: number
}

function ATHENATodaySummaryCard({ tradedToday, openPosition, lastDecision, oracleAdvice, mlSignal, gexContext, spotPrice }: ATHENATodaySummaryProps) {
  const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

  if (tradedToday && openPosition) {
    // We traded today - show the position
    const oracleConf = oracleAdvice?.confidence || oracleAdvice?.win_probability || 0
    const mlConf = mlSignal?.confidence || 0

    return (
      <div className="bg-gradient-to-r from-green-900/30 to-[#0a0a0a] rounded-xl p-5 border border-green-700/50">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
            <div>
              <h3 className="text-lg font-bold text-white">TODAY&apos;S STATUS</h3>
              <span className="text-gray-400 text-sm">{today}</span>
            </div>
          </div>
          <span className="px-3 py-1 bg-green-900/50 text-green-400 rounded-full text-sm font-medium">
            ✓ TRADED
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Position Details */}
          <div className="bg-black/30 rounded-lg p-4">
            <div className="text-gray-400 text-xs mb-2">POSITION</div>
            <div className="text-white font-mono text-lg mb-2">
              {openPosition.ticker} {openPosition.spread_type?.replace(/_/g, ' ')}
            </div>
            <div className="text-orange-300 font-mono">
              {openPosition.long_strike}/{openPosition.short_strike}
            </div>
            <div className="flex gap-4 mt-3 text-sm">
              <div>
                <span className="text-gray-500">Entry: </span>
                <span className="text-white font-bold">${openPosition.entry_price?.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-gray-500">Max Risk: </span>
                <span className="text-red-400">${openPosition.max_loss?.toFixed(0)}</span>
              </div>
            </div>
          </div>

          {/* Why We Traded */}
          <div className="bg-black/30 rounded-lg p-4">
            <div className="text-gray-400 text-xs mb-2">WHY WE TRADED</div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-green-400" />
                <span className="text-white">ML Signal: <span className="text-green-400 font-bold">{(mlConf * 100).toFixed(0)}%</span></span>
              </div>
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-purple-400" />
                <span className="text-white">Oracle: <span className="text-purple-400 font-bold">{(oracleConf * 100).toFixed(0)}%</span></span>
              </div>
              {gexContext && (
                <div className="text-xs text-gray-400">
                  GEX {gexContext.regime} • Put ${gexContext.put_wall?.toFixed(0)} / Call ${gexContext.call_wall?.toFixed(0)}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // No trade today - show why
  const skipReason = lastDecision?.alternatives?.primary_reason || lastDecision?.why || 'Waiting for favorable conditions'
  const mlConf = mlSignal?.confidence || 0
  const oracleConf = oracleAdvice?.win_probability || 0

  return (
    <div className="bg-gradient-to-r from-yellow-900/20 to-[#0a0a0a] rounded-xl p-5 border border-yellow-700/30">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-yellow-500" />
          <div>
            <h3 className="text-lg font-bold text-white">TODAY&apos;S STATUS</h3>
            <span className="text-gray-400 text-sm">{today}</span>
          </div>
        </div>
        <span className="px-3 py-1 bg-yellow-900/50 text-yellow-400 rounded-full text-sm font-medium">
          ⚠ NO TRADE
        </span>
      </div>

      <div className="bg-black/30 rounded-lg p-4">
        <div className="text-gray-400 text-xs mb-2">REASON</div>
        <div className="text-white mb-3">{skipReason}</div>

        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-yellow-400" />
            <span className="text-gray-300">
              ML Confidence: <span className={mlConf >= 0.6 ? 'text-green-400' : 'text-red-400'}>{(mlConf * 100).toFixed(0)}%</span>
              <span className="text-gray-500 ml-2">(need 60%+)</span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-purple-400" />
            <span className="text-gray-300">
              Oracle Win Prob: <span className={oracleConf >= 0.55 ? 'text-green-400' : 'text-red-400'}>{(oracleConf * 100).toFixed(0)}%</span>
              <span className="text-gray-500 ml-2">(need 55%+)</span>
            </span>
          </div>
        </div>

        {/* What would change this */}
        <div className="mt-4 pt-3 border-t border-gray-700">
          <div className="text-gray-400 text-xs mb-2">WHAT WOULD HELP</div>
          <div className="flex flex-wrap gap-2">
            {gexContext?.regime !== 'POSITIVE' && (
              <span className="px-2 py-1 bg-blue-900/30 text-blue-400 rounded text-xs">GEX flip to POSITIVE (+10%)</span>
            )}
            {mlConf < 0.6 && (
              <span className="px-2 py-1 bg-purple-900/30 text-purple-400 rounded text-xs">ML confidence above 60%</span>
            )}
            {oracleConf < 0.55 && (
              <span className="px-2 py-1 bg-green-900/30 text-green-400 rounded text-xs">Oracle win prob above 55%</span>
            )}
            {gexContext && spotPrice > 0 && (
              <span className="px-2 py-1 bg-orange-900/30 text-orange-400 rounded text-xs">
                Better R:R ratio (spot ${spotPrice.toFixed(0)} vs walls)
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ==================== DECISION PATH CARD ====================
interface ATHENADecisionPathProps {
  mlSignal: MLSignal | undefined
  oracleAdvice: OracleAdvice | undefined
  isTraded: boolean
  gexRegime: string
}

function ATHENADecisionPathCard({ mlSignal, oracleAdvice, isTraded, gexRegime }: ATHENADecisionPathProps) {
  const mlConf = mlSignal?.confidence || 0
  const mlWinProb = mlSignal?.win_probability || 0
  const oracleConf = oracleAdvice?.confidence || 0
  const oracleWinProb = oracleAdvice?.win_probability || 0

  // Combined probability (simplified)
  const combinedProb = Math.max(mlWinProb, oracleWinProb)

  return (
    <div className="bg-[#0a0a0a] rounded-xl p-5 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <Brain className="w-5 h-5 text-orange-400" />
        <h3 className="text-lg font-semibold text-white">Decision Path</h3>
      </div>

      <div className="space-y-4">
        {/* Step 1: ML Signal */}
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-purple-900/50 flex items-center justify-center text-purple-400 text-xs font-bold">1</div>
          <div className="flex-1">
            <div className="text-gray-400 text-xs mb-1">GEX ML SIGNAL</div>
            <div className="flex items-center gap-2">
              <span className="text-white">Direction:</span>
              <span className={`font-bold ${mlSignal?.model_predictions?.direction === 'BULLISH' ? 'text-green-400' : mlSignal?.model_predictions?.direction === 'BEARISH' ? 'text-red-400' : 'text-gray-400'}`}>
                {mlSignal?.model_predictions?.direction || 'N/A'}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-white">Win Probability:</span>
              <span className="text-purple-400 font-bold">{(mlWinProb * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>

        {/* Step 2: Oracle Validation */}
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-green-900/50 flex items-center justify-center text-green-400 text-xs font-bold">2</div>
          <div className="flex-1">
            <div className="text-gray-400 text-xs mb-1">ORACLE VALIDATION</div>
            <div className="flex items-center gap-2">
              <span className="text-white">Advice:</span>
              <span className={`font-bold ${oracleAdvice?.advice === 'TRADE' ? 'text-green-400' : 'text-yellow-400'}`}>
                {oracleAdvice?.advice || 'N/A'}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-white">Win Probability:</span>
              <span className="text-green-400 font-bold">{(oracleWinProb * 100).toFixed(0)}%</span>
            </div>
            {oracleAdvice?.reasoning && (
              <div className="mt-1 text-xs text-gray-500 truncate max-w-md">
                {oracleAdvice.reasoning.slice(0, 80)}...
              </div>
            )}
          </div>
        </div>

        {/* Step 3: GEX Context */}
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-blue-900/50 flex items-center justify-center text-blue-400 text-xs font-bold">3</div>
          <div className="flex-1">
            <div className="text-gray-400 text-xs mb-1">GEX REGIME</div>
            <div className="flex items-center gap-2">
              <span className="text-white">Current Regime:</span>
              <span className={`font-bold ${gexRegime === 'POSITIVE' ? 'text-green-400' : 'text-red-400'}`}>
                {gexRegime || 'N/A'}
              </span>
            </div>
          </div>
        </div>

        {/* Step 4: Final Decision */}
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-orange-900/50 flex items-center justify-center text-orange-400 text-xs font-bold">4</div>
          <div className="flex-1">
            <div className="text-gray-400 text-xs mb-1">FINAL DECISION</div>
            <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full ${isTraded ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
              {isTraded ? '✓ TRADE' : '✗ SKIP'}
              <span className="text-xs opacity-70">
                ({combinedProb >= 0.60 ? '≥60%' : '<60%'})
              </span>
            </div>
          </div>
        </div>

        {/* Thresholds Legend */}
        <div className="mt-4 pt-3 border-t border-gray-700">
          <div className="text-gray-500 text-xs mb-2">DECISION THRESHOLDS</div>
          <div className="flex gap-4 text-xs flex-wrap">
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-green-500" />
              <span className="text-gray-400">≥60% = TRADE</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-yellow-500" />
              <span className="text-gray-400">50-60% = REDUCED</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-gray-400">&lt;50% = SKIP</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ==================== QUICK ACTIONS PANEL ====================
interface ATHENAQuickActionsProps {
  onSkipToday: () => void
  onAdjustRisk: (newRisk: number) => void
  onForceScan: () => void
  currentRisk: number
  isActive: boolean
  hasOpenPosition: boolean
}

function ATHENAQuickActionsPanel({ onSkipToday, onAdjustRisk, onForceScan, currentRisk, isActive, hasOpenPosition }: ATHENAQuickActionsProps) {
  const [riskValue, setRiskValue] = useState(currentRisk)
  const [showConfirm, setShowConfirm] = useState<'skip' | 'risk' | null>(null)

  return (
    <div className="bg-[#0a0a0a] rounded-xl p-5 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-5 h-5 text-orange-400" />
        <h3 className="text-lg font-semibold text-white">Quick Actions</h3>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Skip Today */}
        <button
          onClick={() => showConfirm === 'skip' ? (onSkipToday(), setShowConfirm(null)) : setShowConfirm('skip')}
          className={`p-3 rounded-lg border transition flex flex-col items-center gap-2 ${
            showConfirm === 'skip'
              ? 'bg-yellow-900/30 border-yellow-600 text-yellow-400'
              : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:bg-gray-700'
          }`}
        >
          <Clock className="w-5 h-5" />
          <span className="text-xs">{showConfirm === 'skip' ? 'Confirm?' : 'Skip Today'}</span>
        </button>

        {/* Adjust Risk */}
        <div className="p-3 rounded-lg border bg-gray-800/50 border-gray-700 flex flex-col items-center gap-2">
          <Settings className="w-5 h-5 text-blue-400" />
          <span className="text-xs text-gray-400">Risk: {(currentRisk * 100).toFixed(0)}%</span>
        </div>

        {/* Force Scan */}
        <button
          onClick={onForceScan}
          disabled={hasOpenPosition}
          className={`p-3 rounded-lg border transition flex flex-col items-center gap-2 ${
            hasOpenPosition
              ? 'bg-gray-900/50 border-gray-800 text-gray-600 cursor-not-allowed'
              : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:bg-gray-700'
          }`}
        >
          <Play className="w-5 h-5" />
          <span className="text-xs">Force Scan</span>
        </button>

        {/* Status */}
        <div className={`p-3 rounded-lg border flex flex-col items-center gap-2 ${
          isActive ? 'bg-green-900/30 border-green-700' : 'bg-gray-800/50 border-gray-700'
        }`}>
          <div className={`w-3 h-3 rounded-full ${isActive ? 'bg-green-500 animate-pulse' : 'bg-gray-600'}`} />
          <span className={`text-xs ${isActive ? 'text-green-400' : 'text-gray-400'}`}>
            {isActive ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>

      {/* Config Summary */}
      <div className="mt-4 pt-3 border-t border-gray-700 flex flex-wrap gap-4 text-xs text-gray-500">
        <span>Risk: <span className="text-white">{(currentRisk * 100).toFixed(0)}%</span></span>
        <span>Target: <span className="text-green-400">50% profit</span></span>
        <span>Window: <span className="text-cyan-400">9:35-15:55 CT</span></span>
      </div>
    </div>
  )
}

// ==================== CLOSED POSITIONS PANEL ====================
// Unified closed positions display matching Ares style
interface ClosedPositionsPanelProps {
  positions: SpreadPosition[]
  showClosedPositions: boolean
  setShowClosedPositions: (show: boolean) => void
  expandedPosition: string | null
  setExpandedPosition: (id: string | null) => void
  formatCurrency: (val: number) => string
}

function ClosedPositionsPanel({
  positions,
  showClosedPositions,
  setShowClosedPositions,
  expandedPosition,
  setExpandedPosition,
  formatCurrency
}: ClosedPositionsPanelProps) {
  const closedPositions = positions.filter(p => p.status === 'closed' || p.status === 'expired')
  const todayClosed = closedPositions.filter(p => p.exit_time?.startsWith(new Date().toISOString().split('T')[0]))

  if (closedPositions.length === 0) return null

  const totalPnl = closedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0)
  const winRate = closedPositions.length > 0
    ? (closedPositions.filter(p => (p.realized_pnl || 0) > 0).length / closedPositions.length * 100)
    : 0

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      {/* Header with toggle */}
      <div className="p-4 border-b border-gray-700 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-white">Closed Positions</h2>
          <span className="text-sm text-gray-400">
            {todayClosed.length > 0 && (
              <span className="text-orange-400 mr-2">{todayClosed.length} today</span>
            )}
            {closedPositions.length} total
          </span>
        </div>
        <div className="flex items-center gap-4">
          {/* Summary stats */}
          <div className="hidden sm:flex items-center gap-4 text-sm">
            <span className="text-gray-400">
              Win Rate: <span className={winRate >= 50 ? 'text-green-400' : 'text-red-400'}>{winRate.toFixed(0)}%</span>
            </span>
            <span className="text-gray-400">
              Total P&L: <span className={totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}>{formatCurrency(totalPnl)}</span>
            </span>
          </div>
          <button
            onClick={() => setShowClosedPositions(!showClosedPositions)}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition px-3 py-1 rounded-lg bg-gray-700 hover:bg-gray-600"
          >
            {showClosedPositions ? 'Hide' : 'Show'} History
            {showClosedPositions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Position Table */}
      {showClosedPositions && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-900">
              <tr>
                <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Date</th>
                <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Type</th>
                <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Strikes</th>
                <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Qty</th>
                <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Entry</th>
                <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Exit</th>
                <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Regime</th>
                <th className="px-3 py-3 text-right text-xs text-gray-400 uppercase">P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {closedPositions
                .sort((a, b) => new Date(b.exit_time || 0).getTime() - new Date(a.exit_time || 0).getTime())
                .slice(0, 20)
                .map((pos) => {
                  const isExpanded = expandedPosition === pos.position_id
                  const isToday = pos.exit_time?.startsWith(new Date().toISOString().split('T')[0])
                  const greeks = pos.greeks || { net_delta: 0, net_gamma: 0, net_theta: 0 }

                  return (
                    <React.Fragment key={pos.position_id}>
                      <tr
                        className={`hover:bg-gray-700/50 cursor-pointer ${isToday ? 'bg-orange-900/10' : ''}`}
                        onClick={() => setExpandedPosition(isExpanded ? null : pos.position_id)}
                      >
                        <td className="px-3 py-3 text-sm text-gray-300">
                          <div className="flex items-center gap-1">
                            <ChevronRight className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                            <span className={isToday ? 'text-orange-400' : ''}>
                              {pos.exit_time ? new Date(pos.exit_time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '--'}
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <span className={`px-2 py-1 rounded text-xs font-medium ${
                            pos.spread_type === 'BULL_CALL_SPREAD'
                              ? 'bg-green-900/50 text-green-400'
                              : 'bg-red-900/50 text-red-400'
                          }`}>
                            {pos.spread_type === 'BULL_CALL_SPREAD' ? 'BULL' : 'BEAR'}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-sm text-gray-300 font-mono">
                          ${pos.long_strike}/{pos.short_strike}
                        </td>
                        <td className="px-3 py-3 text-sm text-gray-300">{pos.contracts}</td>
                        <td className="px-3 py-3 text-sm text-gray-300">${pos.entry_price?.toFixed(2) || '--'}</td>
                        <td className="px-3 py-3 text-sm text-gray-300">${pos.exit_price?.toFixed(2) || '--'}</td>
                        <td className="px-3 py-3">
                          <span className={`px-2 py-1 rounded text-xs ${
                            pos.gex_regime === 'POSITIVE' ? 'bg-blue-900/50 text-blue-400' : 'bg-orange-900/50 text-orange-400'
                          }`}>
                            {pos.gex_regime}
                          </span>
                        </td>
                        <td className={`px-3 py-3 text-sm font-bold text-right ${
                          (pos.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}>
                          {(pos.realized_pnl || 0) >= 0 ? '+' : ''}{formatCurrency(pos.realized_pnl || 0)}
                        </td>
                      </tr>

                      {/* Expanded Row */}
                      {isExpanded && (
                        <tr className="bg-gray-900/50">
                          <td colSpan={8} className="px-4 py-4">
                            <div className="grid grid-cols-4 gap-4 text-sm">
                              {/* Position Details */}
                              <div className="space-y-2">
                                <h4 className="text-gray-400 font-medium text-xs uppercase">Position Details</h4>
                                <div className="space-y-1">
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Spread Width:</span>
                                    <span className="text-gray-300">${pos.spread_width?.toFixed(0) || '--'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Breakeven:</span>
                                    <span className="text-gray-300">${pos.breakeven?.toFixed(2) || '--'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">SPY at Entry:</span>
                                    <span className="text-gray-300">${pos.spot_at_entry?.toFixed(2) || '--'}</span>
                                  </div>
                                </div>
                              </div>

                              {/* Greeks at Entry */}
                              <div className="space-y-2">
                                <h4 className="text-gray-400 font-medium text-xs uppercase">Greeks at Entry</h4>
                                <div className="space-y-1">
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Net Delta:</span>
                                    <span className={`font-mono ${greeks.net_delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                      {greeks.net_delta?.toFixed(3) || '0.000'}
                                    </span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Net Gamma:</span>
                                    <span className="text-gray-300 font-mono">{greeks.net_gamma?.toFixed(3) || '0.000'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Net Theta:</span>
                                    <span className="text-red-400 font-mono">{greeks.net_theta?.toFixed(3) || '0.000'}</span>
                                  </div>
                                </div>
                              </div>

                              {/* Risk/Reward */}
                              <div className="space-y-2">
                                <h4 className="text-gray-400 font-medium text-xs uppercase">Risk / Reward</h4>
                                <div className="space-y-1">
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Max Profit:</span>
                                    <span className="text-green-400">${pos.max_profit?.toFixed(2) || '--'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Max Loss:</span>
                                    <span className="text-red-400">${pos.max_loss?.toFixed(2) || '--'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Oracle Conf:</span>
                                    <span className="text-blue-400">{((pos.oracle_confidence || 0) * 100).toFixed(0)}%</span>
                                  </div>
                                </div>
                              </div>

                              {/* Exit Info */}
                              <div className="space-y-2">
                                <h4 className="text-gray-400 font-medium text-xs uppercase">Exit Details</h4>
                                <div className="space-y-1">
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Exit Reason:</span>
                                    <span className="text-yellow-400">{pos.exit_reason || 'Unknown'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Exit Time:</span>
                                    <span className="text-gray-300 text-xs">
                                      {pos.exit_time ? new Date(pos.exit_time).toLocaleString() : '--'}
                                    </span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Status:</span>
                                    <span className={pos.status === 'expired' ? 'text-purple-400' : 'text-gray-400'}>{pos.status}</span>
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Oracle Reasoning */}
                            {pos.oracle_reasoning && (
                              <div className="mt-4 pt-3 border-t border-gray-700">
                                <h4 className="text-gray-400 font-medium text-xs uppercase mb-2">Oracle Reasoning</h4>
                                <p className="text-gray-500 text-sm">{pos.oracle_reasoning}</p>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
            </tbody>
          </table>

          {closedPositions.length > 20 && (
            <div className="p-4 text-center text-gray-500 text-sm border-t border-gray-700">
              Showing 20 of {closedPositions.length} closed positions.
              <button className="ml-2 text-orange-400 hover:underline">View all in Positions tab →</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
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
  const { data: scanActivityRes, isLoading: scanActivityLoading, mutate: mutateScanActivity } = useScanActivityAthena(50)
  const { data: livePnLRes, isLoading: livePnLLoading, mutate: mutateLivePnL } = useATHENALivePnL()

  // Extract data from responses
  const status = statusRes?.data as ATHENAStatus | undefined
  const positions = (positionsRes?.data || []) as SpreadPosition[]
  const signals = (signalsRes?.data || []) as Signal[]
  const scanActivity = scanActivityRes?.data?.scans || []
  const performance = performanceRes?.data as PerformanceData | undefined
  const oracleAdvice = adviceRes?.data as OracleAdvice | undefined
  const mlSignal = mlSignalRes?.data as MLSignal | undefined
  const logs = (logsRes?.data || []) as LogEntry[]
  const decisions = (decisionsRes?.data || []) as DecisionLog[]
  const livePnL = livePnLRes?.data as LivePnLData | null

  const loading = statusLoading && !status
  const error = statusError?.message || null
  const isRefreshing = statusValidating || posValidating || signalsValidating || perfValidating || adviceValidating || mlValidating || logsValidating || decisionsValidating

  // Toast notifications for user feedback
  const toast = useToast()

  // UI State - default to portfolio for better visibility
  const [activeTab, setActiveTab] = useState<'portfolio' | 'overview' | 'positions' | 'signals' | 'logs'>('portfolio')
  const [showClosedPositions, setShowClosedPositions] = useState(true)
  const [runningCycle, setRunningCycle] = useState(false)
  const [expandedDecision, setExpandedDecision] = useState<string | null>(null)
  const [expandedPosition, setExpandedPosition] = useState<string | null>(null)
  const [selectedPosition, setSelectedPosition] = useState<any | null>(null)

  // Build skip reasons from decisions
  const skipReasons = useMemo(() => {
    const today = new Date().toISOString().split('T')[0]
    return decisions
      .filter(d => d.timestamp?.startsWith(today) && (d.action === 'SKIP' || d.decision_type === 'SKIP'))
      .map(d => ({
        id: d.decision_id,
        timestamp: d.timestamp,
        reason: d.why || d.what || 'No reason provided',
        category: d.signal_source?.includes('ML') ? 'ml' as const :
                  d.signal_source?.includes('Oracle') ? 'oracle' as const :
                  d.why?.toLowerCase().includes('market') ? 'market' as const :
                  d.why?.toLowerCase().includes('risk') ? 'risk' as const : 'other' as const,
        details: {
          ml_advice: d.ml_predictions?.advice,
          ml_confidence: d.ml_predictions?.ml_confidence,
          oracle_advice: d.oracle_advice?.advice,
          oracle_confidence: d.oracle_advice?.confidence,
          oracle_win_prob: d.oracle_advice?.win_probability,
          vix: d.market_context?.vix,
          spot_price: d.market_context?.spot_price,
          gex_regime: d.gex_context?.regime
        }
      }))
  }, [decisions])

  // Build activity timeline
  const activityItems = useMemo(() => {
    const today = new Date().toISOString().split('T')[0]
    return decisions
      .filter(d => d.timestamp?.startsWith(today))
      .slice(0, 20)
      .map(d => ({
        id: d.decision_id,
        timestamp: d.timestamp,
        type: d.decision_type?.toLowerCase().includes('entry') ? 'entry' as const :
              d.decision_type?.toLowerCase().includes('exit') ? 'exit' as const :
              d.action === 'SKIP' ? 'skip' as const : 'scan' as const,
        title: d.what || d.action,
        description: d.why,
        pnl: d.actual_pnl,
        signalSource: d.signal_source
      }))
  }, [decisions])

  // Robust "Traded Today" detection
  // Uses multiple sources: backend daily_trades count, position creation dates, open positions
  const didTradeToday = useMemo(() => {
    const today = new Date().toISOString().split('T')[0]

    // Primary check: backend tracks daily trades
    if ((status?.daily_trades || 0) > 0) return true

    // Secondary: any open position exists (could be from earlier today)
    if (positions.some(p => p.status === 'open')) return true

    // Tertiary: any position created today
    if (positions.some(p => p.created_at?.startsWith(today))) return true

    // Quaternary: any position closed today
    if (positions.some(p => (p.status === 'closed' || p.status === 'expired') && p.exit_time?.startsWith(today))) return true

    return false
  }, [status?.daily_trades, positions])

  // Transform scan activity for LastScanSummary component
  const lastScanData = useMemo(() => {
    if (!scanActivity || scanActivity.length === 0) return null
    const latest = scanActivity[0] as any
    return {
      scan_id: latest.scan_id,
      timestamp: latest.timestamp || latest.time_ct,
      outcome: latest.outcome || (latest.trade_executed ? 'TRADED' : 'NO_TRADE'),
      decision_summary: latest.decision_summary,
      ml_signal: latest.signal_source?.includes('ML') || latest.signal_direction ? {
        direction: latest.signal_direction || 'NEUTRAL',
        confidence: latest.signal_confidence || 0,
        advice: latest.signal_source?.includes('ML') ? 'ML Signal' : latest.oracle_advice || ''
      } : undefined,
      oracle_signal: latest.oracle_advice || latest.signal_win_probability ? {
        advice: latest.oracle_advice || 'No Oracle advice',
        confidence: latest.signal_confidence || 0,
        win_probability: latest.signal_win_probability || 0
      } : undefined,
      override_occurred: latest.signal_source?.includes('Override') || false,
      override_details: latest.signal_source?.includes('Override') ? {
        winner: latest.signal_source?.includes('ML') ? 'ML' : 'Oracle',
        overridden_signal: latest.signal_direction || 'Unknown',
        override_reason: latest.decision_summary || 'Override applied'
      } : undefined,
      checks: latest.checks_performed?.map((c: any) => ({
        check: c.check_name,
        passed: c.passed,
        value: c.value,
        reason: c.reason
      })),
      market_context: {
        spot_price: latest.underlying_price || 0,
        vix: latest.vix || 0,
        gex_regime: latest.gex_regime || 'Unknown',
        put_wall: latest.put_wall,
        call_wall: latest.call_wall
      },
      what_would_trigger: latest.what_would_trigger
    }
  }, [scanActivity])

  // Build signal conflict data from scan activity
  const signalConflicts = useMemo(() => {
    if (!scanActivity) return []
    const today = new Date().toISOString().split('T')[0]
    return scanActivity
      .filter((s: any) => s.timestamp?.startsWith(today) && s.signal_source?.includes('Override'))
      .map((s: any, idx: number) => ({
        id: `conflict-${idx}`,
        timestamp: s.timestamp,
        mlSignal: s.signal_direction || 'NEUTRAL',
        mlConfidence: s.signal_confidence || 0,
        oracleSignal: s.oracle_advice || 'HOLD',
        oracleConfidence: s.signal_win_probability || 0,
        winner: s.signal_source?.includes('ML') ? 'ML' as const : 'Oracle' as const,
        outcome: s.trade_executed ? 'TRADED' : 'NO_TRADE',
        wasCorrect: undefined
      }))
  }, [scanActivity])

  // Calculate ML vs Oracle stats from today's scans
  const { mlWins, oracleWins, scansToday, tradesToday: tradesTodayCount } = useMemo(() => {
    if (!scanActivity) return { mlWins: 0, oracleWins: 0, scansToday: 0, tradesToday: 0 }
    const today = new Date().toISOString().split('T')[0]
    const todayScans = scanActivity.filter((s: any) => s.timestamp?.startsWith(today))
    const trades = todayScans.filter((s: any) => s.trade_executed || s.outcome === 'TRADED')
    const mlWon = signalConflicts.filter((c: { winner: string }) => c.winner === 'ML').length
    const oracleWon = signalConflicts.filter((c: { winner: string }) => c.winner === 'Oracle').length
    return {
      mlWins: mlWon,
      oracleWins: oracleWon,
      scansToday: todayScans.length,
      tradesToday: trades.length
    }
  }, [scanActivity, signalConflicts])

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
    mutateLivePnL()
  }

  // Build equity curve data for the chart (Robinhood-style)
  // Includes both historical closed positions AND current live equity with unrealized P&L
  const equityChartData: EquityDataPoint[] = useMemo(() => {
    const startingCapital = status?.capital || 100000

    // Include both 'closed' and 'expired' positions (0DTE trades expire with status='expired')
    const closedPositions = positions.filter(p => (p.status === 'closed' || p.status === 'expired') && p.exit_time)
    const openPositions = positions.filter(p => p.status === 'open')

    // Calculate realized P&L from closed positions
    let realizedPnl = 0
    const historicalPoints: EquityDataPoint[] = []

    if (closedPositions.length > 0) {
      // Sort by close date
      const sorted = [...closedPositions].sort((a, b) =>
        new Date(a.exit_time!).getTime() - new Date(b.exit_time!).getTime()
      )

      // Build cumulative equity from closed positions
      sorted.forEach(pos => {
        realizedPnl += pos.realized_pnl || 0
        historicalPoints.push({
          date: new Date(pos.exit_time!).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
          timestamp: new Date(pos.exit_time!).getTime(),
          equity: startingCapital + realizedPnl,
          pnl: realizedPnl
        })
      })
    }

    // Get unrealized P&L from livePnL data (properly calculated with 100x multiplier)
    // This includes: (current_spread_value - entry_debit) * contracts * 100
    const unrealizedPnl = livePnL?.total_unrealized_pnl || 0

    // Add live "now" point with current equity (realized + unrealized)
    const totalPnl = realizedPnl + unrealizedPnl
    const now = new Date()
    const livePoint: EquityDataPoint = {
      date: 'Now',
      timestamp: now.getTime(),
      equity: startingCapital + totalPnl,
      pnl: totalPnl
    }

    // If no historical data, start with starting capital point
    if (historicalPoints.length === 0 && openPositions.length > 0) {
      // Add a starting point at beginning of day
      const todayStart = new Date()
      todayStart.setHours(9, 30, 0, 0) // Market open
      historicalPoints.push({
        date: todayStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        timestamp: todayStart.getTime(),
        equity: startingCapital,
        pnl: 0
      })
    }

    // Always add the live point if there are open positions or historical data
    if (openPositions.length > 0 || historicalPoints.length > 0) {
      return [...historicalPoints, livePoint]
    }

    return historicalPoints
  }, [positions, status?.capital, livePnL?.total_unrealized_pnl])

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
        toast.success('Scan Complete', 'ATHENA cycle completed successfully')
        fetchData()
      }
    } catch (err) {
      console.error('Failed to run cycle:', err)
      toast.error('Scan Failed', 'Failed to run ATHENA cycle')
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
    // Include both 'closed' and 'expired' positions (0DTE trades expire with status='expired')
    const closedPositions = positions.filter(p => (p.status === 'closed' || p.status === 'expired') && p.exit_time)
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
  // Include both 'closed' and 'expired' positions for stats
  const closedPositions = positions.filter(p => p.status === 'closed' || p.status === 'expired')
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
            {(['portfolio', 'overview', 'positions', 'signals', 'logs'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-lg capitalize transition flex items-center gap-2 ${
                  activeTab === tab
                    ? 'bg-orange-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {tab === 'portfolio' && <Wallet className="w-4 h-4" />}
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

          {/* Condensed Market Data Bar */}
          <div className="mb-4 bg-gray-800/50 rounded-lg p-2 border border-gray-700">
            <div className="grid grid-cols-6 gap-2 text-center text-sm">
              <div className="bg-gray-900/50 rounded px-3 py-2">
                <span className="text-gray-500 text-xs block">SPY</span>
                <span className="text-white font-bold">
                  ${(mlSignal?.gex_context?.spot_price || status?.heartbeat?.details?.gex_context?.spot_price || 0).toFixed(2)}
                </span>
              </div>
              <div className="bg-gray-900/50 rounded px-3 py-2">
                <span className="text-gray-500 text-xs block">VIX</span>
                <span className="text-yellow-400 font-bold">
                  {(status?.heartbeat?.details?.vix || 0).toFixed(1)}
                </span>
              </div>
              <div className="bg-green-900/20 rounded px-3 py-2">
                <span className="text-gray-500 text-xs block">Put Wall</span>
                <span className="text-green-400 font-bold">
                  ${(mlSignal?.gex_context?.put_wall || status?.heartbeat?.details?.gex_context?.put_wall || 0).toFixed(0)}
                </span>
              </div>
              <div className="bg-red-900/20 rounded px-3 py-2">
                <span className="text-gray-500 text-xs block">Call Wall</span>
                <span className="text-red-400 font-bold">
                  ${(mlSignal?.gex_context?.call_wall || status?.heartbeat?.details?.gex_context?.call_wall || 0).toFixed(0)}
                </span>
              </div>
              <div className="bg-gray-900/50 rounded px-3 py-2">
                <span className="text-gray-500 text-xs block">Regime</span>
                <span className={`font-bold ${
                  (mlSignal?.gex_context?.regime || status?.heartbeat?.details?.gex_context?.regime) === 'POSITIVE'
                    ? 'text-green-400' : 'text-red-400'
                }`}>
                  {mlSignal?.gex_context?.regime || status?.heartbeat?.details?.gex_context?.regime || 'N/A'}
                </span>
              </div>
              <div className="bg-purple-900/20 rounded px-3 py-2">
                <span className="text-gray-500 text-xs block">Net GEX</span>
                <span className="text-purple-400 font-bold">
                  {((mlSignal?.gex_context?.net_gex || status?.heartbeat?.details?.gex_context?.net_gex || 0) / 1e9).toFixed(2)}B
                </span>
              </div>
            </div>
          </div>

          {error && (
            <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 mb-6">
              <p className="text-red-400">{error}</p>
            </div>
          )}

          {/* Portfolio Tab - Robinhood-style live P&L */}
          {activeTab === 'portfolio' && (
            <div className="space-y-6">
              {/* Bot Status Banner - Shows active/paused/error status with countdown */}
              <BotStatusBanner
                botName="ATHENA"
                isActive={status?.is_active || false}
                lastScan={status?.heartbeat?.last_scan_iso}
                scanInterval={status?.scan_interval_minutes || 5}
                openPositions={positions.filter(p => p.status === 'open').length}
                todayPnl={(livePnL?.total_realized_pnl || 0) + (livePnL?.total_unrealized_pnl || 0)}
                todayTrades={status?.daily_trades || 0}
              />

              {/* ===== TRANSPARENCY SECTION - What Just Happened ===== */}
              {/* Last Scan Summary - THE MOST IMPORTANT: Shows what happened on last scan with full reasoning */}
              <LastScanSummary
                botName="ATHENA"
                lastScan={lastScanData}
                isLoading={scanActivityLoading}
                nextScanIn={undefined}
                scansToday={scansToday}
                tradesToday={tradesTodayCount}
                onRefresh={() => mutateScanActivity()}
              />

              {/* Signal Conflict Tracker - Shows ML vs Oracle disagreements and who won */}
              {signalConflicts.length > 0 && (
                <SignalConflictTracker
                  botName="ATHENA"
                  conflicts={signalConflicts}
                  totalScansToday={scansToday}
                  mlWins={mlWins}
                  oracleWins={oracleWins}
                  isLoading={scanActivityLoading}
                />
              )}

              {/* Live Equity Curve with Intraday Tracking */}
              <LiveEquityCurve
                botName="ATHENA"
                startingCapital={status?.capital || 100000}
                historicalData={equityChartData}
                livePnL={livePnL as any}
                isLoading={livePnLLoading}
                onRefresh={() => mutateLivePnL()}
                lastUpdated={livePnL?.last_updated}
              />

              {/* ALL Open Positions with Timestamps */}
              <AllOpenPositions
                botName="ATHENA"
                positions={livePnL?.positions || []}
                underlyingPrice={livePnL?.underlying_price}
                isLoading={livePnLLoading}
                lastUpdated={livePnL?.last_updated}
                onPositionClick={(pos) => setSelectedPosition(pos)}
              />

              {/* Risk Metrics Panel */}
              <RiskMetrics
                capitalTotal={status?.capital || 100000}
                capitalAtRisk={positions.filter(p => p.status === 'open').reduce((sum, p) => sum + (p.max_loss || 0), 0)}
                openPositions={positions.filter(p => p.status === 'open').length}
                maxPositionsAllowed={status?.config?.max_daily_trades || 5}
                currentDrawdown={0}
                maxDrawdownToday={0}
                currentVix={mlSignal?.gex_context?.spot_price ? undefined : undefined}
              />

              {/* Why Not Trading - Shows skip reasons */}
              <WhyNotTrading
                skipReasons={skipReasons}
                isLoading={decisionsValidating}
                maxDisplay={5}
              />

              {/* Today's Status Summary - Shows ALL open positions now */}
              <ATHENATodaySummaryCard
                tradedToday={didTradeToday}
                openPosition={positions.find(p => p.status === 'open') || null}
                lastDecision={decisions[0] || null}
                oracleAdvice={oracleAdvice}
                mlSignal={mlSignal}
                gexContext={mlSignal?.gex_context || status?.heartbeat?.details?.gex_context}
                spotPrice={mlSignal?.gex_context?.spot_price || status?.heartbeat?.details?.gex_context?.spot_price || 0}
              />

              {/* Decision Path Visualization */}
              <ATHENADecisionPathCard
                mlSignal={mlSignal}
                oracleAdvice={oracleAdvice}
                isTraded={didTradeToday}
                gexRegime={mlSignal?.gex_context?.regime || status?.heartbeat?.details?.gex_context?.regime || 'UNKNOWN'}
              />

              {/* Quick Actions Panel */}
              <ATHENAQuickActionsPanel
                onSkipToday={async () => {
                  try {
                    await apiClient.skipATHENAToday()
                    toast.success('Skipped Today', 'ATHENA will not trade for the rest of today')
                    fetchData()
                  } catch (err) {
                    console.error('Failed to skip today:', err)
                    toast.error('Skip Failed', 'Failed to skip trading for today')
                  }
                }}
                onAdjustRisk={async (newRisk: number) => {
                  try {
                    await apiClient.updateATHENAConfig('risk_per_trade_pct', String(newRisk))
                    toast.success('Risk Adjusted', `Risk per trade set to ${(newRisk * 100).toFixed(0)}%`)
                    fetchData()
                  } catch (err) {
                    console.error('Failed to adjust risk:', err)
                    toast.error('Adjustment Failed', 'Failed to adjust risk setting')
                  }
                }}
                onForceScan={() => runCycle()}
                currentRisk={status?.config?.risk_per_trade || 0.02}
                isActive={status?.is_active || false}
                hasOpenPosition={positions.some(p => p.status === 'open')}
              />

              {/* Today's Stats & Activity Row */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Today's Report Card */}
                <TodayReportCard
                  botName="ATHENA"
                  scansToday={status?.heartbeat?.scan_count_today || 0}
                  tradesToday={status?.daily_trades || 0}
                  winsToday={positions.filter(p =>
                    (p.status === 'closed' || p.status === 'expired') &&
                    p.exit_time?.startsWith(new Date().toISOString().split('T')[0]) &&
                    p.realized_pnl > 0
                  ).length}
                  lossesToday={positions.filter(p =>
                    (p.status === 'closed' || p.status === 'expired') &&
                    p.exit_time?.startsWith(new Date().toISOString().split('T')[0]) &&
                    p.realized_pnl < 0
                  ).length}
                  totalPnl={(livePnL?.total_realized_pnl || 0) + (livePnL?.total_unrealized_pnl || 0)}
                  unrealizedPnl={livePnL?.total_unrealized_pnl || 0}
                  realizedPnl={livePnL?.total_realized_pnl || 0}
                  bestTrade={Math.max(...positions.filter(p =>
                    (p.status === 'closed' || p.status === 'expired') &&
                    p.exit_time?.startsWith(new Date().toISOString().split('T')[0])
                  ).map(p => p.realized_pnl || 0), 0) || undefined}
                  worstTrade={Math.min(...positions.filter(p =>
                    (p.status === 'closed' || p.status === 'expired') &&
                    p.exit_time?.startsWith(new Date().toISOString().split('T')[0])
                  ).map(p => p.realized_pnl || 0), 0) || undefined}
                  openPositions={positions.filter(p => p.status === 'open').length}
                  capitalAtRisk={positions.filter(p => p.status === 'open').reduce((sum, p) => sum + (p.max_loss || 0), 0)}
                  capitalTotal={status?.capital || 100000}
                />

                {/* Activity Timeline */}
                <ActivityTimeline
                  activities={activityItems}
                  isLoading={decisionsValidating}
                  maxDisplay={8}
                />
              </div>

              {/* Closed Positions Section - With toggle for history */}
              <ClosedPositionsPanel
                positions={positions}
                showClosedPositions={showClosedPositions}
                setShowClosedPositions={setShowClosedPositions}
                expandedPosition={expandedPosition}
                setExpandedPosition={setExpandedPosition}
                formatCurrency={formatCurrency}
              />
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

              {/* Enhanced Equity Curve with Event Markers */}
              <div className="mb-6">
                <EquityCurveChart
                  botFilter="ATHENA"
                  title="ATHENA Performance"
                  defaultDays={90}
                  height={350}
                  showDrawdown={true}
                />
              </div>

              {/* Scan Activity Feed - Shows EVERY scan with reasoning */}
              <div className="mb-6">
                <ScanActivityFeed
                  scans={scanActivity}
                  botName="ATHENA"
                  isLoading={scanActivityLoading}
                />
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
                          {((mlSignal.confidence ?? 0) * 100).toFixed(1)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-sm mb-1">Win Probability</p>
                        <p className="text-xl font-bold text-white">
                          {((mlSignal.win_probability ?? 0) * 100).toFixed(1)}%
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
                            <p className="text-sm font-medium text-white">{((mlSignal.model_predictions.flip_gravity ?? 0) * 100).toFixed(0)}%</p>
                          </div>
                          <div className="bg-gray-900 rounded p-2">
                            <p className="text-xs text-gray-500">Magnet Attraction</p>
                            <p className="text-sm font-medium text-white">{((mlSignal.model_predictions.magnet_attraction ?? 0) * 100).toFixed(0)}%</p>
                          </div>
                          <div className="bg-gray-900 rounded p-2">
                            <p className="text-xs text-gray-500">Pin Zone</p>
                            <p className="text-sm font-medium text-white">{((mlSignal.model_predictions.pin_zone ?? 0) * 100).toFixed(0)}%</p>
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
                        {((oracleAdvice.win_probability ?? 0) * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Confidence</p>
                      <p className="text-xl font-bold text-white">
                        {(oracleAdvice.confidence ?? 0).toFixed(1)}%
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
                      <p className={`text-lg font-bold ${(performance.summary?.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(performance.summary?.total_pnl ?? 0)}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm">Win Rate</p>
                      <p className="text-lg font-bold text-white">
                        {(performance.summary?.avg_win_rate ?? 0).toFixed(1)}%
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
                                  {/* OVERRIDE INDICATOR - Very prominent */}
                                  {decision.override_occurred && (
                                    <span className="px-2 py-0.5 rounded text-xs font-bold bg-amber-500/30 text-amber-400 border border-amber-500/50 animate-pulse">
                                      OVERRIDE
                                    </span>
                                  )}
                                  {/* Signal Source Badge */}
                                  {decision.signal_source && (
                                    <span className={`px-2 py-0.5 rounded text-xs ${
                                      decision.signal_source.includes('override')
                                        ? 'bg-amber-900/30 text-amber-300'
                                        : 'bg-blue-900/30 text-blue-300'
                                    }`}>
                                      {decision.signal_source}
                                    </span>
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
                              {/* OVERRIDE DETAILS - Most prominent when present */}
                              {decision.override_occurred && decision.override_details && (
                                <div className="bg-amber-900/20 border-2 border-amber-500/50 rounded-lg p-3">
                                  <div className="flex items-center gap-2 mb-2">
                                    <span className="text-amber-400 text-sm font-bold">SIGNAL OVERRIDE</span>
                                    <span className="px-2 py-0.5 rounded text-xs bg-amber-500/30 text-amber-300">
                                      {decision.override_details.override_by} overrode {decision.override_details.overridden_signal}
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-2 gap-2 text-xs">
                                    <div>
                                      <span className="text-gray-400">ML was saying:</span>
                                      <span className="ml-2 text-red-400 font-medium">{decision.override_details.ml_was_saying || decision.override_details.overridden_advice}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-400">Oracle said:</span>
                                      <span className="ml-2 text-green-400 font-medium">{decision.override_details.oracle_advice}</span>
                                    </div>
                                    <div>
                                      <span className="text-gray-400">Oracle Confidence:</span>
                                      <span className="ml-2 text-white font-medium">
                                        {decision.override_details.oracle_confidence ? `${(decision.override_details.oracle_confidence * 100).toFixed(0)}%` : 'N/A'}
                                      </span>
                                    </div>
                                    <div>
                                      <span className="text-gray-400">Win Probability:</span>
                                      <span className="ml-2 text-white font-medium">
                                        {decision.override_details.oracle_win_probability ? `${(decision.override_details.oracle_win_probability * 100).toFixed(0)}%` : 'N/A'}
                                      </span>
                                    </div>
                                  </div>
                                  <p className="text-xs text-amber-200 mt-2 italic">
                                    {decision.override_details.override_reason}
                                  </p>
                                </div>
                              )}

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
                                        {decision.ml_predictions.direction} ({((decision.ml_predictions.direction_probability ?? 0) * 100).toFixed(0)}%)
                                      </span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Flip Gravity</span>
                                      <span className="text-purple-400 font-bold">{((decision.ml_predictions.flip_gravity ?? 0) * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Magnet</span>
                                      <span className="text-blue-400 font-bold">{((decision.ml_predictions.magnet_attraction ?? 0) * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Pin Zone</span>
                                      <span className="text-cyan-400 font-bold">{((decision.ml_predictions.pin_zone_probability ?? 0) * 100).toFixed(0)}%</span>
                                    </div>
                                  </div>
                                  <div className="grid grid-cols-3 gap-2 text-xs">
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Exp Volatility</span>
                                      <span className="text-yellow-400 font-bold">{(decision.ml_predictions.expected_volatility ?? 0).toFixed(2)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">ML Confidence</span>
                                      <span className="text-white font-bold">{((decision.ml_predictions.ml_confidence ?? 0) * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Win Prob</span>
                                      <span className="text-green-400 font-bold">{((decision.ml_predictions.win_probability ?? 0) * 100).toFixed(0)}%</span>
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
                                      <span className="text-green-400 font-bold">{(decision.backtest_stats.win_rate ?? 0).toFixed(0)}%</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Expectancy</span>
                                      <span className="text-white font-bold">${(decision.backtest_stats.expectancy ?? 0).toFixed(0)}</span>
                                    </div>
                                    <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                      <span className="text-gray-500 block">Sharpe</span>
                                      <span className="text-cyan-400 font-bold">{(decision.backtest_stats.sharpe_ratio ?? 0).toFixed(2)}</span>
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
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">ID</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Type</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Strikes</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Exp</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Qty</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Entry</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Greeks</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Regime</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Status</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">P&L</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-700">
                    {positions
                      .filter(p => showClosedPositions || p.status === 'open')
                      .map((pos) => {
                        const isExpanded = expandedPosition === pos.position_id
                        const greeks = pos.greeks || { net_delta: 0, net_gamma: 0, net_theta: 0, long_delta: 0, short_delta: 0 }
                        return (
                          <React.Fragment key={pos.position_id}>
                            <tr
                              className="hover:bg-gray-700/50 cursor-pointer"
                              onClick={() => setExpandedPosition(isExpanded ? null : pos.position_id)}
                            >
                              <td className="px-3 py-3 text-sm text-gray-300 font-mono">
                                <div className="flex items-center gap-1">
                                  <ChevronRight className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                                  {pos.position_id.slice(-8)}
                                </div>
                              </td>
                              <td className="px-3 py-3">
                                <span className={`px-2 py-1 rounded text-xs font-medium ${
                                  pos.spread_type === 'BULL_CALL_SPREAD'
                                    ? 'bg-green-900/50 text-green-400'
                                    : 'bg-red-900/50 text-red-400'
                                }`}>
                                  {pos.spread_type === 'BULL_CALL_SPREAD' ? 'BULL' : 'BEAR'}
                                </span>
                              </td>
                              <td className="px-3 py-3 text-sm text-gray-300">
                                ${pos.long_strike} / ${pos.short_strike}
                              </td>
                              <td className="px-3 py-3">
                                <span className={`px-2 py-1 rounded text-xs ${
                                  pos.is_0dte ? 'bg-purple-900/50 text-purple-400' : 'bg-gray-700 text-gray-400'
                                }`}>
                                  {pos.is_0dte ? '0DTE' : pos.expiration?.slice(5) || '--'}
                                </span>
                              </td>
                              <td className="px-3 py-3 text-sm text-gray-300">{pos.contracts}</td>
                              <td className="px-3 py-3 text-sm text-gray-300">${pos.entry_price?.toFixed(2) || '0.00'}</td>
                              <td className="px-3 py-3 text-xs font-mono">
                                <span className={greeks.net_delta >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  Δ{greeks.net_delta >= 0 ? '+' : ''}{greeks.net_delta?.toFixed(2) || '0.00'}
                                </span>
                              </td>
                              <td className="px-3 py-3">
                                <span className={`px-2 py-1 rounded text-xs ${
                                  pos.gex_regime === 'POSITIVE'
                                    ? 'bg-blue-900/50 text-blue-400'
                                    : 'bg-orange-900/50 text-orange-400'
                                }`}>
                                  {pos.gex_regime}
                                </span>
                              </td>
                              <td className="px-3 py-3">
                                <span className={`px-2 py-1 rounded text-xs ${
                                  pos.status === 'open'
                                    ? 'bg-yellow-900/50 text-yellow-400'
                                    : pos.status === 'expired'
                                    ? 'bg-purple-900/50 text-purple-400'
                                    : 'bg-gray-700 text-gray-400'
                                }`}>
                                  {pos.status}
                                </span>
                              </td>
                              <td className={`px-3 py-3 text-sm font-medium ${
                                (pos.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                              }`}>
                                {(pos.status === 'closed' || pos.status === 'expired') ? formatCurrency(pos.realized_pnl || 0) : '--'}
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr className="bg-gray-900/50">
                                <td colSpan={10} className="px-4 py-4">
                                  <div className="grid grid-cols-4 gap-4 text-sm">
                                    {/* Position Details */}
                                    <div className="space-y-2">
                                      <h4 className="text-gray-400 font-medium text-xs uppercase">Position Details</h4>
                                      <div className="space-y-1">
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Full ID:</span>
                                          <span className="text-gray-300 font-mono text-xs">{pos.position_id}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Spread Width:</span>
                                          <span className="text-gray-300">${pos.spread_width?.toFixed(2) || '--'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Breakeven:</span>
                                          <span className="text-gray-300">${pos.breakeven?.toFixed(2) || '--'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">SPY at Entry:</span>
                                          <span className="text-gray-300">${pos.spot_at_entry?.toFixed(2) || '--'}</span>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Greeks */}
                                    <div className="space-y-2">
                                      <h4 className="text-gray-400 font-medium text-xs uppercase">Greeks at Entry</h4>
                                      <div className="space-y-1">
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Net Delta:</span>
                                          <span className={`font-mono ${greeks.net_delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {greeks.net_delta >= 0 ? '+' : ''}{greeks.net_delta?.toFixed(3) || '0.000'}
                                          </span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Net Gamma:</span>
                                          <span className="text-gray-300 font-mono">{greeks.net_gamma?.toFixed(3) || '0.000'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Net Theta:</span>
                                          <span className="text-red-400 font-mono">{greeks.net_theta?.toFixed(3) || '0.000'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Long Δ / Short Δ:</span>
                                          <span className="text-gray-300 font-mono text-xs">
                                            {greeks.long_delta?.toFixed(2) || '--'} / {greeks.short_delta?.toFixed(2) || '--'}
                                          </span>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Risk/Reward */}
                                    <div className="space-y-2">
                                      <h4 className="text-gray-400 font-medium text-xs uppercase">Risk / Reward</h4>
                                      <div className="space-y-1">
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Max Profit:</span>
                                          <span className="text-green-400">${pos.max_profit?.toFixed(2) || '--'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Max Loss:</span>
                                          <span className="text-red-400">${pos.max_loss?.toFixed(2) || '--'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">R:R Ratio:</span>
                                          <span className="text-gray-300">
                                            1:{((pos.max_profit || 0) / (pos.max_loss || 1)).toFixed(2)}
                                          </span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-gray-500">Oracle Conf:</span>
                                          <span className="text-blue-400">{((pos.oracle_confidence || 0) * 100).toFixed(0)}%</span>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Oracle Reasoning */}
                                    <div className="space-y-2">
                                      <h4 className="text-gray-400 font-medium text-xs uppercase">Oracle Reasoning</h4>
                                      <p className="text-gray-400 text-xs leading-relaxed">
                                        {pos.oracle_reasoning || 'No reasoning available'}
                                      </p>
                                      {pos.exit_reason && (
                                        <div className="mt-2 pt-2 border-t border-gray-700">
                                          <span className="text-gray-500 text-xs">Exit Reason: </span>
                                          <span className="text-yellow-400 text-xs">{pos.exit_reason}</span>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        )
                      })}
                    {positions.length === 0 && (
                      <tr>
                        <td colSpan={10} className="px-4 py-8 text-center text-gray-500">
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

      {/* Position Detail Modal */}
      <PositionDetailModal
        isOpen={selectedPosition !== null}
        onClose={() => setSelectedPosition(null)}
        position={selectedPosition || {
          position_id: '',
          spread_type: '',
          long_strike: 0,
          short_strike: 0,
          expiration: '',
          contracts: 0,
          entry_price: 0,
          status: ''
        }}
        underlyingPrice={livePnL?.underlying_price}
        botType="ATHENA"
      />

    </div>
  )
}
