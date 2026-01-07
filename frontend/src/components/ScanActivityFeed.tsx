'use client'

import { useState } from 'react'
import { Activity, CheckCircle, XCircle, AlertTriangle, Clock, TrendingUp, TrendingDown, Ban, Zap, Brain, Cpu, Shield, BarChart3, Beaker, ChevronDown, ChevronRight, Database, Timer, DollarSign, Target, Percent } from 'lucide-react'

interface ScanActivity {
  id: number
  scan_id: string
  scan_number: number
  timestamp: string
  time_ct: string
  outcome: string
  decision_summary: string
  full_reasoning?: string
  what_would_trigger?: string
  market_insight?: string
  underlying_price?: number
  vix?: number
  expected_move?: number
  signal_source?: string
  signal_direction?: string
  signal_confidence?: number
  signal_win_probability?: number
  oracle_advice?: string
  oracle_reasoning?: string
  // Full Oracle context
  oracle_win_probability?: number
  oracle_confidence?: number
  oracle_top_factors?: Array<{
    factor: string
    impact: number
  }>
  oracle_probabilities?: {
    win?: number
    loss?: number
    breakeven?: number
  }
  oracle_suggested_strikes?: {
    sd_multiplier?: number
    use_gex_walls?: boolean
    put_strike?: number
    call_strike?: number
  }
  oracle_thresholds?: {
    min_win_probability?: number
    vix_skip?: number
    vix_monday_friday_skip?: number
    vix_streak_skip?: number
  }
  min_win_probability_threshold?: number
  trade_executed: boolean
  risk_reward_ratio?: number
  gex_regime?: string
  net_gex?: number
  call_wall?: number
  put_wall?: number
  flip_point?: number
  distance_to_call_wall_pct?: number
  distance_to_put_wall_pct?: number
  error_message?: string
  error_type?: string
  // Enhanced skip/no-trade explanation
  skip_reason?: string
  skip_explanation?: string
  checks_performed?: Array<{
    check_name: string
    passed: boolean
    value?: string
    threshold?: string
    reason?: string
  }>

  // === NEW FIELDS FOR COMPLETE VISIBILITY ===

  // Claude AI Context
  claude_prompt?: string
  claude_response?: string
  claude_model?: string
  claude_tokens_used?: number
  claude_response_time_ms?: number
  ai_confidence?: number
  ai_warnings?: string[]

  // Psychology Patterns
  psychology_pattern?: string
  liberation_setup?: boolean
  false_floor_detected?: boolean
  forward_magnets?: Array<{
    level: number
    strength: number
    type?: string
  }>

  // Execution Details
  order_submitted_at?: string
  order_filled_at?: string
  broker_order_id?: string
  expected_fill_price?: number
  actual_fill_price?: number
  slippage_pct?: number
  broker_status?: string
  execution_notes?: string

  // Trade Details (for executed trades)
  position_id?: string
  strike_selection?: {
    put_long?: number
    put_short?: number
    call_short?: number
    call_long?: number
  }
  contracts?: number
  premium_collected?: number
  max_risk?: number

  // Risk Management
  kelly_pct?: number
  position_size_dollars?: number
  max_risk_dollars?: number
  passed_all_checks?: boolean
  blocked_reason?: string
  risk_checks_performed?: Array<{
    check: string
    passed: boolean
    value?: number
    limit?: number
    reason?: string
  }>

  // Backtest Reference
  backtest_win_rate?: number
  backtest_expectancy?: number
  backtest_sharpe?: number

  // Greeks at Entry
  entry_delta?: number
  entry_gamma?: number
  entry_theta?: number
  entry_vega?: number
  entry_iv?: number

  // Reasoning Breakdown
  entry_reasoning?: string
  strike_reasoning?: string
  size_reasoning?: string
  exit_reasoning?: string

  // Alternatives & Rejections
  alternatives_considered?: Array<{
    strategy?: string
    reason?: string
  }>
  other_strategies_considered?: Array<{
    strategy: string
    rejected_reason?: string
  }>

  // Performance Metrics
  processing_time_ms?: number
  api_calls_made?: Array<{
    api: string
    endpoint?: string
    time_ms?: number
    success?: boolean
  }>
  errors_encountered?: Array<{
    error: string
    context?: string
  }>

  // Outcome (for closed trades)
  actual_pnl?: number
  exit_triggered_by?: string
  exit_timestamp?: string
  exit_price?: number
  exit_slippage_pct?: number
  outcome_correct?: boolean
  outcome_notes?: string
}

// Helper to derive skip reason from outcome and checks
function deriveSkipReason(outcome: string, checks?: Array<{ check_name: string; passed: boolean; value?: string }>): string {
  if (outcome === 'MARKET_CLOSED') return 'MARKET_CLOSED'
  if (outcome === 'BEFORE_WINDOW') return 'BEFORE_WINDOW'
  if (outcome === 'ERROR') return 'ERROR'

  if (!checks || checks.length === 0) return 'NO_SIGNAL'

  const failedChecks = checks.filter(c => !c.passed)
  if (failedChecks.length === 0) return 'NO_SIGNAL'

  for (const check of failedChecks) {
    const checkLower = check.check_name.toLowerCase()
    if (checkLower.includes('vix') && (checkLower.includes('high') || checkLower.includes('max'))) return 'VIX_TOO_HIGH'
    if (checkLower.includes('vix') && (checkLower.includes('low') || checkLower.includes('min'))) return 'VIX_TOO_LOW'
    if (checkLower.includes('max') && checkLower.includes('trade')) return 'MAX_TRADES_REACHED'
    if (checkLower.includes('confidence')) return 'LOW_CONFIDENCE'
    if (checkLower.includes('oracle')) return 'ORACLE_SAYS_NO'
    if (checkLower.includes('market') && checkLower.includes('hour')) return 'BEFORE_WINDOW'
    if (checkLower.includes('conflict')) return 'CONFLICTING_SIGNALS'
  }

  return 'RISK_CHECK_FAILED'
}

function getSkipReasonDisplay(reason: string): { icon: string; label: string; color: string } {
  switch (reason) {
    case 'MARKET_CLOSED': return { icon: '🌙', label: 'Market Closed', color: 'text-gray-400' }
    case 'BEFORE_WINDOW': return { icon: '⏰', label: 'Before Window', color: 'text-gray-400' }
    case 'AFTER_WINDOW': return { icon: '🔚', label: 'After Window', color: 'text-gray-400' }
    case 'VIX_TOO_HIGH': return { icon: '📈', label: 'VIX Too High', color: 'text-red-400' }
    case 'VIX_TOO_LOW': return { icon: '📉', label: 'VIX Too Low', color: 'text-yellow-400' }
    case 'MAX_TRADES_REACHED': return { icon: '🛑', label: 'Max Trades', color: 'text-blue-400' }
    case 'NO_SIGNAL': return { icon: '📡', label: 'No Signal', color: 'text-yellow-400' }
    case 'LOW_CONFIDENCE': return { icon: '🎯', label: 'Low Confidence', color: 'text-yellow-400' }
    case 'RISK_CHECK_FAILED': return { icon: '⚠️', label: 'Risk Check Failed', color: 'text-orange-400' }
    case 'ORACLE_SAYS_NO': return { icon: '🔮', label: 'Oracle Said No', color: 'text-purple-400' }
    case 'CONFLICTING_SIGNALS': return { icon: '⚔️', label: 'Conflicting Signals', color: 'text-amber-400' }
    case 'ERROR': return { icon: '❌', label: 'Error', color: 'text-red-400' }
    default: return { icon: '❓', label: reason.replace(/_/g, ' '), color: 'text-gray-400' }
  }
}

