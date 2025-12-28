'use client'

import React, { useState, useMemo } from 'react'
import { Sword, TrendingUp, TrendingDown, Activity, DollarSign, Target, RefreshCw, BarChart3, ChevronDown, ChevronUp, ChevronRight, Server, Play, AlertTriangle, Clock, Zap, Brain, Shield, Crosshair, TrendingUp as TrendUp, FileText, ListChecks, Settings, Wallet } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, ReferenceLine } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useToast } from '@/components/ui/Toast'
import {
  useARESStatus,
  useARESPerformance,
  useARESEquityCurve,
  useARESPositions,
  useARESMarketData,
  useARESTradierStatus,
  useARESConfig,
  useARESDecisions,
  useScanActivityAres,
  useARESLivePnL,
  useARESStrategyPresets
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
  PositionEntryContext,
  PresetPerformanceChart,
  // Enhanced Scan Activity - MAXIMUM TRANSPARENCY
  ScanDetailCard,
  // Unified Branding Components
  BOT_BRANDS,
  BotPageHeader,
  BotCard,
  DataFreshnessIndicator,
  EmptyState,
  LoadingState,
  StatCard,
  StatusBadge,
  DirectionIndicator,
  PnLDisplay,
  // NEW: Time & Context Display Components
  formatDuration,
  TimeInPosition,
  DateRangeDisplay,
  BreakevenDistance,
  EntryContext,
  UnlockConditions,
  DrawdownDisplay,
} from '@/components/trader'
import type { TradeDecision, TabId, ScanData } from '@/components/trader'
import EquityCurveChart from '@/components/charts/EquityCurveChart'
import { History, LayoutDashboard } from 'lucide-react'

// Unified tab configuration for ARES
const ARES_TABS = [
  { id: 'portfolio' as const, label: 'Portfolio', icon: Wallet, description: 'Live P&L and positions' },
  { id: 'overview' as const, label: 'Overview', icon: LayoutDashboard, description: 'Bot status and metrics' },
  { id: 'activity' as const, label: 'Activity', icon: Activity, description: 'Scans and decisions' },
  { id: 'history' as const, label: 'History', icon: History, description: 'Closed positions' },
  { id: 'config' as const, label: 'Config', icon: Settings, description: 'Settings and controls' },
]
type AresTabId = typeof ARES_TABS[number]['id']

// ==================== INTERFACES ====================

interface Heartbeat {
  last_scan: string | null
  last_scan_iso: string | null
  status: string
  scan_count_today: number
  details: Record<string, any>
}

interface ARESStatus {
  mode: string
  capital: number
  total_pnl: number
  trade_count: number
  win_rate: number
  open_positions: number
  closed_positions: number
  traded_today: boolean
  in_trading_window: boolean
  current_time: string
  is_active: boolean
  high_water_mark: number
  sandbox_connected?: boolean
  paper_mode_type?: 'sandbox' | 'simulated'
  scan_interval_minutes?: number
  heartbeat?: Heartbeat
  config: {
    risk_per_trade: number
    spread_width: number
    sd_multiplier: number
    ticker: string
  }
}

interface IronCondorPosition {
  position_id: string
  ticker?: string
  open_date: string
  close_date?: string
  expiration: string
  put_long_strike: number
  put_short_strike: number
  call_short_strike: number
  call_long_strike: number
  total_credit: number
  close_price?: number
  realized_pnl?: number
  max_loss: number
  contracts: number
  spread_width?: number
  underlying_at_entry: number
  vix_at_entry: number
  status: string
}

interface Performance {
  total_trades: number
  closed_trades: number
  open_positions: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  avg_pnl_per_trade: number
  best_trade: number
  worst_trade: number
  current_capital: number
  return_pct: number
  high_water_mark: number
  max_drawdown_pct: number
}

interface EquityPoint {
  date: string
  equity: number
  pnl: number
  daily_pnl: number
  return_pct: number
}

interface MarketData {
  ticker: string
  underlying_price: number
  vix: number
  expected_move: number
  timestamp: string
  source: string
  spx?: { ticker: string; price: number; expected_move: number }
  spy?: { ticker: string; price: number; expected_move: number }
  // GEX data
  gex_context?: {
    put_wall: number
    call_wall: number
    net_gex: number
    regime: string
    flip_point: number
    between_walls?: boolean
  }
}

interface TradierStatus {
  mode: string
  success?: boolean
  paper_mode_type?: 'simulated' | 'sandbox' | 'live'
  account: {
    account_number?: string
    type?: string
    cash?: number
    equity?: number
    buying_power?: number
    note?: string
  }
  positions: Array<{ symbol: string; quantity: number; cost_basis: number; date_acquired?: string; status?: string }>
  orders: Array<{ id: string; symbol: string; side: string; quantity: number; status: string; type?: string; price?: number; created_date?: string }>
  errors: string[]
}

interface Config {
  ticker: string
  spread_width: number
  spread_width_spy?: number
  risk_per_trade_pct: number
  sd_multiplier: number
  sd_multiplier_spy?: number
  min_credit: number
  profit_target_pct: number
  entry_window: string
  mode?: string
  strategy_preset?: string
  vix_hard_skip?: number
  vix_monday_friday_skip?: number
  vix_streak_skip?: number
}

interface StrategyPreset {
  id: string
  name: string
  description: string
  vix_hard_skip: number
  vix_monday_friday_skip: number
  vix_streak_skip: number
  risk_per_trade_pct: number
  sd_multiplier: number
  backtest_sharpe: number
  backtest_win_rate: number
  is_active: boolean
}

interface DecisionLog {
  id: number
  bot_name: string
  symbol: string
  decision_type: string
  action: string
  what: string
  why: string
  how: string
  outcome: string
  timestamp: string
  strike?: number
  expiration?: string
  spot_price?: number
  vix?: number
  actual_pnl?: number
  underlying_price_at_entry?: number
  underlying_price_at_exit?: number
  outcome_notes?: string
  // SIGNAL SOURCE TRACKING
  signal_source?: string  // "Oracle", "Config", etc.
  override_occurred?: boolean
  override_details?: {
    overridden_signal?: string
    overridden_advice?: string
    override_reason?: string
    override_by?: string
  }
  legs?: Array<{
    leg_id: number; action: string; option_type: string; strike: number; expiration: string
    entry_price: number; exit_price: number; contracts: number; premium_per_contract: number
    delta: number; gamma: number; theta: number; iv: number; realized_pnl: number
  }>
  oracle_advice?: {
    advice: string; win_probability: number; confidence: number; suggested_risk_pct: number
    suggested_sd_multiplier: number; use_gex_walls: boolean; suggested_put_strike?: number
    suggested_call_strike?: number; top_factors: Array<[string, number]>; reasoning: string
    model_version: string; claude_analysis?: { analysis: string; confidence_adjustment: number; risk_factors: string[]; opportunities: string[]; recommendation: string }
  }
  gex_context?: { net_gex: number; gex_normalized: number; call_wall: number; put_wall: number; flip_point: number; distance_to_flip_pct: number; regime: string; between_walls: boolean }
  market_context?: { spot_price: number; vix: number; vix_percentile: number; expected_move: number; trend: string; day_of_week: number; days_to_opex: number }
  backtest_stats?: { strategy_name: string; win_rate: number; expectancy: number; avg_win: number; avg_loss: number; sharpe_ratio: number; max_drawdown: number; total_trades: number; uses_real_data: boolean; backtest_period: string }
  position_sizing?: { contracts: number; position_dollars: number; max_risk_dollars: number; sizing_method: string; target_profit_pct: number; stop_loss_pct: number; probability_of_profit: number }
  alternatives?: { primary_reason: string; supporting_factors: string[]; risk_factors: string[]; alternatives_considered: string[]; why_not_alternatives: string[] }
  risk_checks?: Array<{ check: string; passed: boolean; value?: string }>
  passed_risk_checks?: boolean
}

// ==================== HELPER COMPONENTS ====================

// Today's Summary Card - Shows what happened today at a glance
interface TodaySummaryProps {
  tradedToday: boolean
  openPosition: IronCondorPosition | null
  todayDecision: DecisionLog | null
  marketData: MarketData | undefined
  gexContext: MarketData['gex_context']
  heartbeat?: Heartbeat
}

