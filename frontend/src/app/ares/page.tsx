'use client'

import React, { useState, useMemo } from 'react'
import { Sword, TrendingUp, TrendingDown, Activity, DollarSign, Target, RefreshCw, BarChart3, ChevronDown, ChevronUp, ChevronRight, Server, Play, AlertTriangle, Clock, Zap, Brain, Shield, Crosshair, TrendingUp as TrendUp, FileText, ListChecks, Settings, Wallet } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, ReferenceLine } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
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
import LivePortfolio, { EquityDataPoint, LivePnLData } from '@/components/trader/LivePortfolio'
import OpenPositionsLive from '@/components/trader/OpenPositionsLive'
import {
  BotStatusBanner,
  WhyNotTrading,
  TodayReportCard,
  ActivityTimeline,
  ExitNotificationContainer,
  RiskMetrics,
  PerformanceComparison,
  PositionDetailModal
} from '@/components/trader'

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
  account: {
    account_number?: string
    type?: string
    cash?: number
    equity?: number
    buying_power?: number
  }
  positions: Array<{ symbol: string; quantity: number; cost_basis: number; date_acquired?: string }>
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
      <div className="bg-gradient-to-r from-green-900/30 to-gray-800 rounded-xl p-5 border border-green-700/50">
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
              {gexContext && (
                <div className="text-xs text-gray-400">
                  Put wall ${gexContext.put_wall?.toFixed(0)} ({((marketData?.underlying_price || 0) - gexContext.put_wall).toFixed(0)} pts buffer)
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
    <div className="bg-gradient-to-r from-yellow-900/20 to-gray-800 rounded-xl p-5 border border-yellow-700/30">
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
  currentRisk: number
  isTrading: boolean
  hasOpenPosition: boolean
}

function QuickActionsPanel({ onSkipToday, onAdjustRisk, currentRisk, isTrading, hasOpenPosition }: QuickActionsProps) {
  const [riskValue, setRiskValue] = useState(currentRisk)
  const [showConfirm, setShowConfirm] = useState<'skip' | 'risk' | null>(null)

  return (
    <div className="bg-gray-800/50 rounded-xl p-5 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-5 h-5 text-yellow-400" />
        <h3 className="text-lg font-semibold text-white">Quick Actions</h3>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Skip Today */}
        <div className="relative">
          {showConfirm === 'skip' ? (
            <div className="flex flex-col gap-2">
              <span className="text-xs text-gray-400">Skip trading today?</span>
              <div className="flex gap-2">
                <button
                  onClick={() => { onSkipToday(); setShowConfirm(null) }}
                  className="flex-1 px-2 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-500"
                >
                  Yes
                </button>
                <button
                  onClick={() => setShowConfirm(null)}
                  className="flex-1 px-2 py-1 bg-gray-600 text-white text-xs rounded hover:bg-gray-500"
                >
                  No
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowConfirm('skip')}
              disabled={hasOpenPosition}
              className="w-full px-4 py-3 bg-yellow-900/30 text-yellow-400 rounded-lg hover:bg-yellow-900/50 disabled:opacity-50 disabled:cursor-not-allowed flex flex-col items-center gap-1"
            >
              <AlertTriangle className="w-5 h-5" />
              <span className="text-xs">Skip Today</span>
            </button>
          )}
        </div>

        {/* Adjust Risk */}
        <div className="relative">
          {showConfirm === 'risk' ? (
            <div className="flex flex-col gap-2">
              <input
                type="range"
                min="1"
                max="15"
                value={riskValue}
                onChange={(e) => setRiskValue(Number(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-400">
                <span>{riskValue}%</span>
                <button
                  onClick={() => { onAdjustRisk(riskValue); setShowConfirm(null) }}
                  className="px-2 py-0.5 bg-blue-600 text-white rounded"
                >
                  Apply
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowConfirm('risk')}
              className="w-full px-4 py-3 bg-blue-900/30 text-blue-400 rounded-lg hover:bg-blue-900/50 flex flex-col items-center gap-1"
            >
              <Target className="w-5 h-5" />
              <span className="text-xs">Risk: {currentRisk}%</span>
            </button>
          )}
        </div>

        {/* Force Run */}
        <button
          disabled={isTrading}
          className="px-4 py-3 bg-green-900/30 text-green-400 rounded-lg hover:bg-green-900/50 disabled:opacity-50 flex flex-col items-center gap-1"
        >
          <Play className="w-5 h-5" />
          <span className="text-xs">Force Scan</span>
        </button>

        {/* Status */}
        <div className="px-4 py-3 bg-gray-900/50 rounded-lg flex flex-col items-center gap-1">
          <div className={`w-5 h-5 rounded-full ${isTrading ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
          <span className="text-xs text-gray-400">{isTrading ? 'Active' : 'Idle'}</span>
        </div>
      </div>

      {/* Current Config Summary */}
      <div className="mt-4 pt-3 border-t border-gray-700 flex flex-wrap gap-4 text-xs text-gray-500">
        <span>Risk: <span className="text-white">{currentRisk}%</span></span>
        <span>SD: <span className="text-white">Oracle Dynamic</span></span>
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
  const livePnL = livePnLRes?.data as LivePnLData | null
  const strategyPresets = (strategyPresetsRes?.data?.presets || []) as StrategyPreset[]
  const activeStrategyPreset = strategyPresetsRes?.data?.active_preset || 'moderate'

  const loading = statusLoading && !status
  const error = statusError?.message || null
  const isRefreshing = statusValidating || perfValidating || equityValidating || posValidating || marketValidating || tradierValidating || configValidating || decisionsValidating

  // UI State - default to portfolio for Robinhood-style view
  const [activeTab, setActiveTab] = useState<'portfolio' | 'overview' | 'spx' | 'spy' | 'decisions' | 'config'>('portfolio')
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
  const [exitNotifications, setExitNotifications] = useState<any[]>([])

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
                  d.why?.toLowerCase().includes('risk') ? 'risk' as const :
                  d.why?.toLowerCase().includes('vix') ? 'market' as const : 'other' as const,
        details: {
          oracle_advice: d.oracle_prediction?.advice,
          oracle_confidence: d.oracle_prediction?.confidence,
          oracle_win_prob: d.oracle_prediction?.win_probability,
          vix: d.market_context?.vix,
          spot_price: d.market_context?.underlying_price,
          gex_regime: d.market_context?.gex_regime
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

  const fetchData = () => { mutateStatus(); mutatePerf(); mutateEquity(); mutatePositions(); mutateMarket(); mutateTradier(); mutateConfig(); mutateDecisions() }

  const runCycle = async () => {
    setRunningCycle(true)
    try {
      await apiClient.runARESCycle()
      fetchData()
    } catch (err) {
      console.error('Failed to run cycle:', err)
    } finally {
      setRunningCycle(false)
    }
  }

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
  const tradierConnected = tradierStatus?.success && tradierStatus?.account?.account_number

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
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Sword className="w-8 h-8 text-red-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">ARES</h1>
                <p className="text-gray-400 text-sm">0DTE Iron Condor Strategy</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${status?.in_trading_window ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'}`}>
                {status?.in_trading_window ? 'MARKET OPEN' : 'MARKET CLOSED'}
              </span>
              <button onClick={fetchData} disabled={isRefreshing} className="p-2 bg-gray-800 rounded-lg hover:bg-gray-700 disabled:opacity-50">
                <RefreshCw className={`w-5 h-5 text-gray-400 ${isRefreshing ? 'animate-spin' : ''}`} />
              </button>
              <button onClick={runCycle} disabled={runningCycle} className="flex items-center gap-2 px-4 py-2 bg-red-600 rounded-lg hover:bg-red-500 disabled:opacity-50">
                <Play className={`w-4 h-4 ${runningCycle ? 'animate-pulse' : ''}`} />
                <span className="text-white text-sm">Run Cycle</span>
              </button>
            </div>
          </div>

          {error && <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-300">{error}</div>}

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

          {/* Tabs */}
          <div className="flex gap-2 mb-6 flex-wrap">
            {(['portfolio', 'overview', 'spx', 'spy', 'decisions', 'config'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-lg capitalize transition flex items-center gap-2 ${activeTab === tab ? 'bg-red-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
              >
                {tab === 'portfolio' && <Wallet className="w-4 h-4" />}
                {tab === 'spx' ? 'SPX' : tab === 'spy' ? 'SPY' : tab}
              </button>
            ))}
          </div>

          {/* ==================== PORTFOLIO TAB - Robinhood-style ==================== */}
          {activeTab === 'portfolio' && (
            <div className="space-y-6">
              {/* Live Portfolio Component */}
              <LivePortfolio
                botName="ARES"
                totalValue={(status?.capital || 200000) + (livePnL?.net_pnl || status?.total_pnl || 0)}
                startingCapital={status?.capital || 200000}
                livePnL={livePnL}
                equityData={equityDataWithLive as EquityDataPoint[]}
                isLoading={livePnLLoading}
                onRefresh={() => mutateLivePnL()}
                lastUpdated={livePnL?.last_updated}
              />

              {/* Open Positions with Live P&L */}
              <OpenPositionsLive
                botName="ARES"
                positions={livePnL?.positions || []}
                underlyingPrice={livePnL?.underlying_price || marketData?.underlying_price}
                isLoading={livePnLLoading}
                onPositionClick={(pos) => setSelectedPosition(pos)}
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
                    fetchData()
                  } catch (err) {
                    console.error('Failed to skip today:', err)
                  }
                }}
                onAdjustRisk={async (newRisk: number) => {
                  try {
                    await apiClient.updateARESConfig({ risk_per_trade_pct: newRisk })
                    mutateConfig()
                  } catch (err) {
                    console.error('Failed to adjust risk:', err)
                  }
                }}
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
                    <span className={`px-2 py-1 rounded text-xs ${tradierConnected ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'}`}>
                      {tradierConnected ? 'TRADIER' : 'DISCONNECTED'}
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
                    <button onClick={() => setActiveTab('decisions')} className="text-sm text-red-400 hover:underline">View All →</button>
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

          {/* ==================== SPX TAB - Robinhood Style ==================== */}
          {activeTab === 'spx' && (
            <div className="space-y-6">
              {/* Portfolio Header - Robinhood Style */}
              <div className="bg-[#0a0a0a] rounded-lg p-6">
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400 text-sm">SPX Iron Condors</span>
                      <span className="px-2 py-1 rounded text-xs bg-purple-900 text-purple-300">PAPER</span>
                    </div>
                  </div>

                  {/* Big Portfolio Value */}
                  <div className="text-4xl font-bold text-white mb-2">
                    ${(spxStats.capital + spxStats.totalPnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>

                  {/* P&L Change */}
                  <div className="flex items-center gap-2">
                    {spxStats.totalPnl >= 0 ? (
                      <TrendingUp className="w-4 h-4 text-[#00C805]" />
                    ) : (
                      <TrendingDown className="w-4 h-4 text-[#FF5000]" />
                    )}
                    <span className={`font-semibold ${spxStats.totalPnl >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
                      {spxStats.totalPnl >= 0 ? '+' : ''}${spxStats.totalPnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      {' '}({spxStats.totalPnl >= 0 ? '+' : ''}{((spxStats.totalPnl / spxStats.capital) * 100).toFixed(2)}%)
                    </span>
                    <span className="text-gray-500 text-sm">Total</span>
                  </div>

                  {/* Stats Row */}
                  <div className="flex gap-4 mt-2 text-sm">
                    <span className="text-gray-500">
                      Win Rate: <span className="text-white font-bold">{spxStats.winRate.toFixed(1)}%</span>
                    </span>
                    <span className="text-gray-500">
                      Trades: <span className="text-white font-bold">{spxStats.totalTrades}</span>
                    </span>
                    <span className="text-gray-500">
                      Avg Trade: <span className={spxStats.avgTrade >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}>${spxStats.avgTrade.toFixed(2)}</span>
                    </span>
                    <span className="text-gray-500">
                      Max DD: <span className="text-[#FF5000]">${spxStats.maxDrawdown.toFixed(2)}</span>
                    </span>
                  </div>
                </div>

                {/* Equity Chart - Robinhood Style */}
                <div className="h-64 mb-4">
                  {filteredSpxEquity.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={filteredSpxEquity} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                        <defs>
                          <linearGradient id="spxGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={spxChartColor} stopOpacity={0.3} />
                            <stop offset="100%" stopColor={spxChartColor} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="date" hide axisLine={false} tickLine={false} />
                        <YAxis hide domain={['dataMin - 1000', 'dataMax + 1000']} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: '8px', color: '#fff' }}
                          formatter={(value: number) => [`$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Equity']}
                          labelFormatter={(label) => label}
                        />
                        <ReferenceLine y={spxStats.capital} stroke="#333" strokeDasharray="3 3" />
                        <Line type="monotone" dataKey="equity" stroke={spxChartColor} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: spxChartColor }} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                      <div className="text-center">
                        <p>No equity data available</p>
                        <p className="text-xs text-gray-600 mt-1">Chart will populate as trades are closed</p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Period Toggles - Robinhood Style */}
                <div className="flex justify-center gap-2">
                  {periods.map((period) => (
                    <button
                      key={period}
                      onClick={() => setSpxPeriod(period)}
                      className={`px-4 py-2 text-sm font-medium rounded-full transition-all ${
                        spxPeriod === period
                          ? 'bg-[#A855F7] text-black'
                          : 'text-gray-400 hover:text-white hover:bg-gray-800'
                      }`}
                    >
                      {period}
                    </button>
                  ))}
                </div>
              </div>

              {/* Scan Activity for SPX */}
              <div className="bg-gray-800 rounded-xl p-4 border border-purple-700/30">
                <h3 className="text-lg font-semibold text-purple-300 mb-3 flex items-center gap-2">
                  <Activity className="w-5 h-5" /> Recent SPX Scans
                </h3>
                <ScanActivityFeed
                  scans={scanActivity.filter((s: any) => s.symbol === 'SPX' || s.ticker === 'SPX').slice(0, 10)}
                  botName="ARES"
                  isLoading={scanActivityLoading}
                />
              </div>

              {/* Open Positions Section */}
              <div className="bg-[#0a0a0a] rounded-lg p-6">
                <h3 className="text-lg font-semibold text-purple-300 mb-4 flex items-center gap-2">
                  <Target className="w-5 h-5" /> Open Positions ({spxOpenPositions.length})
                </h3>
                {spxOpenPositions.length > 0 ? (
                  <div className="space-y-2">
                    {spxOpenPositions.map((pos) => (
                      <div key={pos.position_id} className="flex justify-between items-center p-3 bg-[#111] rounded-lg border border-gray-800">
                        <div className="flex items-center gap-3">
                          <div className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
                          <span className="text-white">
                            SPX IC {pos.put_short_strike}P / {pos.call_short_strike}C
                          </span>
                          <span className="text-gray-500 text-sm">{pos.expiration}</span>
                          <span className="text-gray-500 text-sm">{pos.contracts} contracts</span>
                        </div>
                        <div className="text-right">
                          <div className="text-green-400 font-bold">
                            +${(pos.total_credit * 100 * pos.contracts).toFixed(2)} credit
                          </div>
                          <div className="text-gray-500 text-xs">
                            Max Loss: ${pos.max_loss.toFixed(2)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-center text-gray-500 py-4">No open SPX positions</p>
                )}
              </div>

              {/* Closed Positions Table - Like Athena */}
              <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
                <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                  <h2 className="text-lg font-semibold text-purple-300 flex items-center gap-2">
                    <BarChart3 className="w-5 h-5" /> Closed Trades ({spxClosedPositions.length})
                  </h2>
                  <button
                    onClick={() => setShowSpxClosedPositions(!showSpxClosedPositions)}
                    className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition"
                  >
                    {showSpxClosedPositions ? 'Hide' : 'Show'} Trades
                    {showSpxClosedPositions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                </div>
                {showSpxClosedPositions && (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-gray-900">
                        <tr>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">ID</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Strikes</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Exp</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Closed</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Qty</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Credit</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">VIX</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">SPX Entry</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">P&L</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {spxClosedPositions.map((pos) => {
                          const isExpanded = expandedSpxPosition === pos.position_id
                          return (
                            <React.Fragment key={pos.position_id}>
                              <tr
                                className="hover:bg-gray-700/50 cursor-pointer"
                                onClick={() => setExpandedSpxPosition(isExpanded ? null : pos.position_id)}
                              >
                                <td className="px-3 py-3 text-sm text-gray-300 font-mono">
                                  <div className="flex items-center gap-1">
                                    <ChevronRight className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                                    {pos.position_id.slice(-8)}
                                  </div>
                                </td>
                                <td className="px-3 py-3 text-sm text-purple-300 font-mono">
                                  {pos.put_long_strike}P/{pos.put_short_strike}P - {pos.call_short_strike}C/{pos.call_long_strike}C
                                </td>
                                <td className="px-3 py-3 text-sm text-gray-400">{pos.expiration}</td>
                                <td className="px-3 py-3 text-sm text-gray-400">{pos.close_date || pos.expiration}</td>
                                <td className="px-3 py-3 text-sm text-gray-300">{pos.contracts}</td>
                                <td className="px-3 py-3 text-sm text-green-400">${(pos.total_credit * 100).toFixed(2)}</td>
                                <td className="px-3 py-3 text-sm text-yellow-400">{pos.vix_at_entry?.toFixed(1) || '--'}</td>
                                <td className="px-3 py-3 text-sm text-gray-300">${pos.underlying_at_entry?.toFixed(0) || '--'}</td>
                                <td className={`px-3 py-3 text-sm font-bold ${(pos.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {(pos.realized_pnl || 0) >= 0 ? '+' : ''}${(pos.realized_pnl || 0).toFixed(2)}
                                </td>
                              </tr>
                              {isExpanded && (
                                <tr className="bg-gray-900/50">
                                  <td colSpan={9} className="px-4 py-4">
                                    <div className="grid grid-cols-4 gap-4 text-sm">
                                      <div className="space-y-2">
                                        <h4 className="text-gray-400 font-medium text-xs uppercase">Position Details</h4>
                                        <div className="space-y-1">
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Full ID:</span>
                                            <span className="text-gray-300 font-mono text-xs">{pos.position_id}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Spread Width:</span>
                                            <span className="text-gray-300">${pos.spread_width || 10}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Open Date:</span>
                                            <span className="text-gray-300">{pos.open_date}</span>
                                          </div>
                                        </div>
                                      </div>
                                      <div className="space-y-2">
                                        <h4 className="text-gray-400 font-medium text-xs uppercase">Strikes</h4>
                                        <div className="space-y-1">
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Put Long:</span>
                                            <span className="text-green-400">${pos.put_long_strike}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Put Short:</span>
                                            <span className="text-red-400">${pos.put_short_strike}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Call Short:</span>
                                            <span className="text-red-400">${pos.call_short_strike}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Call Long:</span>
                                            <span className="text-green-400">${pos.call_long_strike}</span>
                                          </div>
                                        </div>
                                      </div>
                                      <div className="space-y-2">
                                        <h4 className="text-gray-400 font-medium text-xs uppercase">Risk / Reward</h4>
                                        <div className="space-y-1">
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Credit:</span>
                                            <span className="text-green-400">${(pos.total_credit * 100 * pos.contracts).toFixed(2)}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Max Loss:</span>
                                            <span className="text-red-400">${pos.max_loss.toFixed(2)}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Close Price:</span>
                                            <span className="text-gray-300">${(pos.close_price || 0).toFixed(2)}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">R:R Ratio:</span>
                                            <span className="text-gray-300">1:{((pos.max_loss || 1) / (pos.total_credit * 100 * pos.contracts || 1)).toFixed(1)}</span>
                                          </div>
                                        </div>
                                      </div>
                                      <div className="space-y-2">
                                        <h4 className="text-gray-400 font-medium text-xs uppercase">Market Context</h4>
                                        <div className="space-y-1">
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">SPX at Entry:</span>
                                            <span className="text-gray-300">${pos.underlying_at_entry?.toFixed(2) || '--'}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">VIX at Entry:</span>
                                            <span className="text-yellow-400">{pos.vix_at_entry?.toFixed(2) || '--'}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Status:</span>
                                            <span className={`px-2 py-0.5 rounded text-xs ${pos.status === 'closed' ? 'bg-gray-700 text-gray-300' : pos.status === 'expired' ? 'bg-purple-900/50 text-purple-400' : 'bg-yellow-900/50 text-yellow-400'}`}>
                                              {pos.status}
                                            </span>
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          )
                        })}
                        {spxClosedPositions.length === 0 && (
                          <tr>
                            <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                              No closed SPX trades yet
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ==================== SPY TAB - Robinhood Style ==================== */}
          {activeTab === 'spy' && (
            <div className="space-y-6">
              {/* Portfolio Header - Robinhood Style */}
              <div className="bg-[#0a0a0a] rounded-lg p-6">
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400 text-sm">SPY Iron Condors</span>
                      <span className={`px-2 py-1 rounded text-xs ${tradierConnected ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'}`}>
                        {tradierConnected ? 'TRADIER' : 'DISCONNECTED'}
                      </span>
                    </div>
                  </div>

                  {/* Big Portfolio Value */}
                  <div className="text-4xl font-bold text-white mb-2">
                    ${(spyStats.capital + spyStats.totalPnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>

                  {/* P&L Change */}
                  <div className="flex items-center gap-2">
                    {spyStats.totalPnl >= 0 ? (
                      <TrendingUp className="w-4 h-4 text-[#00C805]" />
                    ) : (
                      <TrendingDown className="w-4 h-4 text-[#FF5000]" />
                    )}
                    <span className={`font-semibold ${spyStats.totalPnl >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
                      {spyStats.totalPnl >= 0 ? '+' : ''}${spyStats.totalPnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      {' '}({spyStats.totalPnl >= 0 ? '+' : ''}{((spyStats.totalPnl / spyStats.capital) * 100).toFixed(2)}%)
                    </span>
                    <span className="text-gray-500 text-sm">Total</span>
                  </div>

                  {/* Stats Row */}
                  <div className="flex gap-4 mt-2 text-sm flex-wrap">
                    <span className="text-gray-500">
                      Win Rate: <span className="text-white font-bold">{spyStats.winRate.toFixed(1)}%</span>
                    </span>
                    <span className="text-gray-500">
                      Trades: <span className="text-white font-bold">{spyStats.totalTrades}</span>
                    </span>
                    <span className="text-gray-500">
                      Avg Trade: <span className={spyStats.avgTrade >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}>${spyStats.avgTrade.toFixed(2)}</span>
                    </span>
                    <span className="text-gray-500">
                      Max DD: <span className="text-[#FF5000]">${spyStats.maxDrawdown.toFixed(2)}</span>
                    </span>
                    {tradierConnected && (
                      <span className="text-gray-500">
                        Buying Power: <span className="text-blue-400">${(tradierStatus?.account?.buying_power || 0).toLocaleString()}</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Equity Chart - Robinhood Style */}
                <div className="h-64 mb-4">
                  {filteredSpyEquity.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={filteredSpyEquity} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                        <defs>
                          <linearGradient id="spyGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={spyChartColor} stopOpacity={0.3} />
                            <stop offset="100%" stopColor={spyChartColor} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="date" hide axisLine={false} tickLine={false} />
                        <YAxis hide domain={['dataMin - 1000', 'dataMax + 1000']} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: '8px', color: '#fff' }}
                          formatter={(value: number) => [`$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Equity']}
                          labelFormatter={(label) => label}
                        />
                        <ReferenceLine y={spyStats.capital} stroke="#333" strokeDasharray="3 3" />
                        <Line type="monotone" dataKey="equity" stroke={spyChartColor} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: spyChartColor }} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                      <div className="text-center">
                        <p>No equity data available</p>
                        <p className="text-xs text-gray-600 mt-1">Chart will populate as trades are closed</p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Period Toggles - Robinhood Style */}
                <div className="flex justify-center gap-2">
                  {periods.map((period) => (
                    <button
                      key={period}
                      onClick={() => setSpyPeriod(period)}
                      className={`px-4 py-2 text-sm font-medium rounded-full transition-all ${
                        spyPeriod === period
                          ? 'bg-[#3B82F6] text-white'
                          : 'text-gray-400 hover:text-white hover:bg-gray-800'
                      }`}
                    >
                      {period}
                    </button>
                  ))}
                </div>
              </div>

              {/* Scan Activity for SPY */}
              <div className="bg-gray-800 rounded-xl p-4 border border-blue-700/30">
                <h3 className="text-lg font-semibold text-blue-300 mb-3 flex items-center gap-2">
                  <Activity className="w-5 h-5" /> Recent SPY Scans
                </h3>
                <ScanActivityFeed
                  scans={scanActivity.filter((s: any) => s.symbol === 'SPY' || s.ticker === 'SPY').slice(0, 10)}
                  botName="ARES"
                  isLoading={scanActivityLoading}
                />
              </div>

              {/* Open Positions Section */}
              <div className="bg-[#0a0a0a] rounded-lg p-6">
                <h3 className="text-lg font-semibold text-blue-300 mb-4 flex items-center gap-2">
                  <Target className="w-5 h-5" /> Open Positions ({spyOpenPositions.length})
                </h3>
                {spyOpenPositions.length > 0 ? (
                  <div className="space-y-2">
                    {spyOpenPositions.map((pos) => (
                      <div key={pos.position_id} className="flex justify-between items-center p-3 bg-[#111] rounded-lg border border-gray-800">
                        <div className="flex items-center gap-3">
                          <div className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
                          <span className="text-white">
                            SPY IC {pos.put_short_strike}P / {pos.call_short_strike}C
                          </span>
                          <span className="text-gray-500 text-sm">{pos.expiration}</span>
                          <span className="text-gray-500 text-sm">{pos.contracts} contracts</span>
                        </div>
                        <div className="text-right">
                          <div className="text-green-400 font-bold">
                            +${(pos.total_credit * 100 * pos.contracts).toFixed(2)} credit
                          </div>
                          <div className="text-gray-500 text-xs">
                            Max Loss: ${pos.max_loss.toFixed(2)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-center text-gray-500 py-4">No open SPY positions</p>
                )}
              </div>

              {/* Tradier Account Info */}
              {tradierConnected && (
                <div className="bg-gray-800 rounded-xl p-4 border border-blue-700/30">
                  <h3 className="text-lg font-semibold text-blue-300 mb-3 flex items-center gap-2">
                    <Server className="w-5 h-5" /> Tradier Account
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-gray-900/50 rounded-lg p-3 text-center">
                      <span className="text-gray-400 text-xs block">Account</span>
                      <span className="text-white font-mono">{tradierStatus?.account?.account_number || '--'}</span>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3 text-center">
                      <span className="text-gray-400 text-xs block">Equity</span>
                      <span className="text-white font-bold">${(tradierStatus?.account?.equity || 0).toLocaleString()}</span>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3 text-center">
                      <span className="text-gray-400 text-xs block">Cash</span>
                      <span className="text-green-400 font-bold">${(tradierStatus?.account?.cash || 0).toLocaleString()}</span>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3 text-center">
                      <span className="text-gray-400 text-xs block">Buying Power</span>
                      <span className="text-blue-400 font-bold">${(tradierStatus?.account?.buying_power || 0).toLocaleString()}</span>
                    </div>
                  </div>

                  {/* Recent Tradier Orders */}
                  {tradierStatus?.orders && tradierStatus.orders.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-gray-400 text-sm mb-2">Recent Orders</h4>
                      <div className="space-y-2 max-h-32 overflow-y-auto">
                        {tradierStatus.orders.slice(0, 5).map((order) => (
                          <div key={order.id} className="flex items-center justify-between bg-gray-900/50 rounded p-2 text-sm">
                            <span className="text-white font-mono">{order.symbol}</span>
                            <span className={order.side === 'buy' ? 'text-green-400' : 'text-red-400'}>{order.side.toUpperCase()} x{order.quantity}</span>
                            <span className={`px-2 py-0.5 rounded text-xs ${order.status === 'filled' ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'}`}>{order.status}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Tradier Not Connected Warning */}
              {!tradierConnected && (
                <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-yellow-400 font-medium">Tradier Not Connected</h4>
                      <p className="text-gray-400 text-sm mt-1">Configure Tradier sandbox credentials to enable real SPY paper trading.</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Closed Positions Table - Like Athena */}
              <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
                <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                  <h2 className="text-lg font-semibold text-blue-300 flex items-center gap-2">
                    <BarChart3 className="w-5 h-5" /> Closed Trades ({spyClosedPositions.length})
                  </h2>
                  <button
                    onClick={() => setShowSpyClosedPositions(!showSpyClosedPositions)}
                    className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition"
                  >
                    {showSpyClosedPositions ? 'Hide' : 'Show'} Trades
                    {showSpyClosedPositions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                </div>
                {showSpyClosedPositions && (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-gray-900">
                        <tr>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">ID</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Strikes</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Exp</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Closed</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Qty</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Credit</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">VIX</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">SPY Entry</th>
                          <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">P&L</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {spyClosedPositions.map((pos) => {
                          const isExpanded = expandedSpyPosition === pos.position_id
                          return (
                            <React.Fragment key={pos.position_id}>
                              <tr
                                className="hover:bg-gray-700/50 cursor-pointer"
                                onClick={() => setExpandedSpyPosition(isExpanded ? null : pos.position_id)}
                              >
                                <td className="px-3 py-3 text-sm text-gray-300 font-mono">
                                  <div className="flex items-center gap-1">
                                    <ChevronRight className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                                    {pos.position_id.slice(-8)}
                                  </div>
                                </td>
                                <td className="px-3 py-3 text-sm text-blue-300 font-mono">
                                  {pos.put_long_strike}P/{pos.put_short_strike}P - {pos.call_short_strike}C/{pos.call_long_strike}C
                                </td>
                                <td className="px-3 py-3 text-sm text-gray-400">{pos.expiration}</td>
                                <td className="px-3 py-3 text-sm text-gray-400">{pos.close_date || pos.expiration}</td>
                                <td className="px-3 py-3 text-sm text-gray-300">{pos.contracts}</td>
                                <td className="px-3 py-3 text-sm text-green-400">${(pos.total_credit * 100).toFixed(2)}</td>
                                <td className="px-3 py-3 text-sm text-yellow-400">{pos.vix_at_entry?.toFixed(1) || '--'}</td>
                                <td className="px-3 py-3 text-sm text-gray-300">${pos.underlying_at_entry?.toFixed(0) || '--'}</td>
                                <td className={`px-3 py-3 text-sm font-bold ${(pos.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {(pos.realized_pnl || 0) >= 0 ? '+' : ''}${(pos.realized_pnl || 0).toFixed(2)}
                                </td>
                              </tr>
                              {isExpanded && (
                                <tr className="bg-gray-900/50">
                                  <td colSpan={9} className="px-4 py-4">
                                    <div className="grid grid-cols-4 gap-4 text-sm">
                                      <div className="space-y-2">
                                        <h4 className="text-gray-400 font-medium text-xs uppercase">Position Details</h4>
                                        <div className="space-y-1">
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Full ID:</span>
                                            <span className="text-gray-300 font-mono text-xs">{pos.position_id}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Spread Width:</span>
                                            <span className="text-gray-300">${pos.spread_width || 2}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Open Date:</span>
                                            <span className="text-gray-300">{pos.open_date}</span>
                                          </div>
                                        </div>
                                      </div>
                                      <div className="space-y-2">
                                        <h4 className="text-gray-400 font-medium text-xs uppercase">Strikes</h4>
                                        <div className="space-y-1">
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Put Long:</span>
                                            <span className="text-green-400">${pos.put_long_strike}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Put Short:</span>
                                            <span className="text-red-400">${pos.put_short_strike}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Call Short:</span>
                                            <span className="text-red-400">${pos.call_short_strike}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Call Long:</span>
                                            <span className="text-green-400">${pos.call_long_strike}</span>
                                          </div>
                                        </div>
                                      </div>
                                      <div className="space-y-2">
                                        <h4 className="text-gray-400 font-medium text-xs uppercase">Risk / Reward</h4>
                                        <div className="space-y-1">
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Credit:</span>
                                            <span className="text-green-400">${(pos.total_credit * 100 * pos.contracts).toFixed(2)}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Max Loss:</span>
                                            <span className="text-red-400">${pos.max_loss.toFixed(2)}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Close Price:</span>
                                            <span className="text-gray-300">${(pos.close_price || 0).toFixed(2)}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">R:R Ratio:</span>
                                            <span className="text-gray-300">1:{((pos.max_loss || 1) / (pos.total_credit * 100 * pos.contracts || 1)).toFixed(1)}</span>
                                          </div>
                                        </div>
                                      </div>
                                      <div className="space-y-2">
                                        <h4 className="text-gray-400 font-medium text-xs uppercase">Market Context</h4>
                                        <div className="space-y-1">
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">SPY at Entry:</span>
                                            <span className="text-gray-300">${pos.underlying_at_entry?.toFixed(2) || '--'}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">VIX at Entry:</span>
                                            <span className="text-yellow-400">{pos.vix_at_entry?.toFixed(2) || '--'}</span>
                                          </div>
                                          <div className="flex justify-between">
                                            <span className="text-gray-500">Status:</span>
                                            <span className={`px-2 py-0.5 rounded text-xs ${pos.status === 'closed' ? 'bg-gray-700 text-gray-300' : pos.status === 'expired' ? 'bg-purple-900/50 text-purple-400' : 'bg-yellow-900/50 text-yellow-400'}`}>
                                              {pos.status}
                                            </span>
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          )
                        })}
                        {spyClosedPositions.length === 0 && (
                          <tr>
                            <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                              No closed SPY trades yet
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ==================== DECISIONS TAB ==================== */}
          {activeTab === 'decisions' && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="p-4 border-b border-gray-700">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <FileText className="w-5 h-5 text-red-400" /> Decision Log
                </h2>
                <p className="text-xs text-gray-400 mt-1">Full audit trail: What, Why, How for every trading decision</p>
              </div>
              <div className="p-4 space-y-3 max-h-[800px] overflow-y-auto">
                {decisions.length > 0 ? decisions.map((decision) => {
                  const badge = getDecisionTypeBadge(decision.decision_type)
                  const isExpanded = expandedDecision === decision.id

                  return (
                    <div key={decision.id} className={`bg-gray-900/50 rounded-lg border transition-all ${isExpanded ? 'border-red-500/50' : 'border-gray-700 hover:border-gray-600'}`}>
                      <div className="p-3 cursor-pointer" onClick={() => setExpandedDecision(isExpanded ? null : decision.id)}>
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.bg} ${badge.text}`}>{decision.decision_type?.replace(/_/g, ' ')}</span>
                              <span className={`text-sm font-medium ${getActionColor(decision.action)}`}>{decision.action}</span>
                              {decision.symbol && <span className="text-xs text-gray-400 font-mono">{decision.symbol}</span>}
                              {/* SIGNAL SOURCE BADGE */}
                              {decision.signal_source && (
                                <span className={`px-2 py-0.5 rounded text-xs ${
                                  decision.signal_source.includes('override')
                                    ? 'bg-amber-900/30 text-amber-300'
                                    : decision.signal_source === 'Oracle'
                                    ? 'bg-purple-900/30 text-purple-300'
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
                            <p className="text-sm text-white truncate"><span className="text-gray-500">WHAT: </span>{decision.what}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-500 whitespace-nowrap">{new Date(decision.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                            {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                          </div>
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="px-3 pb-3 space-y-3 border-t border-gray-700/50 pt-3">
                          <div className="bg-yellow-900/10 border-l-2 border-yellow-500 pl-3 py-2">
                            <span className="text-yellow-400 text-xs font-bold">WHY:</span>
                            <p className="text-sm text-gray-300 mt-1">{decision.why || 'Not specified'}</p>
                          </div>
                          {decision.how && (
                            <div className="bg-blue-900/10 border-l-2 border-blue-500 pl-3 py-2">
                              <span className="text-blue-400 text-xs font-bold">HOW:</span>
                              <p className="text-sm text-gray-300 mt-1">{decision.how}</p>
                            </div>
                          )}
                          {decision.gex_context && (
                            <div className="bg-purple-900/20 border border-purple-700/30 rounded p-2">
                              <span className="text-purple-400 text-xs font-bold">GEX LEVELS:</span>
                              <div className="grid grid-cols-4 gap-2 mt-2 text-xs">
                                <div><span className="text-gray-500">Put Wall:</span><span className="text-green-400 ml-1">${decision.gex_context.put_wall}</span></div>
                                <div><span className="text-gray-500">Call Wall:</span><span className="text-red-400 ml-1">${decision.gex_context.call_wall}</span></div>
                                <div><span className="text-gray-500">Regime:</span><span className="text-white ml-1">{decision.gex_context.regime}</span></div>
                                <div><span className="text-gray-500">Net GEX:</span><span className="text-white ml-1">{(decision.gex_context.net_gex / 1e9).toFixed(2)}B</span></div>
                              </div>
                            </div>
                          )}
                          {decision.oracle_advice && (
                            <div className="bg-green-900/20 border border-green-700/30 rounded p-2">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-green-400 text-xs font-bold">ORACLE ADVICE:</span>
                                <span className={`px-2 py-0.5 rounded text-xs ${decision.oracle_advice.advice === 'TRADE_FULL' ? 'bg-green-900/50 text-green-400' : 'bg-yellow-900/50 text-yellow-400'}`}>
                                  {decision.oracle_advice.advice?.replace(/_/g, ' ')}
                                </span>
                              </div>
                              <div className="grid grid-cols-3 gap-2 text-xs">
                                <div><span className="text-gray-500">Win Prob:</span><span className="text-green-400 ml-1">{((decision.oracle_advice.win_probability || 0) * 100).toFixed(0)}%</span></div>
                                <div><span className="text-gray-500">Confidence:</span><span className="text-white ml-1">{((decision.oracle_advice.confidence || 0) * 100).toFixed(0)}%</span></div>
                                <div><span className="text-gray-500">Risk:</span><span className="text-yellow-400 ml-1">{(decision.oracle_advice.suggested_risk_pct || 0).toFixed(1)}%</span></div>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                }) : (
                  <div className="text-center py-8 text-gray-500">
                    <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>No decisions recorded yet</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ==================== CONFIG TAB ==================== */}
          {activeTab === 'config' && (
            <div className="space-y-6">
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

      {/* Exit Notifications */}
      <ExitNotificationContainer
        notifications={exitNotifications}
        onDismiss={(id) => setExitNotifications(prev => prev.filter(n => n.id !== id))}
      />
    </div>
  )
}