interface ScanActivityFeedProps {
  scans: ScanActivity[]
  botName: string
  isLoading?: boolean
}

function getOutcomeIcon(outcome: string, trade_executed: boolean) {
  if (trade_executed) {
    return <CheckCircle className="w-5 h-5 text-green-400" />
  }
  switch (outcome) {
    case 'TRADED':
      return <CheckCircle className="w-5 h-5 text-green-400" />
    case 'NO_TRADE':
      return <Ban className="w-5 h-5 text-yellow-400" />
    case 'SKIP':
      return <Clock className="w-5 h-5 text-blue-400" />
    case 'ERROR':
      return <XCircle className="w-5 h-5 text-red-400" />
    case 'MARKET_CLOSED':
      return <Clock className="w-5 h-5 text-gray-400" />
    case 'BEFORE_WINDOW':
      return <Clock className="w-5 h-5 text-gray-400" />
    default:
      return <Activity className="w-5 h-5 text-gray-400" />
  }
}

function getOutcomeColor(outcome: string, trade_executed: boolean) {
  if (trade_executed) return 'border-green-500/50 bg-green-500/10'
  switch (outcome) {
    case 'TRADED':
      return 'border-green-500/50 bg-green-500/10'
    case 'NO_TRADE':
      return 'border-yellow-500/50 bg-yellow-500/10'
    case 'SKIP':
      return 'border-blue-500/50 bg-blue-500/10'
    case 'ERROR':
      return 'border-red-500/50 bg-red-500/10'
    default:
      return 'border-gray-500/50 bg-gray-500/10'
  }
}

function getDirectionIcon(direction: string) {
  if (direction === 'BULLISH') return <TrendingUp className="w-4 h-4 text-green-400" />
  if (direction === 'BEARISH') return <TrendingDown className="w-4 h-4 text-red-400" />
  return null
}

