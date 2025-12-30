'use client'

import { useState } from 'react'
import {
  Brain, Zap, TrendingUp, TrendingDown, Clock, ChevronDown, ChevronUp,
  AlertTriangle, CheckCircle, XCircle, ArrowRight, Target, Shield,
  Activity, DollarSign, Timer, Eye
} from 'lucide-react'

// Unified Decision interface that works for ARES, ATHENA, and PEGASUS
export interface TradeDecision {
  id: string | number  // Supports both d.id (ARES) and d.decision_id (ATHENA/PEGASUS)
  bot_name: 'ARES' | 'ATHENA' | 'PEGASUS'
  symbol: string
  decision_type: string
  action: string
  what: string
  why: string
  how?: string
  timestamp: string
  outcome?: string
  actual_pnl?: number

  // Signal source & override tracking
  signal_source?: string
  override_occurred?: boolean
  override_details?: {
    overridden_signal?: string
    overridden_advice?: string
    override_reason?: string
    override_by?: string
    ml_was_saying?: string
    oracle_advice?: string
    oracle_confidence?: number
    oracle_win_probability?: number
    ml_confidence?: number
  }

  // ML predictions (primarily ATHENA)
  ml_predictions?: {
    direction: string
    advice: string
    ml_confidence: number
    win_probability: number
    suggested_spread_type?: string
    reasoning?: string
  }

  // Oracle advice
  oracle_advice?: {
    advice: string
    win_probability: number
    confidence: number
    reasoning?: string
    top_factors?: Array<[string, number]> | Array<{ factor: string; importance: number }>
  }

  // GEX context
  gex_context?: {
    net_gex: number
    regime: string
    call_wall: number
    put_wall: number
    flip_point?: number
    between_walls?: boolean
  }

  // Market context
  market_context?: {
    spot_price: number
    vix: number
    expected_move?: number
  }

  // Position data (if trade was executed)
  position?: {
    position_id: string
    entry_price: number
    contracts: number
    max_profit?: number
    max_loss?: number
    strikes?: string  // e.g., "580/585" or "5900P/6000C"
    expiration?: string
    status: 'open' | 'closed' | 'expired'
    exit_price?: number
    realized_pnl?: number
    unrealized_pnl?: number
    exit_reason?: string
    exit_time?: string
  }

  // Risk checks
  risk_checks?: Array<{ check: string; passed: boolean; value?: string }>
  passed_risk_checks?: boolean
}

interface TradeStoryCardProps {
  decision: TradeDecision
  isExpanded?: boolean
  onToggle?: () => void
  showFullStory?: boolean  // When true, shows complete timeline
  underlyingPrice?: number
}

// Format timestamp to readable format (Central Time)
function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago' }) + ' CT'
}

function formatDateTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/Chicago' }) +
    ' ' + date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago' }) + ' CT'
}

// Get action color
function getActionColor(action: string): string {
  const upper = action?.toUpperCase() || ''
  if (upper.includes('ENTRY') || upper.includes('OPEN') || upper.includes('BUY')) return 'text-green-400'
  if (upper.includes('EXIT') || upper.includes('CLOSE') || upper.includes('SELL')) return 'text-blue-400'
  if (upper.includes('SKIP') || upper.includes('NO_TRADE')) return 'text-yellow-400'
  return 'text-gray-400'
}

// Get decision icon
function getDecisionIcon(decision: TradeDecision) {
  const action = decision.action?.toUpperCase() || ''
  if (action.includes('ENTRY') || action.includes('OPEN')) {
    return <TrendingUp className="w-5 h-5 text-green-400" />
  }
  if (action.includes('EXIT') || action.includes('CLOSE')) {
    return <TrendingDown className="w-5 h-5 text-blue-400" />
  }
  if (action.includes('SKIP')) {
    return <XCircle className="w-5 h-5 text-yellow-400" />
  }
  return <Activity className="w-5 h-5 text-gray-400" />
}