function TodaySummaryCard({ tradedToday, openPosition, todayDecision, marketData, gexContext, heartbeat }: TodaySummaryProps) {
  const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

  if (tradedToday && openPosition) {
    // We traded today - show the position
    const credit = openPosition.total_credit * 100 * openPosition.contracts
    const maxRisk = openPosition.max_loss
    const oracleConf = todayDecision?.oracle_advice?.confidence || todayDecision?.oracle_advice?.win_probability || 0

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
              {openPosition.ticker || 'SPX'} Iron Condor
            </div>
            <div className="text-purple-300 font-mono">
              {openPosition.put_short_strike}P / {openPosition.call_short_strike}C
            </div>
            <div className="flex gap-4 mt-3 text-sm">
              <div>
                <span className="text-gray-500">Credit: </span>
                <span className="text-green-400 font-bold">${credit.toFixed(0)}</span>
              </div>
              <div>
                <span className="text-gray-500">Max Risk: </span>
                <span className="text-red-400">${maxRisk.toFixed(0)}</span>
              </div>
            </div>
          </div>

          {/* Why We Traded */}
          <div className="bg-black/30 rounded-lg p-4">
            <div className="text-gray-400 text-xs mb-2">WHY WE TRADED</div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-green-400" />
                <span className="text-white">Oracle: <span className="text-green-400 font-bold">{(oracleConf * 100).toFixed(0)}%</span> confidence</span>
              </div>
              {gexContext && (
                <div className="flex items-center gap-2">
                  <Shield className="w-4 h-4 text-blue-400" />
                  <span className="text-white">GEX: <span className={gexContext.regime === 'POSITIVE' ? 'text-blue-400' : 'text-orange-400'}>{gexContext.regime}</span></span>
                </div>
              )}
              {gexContext && gexContext.put_wall != null && (
                <div className="text-xs text-gray-400">
                  Put wall ${gexContext.put_wall.toFixed(0)} ({((marketData?.underlying_price || 0) - gexContext.put_wall).toFixed(0)} pts buffer)
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // No trade today - show why
  // Check if scans have run today via heartbeat before falling back to "No scan completed yet"
  const hasScannedToday = (heartbeat?.scan_count_today ?? 0) > 0
  const skipReason = todayDecision?.alternatives?.primary_reason || todayDecision?.why ||
    (hasScannedToday ? 'Market conditions not favorable' : 'No scan completed yet')
  const oracleConf = todayDecision?.oracle_advice?.win_probability || 0

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

        {todayDecision?.oracle_advice && (
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-yellow-400" />
              <span className="text-gray-300">
                Oracle confidence: <span className={oracleConf >= 0.55 ? 'text-green-400' : 'text-red-400'}>{(oracleConf * 100).toFixed(0)}%</span>
                <span className="text-gray-500 ml-2">(need 55% to trade)</span>
              </span>
            </div>
            {todayDecision.oracle_advice.top_factors?.slice(0, 3).map(([factor, value], i) => (
              <div key={i} className="flex items-center gap-2 text-gray-400">
                <span className="text-gray-600">•</span>
                <span>{factor}: {typeof value === 'number' ? value.toFixed(2) : value}</span>
              </div>
            ))}
          </div>
        )}

        {/* What would change this */}
        <div className="mt-4 pt-3 border-t border-gray-700">
          <div className="text-gray-400 text-xs mb-2">WHAT WOULD HELP</div>
          <div className="flex flex-wrap gap-2">
            {gexContext?.regime !== 'POSITIVE' && (
              <span className="px-2 py-1 bg-blue-900/30 text-blue-400 rounded text-xs">GEX flip to POSITIVE (+8%)</span>
            )}
            {(marketData?.vix || 0) > 22 && (
              <span className="px-2 py-1 bg-yellow-900/30 text-yellow-400 rounded text-xs">VIX drop below 22 (+4%)</span>
            )}
            {gexContext && !gexContext.between_walls && (
              <span className="px-2 py-1 bg-purple-900/30 text-purple-400 rounded text-xs">Price return between walls (+3%)</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// Strike Placement Diagram - Visual representation of position vs market
interface StrikeDiagramProps {
  position: IronCondorPosition | null
  spotPrice: number
  expectedMove: number
  putWall: number | undefined
  callWall: number | undefined
}

function StrikePlacementDiagram({ position, spotPrice, expectedMove, putWall, callWall }: StrikeDiagramProps) {
  if (!position || !spotPrice) return null

  const minStrike = Math.min(
    position.put_long_strike,
    putWall || position.put_long_strike,
    spotPrice - expectedMove * 1.5
  )
  const maxStrike = Math.max(
    position.call_long_strike,
    callWall || position.call_long_strike,
    spotPrice + expectedMove * 1.5
  )
  const range = maxStrike - minStrike
  const toPercent = (val: number) => ((val - minStrike) / range) * 100

  const spotPct = toPercent(spotPrice)
  const putLongPct = toPercent(position.put_long_strike)
  const putShortPct = toPercent(position.put_short_strike)
  const callShortPct = toPercent(position.call_short_strike)
  const callLongPct = toPercent(position.call_long_strike)
  const putWallPct = putWall ? toPercent(putWall) : null
  const callWallPct = callWall ? toPercent(callWall) : null
  const expMoveLowPct = toPercent(spotPrice - expectedMove)
  const expMoveHighPct = toPercent(spotPrice + expectedMove)

  return (
    <div className="bg-gray-800/50 rounded-xl p-5 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <Crosshair className="w-5 h-5 text-purple-400" />
        <h3 className="text-lg font-semibold text-white">Strike Placement</h3>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 mb-4 text-xs">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span className="text-gray-400">Profit Zone</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <span className="text-gray-400">Max Loss Zone</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-blue-500/50" />
          <span className="text-gray-400">GEX Walls</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-0.5 bg-yellow-500" />
          <span className="text-gray-400">Expected Move</span>
        </div>
      </div>

      {/* Diagram */}
      <div className="relative h-20 mb-4">
        {/* Background track */}
        <div className="absolute top-8 left-0 right-0 h-4 bg-gray-700 rounded-full" />

        {/* Max Loss Zones (wings) */}
        <div
          className="absolute top-8 h-4 bg-red-900/50 rounded-l-full"
          style={{ left: `${putLongPct}%`, width: `${putShortPct - putLongPct}%` }}
        />
        <div
          className="absolute top-8 h-4 bg-red-900/50 rounded-r-full"
          style={{ left: `${callShortPct}%`, width: `${callLongPct - callShortPct}%` }}
        />

        {/* Profit Zone */}
        <div
          className="absolute top-8 h-4 bg-green-900/70"
          style={{ left: `${putShortPct}%`, width: `${callShortPct - putShortPct}%` }}
        />

        {/* GEX Walls */}
        {putWallPct !== null && (
          <div
            className="absolute top-6 w-1 h-8 bg-blue-500/70"
            style={{ left: `${putWallPct}%` }}
            title={`Put Wall: $${putWall?.toFixed(0)}`}
          />
        )}
        {callWallPct !== null && (
          <div
            className="absolute top-6 w-1 h-8 bg-blue-500/70"
            style={{ left: `${callWallPct}%` }}
            title={`Call Wall: $${callWall?.toFixed(0)}`}
          />
        )}

        {/* Expected Move Range */}
        <div
          className="absolute top-12 h-0.5 bg-yellow-500/50"
          style={{ left: `${expMoveLowPct}%`, width: `${expMoveHighPct - expMoveLowPct}%` }}
        />

        {/* Strike Labels */}
        <div className="absolute top-0 text-xs text-red-400 font-mono" style={{ left: `${putLongPct}%`, transform: 'translateX(-50%)' }}>
          ${position.put_long_strike}
        </div>
        <div className="absolute top-0 text-xs text-green-400 font-mono" style={{ left: `${putShortPct}%`, transform: 'translateX(-50%)' }}>
          ${position.put_short_strike}
        </div>
        <div className="absolute top-0 text-xs text-green-400 font-mono" style={{ left: `${callShortPct}%`, transform: 'translateX(-50%)' }}>
          ${position.call_short_strike}
        </div>
        <div className="absolute top-0 text-xs text-red-400 font-mono" style={{ left: `${callLongPct}%`, transform: 'translateX(-50%)' }}>
          ${position.call_long_strike}
        </div>

        {/* Current Price Marker */}
        <div
          className="absolute top-5 flex flex-col items-center"
          style={{ left: `${spotPct}%`, transform: 'translateX(-50%)' }}
        >
          <div className="text-xs text-white font-bold">${spotPrice.toFixed(0)}</div>
          <div className="w-0.5 h-8 bg-white" />
          <div className="w-2 h-2 rounded-full bg-white" />
        </div>
      </div>

      {/* Buffer Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center text-sm">
        <div className="bg-gray-900/50 rounded-lg p-2">
          <div className="text-gray-500 text-xs">Put Buffer</div>
          <div className="text-green-400 font-mono font-bold">
            {(spotPrice - position.put_short_strike).toFixed(0)} pts
          </div>
        </div>
        <div className="bg-gray-900/50 rounded-lg p-2">
          <div className="text-gray-500 text-xs">Call Buffer</div>
          <div className="text-green-400 font-mono font-bold">
            {(position.call_short_strike - spotPrice).toFixed(0)} pts
          </div>
        </div>
        {putWall && (
          <div className="bg-gray-900/50 rounded-lg p-2">
            <div className="text-gray-500 text-xs">Put Wall Gap</div>
            <div className="text-blue-400 font-mono font-bold">
              {(position.put_short_strike - putWall).toFixed(0)} pts
            </div>
          </div>
        )}
        {callWall && (
          <div className="bg-gray-900/50 rounded-lg p-2">
            <div className="text-gray-500 text-xs">Call Wall Gap</div>
            <div className="text-blue-400 font-mono font-bold">
              {(callWall - position.call_short_strike).toFixed(0)} pts
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// Decision Tree Display - Shows Oracle vs ML decision flow
interface DecisionTreeProps {
  decision: DecisionLog | null
}

function DecisionTreeDisplay({ decision }: DecisionTreeProps) {
  if (!decision) return null

  const oracle = decision.oracle_advice
  const gex = decision.gex_context
  const market = decision.market_context

  // Calculate decision path
  const mlBaseProb = oracle?.win_probability || 0
  let adjustedProb = mlBaseProb

  const adjustments: Array<{ label: string; value: number; color: string }> = []

  if (gex?.regime === 'POSITIVE') {
    adjustments.push({ label: 'GEX Positive Regime', value: 0.03, color: 'text-blue-400' })
    adjustedProb += 0.03
  } else if (gex?.regime === 'NEGATIVE') {
    adjustments.push({ label: 'GEX Negative Regime', value: -0.05, color: 'text-orange-400' })
    adjustedProb -= 0.05
  }

  if (gex && !gex.between_walls) {
    adjustments.push({ label: 'Price outside walls', value: -0.03, color: 'text-red-400' })
    adjustedProb -= 0.03
  }

  if ((market?.vix || 0) > 25) {
    adjustments.push({ label: 'High VIX (>25)', value: -0.02, color: 'text-yellow-400' })
    adjustedProb -= 0.02
  }

  const finalAdvice = oracle?.advice || decision.action
  const isTraded = finalAdvice?.includes('TRADE') || decision.action === 'OPEN'

  return (
    <div className="bg-gray-800/50 rounded-xl p-5 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <Brain className="w-5 h-5 text-green-400" />
        <h3 className="text-lg font-semibold text-white">Decision Path</h3>
      </div>

      <div className="space-y-4">
        {/* Step 1: ML Base */}
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-purple-900/50 flex items-center justify-center text-purple-400 text-xs font-bold">1</div>
          <div className="flex-1">
            <div className="text-gray-400 text-xs mb-1">GEX ML MODELS</div>
            <div className="flex items-center gap-2">
              <span className="text-white">Base Win Probability:</span>
              <span className="text-purple-400 font-bold">{(mlBaseProb * 100).toFixed(0)}%</span>
            </div>
            {oracle?.top_factors && oracle.top_factors.length > 0 && (
              <div className="mt-2 text-xs text-gray-500">
                Top factors: {oracle.top_factors.slice(0, 2).map(([f]) => f).join(', ')}
              </div>
            )}
          </div>
        </div>

        {/* Step 2: Oracle Adjustments */}
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-green-900/50 flex items-center justify-center text-green-400 text-xs font-bold">2</div>
          <div className="flex-1">
            <div className="text-gray-400 text-xs mb-1">ORACLE ADJUSTMENTS</div>
            <div className="space-y-1">
              {adjustments.length > 0 ? (
                adjustments.map((adj, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <span className={adj.color}>{adj.value >= 0 ? '+' : ''}{(adj.value * 100).toFixed(0)}%</span>
                    <span className="text-gray-400">{adj.label}</span>
                  </div>
                ))
              ) : (
                <div className="text-gray-500 text-sm">No adjustments applied</div>
              )}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className="text-gray-500">→ Final:</span>
              <span className={`font-bold ${adjustedProb >= 0.70 ? 'text-green-400' : adjustedProb >= 0.55 ? 'text-yellow-400' : 'text-red-400'}`}>
                {(adjustedProb * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>

        {/* Step 3: Decision */}
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-blue-900/50 flex items-center justify-center text-blue-400 text-xs font-bold">3</div>
          <div className="flex-1">
            <div className="text-gray-400 text-xs mb-1">FINAL DECISION</div>
            <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full ${isTraded ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
              {isTraded ? '✓ TRADE' : '✗ SKIP'}
              <span className="text-xs opacity-70">
                ({adjustedProb >= 0.70 ? '≥70%' : adjustedProb >= 0.55 ? '55-70%' : '<55%'})
              </span>
            </div>
          </div>
        </div>

        {/* Thresholds Legend */}
        <div className="mt-4 pt-3 border-t border-gray-700">
          <div className="text-gray-500 text-xs mb-2">DECISION THRESHOLDS</div>
          <div className="flex gap-4 text-xs">
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-green-500" />
              <span className="text-gray-400">≥70% = TRADE_FULL</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-yellow-500" />
              <span className="text-gray-400">55-70% = TRADE_REDUCED</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-gray-400">&lt;55% = SKIP</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// Quick Actions Panel
interface QuickActionsProps {
  onSkipToday: () => void
  onAdjustRisk: (newRisk: number) => void
  onForceScan: () => void
  currentRisk: number
  isTrading: boolean
  hasOpenPosition: boolean
  isScanning?: boolean
}

function QuickActionsPanel({ onSkipToday, onAdjustRisk, onForceScan, currentRisk, isTrading, hasOpenPosition, isScanning }: QuickActionsProps) {
  const [riskValue, setRiskValue] = useState(currentRisk)
  const [showConfirm, setShowConfirm] = useState<'skip' | 'risk' | null>(null)

  return (
    <div className="bg-[#0a0a0a] rounded-xl p-5 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-5 h-5 text-purple-400" />
        <h3 className="text-lg font-semibold text-white">Quick Actions</h3>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Skip Today */}
        <button
          onClick={() => showConfirm === 'skip' ? (onSkipToday(), setShowConfirm(null)) : setShowConfirm('skip')}
          disabled={hasOpenPosition}
          className={`p-3 rounded-lg border transition flex flex-col items-center gap-2 ${
            showConfirm === 'skip'
              ? 'bg-yellow-900/30 border-yellow-600 text-yellow-400'
              : hasOpenPosition
                ? 'bg-gray-900/50 border-gray-800 text-gray-600 cursor-not-allowed'
                : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:bg-gray-700'
          }`}
        >
          <Clock className="w-5 h-5" />
          <span className="text-xs">{showConfirm === 'skip' ? 'Confirm?' : 'Skip Today'}</span>
        </button>

        {/* Adjust Risk */}
        <div className="p-3 rounded-lg border bg-gray-800/50 border-gray-700 flex flex-col items-center gap-2">
          <Settings className="w-5 h-5 text-blue-400" />
          <span className="text-xs text-gray-400">Risk: {currentRisk}%</span>
        </div>

        {/* Force Scan */}
        <button
          onClick={onForceScan}
          disabled={isScanning || hasOpenPosition}
          className={`p-3 rounded-lg border transition flex flex-col items-center gap-2 ${
            isScanning
              ? 'bg-green-900/30 border-green-600 text-green-400 animate-pulse'
              : hasOpenPosition
                ? 'bg-gray-900/50 border-gray-800 text-gray-600 cursor-not-allowed'
                : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:bg-gray-700'
          }`}
        >
          <Play className={`w-5 h-5 ${isScanning ? 'animate-pulse' : ''}`} />
          <span className="text-xs">{isScanning ? 'Scanning...' : 'Force Scan'}</span>
        </button>

        {/* Status */}
        <div className={`p-3 rounded-lg border flex flex-col items-center gap-2 ${
          isTrading ? 'bg-green-900/30 border-green-700' : 'bg-gray-800/50 border-gray-700'
        }`}>
          <div className={`w-3 h-3 rounded-full ${isTrading ? 'bg-green-500 animate-pulse' : 'bg-gray-600'}`} />
          <span className={`text-xs ${isTrading ? 'text-green-400' : 'text-gray-400'}`}>
            {isTrading ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>

      {/* Config Summary */}
      <div className="mt-4 pt-3 border-t border-gray-700 flex flex-wrap gap-4 text-xs text-gray-500">
        <span>Risk: <span className="text-white">{currentRisk}%</span></span>
        <span>Target: <span className="text-green-400">50% profit</span></span>
        <span>Window: <span className="text-cyan-400">9:35-15:55 CT</span></span>
      </div>
    </div>
  )
}

// ==================== MAIN COMPONENT ====================

type TimePeriod = '1D' | '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'ALL'

export default function ARESPage() {
  // SWR hooks for data fetching
  const { data: statusRes, error: statusError, isLoading: statusLoading, isValidating: statusValidating, mutate: mutateStatus } = useARESStatus()
  const { data: performanceRes, isValidating: perfValidating, mutate: mutatePerf } = useARESPerformance()
  const { data: equityRes, isValidating: equityValidating, mutate: mutateEquity } = useARESEquityCurve(30)
  const { data: positionsRes, isValidating: posValidating, mutate: mutatePositions } = useARESPositions()
  const { data: marketRes, isValidating: marketValidating, mutate: mutateMarket } = useARESMarketData()
  const { data: tradierRes, isValidating: tradierValidating, mutate: mutateTradier } = useARESTradierStatus()
  const { data: configRes, isValidating: configValidating, mutate: mutateConfig } = useARESConfig()
  const { data: decisionsRes, isValidating: decisionsValidating, mutate: mutateDecisions } = useARESDecisions(100)
  const { data: scanActivityRes, isLoading: scanActivityLoading, mutate: mutateScanActivity } = useScanActivityAres(50)
  const { data: livePnLRes, isLoading: livePnLLoading, mutate: mutateLivePnL } = useARESLivePnL()
  const { data: strategyPresetsRes, mutate: mutateStrategyPresets } = useARESStrategyPresets()

  // Extract data
  const status = statusRes?.data as ARESStatus | undefined
  const performance = performanceRes?.data as Performance | undefined
  const equityData = (equityRes?.data?.equity_curve || []) as EquityPoint[]
  const scanActivity = scanActivityRes?.data?.scans || []
  const positions = (positionsRes?.data?.open_positions || []) as IronCondorPosition[]
  const closedPositions = (positionsRes?.data?.closed_positions || []) as IronCondorPosition[]
  const marketData = marketRes?.data as MarketData | undefined
  const tradierStatus = tradierRes?.data as TradierStatus | undefined
  const config = configRes?.data as Config | undefined
  const decisions = (decisionsRes?.data?.decisions || []) as DecisionLog[]
  const todayDecision = useMemo(() => {
    const today = new Date().toISOString().split('T')[0]
    return decisions.find(d => d.timestamp?.startsWith(today)) || null
  }, [decisions])
  const livePnL = livePnLRes?.data as LivePnLData | null
  const strategyPresets = (strategyPresetsRes?.data?.presets || []) as StrategyPreset[]
  const activeStrategyPreset = strategyPresetsRes?.data?.active_preset || 'moderate'

  const loading = statusLoading && !status
  const error = statusError?.message || null
  const isRefreshing = statusValidating || perfValidating || equityValidating || posValidating || marketValidating || tradierValidating || configValidating || decisionsValidating

  // Toast notifications for user feedback
  const toast = useToast()

  // UI State - default to portfolio for Robinhood-style view
  const [activeTab, setActiveTab] = useState<AresTabId>('portfolio')
  const [expandedDecision, setExpandedDecision] = useState<number | null>(null)
  const [runningCycle, setRunningCycle] = useState(false)
  const [spxPeriod, setSpxPeriod] = useState<TimePeriod>('1M')
  const [spyPeriod, setSpyPeriod] = useState<TimePeriod>('1M')
  const [showSpxClosedPositions, setShowSpxClosedPositions] = useState(true)
  const [showSpyClosedPositions, setShowSpyClosedPositions] = useState(true)
  const [expandedSpxPosition, setExpandedSpxPosition] = useState<string | null>(null)
  const [expandedSpyPosition, setExpandedSpyPosition] = useState<string | null>(null)
  const [changingStrategy, setChangingStrategy] = useState(false)
  const [selectedPosition, setSelectedPosition] = useState<any | null>(null)

  // Build skip reasons from decisions
  const skipReasons = useMemo(() => {
    const today = new Date().toISOString().split('T')[0]
    return decisions
      .filter(d => d.timestamp?.startsWith(today) && (d.action === 'SKIP' || d.decision_type === 'SKIP'))
      .map(d => ({
        id: String(d.id),
        timestamp: d.timestamp,
        reason: d.why || d.what || 'No reason provided',
        category: d.signal_source?.includes('ML') ? 'ml' as const :
                  d.signal_source?.includes('Oracle') ? 'oracle' as const :
                  d.why?.toLowerCase().includes('market') ? 'market' as const :
                  d.why?.toLowerCase().includes('risk') ? 'risk' as const :
                  d.why?.toLowerCase().includes('vix') ? 'market' as const : 'other' as const,
        details: {
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
        id: String(d.id),
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
        wasCorrect: undefined // To be determined later when position closes
      }))
  }, [scanActivity])

  // Calculate ML vs Oracle stats from today's scans
  const { mlWins, oracleWins, scansToday, tradesToday } = useMemo(() => {
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

  // Strategy change handler
  const handleStrategyChange = async (presetId: string) => {
    if (changingStrategy) return
    setChangingStrategy(true)
    try {
      await apiClient.setARESStrategyPreset(presetId)
      mutateStrategyPresets()
      mutateConfig()
      mutateStatus()
    } catch (err) {
      console.error('Failed to change strategy:', err)
    } finally {
      setChangingStrategy(false)
    }
  }

  // Manual refresh function
  const fetchData = () => {
    mutateStatus()
    mutatePerf()
    mutateEquity()
    mutatePositions()
    mutateMarket()
    mutateTradier()
    mutateConfig()
    mutateDecisions()
    mutateLivePnL()
    mutateScanActivity()
  }

  // Force scan cycle
  const runCycle = async () => {
    setRunningCycle(true)
    try {
      const res = await apiClient.runARESCycle()
      if (res.data?.success) {
        toast.success('Scan Complete', 'ARES cycle completed successfully')
        fetchData()
      } else {
        toast.warning('Scan Complete', res.data?.message || 'ARES cycle completed')
        fetchData()
      }
    } catch (err) {
      console.error('Failed to run ARES cycle:', err)
      toast.error('Scan Failed', 'Failed to run ARES cycle')
    } finally {
      setRunningCycle(false)
    }
  }

  // Helpers
  const isSPX = (pos: IronCondorPosition) => pos.ticker === 'SPX' || (!pos.ticker && (pos.spread_width || 10) > 5)
  const isSPY = (pos: IronCondorPosition) => pos.ticker === 'SPY' || (!pos.ticker && (pos.spread_width || 10) <= 5)
  const spxOpenPositions = positions.filter(isSPX)
  const spyOpenPositions = positions.filter(isSPY)
  const spxClosedPositions = closedPositions.filter(isSPX)
  const spyClosedPositions = closedPositions.filter(isSPY)

  const calcMaxDrawdown = (closed: IronCondorPosition[]) => {
    if (closed.length === 0) return 0
    let peak = 0, maxDD = 0, cum = 0
    closed.forEach(p => {
      cum += p.realized_pnl || 0
      if (cum > peak) peak = cum
      const dd = peak - cum
      if (dd > maxDD) maxDD = dd
    })
    return maxDD
  }

  const spxStats = {
    capital: 200000,
    totalPnl: spxClosedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0),
    totalTrades: spxClosedPositions.length,
    winningTrades: spxClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length,
    losingTrades: spxClosedPositions.filter(p => (p.realized_pnl || 0) <= 0).length,
    winRate: spxClosedPositions.length > 0 ? (spxClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length / spxClosedPositions.length) * 100 : 0,
    bestTrade: spxClosedPositions.length > 0 ? Math.max(...spxClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    worstTrade: spxClosedPositions.length > 0 ? Math.min(...spxClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    maxDrawdown: calcMaxDrawdown(spxClosedPositions),
    avgTrade: spxClosedPositions.length > 0 ? spxClosedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0) / spxClosedPositions.length : 0,
  }

  const spyStats = {
    capital: tradierStatus?.account?.equity || 102000,
    totalPnl: spyClosedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0),
    totalTrades: spyClosedPositions.length,
    winningTrades: spyClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length,
    losingTrades: spyClosedPositions.filter(p => (p.realized_pnl || 0) <= 0).length,
    winRate: spyClosedPositions.length > 0 ? (spyClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length / spyClosedPositions.length) * 100 : 0,
    bestTrade: spyClosedPositions.length > 0 ? Math.max(...spyClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    worstTrade: spyClosedPositions.length > 0 ? Math.min(...spyClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    maxDrawdown: calcMaxDrawdown(spyClosedPositions),
    avgTrade: spyClosedPositions.length > 0 ? spyClosedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0) / spyClosedPositions.length : 0,
  }

  const buildEquityCurve = (pos: IronCondorPosition[], startCap: number) => {
    if (pos.length === 0) return []
    const sorted = [...pos].sort((a, b) => (a.close_date || a.expiration || '').localeCompare(b.close_date || b.expiration || ''))
    const byDate: Record<string, number> = {}
    sorted.forEach(p => { const d = p.close_date || p.expiration || ''; if (d) byDate[d] = (byDate[d] || 0) + (p.realized_pnl || 0) })
    let cum = 0
    return Object.keys(byDate).sort().map(d => {
      cum += byDate[d]
      return {
        date: d,
        timestamp: new Date(d).getTime(),
        equity: startCap + cum,
        daily_pnl: byDate[d],
        pnl: cum
      }
    })
  }

  const filterEquityByPeriod = (data: { date: string; timestamp: number; equity: number; daily_pnl: number; pnl: number }[], period: TimePeriod) => {
    if (data.length === 0) return []
    const now = new Date()
    let startDate: Date

    switch (period) {
      case '1D':
        startDate = new Date(now.getTime() - 24 * 60 * 60 * 1000)
        break
      case '1W':
        startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
        break
      case '1M':
        startDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
        break
      case '3M':
        startDate = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000)
        break
      case 'YTD':
        startDate = new Date(now.getFullYear(), 0, 1)
        break
      case '1Y':
        startDate = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000)
        break
      case 'ALL':
      default:
        return data
    }

    return data.filter(d => new Date(d.date) >= startDate)
  }

  // Build equity curve with live data point (includes unrealized P&L from open positions)
  const equityDataWithLive = useMemo(() => {
    const startingCapital = status?.capital || 200000

    // Get historical equity data from backend
    const historicalData = equityData.map((e: EquityPoint) => ({
      date: e.date,
      timestamp: new Date(e.date).getTime(),
      equity: e.equity,
      pnl: e.pnl
    }))

    // Calculate realized P&L from historical data
    const lastHistoricalPnl = historicalData.length > 0
      ? historicalData[historicalData.length - 1].pnl
      : 0

    // Get unrealized P&L from livePnL data (properly calculated with 100x multiplier)
    const unrealizedPnl = livePnL?.total_unrealized_pnl || 0
    const hasOpenPositions = positions.length > 0

    // Add live "now" point with current equity (historical realized + current unrealized)
    if (hasOpenPositions || historicalData.length > 0) {
      const totalPnl = lastHistoricalPnl + unrealizedPnl
      const now = new Date()
      const livePoint = {
        date: 'Now',
        timestamp: now.getTime(),
        equity: startingCapital + totalPnl,
        pnl: totalPnl
      }

      // If no historical data but have open positions, add starting point
      if (historicalData.length === 0 && hasOpenPositions) {
        const todayStart = new Date()
        todayStart.setHours(9, 30, 0, 0) // Market open
        historicalData.push({
          date: todayStart.toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' }),
          timestamp: todayStart.getTime(),
          equity: startingCapital,
          pnl: 0
        })
      }

      return [...historicalData, livePoint]
    }

    return historicalData
  }, [equityData, livePnL?.total_unrealized_pnl, positions.length, status?.capital])

  const spxEquityData = buildEquityCurve(spxClosedPositions, spxStats.capital)
  const spyEquityData = buildEquityCurve(spyClosedPositions, spyStats.capital)

  const filteredSpxEquity = useMemo(() => filterEquityByPeriod(spxEquityData, spxPeriod), [spxEquityData, spxPeriod])
  const filteredSpyEquity = useMemo(() => filterEquityByPeriod(spyEquityData, spyPeriod), [spyEquityData, spyPeriod])

  // Determine chart colors based on period performance
  const spxPeriodStart = filteredSpxEquity[0]?.equity ?? spxStats.capital
  const spxPeriodEnd = filteredSpxEquity[filteredSpxEquity.length - 1]?.equity ?? (spxStats.capital + spxStats.totalPnl)
  const spxChartColor = (spxPeriodEnd - spxPeriodStart) >= 0 ? '#00C805' : '#FF5000'

  const spyPeriodStart = filteredSpyEquity[0]?.equity ?? spyStats.capital
  const spyPeriodEnd = filteredSpyEquity[filteredSpyEquity.length - 1]?.equity ?? (spyStats.capital + spyStats.totalPnl)
  const spyChartColor = (spyPeriodEnd - spyPeriodStart) >= 0 ? '#00C805' : '#FF5000'

  const periods: TimePeriod[] = ['1D', '1W', '1M', '3M', 'YTD', '1Y', 'ALL']

  const getActionColor = (action: string) => {
    if (action?.includes('BUY') || action?.includes('OPEN') || action?.includes('ENTRY')) return 'text-green-400'
    if (action?.includes('SELL') || action?.includes('CLOSE') || action?.includes('EXIT')) return 'text-red-400'
    if (action?.includes('SKIP') || action?.includes('NO_TRADE')) return 'text-yellow-400'
    return 'text-gray-400'
  }

  const getDecisionTypeBadge = (type: string) => {
    const badges: Record<string, { bg: string, text: string }> = {
      'ENTRY_SIGNAL': { bg: 'bg-green-900/50', text: 'text-green-400' },
      'EXIT_SIGNAL': { bg: 'bg-red-900/50', text: 'text-red-400' },
      'STRIKE_SELECTION': { bg: 'bg-purple-900/50', text: 'text-purple-400' },
      'NO_TRADE': { bg: 'bg-yellow-900/50', text: 'text-yellow-400' },
      'RISK_BLOCKED': { bg: 'bg-orange-900/50', text: 'text-orange-400' },
      'POSITION_SIZE': { bg: 'bg-blue-900/50', text: 'text-blue-400' },
      'EXPIRATION': { bg: 'bg-gray-700', text: 'text-gray-300' },
    }
    return badges[type] || { bg: 'bg-gray-700', text: 'text-gray-400' }
  }

  const formatCurrency = (v: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(v)
  const formatPercent = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`

  // Determine connection status and mode
  // paper_mode_type: 'simulated' (SPX paper - no Tradier), 'sandbox' (SPY paper - Tradier sandbox), 'live' (production)
  const paperModeType = tradierStatus?.paper_mode_type || status?.paper_mode_type || 'unknown'
  const tradierConnected = tradierStatus?.success && tradierStatus?.account?.account_number
  const isSimulatedMode = paperModeType === 'simulated' || tradierStatus?.account?.type === 'simulated'

  // Connection badge configuration
  const getConnectionBadge = () => {
    if (isSimulatedMode) {
      return { bg: 'bg-purple-900', text: 'text-purple-300', label: 'SIMULATED' }
    }
    if (tradierConnected) {
      const accountType = tradierStatus?.account?.type
      if (accountType === 'sandbox') {
        return { bg: 'bg-blue-900', text: 'text-blue-300', label: 'SANDBOX' }
      }
      return { bg: 'bg-green-900', text: 'text-green-300', label: 'TRADIER' }
    }
    return { bg: 'bg-yellow-900', text: 'text-yellow-300', label: 'DISCONNECTED' }
  }
  const connectionBadge = getConnectionBadge()

  // Combined stats
  const totalPnl = spxStats.totalPnl + spyStats.totalPnl
  const totalTrades = spxStats.totalTrades + spyStats.totalTrades
  const totalWins = spxStats.winningTrades + spyStats.winningTrades
  const overallWinRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0

  // ==================== RENDER ====================

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-16 pt-24">
        <div className="p-6">
          {/* Unified Header */}
          <BotPageHeader
            botName="ARES"
            isActive={status?.is_active || false}
            lastHeartbeat={status?.heartbeat?.last_scan_iso || undefined}
            onRefresh={fetchData}
            isRefreshing={isRefreshing}
          />

          {/* Action Bar */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3 text-sm">
              <span className={`px-3 py-1 rounded-full font-medium ${status?.in_trading_window ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'}`}>
                {status?.in_trading_window ? 'MARKET OPEN' : 'MARKET CLOSED'}
              </span>
              <span className={`px-2 py-1 rounded ${connectionBadge.bg} ${connectionBadge.text} text-xs font-medium`}>
                {connectionBadge.label}
              </span>
              <span className="text-gray-500">
                <Clock className="w-4 h-4 inline mr-1" />
                {status?.heartbeat?.scan_count_today || 0} scans today
              </span>
            </div>
            <button onClick={runCycle} disabled={runningCycle} className="flex items-center gap-2 px-4 py-2 bg-red-600 rounded-lg hover:bg-red-500 disabled:opacity-50">
              <Play className={`w-4 h-4 ${runningCycle ? 'animate-pulse' : ''}`} />
              <span className="text-white text-sm">Run Cycle</span>
            </button>
          </div>

          {error && <div className="mb-4 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-300">{error}</div>}

          {/* Heartbeat Status Bar */}
          <div className="mb-4 bg-gray-800/50 rounded-lg p-3 border border-gray-700">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${
                    status?.heartbeat?.status === 'TRADED' ? 'bg-green-500 animate-pulse' :
                    status?.heartbeat?.status === 'SCAN_COMPLETE' ? 'bg-blue-500' :
                    status?.heartbeat?.status === 'ERROR' ? 'bg-red-500' :
                    status?.heartbeat?.status === 'MARKET_CLOSED' ? 'bg-yellow-500' : 'bg-gray-500'
                  }`} />
                  <span className="text-gray-400 text-sm">Heartbeat</span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Last Scan: </span>
                  <span className={`font-mono ${status?.heartbeat?.last_scan ? 'text-white' : 'text-gray-500'}`}>{status?.heartbeat?.last_scan || 'Never'}</span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Status: </span>
                  <span className={`font-medium ${status?.heartbeat?.status === 'TRADED' ? 'text-green-400' : status?.heartbeat?.status === 'SCAN_COMPLETE' ? 'text-blue-400' : status?.heartbeat?.status === 'ERROR' ? 'text-red-400' : 'text-gray-400'}`}>
                    {status?.heartbeat?.status?.replace(/_/g, ' ') || 'Unknown'}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <div><span className="text-gray-500">Scans Today: </span><span className="text-white font-bold">{status?.heartbeat?.scan_count_today || 0}</span></div>
                <div><span className="text-gray-500">Interval: </span><span className="text-cyan-400">{status?.scan_interval_minutes || 5} min</span></div>
                <Clock className="w-4 h-4 text-gray-500" />
              </div>
            </div>
          </div>

          {/* Market Data Bar - Condensed */}
          <div className="mb-4 bg-gray-800 rounded-lg p-3 border border-gray-700">
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-center">
              <div className="bg-purple-900/20 rounded-lg p-2">
                <span className="text-purple-400 text-xs">SPX</span>
                <p className="text-white font-mono text-lg font-bold">${marketData?.spx?.price?.toLocaleString() || '--'}</p>
              </div>
              <div className="bg-blue-900/20 rounded-lg p-2">
                <span className="text-blue-400 text-xs">SPY</span>
                <p className="text-white font-mono text-lg font-bold">${marketData?.spy?.price?.toFixed(2) || '--'}</p>
              </div>
              <div className="bg-yellow-900/20 rounded-lg p-2">
                <span className="text-yellow-400 text-xs">VIX</span>
                <p className="text-white font-mono text-lg font-bold">{marketData?.vix?.toFixed(2) || '--'}</p>
              </div>
              <div className="bg-gray-700/50 rounded-lg p-2">
                <span className="text-gray-400 text-xs">SPX ±Move</span>
                <p className="text-white font-mono text-lg font-bold">±${marketData?.spx?.expected_move?.toFixed(0) || '--'}</p>
              </div>
              <div className="bg-gray-700/50 rounded-lg p-2">
                <span className="text-gray-400 text-xs">SD Mult</span>
                <p className="text-white font-mono text-lg font-bold">{config?.sd_multiplier || 0.5}</p>
              </div>
              <div className="bg-green-900/20 rounded-lg p-2">
                <span className="text-green-400 text-xs">Target</span>
                <p className="text-green-400 font-mono text-lg font-bold">10%/mo</p>
              </div>
            </div>
          </div>

          {/* Unified Tabs */}
          <div className="flex gap-1 mb-6 bg-gray-800/50 p-1 rounded-xl">
            {ARES_TABS.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex-1 px-4 py-2.5 rounded-lg transition flex items-center justify-center gap-2 ${
                    activeTab === tab.id
                      ? 'bg-red-600 text-white shadow-lg'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
                  }`}
                  title={tab.description}
                >
                  <Icon className="w-4 h-4" />
                  <span className="text-sm font-medium">{tab.label}</span>
                </button>
              )
            })}
          </div>

          {/* ==================== PORTFOLIO TAB - Robinhood-style ==================== */}
          {activeTab === 'portfolio' && (
            <div className="space-y-6">
              {/* Bot Status Banner - Shows active/paused/error status with countdown */}
              <BotStatusBanner
                botName="ARES"
                isActive={status?.is_active || false}
                lastScan={status?.heartbeat?.last_scan_iso}
                scanInterval={status?.scan_interval_minutes || 30}
                openPositions={positions.length}
                todayPnl={(livePnL?.total_realized_pnl || 0) + (livePnL?.total_unrealized_pnl || 0)}
                todayTrades={closedPositions.filter(p => p.close_date?.startsWith(new Date().toISOString().split('T')[0])).length}
              />

              {/* ===== TRANSPARENCY SECTION - What Just Happened ===== */}
              {/* Last Scan Summary - THE MOST IMPORTANT: Shows what happened on last scan with full reasoning */}
              <LastScanSummary
                botName="ARES"
                lastScan={lastScanData}
                isLoading={scanActivityLoading}
                nextScanIn={undefined} // Could calculate from heartbeat
                scansToday={scansToday}
                tradesToday={tradesToday}
                onRefresh={() => mutateScanActivity()}
              />

              {/* Signal Conflict Tracker - Shows ML vs Oracle disagreements and who won */}
              {signalConflicts.length > 0 && (
                <SignalConflictTracker
                  botName="ARES"
                  conflicts={signalConflicts}
                  totalScansToday={scansToday}
                  mlWins={mlWins}
                  oracleWins={oracleWins}
                  isLoading={scanActivityLoading}
                />
              )}

              {/* Live Equity Curve with Intraday Tracking */}
              <LiveEquityCurve
                botName="ARES"
                startingCapital={status?.capital || 200000}
                historicalData={equityDataWithLive as EquityDataPoint[]}
                livePnL={livePnL as any}
                isLoading={livePnLLoading}
                onRefresh={() => mutateLivePnL()}
                lastUpdated={livePnL?.last_updated}
              />

              {/* ALL Open Positions with Timestamps */}
              <AllOpenPositions
                botName="ARES"
                positions={livePnL?.positions || []}
                underlyingPrice={livePnL?.underlying_price || marketData?.underlying_price}
                isLoading={livePnLLoading}
                lastUpdated={livePnL?.last_updated}
                onPositionClick={(pos) => setSelectedPosition(pos)}
              />

              {/* Risk Metrics Panel */}
              <RiskMetrics
                capitalTotal={status?.capital || 200000}
                capitalAtRisk={positions.reduce((sum, p) => sum + (p.max_loss || 0), 0)}
                openPositions={positions.length}
                maxPositionsAllowed={2}
                currentDrawdown={0}
                maxDrawdownToday={0}
                currentVix={marketData?.vix}
                vixRange={{ min: 15, max: 25 }}
              />

              {/* Why Not Trading - Shows skip reasons */}
              <WhyNotTrading
                skipReasons={skipReasons}
                isLoading={decisionsValidating}
                maxDisplay={5}
              />

              {/* Today's Summary Card - Shows what happened today at a glance */}
              <TodaySummaryCard
                tradedToday={status?.traded_today || false}
                openPosition={positions[0] || null}
                todayDecision={decisions.find(d => d.timestamp?.startsWith(new Date().toISOString().split('T')[0])) || null}
                marketData={marketData}
                gexContext={marketData?.gex_context}
                heartbeat={status?.heartbeat}
              />

              {/* Decision Tree - Shows Oracle vs ML decision path */}
              {decisions.length > 0 && (
                <DecisionTreeDisplay
                  decision={decisions.find(d => d.timestamp?.startsWith(new Date().toISOString().split('T')[0])) || decisions[0]}
                />
              )}

              {/* Strike Placement Diagram - Visual representation of position vs market */}
              {positions[0] && marketData?.underlying_price && (
                <StrikePlacementDiagram
                  position={positions[0]}
                  spotPrice={marketData.underlying_price}
                  expectedMove={marketData.expected_move || 0}
                  putWall={marketData.gex_context?.put_wall}
                  callWall={marketData.gex_context?.call_wall}
                />
              )}

              {/* Quick Actions Panel */}
              <QuickActionsPanel
                onSkipToday={async () => {
                  try {
                    await apiClient.skipARESToday()
                    toast.success('Skipped Today', 'ARES will not trade for the rest of today')
                    fetchData()
                  } catch (err) {
                    console.error('Failed to skip today:', err)
                    toast.error('Skip Failed', 'Failed to skip trading for today')
                  }
                }}
                onAdjustRisk={async (newRisk: number) => {
                  try {
                    await apiClient.updateARESConfig({ risk_per_trade_pct: newRisk })
                    toast.success('Risk Adjusted', `Risk per trade set to ${newRisk}%`)
                    mutateConfig()
                  } catch (err) {
                    console.error('Failed to adjust risk:', err)
                    toast.error('Adjustment Failed', 'Failed to adjust risk setting')
                  }
                }}
                onForceScan={runCycle}
                isScanning={runningCycle}
                currentRisk={config?.risk_per_trade_pct || 5}
                isTrading={status?.in_trading_window || false}
                hasOpenPosition={positions.length > 0}
              />

              {/* Today's Stats & Activity Row */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Today's Report Card */}
                <TodayReportCard
                  botName="ARES"
                  scansToday={status?.heartbeat?.scan_count_today || 0}
                  tradesToday={closedPositions.filter(p => p.close_date?.startsWith(new Date().toISOString().split('T')[0])).length}
                  winsToday={closedPositions.filter(p =>
                    p.close_date?.startsWith(new Date().toISOString().split('T')[0]) &&
                    (p.realized_pnl || 0) > 0
                  ).length}
                  lossesToday={closedPositions.filter(p =>
                    p.close_date?.startsWith(new Date().toISOString().split('T')[0]) &&
                    (p.realized_pnl || 0) < 0
                  ).length}
                  totalPnl={(livePnL?.total_realized_pnl || 0) + (livePnL?.total_unrealized_pnl || 0)}
                  unrealizedPnl={livePnL?.total_unrealized_pnl || 0}
                  realizedPnl={livePnL?.total_realized_pnl || 0}
                  bestTrade={Math.max(...closedPositions.filter(p =>
                    p.close_date?.startsWith(new Date().toISOString().split('T')[0])
                  ).map(p => p.realized_pnl || 0), 0) || undefined}
                  worstTrade={Math.min(...closedPositions.filter(p =>
                    p.close_date?.startsWith(new Date().toISOString().split('T')[0])
                  ).map(p => p.realized_pnl || 0), 0) || undefined}
                  openPositions={positions.length}
                  capitalAtRisk={positions.reduce((sum, p) => sum + (p.max_loss || 0), 0)}
                  capitalTotal={status?.capital || 200000}
                />

                {/* Activity Timeline */}
                <ActivityTimeline
                  activities={activityItems}
                  isLoading={decisionsValidating}
                  maxDisplay={8}
                />
              </div>

              {/* Today's Closed Iron Condors */}
              {closedPositions.filter(p => p.close_date?.startsWith(new Date().toISOString().split('T')[0])).length > 0 && (
                <div className="bg-[#0a0a0a] rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-white mb-4">Today&apos;s Closed Iron Condors</h3>
                  <div className="space-y-2">
                    {closedPositions
                      .filter(p => p.close_date?.startsWith(new Date().toISOString().split('T')[0]))
                      .map(pos => (
                        <div key={pos.position_id} className="flex justify-between items-center p-3 bg-[#111] rounded-lg border border-gray-800">
                          <div className="flex items-center gap-3">
                            <div className={`w-2 h-2 rounded-full ${(pos.realized_pnl ?? 0) >= 0 ? 'bg-[#00C805]' : 'bg-[#FF5000]'}`} />
                            <span className="text-white">
                              {pos.ticker || 'SPY'} IC {pos.put_short_strike}/{pos.call_short_strike}
                            </span>
                            <span className="text-gray-500 text-sm">{pos.contracts} contracts</span>
                          </div>
                          <div className="text-right">
                            <div className={`font-bold ${(pos.realized_pnl ?? 0) >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
                              {(pos.realized_pnl ?? 0) >= 0 ? '+' : ''}${(pos.realized_pnl ?? 0).toFixed(2)}
                            </div>
                            <div className="text-gray-500 text-xs">
                              {pos.close_date}
                            </div>
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ==================== OVERVIEW TAB ==================== */}
          {activeTab === 'overview' && (
            <>
              {/* Stats Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <DollarSign className="w-5 h-5 text-green-500" />
                    <span className="text-gray-400 text-sm">Total Capital</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{formatCurrency(spxStats.capital + spyStats.capital + totalPnl)}</p>
                  <p className="text-sm text-gray-500">SPX + SPY Combined</p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 className="w-5 h-5 text-purple-500" />
                    <span className="text-gray-400 text-sm">Total P&L</span>
                  </div>
                  <p className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatCurrency(totalPnl)}</p>
                  <p className="text-sm text-gray-500">{formatPercent((totalPnl / (spxStats.capital + spyStats.capital)) * 100)}</p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <Target className="w-5 h-5 text-blue-500" />
                    <span className="text-gray-400 text-sm">Win Rate</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{overallWinRate.toFixed(1)}%</p>
                  <p className="text-sm text-gray-500">{totalWins}W / {totalTrades - totalWins}L</p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="w-5 h-5 text-orange-500" />
                    <span className="text-gray-400 text-sm">Positions</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{positions.length} open</p>
                  <p className="text-sm text-gray-500">{totalTrades} total trades</p>
                </div>
              </div>

              {/* Enhanced Equity Curve with Event Markers */}
              <div className="mb-6">
                <EquityCurveChart
                  botFilter="ARES"
                  title="ARES Performance"
                  defaultDays={90}
                  height={350}
                  showDrawdown={true}
                />
              </div>

              {/* Scan Activity Feed - Shows EVERY scan with reasoning */}
              <div className="mb-6">
                <ScanActivityFeed
                  scans={scanActivity}
                  botName="ARES"
                  isLoading={scanActivityLoading}
                />
              </div>

              {/* GEX Context Panel */}
              <div className="bg-gray-800 rounded-xl p-6 border border-purple-700/50 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Crosshair className="w-5 h-5 text-purple-500" />
                    <h2 className="text-lg font-semibold text-white">Iron Condor Strike Zones</h2>
                    <span className="px-2 py-0.5 text-xs bg-purple-900/50 text-purple-400 rounded">GEX</span>
                  </div>
                </div>
                {marketData?.gex_context || marketData?.spx?.price ? (
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">SPX Price</p>
                      <p className="text-2xl font-bold text-white">${marketData?.spx?.price?.toLocaleString() || '--'}</p>
                    </div>
                    <div className="bg-green-900/20 border border-green-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Put Wall (Support)</p>
                      <p className="text-2xl font-bold text-green-400">${marketData?.gex_context?.put_wall?.toFixed(0) || '--'}</p>
                    </div>
                    <div className="bg-red-900/20 border border-red-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Call Wall (Resistance)</p>
                      <p className="text-2xl font-bold text-red-400">${marketData?.gex_context?.call_wall?.toFixed(0) || '--'}</p>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">GEX Regime</p>
                      <p className={`text-xl font-bold ${marketData?.gex_context?.regime === 'POSITIVE' ? 'text-green-400' : 'text-red-400'}`}>
                        {marketData?.gex_context?.regime || 'N/A'}
                      </p>
                    </div>
                    <div className="bg-purple-900/20 border border-purple-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Net GEX</p>
                      <p className="text-xl font-bold text-purple-400">
                        {marketData?.gex_context?.net_gex ? `${(marketData.gex_context.net_gex / 1e9).toFixed(2)}B` : '--'}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-4 text-gray-500">
                    <p>GEX data will appear after ARES runs a scan during market hours</p>
                  </div>
                )}

                {/* Condor visualization */}
                {marketData?.spx?.price && marketData?.spx?.expected_move && (
                  <div className="mt-4 pt-4 border-t border-gray-700">
                    <p className="text-xs text-gray-500 mb-2">Expected Range (±{config?.sd_multiplier || 0.5} SD)</p>
                    <div className="relative h-8 bg-gray-700 rounded-lg overflow-hidden">
                      <div className="absolute inset-0 bg-gradient-to-r from-red-600/30 via-green-600/30 to-red-600/30" />
                      {/* Put short strike zone */}
                      <div className="absolute left-[15%] top-0 bottom-0 w-[20%] bg-green-600/40 border-l-2 border-green-500" />
                      {/* Call short strike zone */}
                      <div className="absolute right-[15%] top-0 bottom-0 w-[20%] bg-green-600/40 border-r-2 border-green-500" />
                      {/* Center marker */}
                      <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-white" />
                    </div>
                    <div className="flex justify-between text-xs mt-1">
                      <span className="text-red-400">Put Wing</span>
                      <span className="text-green-400">Put Short</span>
                      <span className="text-white">SPX</span>
                      <span className="text-green-400">Call Short</span>
                      <span className="text-red-400">Call Wing</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Oracle/ML Predictions Panel */}
              {todayDecision && (
                <div className="bg-gray-800 rounded-xl p-6 border border-yellow-700/50 mb-6">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <Brain className="w-5 h-5 text-yellow-500" />
                      <h2 className="text-lg font-semibold text-white">Oracle Predictions</h2>
                      <span className="px-2 py-0.5 text-xs bg-yellow-900/50 text-yellow-400 rounded">ML</span>
                    </div>
                    <span className="text-xs text-gray-500">
                      {todayDecision.timestamp ? new Date(todayDecision.timestamp).toLocaleString('en-US', {
                        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                      }) : 'Latest'}
                    </span>
                  </div>

                  {todayDecision.oracle_advice ? (
                    <div className="space-y-4">
                      {/* Main Prediction */}
                      <div className="flex items-center justify-between bg-gray-900/50 rounded-lg p-4">
                        <div>
                          <span className="text-gray-400 text-sm">Oracle Recommendation</span>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`text-2xl font-bold ${
                              todayDecision.oracle_advice.advice === 'TRADE_FULL' ? 'text-green-400' :
                              todayDecision.oracle_advice.advice === 'TRADE_REDUCED' ? 'text-yellow-400' :
                              'text-red-400'
                            }`}>
                              {todayDecision.oracle_advice.advice?.replace(/_/g, ' ') || 'HOLD'}
                            </span>
                          </div>
                        </div>
                        <div className="text-right">
                          <span className="text-gray-400 text-sm">Win Probability</span>
                          <div className={`text-2xl font-bold ${
                            (todayDecision.oracle_advice.win_probability || 0) >= 0.55 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {((todayDecision.oracle_advice.win_probability || 0) * 100).toFixed(0)}%
                          </div>
                        </div>
                      </div>

                      {/* Metrics Grid */}
                      <div className="grid grid-cols-3 gap-4">
                        <div className="bg-gray-900/30 rounded-lg p-3 text-center">
                          <p className="text-gray-400 text-xs mb-1">Confidence</p>
                          <p className="text-xl font-bold text-white">
                            {((todayDecision.oracle_advice.confidence || 0) * 100).toFixed(0)}%
                          </p>
                        </div>
                        <div className="bg-gray-900/30 rounded-lg p-3 text-center">
                          <p className="text-gray-400 text-xs mb-1">Suggested Risk</p>
                          <p className="text-xl font-bold text-yellow-400">
                            {(todayDecision.oracle_advice.suggested_risk_pct || 0).toFixed(1)}%
                          </p>
                        </div>
                        <div className="bg-gray-900/30 rounded-lg p-3 text-center">
                          <p className="text-gray-400 text-xs mb-1">SD Multiplier</p>
                          <p className="text-xl font-bold text-blue-400">
                            {(todayDecision.oracle_advice.suggested_sd_multiplier || 0).toFixed(2)}x
                          </p>
                        </div>
                      </div>

                      {/* Top Factors */}
                      {todayDecision.oracle_advice.top_factors && todayDecision.oracle_advice.top_factors.length > 0 && (
                        <div className="bg-gray-900/30 rounded-lg p-3">
                          <p className="text-gray-400 text-xs mb-2">TOP DECISION FACTORS</p>
                          <div className="space-y-1">
                            {todayDecision.oracle_advice.top_factors.slice(0, 5).map(([factor, value], i) => (
                              <div key={i} className="flex items-center justify-between text-sm">
                                <span className="text-gray-300">{factor}</span>
                                <span className={`font-mono ${Number(value) > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {typeof value === 'number' ? value.toFixed(3) : value}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Reasoning */}
                      {todayDecision.oracle_advice.reasoning && (
                        <div className="bg-gray-900/30 rounded-lg p-3">
                          <p className="text-gray-400 text-xs mb-1">ORACLE REASONING</p>
                          <p className="text-gray-300 text-sm">{todayDecision.oracle_advice.reasoning}</p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-gray-500">
                      <Brain className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p>Oracle predictions will appear after the next scan</p>
                      <p className="text-xs text-gray-600 mt-1">Scans run during market hours</p>
                    </div>
                  )}
                </div>
              )}

              {/* Two Column: SPX Summary | SPY Summary */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* SPX Summary */}
                <div className="bg-gradient-to-br from-purple-900/30 to-gray-800 rounded-lg border border-purple-700/50 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-lg font-bold text-purple-300 flex items-center gap-2">
                      <Play className="w-5 h-5" /> SPX Performance
                    </h3>
                    <span className="px-2 py-1 rounded text-xs bg-purple-900 text-purple-300">PAPER</span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">P&L</p>
                      <p className={`font-bold ${spxStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatCurrency(spxStats.totalPnl)}</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Win Rate</p>
                      <p className="text-white font-bold">{spxStats.winRate.toFixed(1)}%</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Trades</p>
                      <p className="text-white font-bold">{spxStats.totalTrades}</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Open</p>
                      <p className="text-white font-bold">{spxOpenPositions.length}</p>
                    </div>
                  </div>
                </div>

                {/* SPY Summary */}
                <div className="bg-gradient-to-br from-blue-900/30 to-gray-800 rounded-lg border border-blue-700/50 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-lg font-bold text-blue-300 flex items-center gap-2">
                      <Server className="w-5 h-5" /> SPY Performance
                    </h3>
                    <span className={`px-2 py-1 rounded text-xs ${connectionBadge.bg} ${connectionBadge.text}`}>
                      {connectionBadge.label}
                    </span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">P&L</p>
                      <p className={`font-bold ${spyStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatCurrency(spyStats.totalPnl)}</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Win Rate</p>
                      <p className="text-white font-bold">{spyStats.winRate.toFixed(1)}%</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Trades</p>
                      <p className="text-white font-bold">{spyStats.totalTrades}</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Open</p>
                      <p className="text-white font-bold">{spyOpenPositions.length}</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Recent Decisions Summary */}
              <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    <FileText className="w-5 h-5 text-red-400" /> Recent Decisions
                  </h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        const csv = [
                          ['Time', 'Type', 'What', 'Why'].join(','),
                          ...decisions.map(d => [
                            new Date(d.timestamp).toLocaleString(),
                            d.decision_type?.replace(/_/g, ' '),
                            `"${(d.what || '').replace(/"/g, '""')}"`,
                            `"${(d.why || '').replace(/"/g, '""')}"`
                          ].join(','))
                        ].join('\n')
                        const blob = new Blob([csv], { type: 'text/csv' })
                        const url = URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url
                        a.download = `ares-decisions-${new Date().toISOString().split('T')[0]}.csv`
                        a.click()
                        URL.revokeObjectURL(url)
                      }}
                      className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded"
                    >
                      📥 Export
                    </button>
                    <button onClick={() => setActiveTab('activity')} className="text-sm text-red-400 hover:underline">View All →</button>
                  </div>
                </div>
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {decisions.slice(0, 8).map((d) => (
                    <div key={d.id} className="bg-gray-900/50 rounded p-3 border border-gray-700/50">
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs ${getDecisionTypeBadge(d.decision_type).bg} ${getDecisionTypeBadge(d.decision_type).text}`}>
                            {d.decision_type?.replace(/_/g, ' ')}
                          </span>
                          <span className="text-xs text-gray-500">{new Date(d.timestamp).toLocaleTimeString()}</span>
                        </div>
                      </div>
                      {/* WHAT - Full text, no truncation */}
                      <p className="text-gray-200 text-sm mb-1">{d.what}</p>
                      {/* WHY - Show the reason */}
                      {d.why && (
                        <p className="text-gray-400 text-xs italic">
                          <span className="text-yellow-500 font-medium">Why:</span> {d.why}
                        </p>
                      )}
                    </div>
                  ))}
                  {decisions.length === 0 && <p className="text-center text-gray-500 py-4">No decisions yet</p>}
                </div>
              </div>
            </>
          )}

          {/* ==================== ACTIVITY TAB - Unified scan activity and decisions ==================== */}
          {activeTab === 'activity' && (
            <div className="space-y-6">
              {/* Equity Curve - FIRST (at top) */}
              <EquityCurveChart
                botFilter="ARES"
                title="ARES Performance"
                defaultDays={30}
                height={280}
                showDrawdown={true}
              />

              {/* Scan Activity Feed - Enhanced with MAXIMUM detail */}
              <BotCard
                title="Scan Activity"
                subtitle="Full transparency: market context, signals, checks, and decisions"
                icon={<Activity className="w-5 h-5" />}
                botName="ARES"
                freshness={{
                  lastUpdated: status?.heartbeat?.last_scan_iso || null,
                  onRefresh: () => mutateScanActivity(),
                  isRefreshing: scanActivityLoading
                }}
              >
                <div className="space-y-3 max-h-[800px] overflow-y-auto">
                  {scanActivity && scanActivity.length > 0 ? (
                    scanActivity.slice(0, 30).map((scan: any, index: number) => {
                      // Transform scan data to ScanData format for ScanDetailCard
                      const scanData: ScanData = {
                        id: scan.id || index,
                        timestamp: scan.timestamp,
                        scan_number: scan.scan_number,
                        scan_duration_ms: scan.scan_duration_ms,
                        outcome: scan.trade_executed ? 'TRADED' : scan.error ? 'ERROR' : 'NO_TRADE',
                        market_context: {
                          spy_price: scan.spy_price || scan.spot_price,
                          spx_price: scan.spx_price,
                          vix: scan.vix,
                          gex_regime: scan.gex_regime || scan.regime,
                          put_wall: scan.put_wall,
                          call_wall: scan.call_wall,
                          gamma_flip: scan.gamma_flip,
                        },
                        oracle_signal: scan.oracle_advice ? {
                          signal: scan.oracle_advice.advice || scan.oracle_advice,
                          confidence: scan.oracle_advice.confidence || scan.signal_confidence || 0,
                          win_probability: scan.oracle_advice.win_probability || scan.signal_win_probability,
                          reasoning: scan.oracle_advice.reasoning,
                        } : undefined,
                        ml_signal: scan.ml_signal ? {
                          signal: scan.ml_signal.signal || scan.ml_signal,
                          confidence: scan.ml_signal.confidence || 0,
                        } : undefined,
                        winning_signal: scan.signal_source?.includes('Oracle') ? 'oracle' : scan.signal_source?.includes('ML') ? 'ml' : 'aligned',
                        override_occurred: scan.override_occurred,
                        override_reason: scan.override_reason,
                        checks: scan.checks || scan.validation_checks,
                        decision_type: scan.decision_type,
                        primary_reason: scan.skip_reason || scan.why || scan.decision_reason,
                        all_reasons: scan.all_reasons || (scan.skip_reason ? [scan.skip_reason] : undefined),
                        trade: scan.trade_executed ? {
                          spread_type: scan.spread_type,
                          long_strike: scan.long_strike,
                          short_strike: scan.short_strike,
                          expiration: scan.expiration,
                          contracts: scan.contracts,
                          entry_price: scan.entry_price,
                        } : undefined,
                        timestamps: {
                          scan_started: scan.scan_started_at,
                          data_fetched: scan.data_fetched_at,
                          analysis_complete: scan.analysis_complete_at,
                          decision_logged: scan.timestamp,
                        },
                        unlock_conditions: scan.unlock_conditions,
                      }
                      return (
                        <ScanDetailCard
                          key={scan.id || index}
                          scan={scanData}
                          botName="ARES"
                          defaultExpanded={index === 0}
                        />
                      )
                    })
                  ) : scanActivityLoading ? (
                    <LoadingState message="Loading scan activity..." />
                  ) : (
                    <EmptyState
                      icon={<Activity className="w-8 h-8" />}
                      title="No Scans Yet"
                      description="Scan activity will populate when ARES runs during market hours."
                    />
                  )}
                </div>
              </BotCard>

              {/* Decision Log - Quick summary view */}
              <BotCard
                title="Decision Log"
                subtitle="Quick summary of all trading decisions"
                icon={<FileText className="w-5 h-5" />}
                botName="ARES"
              >
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {decisions.length > 0 ? (
                    decisions.slice(0, 20).map((decision) => {
                      const badge = getDecisionTypeBadge(decision.decision_type)
                      return (
                        <div
                          key={decision.id}
                          className="flex items-center justify-between p-2 bg-gray-900/50 rounded border border-gray-700/50 hover:border-amber-700/50 transition-colors"
                        >
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.bg} ${badge.text}`}>
                              {decision.decision_type?.replace(/_/g, ' ')}
                            </span>
                            <span className={`text-sm ${getActionColor(decision.action)}`}>
                              {decision.action}
                            </span>
                            {decision.override_occurred && (
                              <span className="px-1.5 py-0.5 rounded text-xs bg-amber-500/30 text-amber-400">OVR</span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            {decision.actual_pnl !== undefined && decision.actual_pnl !== 0 && (
                              <PnLDisplay value={decision.actual_pnl} size="sm" />
                            )}
                            <span className="text-xs text-gray-500">
                              {new Date(decision.timestamp).toLocaleString('en-US', {
                                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                              })}
                            </span>
                          </div>
                        </div>
                      )
                    })
                  ) : (
                    <EmptyState
                      icon={<FileText className="w-8 h-8" />}
                      title="No Decisions Yet"
                      description="Decision log will populate when ARES runs scans during market hours."
                    />
                  )}
                </div>
              </BotCard>
            </div>
          )}

          {/* ==================== HISTORY TAB - Closed positions ==================== */}
          {activeTab === 'history' && (
            <BotCard
              title="Trade History"
              subtitle="All closed Iron Condor positions"
              icon={<History className="w-5 h-5" />}
              botName="ARES"
            >
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-900">
                    <tr>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Entry Date</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Exit Date</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Duration</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Ticker</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Strikes</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Credit</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Close</th>
                      <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">VIX</th>
                      <th className="px-3 py-3 text-right text-xs text-gray-400 uppercase">P&L</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-700">
                    {closedPositions
                      .sort((a, b) => new Date(b.close_date || 0).getTime() - new Date(a.close_date || 0).getTime())
                      .map((pos) => (
                        <tr key={pos.position_id} className="hover:bg-gray-700/50">
                          <td className="px-3 py-3 text-sm text-gray-300">
                            {pos.open_date ? (
                              <div className="flex flex-col">
                                <span>{new Date(pos.open_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                                <span className="text-xs text-gray-500">{new Date(pos.open_date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}</span>
                              </div>
                            ) : '--'}
                          </td>
                          <td className="px-3 py-3 text-sm text-gray-300">
                            {pos.close_date ? (
                              <div className="flex flex-col">
                                <span>{new Date(pos.close_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                                <span className="text-xs text-gray-500">{new Date(pos.close_date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}</span>
                              </div>
                            ) : '--'}
                          </td>
                          <td className="px-3 py-3 text-sm">
                            <TimeInPosition entryTime={pos.open_date} exitTime={pos.close_date} showLabel={false} />
                          </td>
                          <td className="px-3 py-3">
                            <span className={`px-2 py-1 rounded text-xs font-medium ${
                              pos.ticker === 'SPX' ? 'bg-purple-900/50 text-purple-400' : 'bg-blue-900/50 text-blue-400'
                            }`}>
                              {pos.ticker || 'SPX'}
                            </span>
                          </td>
                          <td className="px-3 py-3 text-xs text-gray-300 font-mono">
                            <span className="text-green-400">{pos.put_long_strike}/{pos.put_short_strike}</span>
                            <span className="text-gray-500"> | </span>
                            <span className="text-red-400">{pos.call_short_strike}/{pos.call_long_strike}</span>
                          </td>
                          <td className="px-3 py-3 text-sm text-green-400">${pos.total_credit?.toFixed(2) || '0.00'}</td>
                          <td className="px-3 py-3 text-sm text-gray-300">${pos.close_price?.toFixed(2) || '0.00'}</td>
                          <td className="px-3 py-3 text-sm text-yellow-400">{pos.vix_at_entry?.toFixed(1) || '--'}</td>
                          <td className="px-3 py-3 text-right">
                            <PnLDisplay value={pos.realized_pnl || 0} size="sm" />
                          </td>
                        </tr>
                      ))}
                    {closedPositions.length === 0 && (
                      <tr>
                        <td colSpan={9} className="px-4 py-8">
                          <EmptyState
                            icon={<History className="w-8 h-8" />}
                            title="No Trade History"
                            description="Closed trades will appear here after ARES completes Iron Condor positions."
                          />
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* Summary Stats */}
              {closedPositions.length > 0 && (
                <div className="mt-4 pt-4 border-t border-gray-700 grid grid-cols-4 gap-4">
                  <StatCard
                    label="Total Trades"
                    value={closedPositions.length}
                    color="gray"
                  />
                  <StatCard
                    label="Win Rate"
                    value={`${((closedPositions.filter(p => (p.realized_pnl || 0) > 0).length / closedPositions.length) * 100).toFixed(0)}%`}
                    color={closedPositions.filter(p => (p.realized_pnl || 0) > 0).length / closedPositions.length >= 0.5 ? 'green' : 'red'}
                  />
                  <StatCard
                    label="Total P&L"
                    value={formatCurrency(closedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0))}
                    color={closedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0) >= 0 ? 'green' : 'red'}
                  />
                  <StatCard
                    label="Avg Trade"
                    value={formatCurrency(closedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0) / closedPositions.length)}
                    color={closedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0) >= 0 ? 'green' : 'red'}
                  />
                </div>
              )}
            </BotCard>
          )}

          {/* ==================== CONFIG TAB ==================== */}
          {activeTab === 'config' && (
            <div className="space-y-6">
              {/* Preset Performance Visualization */}
              {strategyPresets && strategyPresets.length > 0 && (
                <PresetPerformanceChart
                  presets={strategyPresets}
                  activePreset={activeStrategyPreset}
                  currentVix={marketData?.vix}
                />
              )}

              {/* Strategy Preset Selector */}
              <div className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 rounded-xl border border-purple-700/50 p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Brain className="w-5 h-5 text-purple-400" />
                  <h2 className="text-lg font-semibold text-white">Strategy Preset</h2>
                  <span className="ml-auto text-xs text-gray-400">Based on 2022-2024 Backtests</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {strategyPresets.map((preset) => (
                    <button
                      key={preset.id}
                      onClick={() => handleStrategyChange(preset.id)}
                      disabled={changingStrategy || preset.is_active}
                      className={`relative p-4 rounded-lg border-2 transition-all text-left ${
                        preset.is_active
                          ? 'border-green-500 bg-green-900/30'
                          : 'border-gray-600 bg-gray-800/50 hover:border-purple-500 hover:bg-purple-900/20'
                      } ${changingStrategy ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      {preset.is_active && (
                        <div className="absolute top-2 right-2">
                          <span className="px-2 py-0.5 bg-green-900/50 text-green-400 rounded text-xs font-medium">ACTIVE</span>
                        </div>
                      )}
                      <h3 className={`font-semibold mb-1 ${preset.is_active ? 'text-green-400' : 'text-white'}`}>
                        {preset.name}
                      </h3>
                      <p className="text-gray-400 text-sm mb-3">{preset.description}</p>

                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-gray-500">VIX Skip:</span>
                          <span className={`ml-1 font-mono ${preset.vix_hard_skip > 0 ? 'text-yellow-400' : 'text-gray-500'}`}>
                            {preset.vix_hard_skip > 0 ? `>${preset.vix_hard_skip}` : 'Off'}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-500">SD:</span>
                          <span className="ml-1 font-mono text-white">{preset.sd_multiplier}</span>
                        </div>
                        <div>
                          <span className="text-gray-500">Sharpe:</span>
                          <span className="ml-1 font-mono text-blue-400">{preset.backtest_sharpe.toFixed(2)}</span>
                        </div>
                        <div>
                          <span className="text-gray-500">Win Rate:</span>
                          <span className="ml-1 font-mono text-green-400">{preset.backtest_win_rate.toFixed(1)}%</span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>

                {/* Current VIX Status */}
                {marketData?.vix && (
                  <div className="mt-4 pt-4 border-t border-gray-700 flex items-center gap-4">
                    <span className="text-gray-400 text-sm">Current VIX:</span>
                    <span className={`font-mono text-lg font-bold ${
                      marketData.vix > 32 ? 'text-red-400' :
                      marketData.vix > 25 ? 'text-yellow-400' :
                      'text-green-400'
                    }`}>
                      {marketData.vix.toFixed(2)}
                    </span>
                    {config?.vix_hard_skip && config.vix_hard_skip > 0 && (
                      <span className={`text-sm ${marketData.vix > config.vix_hard_skip ? 'text-red-400' : 'text-gray-500'}`}>
                        {marketData.vix > config.vix_hard_skip
                          ? `⚠️ Above skip threshold (${config.vix_hard_skip}) - will skip trades`
                          : `Below skip threshold (${config.vix_hard_skip})`
                        }
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Settings Details */}
              <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
                <div className="flex items-center gap-2 mb-6">
                  <Settings className="w-5 h-5 text-gray-400" />
                  <h2 className="text-lg font-semibold text-white">ARES Configuration</h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* SPX Config */}
                  <div className="bg-purple-900/20 border border-purple-700/30 rounded-lg p-4">
                  <h3 className="text-purple-300 font-semibold mb-4">SPX Settings</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between"><span className="text-gray-400">Spread Width:</span><span className="text-white font-mono">${config?.spread_width || 10}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">SD Multiplier:</span><span className="text-white font-mono">{config?.sd_multiplier || 0.5}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Risk per Trade:</span><span className="text-white font-mono">{config?.risk_per_trade_pct || 10}%</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Min Credit:</span><span className="text-white font-mono">${config?.min_credit || 0.50}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Profit Target:</span><span className="text-white font-mono">{config?.profit_target_pct || 50}%</span></div>
                  </div>
                </div>

                {/* SPY Config */}
                <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-4">
                  <h3 className="text-blue-300 font-semibold mb-4">SPY Settings</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between"><span className="text-gray-400">Spread Width:</span><span className="text-white font-mono">${config?.spread_width_spy || 2}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">SD Multiplier:</span><span className="text-white font-mono">{config?.sd_multiplier_spy || config?.sd_multiplier || 0.5}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Tradier Mode:</span><span className="text-white font-mono">{tradierStatus?.mode || 'sandbox'}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Account:</span><span className="text-white font-mono">{tradierStatus?.account?.account_number || 'Not Connected'}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Buying Power:</span><span className="text-white font-mono">{tradierStatus?.account?.buying_power ? formatCurrency(tradierStatus.account.buying_power) : '--'}</span></div>
                  </div>
                </div>

                {/* General Config */}
                <div className="md:col-span-2 bg-gray-700/30 border border-gray-600 rounded-lg p-4">
                  <h3 className="text-gray-300 font-semibold mb-4">General Settings</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="flex flex-col"><span className="text-gray-400 text-sm">Entry Window:</span><span className="text-white font-mono">{config?.entry_window || '9:35 AM - 2:55 PM CT'}</span></div>
                    <div className="flex flex-col"><span className="text-gray-400 text-sm">Scan Interval:</span><span className="text-white font-mono">{status?.scan_interval_minutes || 5} min</span></div>
                    <div className="flex flex-col"><span className="text-gray-400 text-sm">Mode:</span><span className="text-white font-mono">{status?.mode || 'paper'}</span></div>
                    <div className="flex flex-col"><span className="text-gray-400 text-sm">Monthly Target:</span><span className="text-green-400 font-mono">10%</span></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          )}

          {/* Footer */}
          <div className="mt-6 text-center text-sm text-gray-500">
            Auto-refresh every 30 seconds • Cached across pages
          </div>
        </div>
      </main>

      {/* Position Detail Modal */}
      <PositionDetailModal
        isOpen={selectedPosition !== null}
        onClose={() => setSelectedPosition(null)}
        position={selectedPosition ? {
          ...selectedPosition,
          position_id: selectedPosition.position_id || '',
          spread_type: 'IRON_CONDOR',
          long_strike: selectedPosition.put_long_strike || 0,
          short_strike: selectedPosition.put_short_strike || 0,
          expiration: selectedPosition.expiration || '',
          contracts: selectedPosition.contracts || 1,
          entry_price: selectedPosition.credit_received || selectedPosition.total_credit || 0,
          status: selectedPosition.status || 'open'
        } : {
          position_id: '',
          spread_type: 'IRON_CONDOR',
          long_strike: 0,
          short_strike: 0,
          expiration: '',
          contracts: 0,
          entry_price: 0,
          status: ''
        }}
        underlyingPrice={livePnL?.underlying_price || marketData?.underlying_price}
        botType="ARES"
      />

    </div>
  )
}