export default function ScanActivityFeed({ scans, botName, isLoading }: ScanActivityFeedProps) {
  if (isLoading) {
    return (
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-blue-400 animate-pulse" />
          <h3 className="text-lg font-semibold text-white">Scan Activity</h3>
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse bg-gray-700/50 rounded-lg h-20" />
          ))}
        </div>
      </div>
    )
  }

  if (!scans || scans.length === 0) {
    return (
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-semibold text-white">Scan Activity</h3>
        </div>
        <div className="text-center py-8 text-gray-400">
          <Activity className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>No scan activity yet today</p>
          <p className="text-sm mt-1">Scans will appear here as {botName} runs</p>
        </div>
      </div>
    )
  }

  // Calculate summary stats
  const trades = scans.filter(s => s.trade_executed).length
  const noTrades = scans.filter(s => s.outcome === 'NO_TRADE').length
  const errors = scans.filter(s => s.outcome === 'ERROR').length

  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
      {/* Header with stats */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-semibold text-white">Scan Activity</h3>
          <span className="text-sm text-gray-400">({scans.length} scans)</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1">
            <CheckCircle className="w-4 h-4 text-green-400" />
            <span className="text-green-400">{trades} trades</span>
          </div>
          <div className="flex items-center gap-1">
            <Ban className="w-4 h-4 text-yellow-400" />
            <span className="text-yellow-400">{noTrades} skipped</span>
          </div>
          {errors > 0 && (
            <div className="flex items-center gap-1">
              <XCircle className="w-4 h-4 text-red-400" />
              <span className="text-red-400">{errors} errors</span>
            </div>
          )}
        </div>
      </div>

      {/* Activity Feed */}
      <div className="space-y-3 max-h-[500px] overflow-y-auto">
        {scans.map((scan) => (
          <div
            key={scan.scan_id || scan.id}
            className={`rounded-lg border p-3 ${getOutcomeColor(scan.outcome, scan.trade_executed)}`}
          >
            {/* Header Row */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                {getOutcomeIcon(scan.outcome, scan.trade_executed)}
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white">
                      Scan #{scan.scan_number}
                    </span>
                    <span className="text-sm text-gray-400">
                      {new Date(scan.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/Chicago' })} • {scan.time_ct}
                    </span>
                    {scan.signal_direction && getDirectionIcon(scan.signal_direction)}
                  </div>
                  <p className="text-sm text-gray-300 mt-0.5">
                    {scan.decision_summary}
                  </p>
                  {/* Skip Reason Badge - Prominent explanation for non-trades */}
                  {!scan.trade_executed && scan.outcome !== 'TRADED' && (() => {
                    const reason = scan.skip_reason || deriveSkipReason(scan.outcome, scan.checks_performed)
                    const display = getSkipReasonDisplay(reason)
                    return (
                      <div className={`mt-1 inline-flex items-center gap-1 text-xs ${display.color}`}>
                        <span>{display.icon}</span>
                        <span className="font-medium">{display.label}</span>
                        {scan.skip_explanation && (
                          <span className="text-gray-500 ml-1">— {scan.skip_explanation}</span>
                        )}
                      </div>
                    )
                  })()}
                </div>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                scan.trade_executed ? 'bg-green-500/20 text-green-400' :
                scan.outcome === 'NO_TRADE' ? 'bg-yellow-500/20 text-yellow-400' :
                scan.outcome === 'ERROR' ? 'bg-red-500/20 text-red-400' :
                'bg-gray-500/20 text-gray-400'
              }`}>
                {scan.outcome}
              </span>
            </div>

            {/* Market Data Row */}
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
              {scan.underlying_price != null && scan.underlying_price > 0 && (
                <span>SPY: ${scan.underlying_price.toFixed(2)}</span>
              )}
              {scan.vix != null && scan.vix > 0 && (
                <span>VIX: {scan.vix.toFixed(1)}</span>
              )}
              {scan.gex_regime && scan.gex_regime !== 'UNKNOWN' && (
                <span className={`px-1.5 py-0.5 rounded ${
                  scan.gex_regime === 'POSITIVE' ? 'bg-green-500/20 text-green-400' :
                  scan.gex_regime === 'NEGATIVE' ? 'bg-red-500/20 text-red-400' : 'bg-gray-500/20'
                }`}>
                  GEX: {scan.gex_regime}
                </span>
              )}
              {scan.risk_reward_ratio != null && scan.risk_reward_ratio > 0 && (
                <span className={scan.risk_reward_ratio >= 1.5 ? 'text-green-400' : 'text-yellow-400'}>
                  R:R {scan.risk_reward_ratio.toFixed(2)}:1
                </span>
              )}
            </div>

            {/* GEX Walls with Distance Indicators */}
            {((scan.call_wall != null && scan.call_wall > 0) || (scan.put_wall != null && scan.put_wall > 0)) && (
              <div className="mt-2 p-2 bg-gray-900/50 rounded border border-gray-700">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-cyan-400">📊 GEX Walls (Updated Every 5 Min)</span>
                  {scan.net_gex !== undefined && (
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      scan.net_gex > 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      Net GEX: {(scan.net_gex / 1e9).toFixed(2)}B
                    </span>
                  )}
                </div>

                {/* Price Position Visual */}
                <div className="mb-2">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-red-400">Put Wall: ${scan.put_wall?.toFixed(0) || 'N/A'}</span>
                    <span className="text-white font-bold">Price: ${scan.underlying_price?.toFixed(2) || 'N/A'}</span>
                    <span className="text-green-400">Call Wall: ${scan.call_wall?.toFixed(0) || 'N/A'}</span>
                  </div>

                  {/* Visual bar showing price position between walls */}
                  {scan.put_wall != null && scan.put_wall > 0 && scan.call_wall != null && scan.call_wall > 0 && scan.underlying_price != null && scan.underlying_price > 0 && (
                    <div className="relative h-2 bg-gray-700 rounded-full overflow-hidden">
                      {/* Calculate position: 0% = at put wall, 100% = at call wall */}
                      {(() => {
                        const range = scan.call_wall - scan.put_wall
                        const position = range > 0 ? ((scan.underlying_price - scan.put_wall) / range) * 100 : 50
                        const clampedPosition = Math.max(0, Math.min(100, position))
                        const isInside = position >= 0 && position <= 100
                        return (
                          <>
                            {/* Safe zone gradient */}
                            <div className="absolute inset-0 bg-gradient-to-r from-red-500/30 via-green-500/30 to-red-500/30" />
                            {/* Price marker */}
                            <div
                              className={`absolute top-0 bottom-0 w-1 ${isInside ? 'bg-white' : 'bg-yellow-400'}`}
                              style={{ left: `${clampedPosition}%`, transform: 'translateX(-50%)' }}
                            />
                          </>
                        )
                      })()}
                    </div>
                  )}
                </div>

                {/* Distance to Walls */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className={`p-1.5 rounded ${
                    (scan.distance_to_put_wall_pct || 0) < 0.5 ? 'bg-red-500/20 border border-red-500/50' :
                    (scan.distance_to_put_wall_pct || 0) < 1.0 ? 'bg-yellow-500/20 border border-yellow-500/50' :
                    'bg-gray-800'
                  }`}>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">↓ To Put Wall:</span>
                      <span className={`font-bold ${
                        (scan.distance_to_put_wall_pct || 0) < 0.5 ? 'text-red-400' :
                        (scan.distance_to_put_wall_pct || 0) < 1.0 ? 'text-yellow-400' : 'text-green-400'
                      }`}>
                        {scan.distance_to_put_wall_pct?.toFixed(2) || '0.00'}%
                      </span>
                    </div>
                    {(scan.distance_to_put_wall_pct || 0) < 0.5 && (
                      <div className="text-red-400 text-[10px] mt-0.5">⚠️ Very close to put wall!</div>
                    )}
                  </div>

                  <div className={`p-1.5 rounded ${
                    (scan.distance_to_call_wall_pct || 0) < 0.5 ? 'bg-red-500/20 border border-red-500/50' :
                    (scan.distance_to_call_wall_pct || 0) < 1.0 ? 'bg-yellow-500/20 border border-yellow-500/50' :
                    'bg-gray-800'
                  }`}>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">↑ To Call Wall:</span>
                      <span className={`font-bold ${
                        (scan.distance_to_call_wall_pct || 0) < 0.5 ? 'text-red-400' :
                        (scan.distance_to_call_wall_pct || 0) < 1.0 ? 'text-yellow-400' : 'text-green-400'
                      }`}>
                        {scan.distance_to_call_wall_pct?.toFixed(2) || '0.00'}%
                      </span>
                    </div>
                    {(scan.distance_to_call_wall_pct || 0) < 0.5 && (
                      <div className="text-red-400 text-[10px] mt-0.5">⚠️ Very close to call wall!</div>
                    )}
                  </div>
                </div>

                {/* Trade Trigger Status */}
                {scan.oracle_win_probability !== undefined && scan.min_win_probability_threshold !== undefined && (
                  <div className={`mt-2 p-1.5 rounded text-xs ${
                    scan.oracle_win_probability >= scan.min_win_probability_threshold
                      ? 'bg-green-500/20 border border-green-500/50'
                      : 'bg-gray-800 border border-gray-600'
                  }`}>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Trade Trigger:</span>
                      {scan.oracle_win_probability >= scan.min_win_probability_threshold ? (
                        <span className="text-green-400 font-bold">✅ WOULD TRADE (Win Prob {(scan.oracle_win_probability * 100).toFixed(0)}% ≥ {(scan.min_win_probability_threshold * 100).toFixed(0)}%)</span>
                      ) : (
                        <span className="text-gray-400">
                          Need +{((scan.min_win_probability_threshold - scan.oracle_win_probability) * 100).toFixed(1)}% win prob
                          <span className="text-gray-500 ml-1">({(scan.oracle_win_probability * 100).toFixed(0)}% → {(scan.min_win_probability_threshold * 100).toFixed(0)}%)</span>
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Signal Details Row */}
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
              {scan.signal_source && (
                <span>Signal: {scan.signal_source}</span>
              )}
              {scan.signal_confidence != null && scan.signal_confidence > 0 && (
                <span>Confidence: {(scan.signal_confidence * 100).toFixed(0)}%</span>
              )}
              {scan.signal_win_probability != null && scan.signal_win_probability > 0 && (
                <span>Win Prob: {(scan.signal_win_probability * 100).toFixed(0)}%</span>
              )}
              {scan.oracle_advice && (
                <span>Oracle: {scan.oracle_advice}</span>
              )}
            </div>

            {/* Oracle Analysis Section - Full visibility into Oracle decision */}
            {(scan.oracle_win_probability !== undefined || scan.oracle_top_factors) && (
              <details className="mt-2">
                <summary className="text-xs text-purple-400 cursor-pointer hover:text-purple-300 flex items-center gap-1">
                  🔮 Oracle Analysis
                  {scan.oracle_win_probability !== undefined && (
                    <span className={`ml-1 px-1.5 py-0.5 rounded ${
                      scan.oracle_win_probability >= (scan.min_win_probability_threshold || 0.55)
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {(scan.oracle_win_probability * 100).toFixed(0)}% win prob
                    </span>
                  )}
                </summary>
                <div className="mt-2 p-3 bg-purple-900/20 border border-purple-500/30 rounded text-xs space-y-2">
                  {/* Win Probability vs Threshold */}
                  {scan.oracle_win_probability !== undefined && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Win Probability:</span>
                      <div className="flex items-center gap-2">
                        <span className={`font-medium ${
                          scan.oracle_win_probability >= (scan.min_win_probability_threshold || 0.55)
                            ? 'text-green-400'
                            : 'text-red-400'
                        }`}>
                          {(scan.oracle_win_probability * 100).toFixed(1)}%
                        </span>
                        {scan.min_win_probability_threshold && (
                          <span className="text-gray-500">
                            (min: {(scan.min_win_probability_threshold * 100).toFixed(0)}%)
                          </span>
                        )}
                        {scan.oracle_win_probability < (scan.min_win_probability_threshold || 0.55) && (
                          <span className="text-red-400">
                            ⚠️ {((scan.min_win_probability_threshold || 0.55) - scan.oracle_win_probability) * 100 > 0
                              ? `-${(((scan.min_win_probability_threshold || 0.55) - scan.oracle_win_probability) * 100).toFixed(1)}% shortfall`
                              : ''}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Oracle Confidence */}
                  {scan.oracle_confidence !== undefined && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Oracle Confidence:</span>
                      <span className={`font-medium ${
                        scan.oracle_confidence >= 0.7 ? 'text-green-400' :
                        scan.oracle_confidence >= 0.5 ? 'text-yellow-400' : 'text-red-400'
                      }`}>
                        {(scan.oracle_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}

                  {/* Top Factors */}
                  {scan.oracle_top_factors && scan.oracle_top_factors.length > 0 && (
                    <div>
                      <span className="text-gray-400 block mb-1">Top Factors:</span>
                      <div className="flex flex-wrap gap-1">
                        {scan.oracle_top_factors.slice(0, 5).map((factor, i) => (
                          <span
                            key={i}
                            className={`px-2 py-0.5 rounded ${
                              factor.impact > 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                            }`}
                            title={`Impact: ${factor.impact > 0 ? '+' : ''}${(factor.impact * 100).toFixed(1)}%`}
                          >
                            {factor.factor}: {factor.impact > 0 ? '+' : ''}{(factor.impact * 100).toFixed(1)}%
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Thresholds Used */}
                  {scan.oracle_thresholds && (
                    <div>
                      <span className="text-gray-400 block mb-1">Thresholds:</span>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-gray-500">
                        {scan.oracle_thresholds.min_win_probability != null && scan.oracle_thresholds.min_win_probability > 0 && (
                          <span>Min Win: {(scan.oracle_thresholds.min_win_probability * 100).toFixed(0)}%</span>
                        )}
                        {scan.oracle_thresholds.vix_skip != null && scan.oracle_thresholds.vix_skip > 0 && (
                          <span>VIX Skip: {scan.oracle_thresholds.vix_skip}</span>
                        )}
                        {scan.oracle_thresholds.vix_monday_friday_skip != null && scan.oracle_thresholds.vix_monday_friday_skip > 0 && (
                          <span>VIX Mon/Fri: {scan.oracle_thresholds.vix_monday_friday_skip}</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Oracle Reasoning */}
                  {scan.oracle_reasoning && (
                    <div className="mt-1 pt-1 border-t border-purple-500/20">
                      <span className="text-gray-400">Reasoning: </span>
                      <span className="text-gray-300">{scan.oracle_reasoning}</span>
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Checks Summary (if available) */}
            {scan.checks_performed && scan.checks_performed.length > 0 && (
              <details className="mt-2">
                <summary className="text-xs text-orange-400 cursor-pointer hover:text-orange-300 flex items-center gap-1">
                  <Shield className="w-3 h-3" />
                  Risk Checks ({scan.checks_performed.filter(c => c.passed).length}/{scan.checks_performed.length} passed)
                  {scan.blocked_reason && (
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">
                      Blocked: {scan.blocked_reason}
                    </span>
                  )}
                </summary>
                <div className="mt-2 p-2 bg-orange-900/20 border border-orange-500/30 rounded text-xs space-y-1">
                  {scan.checks_performed.map((check, i) => (
                    <div key={i} className={`flex items-center justify-between p-1.5 rounded ${
                      check.passed ? 'bg-green-500/10' : 'bg-red-500/10'
                    }`}>
                      <div className="flex items-center gap-2">
                        <span className={check.passed ? 'text-green-400' : 'text-red-400'}>
                          {check.passed ? '✓' : '✗'}
                        </span>
                        <span className="text-gray-300">{check.check_name}</span>
                      </div>
                      <div className="flex items-center gap-2 text-gray-400">
                        {check.value && <span>Value: {typeof check.value === 'object' ? JSON.stringify(check.value) : check.value}</span>}
                        {check.threshold && <span>Limit: {typeof check.threshold === 'object' ? JSON.stringify(check.threshold) : check.threshold}</span>}
                        {check.reason && <span className="text-gray-500">({check.reason})</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {/* What Would Trigger Trade - KEY INFO */}
            {scan.what_would_trigger && !scan.trade_executed && (
              <div className="mt-2 p-2 bg-blue-500/10 border border-blue-500/30 rounded text-xs">
                <span className="text-blue-400 font-medium">📍 What would trigger trade: </span>
                <span className="text-gray-300">{scan.what_would_trigger}</span>
              </div>
            )}

            {/* Market Insight */}
            {scan.market_insight && (
              <div className="mt-1 text-xs text-gray-500 italic">
                💡 {scan.market_insight}
              </div>
            )}

            {/* === NEW DETAILED SECTIONS === */}

            {/* Psychology Patterns Section */}
            {(scan.psychology_pattern || scan.liberation_setup || scan.false_floor_detected || (scan.forward_magnets && scan.forward_magnets.length > 0)) && (
              <details className="mt-2">
                <summary className="text-xs text-pink-400 cursor-pointer hover:text-pink-300 flex items-center gap-1">
                  <Brain className="w-3 h-3" />
                  Psychology Patterns
                  {scan.psychology_pattern && (
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-pink-500/20 text-pink-400">
                      {scan.psychology_pattern}
                    </span>
                  )}
                </summary>
                <div className="mt-2 p-3 bg-pink-900/20 border border-pink-500/30 rounded text-xs space-y-2">
                  {scan.psychology_pattern && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Detected Pattern:</span>
                      <span className="text-pink-400 font-medium">{scan.psychology_pattern}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-4">
                    {scan.liberation_setup !== undefined && (
                      <div className={`flex items-center gap-1 ${scan.liberation_setup ? 'text-green-400' : 'text-gray-500'}`}>
                        {scan.liberation_setup ? '✓' : '✗'} Liberation Setup
                      </div>
                    )}
                    {scan.false_floor_detected !== undefined && (
                      <div className={`flex items-center gap-1 ${scan.false_floor_detected ? 'text-red-400' : 'text-gray-500'}`}>
                        {scan.false_floor_detected ? '⚠️' : '✓'} False Floor {scan.false_floor_detected ? 'Detected' : 'Clear'}
                      </div>
                    )}
                  </div>
                  {scan.forward_magnets && scan.forward_magnets.length > 0 && (
                    <div>
                      <span className="text-gray-400 block mb-1">Forward Magnets:</span>
                      <div className="flex flex-wrap gap-1">
                        {scan.forward_magnets.map((magnet, i) => (
                          <span key={i} className="px-2 py-0.5 rounded bg-pink-500/20 text-pink-400">
                            ${magnet.level?.toFixed(0)} (Strength: {(magnet.strength * 100).toFixed(0)}%)
                            {magnet.type && ` - ${magnet.type}`}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Trade Execution Details (for executed trades) */}
            {scan.trade_executed && (scan.position_id || scan.strike_selection || (scan.contracts != null && scan.contracts > 0) || (scan.premium_collected != null && scan.premium_collected > 0)) && (
              <details className="mt-2">
                <summary className="text-xs text-green-400 cursor-pointer hover:text-green-300 flex items-center gap-1">
                  <DollarSign className="w-3 h-3" />
                  Trade Execution Details
                  {scan.premium_collected != null && scan.premium_collected > 0 && (
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-green-500/20 text-green-400">
                      +${scan.premium_collected.toFixed(0)} premium
                    </span>
                  )}
                </summary>
                <div className="mt-2 p-3 bg-green-900/20 border border-green-500/30 rounded text-xs space-y-2">
                  {scan.position_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Position ID:</span>
                      <span className="text-green-400 font-mono">{scan.position_id}</span>
                    </div>
                  )}
                  {scan.strike_selection && (
                    <div>
                      <span className="text-gray-400 block mb-1">Strike Selection:</span>
                      <div className="grid grid-cols-2 gap-2">
                        {scan.strike_selection.put_long != null && scan.strike_selection.put_long > 0 && (
                          <div className="p-1.5 bg-red-500/10 rounded">
                            <span className="text-red-400">Put Long:</span> ${scan.strike_selection.put_long}
                          </div>
                        )}
                        {scan.strike_selection.put_short != null && scan.strike_selection.put_short > 0 && (
                          <div className="p-1.5 bg-red-500/20 rounded">
                            <span className="text-red-400">Put Short:</span> ${scan.strike_selection.put_short}
                          </div>
                        )}
                        {scan.strike_selection.call_short != null && scan.strike_selection.call_short > 0 && (
                          <div className="p-1.5 bg-green-500/20 rounded">
                            <span className="text-green-400">Call Short:</span> ${scan.strike_selection.call_short}
                          </div>
                        )}
                        {scan.strike_selection.call_long != null && scan.strike_selection.call_long > 0 && (
                          <div className="p-1.5 bg-green-500/10 rounded">
                            <span className="text-green-400">Call Long:</span> ${scan.strike_selection.call_long}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  <div className="grid grid-cols-3 gap-2">
                    {scan.contracts != null && scan.contracts > 0 && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Contracts</span>
                        <span className="text-white font-medium">{scan.contracts}</span>
                      </div>
                    )}
                    {scan.premium_collected != null && scan.premium_collected > 0 && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Premium</span>
                        <span className="text-green-400 font-medium">${scan.premium_collected.toFixed(2)}</span>
                      </div>
                    )}
                    {scan.max_risk != null && scan.max_risk > 0 && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Max Risk</span>
                        <span className="text-red-400 font-medium">${scan.max_risk.toFixed(2)}</span>
                      </div>
                    )}
                  </div>
                </div>
              </details>
            )}

            {/* Order Execution Timeline (slippage, fills, timing) */}
            {(scan.order_submitted_at || scan.actual_fill_price || scan.slippage_pct !== undefined) && (
              <details className="mt-2">
                <summary className="text-xs text-cyan-400 cursor-pointer hover:text-cyan-300 flex items-center gap-1">
                  <Timer className="w-3 h-3" />
                  Execution Timeline
                  {scan.slippage_pct !== undefined && (
                    <span className={`ml-1 px-1.5 py-0.5 rounded ${
                      Math.abs(scan.slippage_pct) < 0.5 ? 'bg-green-500/20 text-green-400' :
                      Math.abs(scan.slippage_pct) < 1 ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-red-500/20 text-red-400'
                    }`}>
                      {scan.slippage_pct > 0 ? '+' : ''}{scan.slippage_pct.toFixed(2)}% slippage
                    </span>
                  )}
                </summary>
                <div className="mt-2 p-3 bg-cyan-900/20 border border-cyan-500/30 rounded text-xs space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    {scan.order_submitted_at && (
                      <div>
                        <span className="text-gray-400 block text-[10px]">Submitted</span>
                        <span className="text-white">{new Date(scan.order_submitted_at).toLocaleTimeString()}</span>
                      </div>
                    )}
                    {scan.order_filled_at && (
                      <div>
                        <span className="text-gray-400 block text-[10px]">Filled</span>
                        <span className="text-white">{new Date(scan.order_filled_at).toLocaleTimeString()}</span>
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {scan.expected_fill_price && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Expected</span>
                        <span className="text-white">${scan.expected_fill_price.toFixed(2)}</span>
                      </div>
                    )}
                    {scan.actual_fill_price && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Actual</span>
                        <span className="text-white">${scan.actual_fill_price.toFixed(2)}</span>
                      </div>
                    )}
                    {scan.slippage_pct !== undefined && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Slippage</span>
                        <span className={scan.slippage_pct > 0.5 ? 'text-red-400' : 'text-green-400'}>
                          {scan.slippage_pct > 0 ? '+' : ''}{scan.slippage_pct.toFixed(2)}%
                        </span>
                      </div>
                    )}
                  </div>
                  {scan.broker_order_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Broker Order ID:</span>
                      <span className="text-cyan-400 font-mono text-[10px]">{scan.broker_order_id}</span>
                    </div>
                  )}
                  {scan.broker_status && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Broker Status:</span>
                      <span className={`px-1.5 py-0.5 rounded ${
                        scan.broker_status === 'filled' ? 'bg-green-500/20 text-green-400' :
                        scan.broker_status === 'rejected' ? 'bg-red-500/20 text-red-400' :
                        'bg-yellow-500/20 text-yellow-400'
                      }`}>{scan.broker_status}</span>
                    </div>
                  )}
                  {scan.execution_notes && (
                    <div className="pt-1 border-t border-cyan-500/20">
                      <span className="text-gray-400">Notes: </span>
                      <span className="text-gray-300">{scan.execution_notes}</span>
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Risk Management Details */}
            {(scan.kelly_pct !== undefined || scan.position_size_dollars || scan.max_risk_dollars || scan.backtest_win_rate !== undefined) && (
              <details className="mt-2">
                <summary className="text-xs text-amber-400 cursor-pointer hover:text-amber-300 flex items-center gap-1">
                  <BarChart3 className="w-3 h-3" />
                  Risk Management
                  {scan.kelly_pct !== undefined && (
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">
                      Kelly: {(scan.kelly_pct * 100).toFixed(1)}%
                    </span>
                  )}
                </summary>
                <div className="mt-2 p-3 bg-amber-900/20 border border-amber-500/30 rounded text-xs space-y-2">
                  <div className="grid grid-cols-3 gap-2">
                    {scan.kelly_pct !== undefined && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Kelly %</span>
                        <span className="text-amber-400 font-medium">{(scan.kelly_pct * 100).toFixed(1)}%</span>
                      </div>
                    )}
                    {scan.position_size_dollars != null && scan.position_size_dollars > 0 && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Position Size</span>
                        <span className="text-white font-medium">${scan.position_size_dollars.toLocaleString()}</span>
                      </div>
                    )}
                    {scan.max_risk_dollars != null && scan.max_risk_dollars > 0 && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Max Risk</span>
                        <span className="text-red-400 font-medium">${scan.max_risk_dollars.toLocaleString()}</span>
                      </div>
                    )}
                  </div>
                  {/* Backtest Reference */}
                  {(scan.backtest_win_rate !== undefined || scan.backtest_expectancy !== undefined || scan.backtest_sharpe !== undefined) && (
                    <div>
                      <span className="text-gray-400 block mb-1">Backtest Reference:</span>
                      <div className="grid grid-cols-3 gap-2">
                        {scan.backtest_win_rate !== undefined && (
                          <div className="p-1.5 bg-gray-800 rounded">
                            <span className="text-gray-400 block text-[10px]">Win Rate</span>
                            <span className={scan.backtest_win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}>
                              {(scan.backtest_win_rate * 100).toFixed(1)}%
                            </span>
                          </div>
                        )}
                        {scan.backtest_expectancy !== undefined && (
                          <div className="p-1.5 bg-gray-800 rounded">
                            <span className="text-gray-400 block text-[10px]">Expectancy</span>
                            <span className={scan.backtest_expectancy > 0 ? 'text-green-400' : 'text-red-400'}>
                              ${scan.backtest_expectancy.toFixed(2)}
                            </span>
                          </div>
                        )}
                        {scan.backtest_sharpe !== undefined && (
                          <div className="p-1.5 bg-gray-800 rounded">
                            <span className="text-gray-400 block text-[10px]">Sharpe</span>
                            <span className={scan.backtest_sharpe >= 1 ? 'text-green-400' : scan.backtest_sharpe >= 0.5 ? 'text-yellow-400' : 'text-red-400'}>
                              {scan.backtest_sharpe.toFixed(2)}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Greeks at Entry */}
            {(scan.entry_delta !== undefined || scan.entry_gamma !== undefined || scan.entry_theta !== undefined || scan.entry_vega !== undefined || scan.entry_iv !== undefined) && (
              <details className="mt-2">
                <summary className="text-xs text-indigo-400 cursor-pointer hover:text-indigo-300 flex items-center gap-1">
                  <Percent className="w-3 h-3" />
                  Greeks at Entry
                </summary>
                <div className="mt-2 p-3 bg-indigo-900/20 border border-indigo-500/30 rounded text-xs">
                  <div className="grid grid-cols-5 gap-2">
                    {scan.entry_delta !== undefined && (
                      <div className="p-1.5 bg-gray-800 rounded text-center">
                        <span className="text-gray-400 block text-[10px]">Delta</span>
                        <span className={scan.entry_delta > 0 ? 'text-green-400' : 'text-red-400'}>
                          {scan.entry_delta.toFixed(3)}
                        </span>
                      </div>
                    )}
                    {scan.entry_gamma !== undefined && (
                      <div className="p-1.5 bg-gray-800 rounded text-center">
                        <span className="text-gray-400 block text-[10px]">Gamma</span>
                        <span className="text-indigo-400">{scan.entry_gamma.toFixed(4)}</span>
                      </div>
                    )}
                    {scan.entry_theta !== undefined && (
                      <div className="p-1.5 bg-gray-800 rounded text-center">
                        <span className="text-gray-400 block text-[10px]">Theta</span>
                        <span className={scan.entry_theta < 0 ? 'text-red-400' : 'text-green-400'}>
                          {scan.entry_theta.toFixed(3)}
                        </span>
                      </div>
                    )}
                    {scan.entry_vega !== undefined && (
                      <div className="p-1.5 bg-gray-800 rounded text-center">
                        <span className="text-gray-400 block text-[10px]">Vega</span>
                        <span className="text-indigo-400">{scan.entry_vega.toFixed(3)}</span>
                      </div>
                    )}
                    {scan.entry_iv !== undefined && (
                      <div className="p-1.5 bg-gray-800 rounded text-center">
                        <span className="text-gray-400 block text-[10px]">IV</span>
                        <span className="text-yellow-400">{(scan.entry_iv * 100).toFixed(1)}%</span>
                      </div>
                    )}
                  </div>
                </div>
              </details>
            )}

            {/* Claude AI Context */}
            {(scan.claude_prompt || scan.claude_response || (scan.claude_tokens_used != null && scan.claude_tokens_used > 0)) && (
              <details className="mt-2">
                <summary className="text-xs text-violet-400 cursor-pointer hover:text-violet-300 flex items-center gap-1">
                  <Cpu className="w-3 h-3" />
                  Claude AI Context
                  {scan.claude_model && (
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-400 text-[10px]">
                      {scan.claude_model}
                    </span>
                  )}
                  {scan.claude_tokens_used != null && scan.claude_tokens_used > 0 && (
                    <span className="ml-1 text-gray-500">{scan.claude_tokens_used} tokens</span>
                  )}
                </summary>
                <div className="mt-2 p-3 bg-violet-900/20 border border-violet-500/30 rounded text-xs space-y-2">
                  <div className="grid grid-cols-3 gap-2">
                    {scan.claude_model && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Model</span>
                        <span className="text-violet-400">{scan.claude_model}</span>
                      </div>
                    )}
                    {scan.claude_tokens_used != null && scan.claude_tokens_used > 0 && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Tokens</span>
                        <span className="text-white">{scan.claude_tokens_used.toLocaleString()}</span>
                      </div>
                    )}
                    {scan.claude_response_time_ms != null && scan.claude_response_time_ms > 0 && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Response Time</span>
                        <span className={scan.claude_response_time_ms > 5000 ? 'text-yellow-400' : 'text-green-400'}>
                          {(scan.claude_response_time_ms / 1000).toFixed(2)}s
                        </span>
                      </div>
                    )}
                  </div>
                  {scan.ai_confidence !== undefined && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">AI Confidence:</span>
                      <span className={`font-medium ${
                        scan.ai_confidence >= 0.8 ? 'text-green-400' :
                        scan.ai_confidence >= 0.6 ? 'text-yellow-400' : 'text-red-400'
                      }`}>
                        {(scan.ai_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}
                  {scan.ai_warnings && scan.ai_warnings.length > 0 && (
                    <div>
                      <span className="text-yellow-400 block mb-1">AI Warnings:</span>
                      <div className="space-y-1">
                        {scan.ai_warnings.map((warning, i) => (
                          <div key={i} className="p-1.5 bg-yellow-500/10 rounded text-yellow-400">
                            ⚠️ {warning}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {scan.claude_prompt && (
                    <details className="mt-1">
                      <summary className="text-violet-400 cursor-pointer hover:text-violet-300">
                        View Full Prompt
                      </summary>
                      <div className="mt-1 p-2 bg-gray-900 rounded max-h-40 overflow-y-auto">
                        <pre className="text-gray-300 whitespace-pre-wrap text-[10px]">{scan.claude_prompt}</pre>
                      </div>
                    </details>
                  )}
                  {scan.claude_response && (
                    <details className="mt-1">
                      <summary className="text-violet-400 cursor-pointer hover:text-violet-300">
                        View Full Response
                      </summary>
                      <div className="mt-1 p-2 bg-gray-900 rounded max-h-40 overflow-y-auto">
                        <pre className="text-gray-300 whitespace-pre-wrap text-[10px]">{scan.claude_response}</pre>
                      </div>
                    </details>
                  )}
                </div>
              </details>
            )}

            {/* Detailed Reasoning Breakdown */}
            {(scan.entry_reasoning || scan.strike_reasoning || scan.size_reasoning || scan.exit_reasoning) && (
              <details className="mt-2">
                <summary className="text-xs text-teal-400 cursor-pointer hover:text-teal-300 flex items-center gap-1">
                  <Target className="w-3 h-3" />
                  Detailed Reasoning
                </summary>
                <div className="mt-2 p-3 bg-teal-900/20 border border-teal-500/30 rounded text-xs space-y-2">
                  {scan.entry_reasoning && (
                    <div>
                      <span className="text-teal-400 font-medium block mb-1">Entry Reasoning:</span>
                      <p className="text-gray-300 pl-2 border-l-2 border-teal-500/30">{scan.entry_reasoning}</p>
                    </div>
                  )}
                  {scan.strike_reasoning && (
                    <div>
                      <span className="text-teal-400 font-medium block mb-1">Strike Selection:</span>
                      <p className="text-gray-300 pl-2 border-l-2 border-teal-500/30">{scan.strike_reasoning}</p>
                    </div>
                  )}
                  {scan.size_reasoning && (
                    <div>
                      <span className="text-teal-400 font-medium block mb-1">Position Sizing:</span>
                      <p className="text-gray-300 pl-2 border-l-2 border-teal-500/30">{scan.size_reasoning}</p>
                    </div>
                  )}
                  {scan.exit_reasoning && (
                    <div>
                      <span className="text-teal-400 font-medium block mb-1">Exit Plan:</span>
                      <p className="text-gray-300 pl-2 border-l-2 border-teal-500/30">{scan.exit_reasoning}</p>
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Alternatives Considered */}
            {((scan.alternatives_considered && scan.alternatives_considered.length > 0) || (scan.other_strategies_considered && scan.other_strategies_considered.length > 0)) && (
              <details className="mt-2">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300 flex items-center gap-1">
                  <Database className="w-3 h-3" />
                  Alternatives Considered
                </summary>
                <div className="mt-2 p-3 bg-gray-800/50 border border-gray-600 rounded text-xs space-y-2">
                  {scan.alternatives_considered && scan.alternatives_considered.length > 0 && (
                    <div>
                      <span className="text-gray-400 block mb-1">Alternatives:</span>
                      {scan.alternatives_considered.map((alt, i) => (
                        <div key={i} className="p-1.5 bg-gray-900/50 rounded mb-1">
                          {alt.strategy && <span className="text-white">{alt.strategy}</span>}
                          {alt.reason && <span className="text-gray-500 ml-2">- {alt.reason}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                  {scan.other_strategies_considered && scan.other_strategies_considered.length > 0 && (
                    <div>
                      <span className="text-gray-400 block mb-1">Other Strategies:</span>
                      {scan.other_strategies_considered.map((strat, i) => (
                        <div key={i} className="p-1.5 bg-gray-900/50 rounded mb-1 flex items-center justify-between">
                          <span className="text-white">{strat.strategy}</span>
                          {strat.rejected_reason && (
                            <span className="text-red-400 text-[10px]">Rejected: {strat.rejected_reason}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Processing Metrics */}
            {((scan.processing_time_ms != null && scan.processing_time_ms > 0) || (scan.api_calls_made && scan.api_calls_made.length > 0) || (scan.errors_encountered && scan.errors_encountered.length > 0)) && (
              <details className="mt-2">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300 flex items-center gap-1">
                  <Beaker className="w-3 h-3" />
                  Processing Metrics
                  {scan.processing_time_ms != null && scan.processing_time_ms > 0 && (
                    <span className="ml-1 text-gray-500">{scan.processing_time_ms}ms</span>
                  )}
                  {scan.errors_encountered && scan.errors_encountered.length > 0 && (
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">
                      {scan.errors_encountered.length} errors
                    </span>
                  )}
                </summary>
                <div className="mt-2 p-3 bg-gray-800/50 border border-gray-600 rounded text-xs space-y-2">
                  {scan.processing_time_ms != null && scan.processing_time_ms > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Total Processing Time:</span>
                      <span className={scan.processing_time_ms > 10000 ? 'text-yellow-400' : 'text-green-400'}>
                        {(scan.processing_time_ms / 1000).toFixed(2)}s
                      </span>
                    </div>
                  )}
                  {scan.api_calls_made && scan.api_calls_made.length > 0 && (
                    <div>
                      <span className="text-gray-400 block mb-1">API Calls:</span>
                      <div className="space-y-1">
                        {scan.api_calls_made.map((call, i) => (
                          <div key={i} className="flex items-center justify-between p-1 bg-gray-900/50 rounded">
                            <span className="text-white">{call.api}{call.endpoint ? `: ${call.endpoint}` : ''}</span>
                            <div className="flex items-center gap-2">
                              {call.time_ms != null && call.time_ms > 0 && <span className="text-gray-500">{call.time_ms}ms</span>}
                              <span className={call.success ? 'text-green-400' : 'text-red-400'}>
                                {call.success ? '✓' : '✗'}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {scan.errors_encountered && scan.errors_encountered.length > 0 && (
                    <div>
                      <span className="text-red-400 block mb-1">Errors:</span>
                      {scan.errors_encountered.map((err, i) => (
                        <div key={i} className="p-1.5 bg-red-500/10 rounded mb-1">
                          <span className="text-red-400">{err.error}</span>
                          {err.context && <span className="text-gray-500 block text-[10px]">{err.context}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Trade Outcome (for closed positions) */}
            {(scan.actual_pnl !== undefined || scan.exit_triggered_by || scan.outcome_notes) && (
              <details className="mt-2" open={scan.actual_pnl !== undefined}>
                <summary className="text-xs cursor-pointer flex items-center gap-1" style={{
                  color: scan.actual_pnl && scan.actual_pnl > 0 ? '#4ade80' : scan.actual_pnl && scan.actual_pnl < 0 ? '#f87171' : '#9ca3af'
                }}>
                  <DollarSign className="w-3 h-3" />
                  Trade Outcome
                  {scan.actual_pnl !== undefined && (
                    <span className={`ml-1 px-1.5 py-0.5 rounded font-medium ${
                      scan.actual_pnl > 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      {scan.actual_pnl > 0 ? '+' : ''}${scan.actual_pnl.toFixed(2)}
                    </span>
                  )}
                </summary>
                <div className={`mt-2 p-3 rounded text-xs space-y-2 ${
                  scan.actual_pnl && scan.actual_pnl > 0 ? 'bg-green-900/20 border border-green-500/30' :
                  scan.actual_pnl && scan.actual_pnl < 0 ? 'bg-red-900/20 border border-red-500/30' :
                  'bg-gray-800/50 border border-gray-600'
                }`}>
                  <div className="grid grid-cols-3 gap-2">
                    {scan.actual_pnl !== undefined && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">P&L</span>
                        <span className={`font-bold ${scan.actual_pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {scan.actual_pnl > 0 ? '+' : ''}${scan.actual_pnl.toFixed(2)}
                        </span>
                      </div>
                    )}
                    {scan.exit_triggered_by && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Exit Trigger</span>
                        <span className="text-white">{scan.exit_triggered_by}</span>
                      </div>
                    )}
                    {scan.exit_price && (
                      <div className="p-1.5 bg-gray-800 rounded">
                        <span className="text-gray-400 block text-[10px]">Exit Price</span>
                        <span className="text-white">${scan.exit_price.toFixed(2)}</span>
                      </div>
                    )}
                  </div>
                  {scan.exit_timestamp && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Exit Time:</span>
                      <span className="text-white">{new Date(scan.exit_timestamp).toLocaleString()}</span>
                    </div>
                  )}
                  {scan.exit_slippage_pct !== undefined && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Exit Slippage:</span>
                      <span className={Math.abs(scan.exit_slippage_pct) < 0.5 ? 'text-green-400' : 'text-yellow-400'}>
                        {scan.exit_slippage_pct > 0 ? '+' : ''}{scan.exit_slippage_pct.toFixed(2)}%
                      </span>
                    </div>
                  )}
                  {scan.outcome_correct !== undefined && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Prediction Correct:</span>
                      <span className={scan.outcome_correct ? 'text-green-400' : 'text-red-400'}>
                        {scan.outcome_correct ? '✓ Yes' : '✗ No'}
                      </span>
                    </div>
                  )}
                  {scan.outcome_notes && (
                    <div className="pt-1 border-t border-gray-700">
                      <span className="text-gray-400">Notes: </span>
                      <span className="text-gray-300">{scan.outcome_notes}</span>
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Full Reasoning - No truncation */}
            {scan.full_reasoning && (
              <details className="mt-2">
                <summary className="text-xs text-blue-400 cursor-pointer hover:text-blue-300">
                  📋 View Full Analysis
                </summary>
                <div className="mt-2 p-2 bg-gray-900/50 rounded text-xs text-gray-300 whitespace-pre-wrap">
                  {scan.full_reasoning}
                </div>
              </details>
            )}

            {/* Error details for crashes */}
            {scan.outcome === 'ERROR' && scan.error_message && (
              <div className="mt-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs">
                <span className="text-red-400 font-medium">⚠️ Error: </span>
                <span className="text-gray-300">{scan.error_message}</span>
                {scan.error_type && (
                  <span className="text-gray-500 ml-2">({scan.error_type})</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Export Button */}
      <div className="mt-4 pt-3 border-t border-gray-700 flex justify-end gap-2">
        <button
          onClick={() => {
            // Comprehensive CSV export with all fields
            const headers = [
              'Scan #', 'Time', 'Outcome', 'Summary', 'Trade Executed',
              // Market Data
              'SPY', 'VIX', 'Expected Move', 'GEX Regime', 'Net GEX (B)', 'Put Wall', 'Call Wall', 'Flip Point',
              'Dist to Put Wall %', 'Dist to Call Wall %', 'R:R',
              // Signal
              'Signal Source', 'Signal Direction', 'Signal Confidence', 'Signal Win Prob',
              // Oracle
              'Oracle Advice', 'Oracle Win Prob', 'Oracle Confidence', 'Min Threshold',
              'Oracle Probabilities', 'Oracle Suggested Strikes', 'Oracle Reasoning', 'Top Factors',
              // Psychology
              'Psychology Pattern', 'Liberation Setup', 'False Floor', 'Forward Magnets',
              // Execution
              'Position ID', 'Contracts', 'Premium Collected', 'Max Risk',
              'Expected Fill', 'Actual Fill', 'Slippage %', 'Broker Status',
              // Risk Management
              'Kelly %', 'Position Size $', 'Max Risk $', 'Blocked Reason',
              'Backtest Win Rate', 'Backtest Expectancy', 'Backtest Sharpe',
              // Greeks
              'Entry Delta', 'Entry Gamma', 'Entry Theta', 'Entry Vega', 'Entry IV',
              // AI
              'Claude Model', 'Claude Tokens', 'Claude Response Time (ms)', 'AI Confidence',
              // Outcome
              'Actual P&L', 'Exit Trigger', 'Exit Price', 'Exit Slippage %', 'Outcome Correct',
              // Processing
              'Processing Time (ms)', 'Errors',
              // Full Text
              'What Would Trigger', 'Market Insight', 'Entry Reasoning', 'Full Reasoning'
            ].join(',')

            const rows = scans.map(s => [
              s.scan_number,
              s.time_ct,
              s.outcome,
              `"${(s.decision_summary || '').replace(/"/g, '""')}"`,
              s.trade_executed ? 'Yes' : 'No',
              // Market Data
              s.underlying_price?.toFixed(2) || '',
              s.vix?.toFixed(1) || '',
              s.expected_move?.toFixed(2) || '',
              s.gex_regime || '',
              s.net_gex ? (s.net_gex / 1e9).toFixed(2) : '',
              s.put_wall?.toFixed(0) || '',
              s.call_wall?.toFixed(0) || '',
              s.flip_point?.toFixed(0) || '',
              s.distance_to_put_wall_pct?.toFixed(2) || '',
              s.distance_to_call_wall_pct?.toFixed(2) || '',
              s.risk_reward_ratio?.toFixed(2) || '',
              // Signal
              s.signal_source || '',
              s.signal_direction || '',
              s.signal_confidence ? (s.signal_confidence * 100).toFixed(1) + '%' : '',
              s.signal_win_probability ? (s.signal_win_probability * 100).toFixed(1) + '%' : '',
              // Oracle
              s.oracle_advice || '',
              s.oracle_win_probability ? (s.oracle_win_probability * 100).toFixed(1) + '%' : '',
              s.oracle_confidence ? (s.oracle_confidence * 100).toFixed(0) + '%' : '',
              s.min_win_probability_threshold ? (s.min_win_probability_threshold * 100).toFixed(0) + '%' : '',
              s.oracle_probabilities ? `"Win:${((s.oracle_probabilities.win || 0) * 100).toFixed(0)}% Loss:${((s.oracle_probabilities.loss || 0) * 100).toFixed(0)}%"` : '',
              s.oracle_suggested_strikes ? `"Put:${s.oracle_suggested_strikes.put_strike || 'N/A'} Call:${s.oracle_suggested_strikes.call_strike || 'N/A'}"` : '',
              `"${(s.oracle_reasoning || '').replace(/"/g, '""')}"`,
              s.oracle_top_factors ? `"${s.oracle_top_factors.map(f => `${f.factor}:${(f.impact*100).toFixed(1)}%`).join('; ')}"` : '',
              // Psychology
              s.psychology_pattern || '',
              s.liberation_setup !== undefined ? (s.liberation_setup ? 'Yes' : 'No') : '',
              s.false_floor_detected !== undefined ? (s.false_floor_detected ? 'Yes' : 'No') : '',
              s.forward_magnets ? `"${s.forward_magnets.map(m => `$${m.level?.toFixed(0)}(${(m.strength*100).toFixed(0)}%)`).join('; ')}"` : '',
              // Execution
              s.position_id || '',
              s.contracts || '',
              s.premium_collected?.toFixed(2) || '',
              s.max_risk?.toFixed(2) || '',
              s.expected_fill_price?.toFixed(2) || '',
              s.actual_fill_price?.toFixed(2) || '',
              s.slippage_pct?.toFixed(2) || '',
              s.broker_status || '',
              // Risk Management
              s.kelly_pct ? (s.kelly_pct * 100).toFixed(1) + '%' : '',
              s.position_size_dollars?.toLocaleString() || '',
              s.max_risk_dollars?.toLocaleString() || '',
              s.blocked_reason || '',
              s.backtest_win_rate ? (s.backtest_win_rate * 100).toFixed(1) + '%' : '',
              s.backtest_expectancy?.toFixed(2) || '',
              s.backtest_sharpe?.toFixed(2) || '',
              // Greeks
              s.entry_delta?.toFixed(3) || '',
              s.entry_gamma?.toFixed(4) || '',
              s.entry_theta?.toFixed(3) || '',
              s.entry_vega?.toFixed(3) || '',
              s.entry_iv ? (s.entry_iv * 100).toFixed(1) + '%' : '',
              // AI
              s.claude_model || '',
              s.claude_tokens_used || '',
              s.claude_response_time_ms || '',
              s.ai_confidence ? (s.ai_confidence * 100).toFixed(0) + '%' : '',
              // Outcome
              s.actual_pnl?.toFixed(2) || '',
              s.exit_triggered_by || '',
              s.exit_price?.toFixed(2) || '',
              s.exit_slippage_pct?.toFixed(2) || '',
              s.outcome_correct !== undefined ? (s.outcome_correct ? 'Yes' : 'No') : '',
              // Processing
              s.processing_time_ms || '',
              s.errors_encountered ? s.errors_encountered.length : 0,
              // Full Text
              `"${(s.what_would_trigger || '').replace(/"/g, '""')}"`,
              `"${(s.market_insight || '').replace(/"/g, '""')}"`,
              `"${(s.entry_reasoning || '').replace(/"/g, '""')}"`,
              `"${(s.full_reasoning || '').replace(/"/g, '""').substring(0, 500)}"`
            ].join(','))

            const csv = [headers, ...rows].join('\n')
            const blob = new Blob([csv], { type: 'text/csv' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${botName.toLowerCase()}-scan-activity-full-${new Date().toISOString().split('T')[0]}.csv`
            a.click()
            URL.revokeObjectURL(url)
          }}
          className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded flex items-center gap-1"
        >
          📥 Export Full CSV
        </button>
      </div>
    </div>
  )
}