// Override Badge Component
function OverrideBadge({ details }: { details: TradeDecision['override_details'] }) {
  if (!details) return null

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 mt-3">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle className="w-4 h-4 text-amber-400" />
        <span className="text-amber-400 font-medium text-sm">Override Occurred</span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-gray-500">Original Signal:</span>
          <span className="ml-2 text-red-400">{details.overridden_signal || details.ml_was_saying}</span>
        </div>
        <div>
          <span className="text-gray-500">Override By:</span>
          <span className="ml-2 text-purple-400">{details.override_by || 'Oracle'}</span>
        </div>
        {details.override_reason && (
          <div className="col-span-2">
            <span className="text-gray-500">Reason:</span>
            <span className="ml-2 text-amber-300">{details.override_reason}</span>
          </div>
        )}
      </div>
    </div>
  )
}

// Signal Sources Display
function SignalSourcesDisplay({ decision }: { decision: TradeDecision }) {
  const ml = decision.ml_predictions
  const oracle = decision.oracle_advice

  if (!ml && !oracle) return null

  return (
    <div className="grid grid-cols-2 gap-3 mt-3">
      {/* ML Signal */}
      {ml && (
        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-4 h-4 text-cyan-400" />
            <span className="text-cyan-400 font-medium text-sm">ML Signal</span>
          </div>
          <div className="space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">Direction:</span>
              <span className={ml.direction === 'BULLISH' ? 'text-green-400' : ml.direction === 'BEARISH' ? 'text-red-400' : 'text-gray-400'}>
                {ml.direction}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Confidence:</span>
              <span className="text-white">{((ml.ml_confidence || 0) * 100).toFixed(0)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Win Prob:</span>
              <span className={ml.win_probability >= 0.5 ? 'text-green-400' : 'text-red-400'}>
                {((ml.win_probability || 0) * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Advice:</span>
              <span className={ml.advice === 'TRADE' ? 'text-green-400' : 'text-yellow-400'}>{ml.advice}</span>
            </div>
          </div>
        </div>
      )}

      {/* Oracle Signal */}
      {oracle && (
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-purple-400" />
            <span className="text-purple-400 font-medium text-sm">Oracle</span>
          </div>
          <div className="space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">Advice:</span>
              <span className={oracle.advice === 'TRADE' ? 'text-green-400' : 'text-yellow-400'}>{oracle.advice}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Confidence:</span>
              <span className="text-white">{((oracle.confidence || 0) * 100).toFixed(0)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Win Prob:</span>
              <span className={oracle.win_probability >= 0.55 ? 'text-green-400' : 'text-red-400'}>
                {((oracle.win_probability || 0) * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          {oracle.top_factors && oracle.top_factors.length > 0 && (
            <div className="mt-2 pt-2 border-t border-purple-500/20">
              <span className="text-gray-500 text-xs">Top Factors:</span>
              <div className="mt-1 space-y-0.5">
                {oracle.top_factors.slice(0, 3).map((f, i) => (
                  <div key={i} className="text-xs text-gray-400 flex justify-between">
                    <span>{Array.isArray(f) ? f[0] : f.factor}</span>
                    <span className="text-purple-300">{Array.isArray(f) ? f[1].toFixed(2) : f.importance.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// GEX Context Display
function GexContextDisplay({ gex, market }: { gex?: TradeDecision['gex_context']; market?: TradeDecision['market_context'] }) {
  if (!gex && !market) return null

  return (
    <div className="bg-gray-800/50 rounded-lg p-3 mt-3">
      <div className="flex items-center gap-2 mb-2">
        <Shield className="w-4 h-4 text-blue-400" />
        <span className="text-gray-400 font-medium text-sm">Market Context</span>
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        {gex && (
          <>
            <div>
              <span className="text-gray-500 block">GEX Regime</span>
              <span className={`font-bold ${
                gex.regime === 'POSITIVE' ? 'text-green-400' :
                gex.regime === 'NEGATIVE' ? 'text-red-400' : 'text-yellow-400'
              }`}>{gex.regime}</span>
            </div>
            <div>
              <span className="text-gray-500 block">Put Wall</span>
              <span className="text-orange-400 font-bold">${gex.put_wall?.toFixed(0)}</span>
            </div>
            <div>
              <span className="text-gray-500 block">Call Wall</span>
              <span className="text-cyan-400 font-bold">${gex.call_wall?.toFixed(0)}</span>
            </div>
          </>
        )}
        {market && (
          <>
            <div>
              <span className="text-gray-500 block">Spot Price</span>
              <span className="text-white font-bold">${market.spot_price?.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500 block">VIX</span>
              <span className={`font-bold ${market.vix > 22 ? 'text-red-400' : market.vix > 18 ? 'text-yellow-400' : 'text-green-400'}`}>
                {market.vix?.toFixed(2)}
              </span>
            </div>
            {market.expected_move && (
              <div>
                <span className="text-gray-500 block">±Move</span>
                <span className="text-gray-300 font-bold">${market.expected_move?.toFixed(0)}</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// Position Outcome Display
function PositionOutcome({ position, isLive }: { position: TradeDecision['position']; isLive?: boolean }) {
  if (!position) return null

  const pnl = position.status === 'open' ? position.unrealized_pnl : position.realized_pnl
  const pnlValue = pnl || 0
  const isPositive = pnlValue >= 0

  return (
    <div className={`rounded-lg p-4 mt-3 ${
      position.status === 'open'
        ? 'bg-blue-500/10 border border-blue-500/30'
        : isPositive
          ? 'bg-green-500/10 border border-green-500/30'
          : 'bg-red-500/10 border border-red-500/30'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {position.status === 'open' ? (
            <>
              <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-blue-400 font-medium">Position Open</span>
              {isLive && (
                <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full">LIVE</span>
              )}
            </>
          ) : (
            <>
              <CheckCircle className={`w-4 h-4 ${isPositive ? 'text-green-400' : 'text-red-400'}`} />
              <span className={`font-medium ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                Position Closed
              </span>
            </>
          )}
        </div>
        <div className={`text-xl font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
          {isPositive ? '+' : ''}${Math.abs(pnlValue).toFixed(2)}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div>
          <span className="text-gray-500 block">Entry</span>
          <span className="text-white font-medium">${position.entry_price?.toFixed(2)}</span>
        </div>
        {position.status === 'open' && (
          <div>
            <span className="text-gray-500 block">Contracts</span>
            <span className="text-white font-medium">{position.contracts}</span>
          </div>
        )}
        {position.status !== 'open' && position.exit_price && (
          <div>
            <span className="text-gray-500 block">Exit</span>
            <span className="text-white font-medium">${position.exit_price?.toFixed(2)}</span>
          </div>
        )}
        {position.strikes && (
          <div>
            <span className="text-gray-500 block">Strikes</span>
            <span className="text-purple-400 font-medium">{position.strikes}</span>
          </div>
        )}
        {position.max_loss && (
          <div>
            <span className="text-gray-500 block">Max Risk</span>
            <span className="text-red-400 font-medium">${position.max_loss?.toFixed(0)}</span>
          </div>
        )}
        {position.exit_reason && (
          <div className="col-span-2">
            <span className="text-gray-500 block">Exit Reason</span>
            <span className="text-gray-300">{position.exit_reason}</span>
          </div>
        )}
        {position.exit_time && (
          <div>
            <span className="text-gray-500 block">Closed At</span>
            <span className="text-gray-300">{formatTime(position.exit_time)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

// Risk Checks Display
function RiskChecksDisplay({ checks }: { checks?: TradeDecision['risk_checks'] }) {
  if (!checks || checks.length === 0) return null

  const passed = checks.filter(c => c.passed).length
  const total = checks.length
  const allPassed = passed === total

  return (
    <div className="mt-3">
      <div className="flex items-center gap-2 mb-2">
        <Shield className={`w-4 h-4 ${allPassed ? 'text-green-400' : 'text-yellow-400'}`} />
        <span className="text-gray-400 text-sm">
          Risk Checks: {passed}/{total} passed
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1">
        {checks.map((check, i) => (
          <div key={i} className="flex items-center gap-1 text-xs">
            {check.passed ? (
              <CheckCircle className="w-3 h-3 text-green-400" />
            ) : (
              <XCircle className="w-3 h-3 text-red-400" />
            )}
            <span className={check.passed ? 'text-gray-400' : 'text-red-300'}>{check.check}</span>
            {check.value && <span className="text-gray-500">({check.value})</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

// Main Component
export default function TradeStoryCard({
  decision,
  isExpanded = false,
  onToggle,
  showFullStory = false,
  underlyingPrice
}: TradeStoryCardProps) {
  const [localExpanded, setLocalExpanded] = useState(isExpanded)
  const expanded = isExpanded || localExpanded

  const handleToggle = () => {
    if (onToggle) {
      onToggle()
    } else {
      setLocalExpanded(!localExpanded)
    }
  }

  const isEntry = decision.action?.toUpperCase().includes('ENTRY') || decision.action?.toUpperCase().includes('OPEN')
  const isSkip = decision.action?.toUpperCase().includes('SKIP')
  const hasPosition = !!decision.position
  const pnl = decision.position?.realized_pnl || decision.position?.unrealized_pnl || decision.actual_pnl || 0
  const isPositive = pnl >= 0

  // Determine card border color
  const getBorderColor = () => {
    if (hasPosition && decision.position?.status === 'open') return 'border-blue-500/30'
    if (isSkip) return 'border-yellow-500/30'
    if (decision.override_occurred) return 'border-amber-500/30'
    if (pnl > 0) return 'border-green-500/30'
    if (pnl < 0) return 'border-red-500/30'
    return 'border-gray-700'
  }

  return (
    <div className={`bg-[#0a0a0a] rounded-lg border ${getBorderColor()} overflow-hidden`}>
      {/* Header - Always visible */}
      <div
        className="p-4 cursor-pointer hover:bg-gray-800/30 transition-colors"
        onClick={handleToggle}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3">
            {/* Status icon */}
            <div className="mt-0.5">
              {getDecisionIcon(decision)}
            </div>

            {/* Main info */}
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-white font-medium">{decision.what || decision.action}</span>

                {/* Signal source badge */}
                {decision.signal_source && (
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    decision.signal_source.includes('Oracle')
                      ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                      : decision.signal_source.includes('ML')
                        ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                        : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'
                  }`}>
                    {decision.signal_source}
                  </span>
                )}

                {/* Override badge */}
                {decision.override_occurred && (
                  <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30 animate-pulse">
                    OVERRIDE
                  </span>
                )}

                {/* Position status */}
                {decision.position?.status === 'open' && (
                  <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 flex items-center gap-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                    OPEN
                  </span>
                )}
              </div>

              {/* Why - short version */}
              <p className="text-gray-400 text-sm mt-1 line-clamp-1">{decision.why}</p>

              {/* Timestamp and symbol */}
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {formatDateTime(decision.timestamp)}
                </span>
                <span>{decision.symbol}</span>
                {decision.bot_name && (
                  <span className={`${
                    decision.bot_name === 'ARES' ? 'text-amber-400' :
                    decision.bot_name === 'ATHENA' ? 'text-cyan-400' :
                    decision.bot_name === 'PEGASUS' ? 'text-blue-400' : 'text-gray-400'
                  }`}>
                    {decision.bot_name}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Right side - P&L and expand */}
          <div className="flex items-center gap-3">
            {/* P&L if exists */}
            {(hasPosition || decision.actual_pnl !== undefined) && (
              <div className={`text-right ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                <div className="font-bold">
                  {isPositive ? '+' : ''}${Math.abs(pnl).toFixed(2)}
                </div>
                {decision.position?.status === 'open' && (
                  <div className="text-xs text-gray-500">unrealized</div>
                )}
              </div>
            )}

            {/* Expand icon */}
            <div className="text-gray-500">
              {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </div>
          </div>
        </div>
      </div>

      {/* Expanded Content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-800">
          {/* Full "Why" explanation */}
          <div className="mt-4">
            <h4 className="text-gray-400 text-xs uppercase tracking-wide mb-2">Why This Decision</h4>
            <p className="text-gray-300 text-sm">{decision.why}</p>
            {decision.how && (
              <p className="text-gray-400 text-sm mt-2">{decision.how}</p>
            )}
          </div>

          {/* Signal Sources - ML vs Oracle */}
          <SignalSourcesDisplay decision={decision} />

          {/* Override Details */}
          {decision.override_occurred && decision.override_details && (
            <OverrideBadge details={decision.override_details} />
          )}

          {/* GEX & Market Context */}
          <GexContextDisplay gex={decision.gex_context} market={decision.market_context} />

          {/* Risk Checks */}
          <RiskChecksDisplay checks={decision.risk_checks} />

          {/* Position Outcome */}
          {decision.position && (
            <PositionOutcome
              position={decision.position}
              isLive={decision.position.status === 'open'}
            />
          )}

          {/* View Full Details link */}
          {showFullStory && (
            <div className="mt-4 pt-3 border-t border-gray-800 flex justify-end">
              <button className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1">
                <Eye className="w-4 h-4" />
                View Full Trade Story
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
