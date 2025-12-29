'use client'

import React, { useState } from 'react'
import {
  ChevronDown, ChevronUp, Clock, TrendingUp, TrendingDown,
  CheckCircle, XCircle, AlertTriangle, Brain, Cpu, Target,
  Activity, BarChart3, Zap, Shield, Eye, FileText
} from 'lucide-react'
import { BOT_BRANDS, BotName } from './BotBranding'

// =============================================================================
// TYPES
// =============================================================================

export interface ScanCheck {
  name: string
  passed: boolean
  actual_value: string | number | null
  threshold: string | number | null
  reason?: string
}

export interface SignalData {
  signal: string
  confidence: number
  win_probability?: number
  reasoning?: string
}

export interface MarketContext {
  spy_price?: number
  spx_price?: number
  vix?: number
  gex_regime?: string
  put_wall?: number
  call_wall?: number
  gamma_flip?: number
  distance_to_put_wall?: number
  distance_to_call_wall?: number
}

export interface ScanTimestamps {
  scan_started?: string
  data_fetched?: string
  analysis_complete?: string
  decision_logged?: string
}

export interface TradeDetails {
  spread_type?: string
  long_strike?: number
  short_strike?: number
  expiration?: string
  contracts?: number
  entry_price?: number
  max_loss?: number
  strike_selection_reason?: string
  sizing_reason?: string
}

export interface ScanData {
  id: string | number
  timestamp: string
  scan_number?: number
  scan_duration_ms?: number
  outcome: 'TRADED' | 'NO_TRADE' | 'SKIP' | 'ERROR'

  // Market context at scan time
  market_context?: MarketContext

  // Signals
  oracle_signal?: SignalData
  ml_signal?: SignalData
  winning_signal?: 'oracle' | 'ml' | 'aligned'
  override_occurred?: boolean
  override_reason?: string

  // Checks performed
  checks?: ScanCheck[]

  // Decision
  decision_type?: string
  primary_reason?: string
  all_reasons?: string[]

  // Trade details (if traded)
  trade?: TradeDetails

  // Timestamps
  timestamps?: ScanTimestamps

  // Unlock conditions (if skipped)
  unlock_conditions?: Array<{
    condition: string
    current: string | number
    required: string | number
    probability?: number
  }>
}

interface ScanDetailCardProps {
  scan: ScanData
  botName: BotName
  defaultExpanded?: boolean
}

// =============================================================================
// HELPER COMPONENTS
// =============================================================================

function formatTime(timestamp: string | undefined): string {
  if (!timestamp) return '--'
  const date = new Date(timestamp)
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
    timeZone: 'America/Chicago'
  }) + ' CT'
}

function formatDateTime(timestamp: string | undefined): string {
  if (!timestamp) return '--'
  const date = new Date(timestamp)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
    timeZone: 'America/Chicago'
  }) + ' CT'
}

function formatMs(ms: number | undefined): string {
  if (!ms) return '--'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

// =============================================================================
// MARKET CONTEXT PANEL
// =============================================================================

function MarketContextPanel({ context, botName }: { context?: MarketContext; botName: BotName }) {
  const brand = BOT_BRANDS[botName]

  if (!context) {
    return (
      <div className="bg-gray-900/50 rounded-lg p-3 text-center text-gray-500 text-sm">
        No market context available
      </div>
    )
  }

  const price = context.spy_price || context.spx_price || 0
  const regime = context.gex_regime || 'UNKNOWN'
  const regimeColor = regime.includes('POSITIVE') ? 'text-green-400 bg-green-900/30' :
                      regime.includes('NEGATIVE') ? 'text-red-400 bg-red-900/30' :
                      'text-gray-400 bg-gray-900/30'

  return (
    <div className={`rounded-lg p-4 border ${brand.lightBorder} ${brand.lightBg}`}>
      <div className="flex items-center gap-2 mb-3">
        <Activity className={`w-4 h-4 ${brand.primaryText}`} />
        <h4 className={`text-sm font-semibold ${brand.lightText}`}>Market Context at Scan</h4>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Price */}
        <div className="bg-gray-900/50 rounded p-2">
          <p className="text-xs text-gray-500">SPY Price</p>
          <p className="text-lg font-bold text-white">${price.toFixed(2)}</p>
        </div>

        {/* VIX */}
        <div className="bg-gray-900/50 rounded p-2">
          <p className="text-xs text-gray-500">VIX</p>
          <p className={`text-lg font-bold ${
            (context.vix || 0) < 15 ? 'text-green-400' :
            (context.vix || 0) < 20 ? 'text-yellow-400' :
            (context.vix || 0) < 30 ? 'text-orange-400' : 'text-red-400'
          }`}>{context.vix?.toFixed(1) || '--'}</p>
        </div>

        {/* GEX Regime */}
        <div className="bg-gray-900/50 rounded p-2">
          <p className="text-xs text-gray-500">GEX Regime</p>
          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${regimeColor}`}>
            {regime.replace('_', ' ')}
          </span>
        </div>

        {/* Gamma Flip */}
        <div className="bg-gray-900/50 rounded p-2">
          <p className="text-xs text-gray-500">Gamma Flip</p>
          <p className="text-lg font-bold text-purple-400">${context.gamma_flip?.toFixed(0) || '--'}</p>
        </div>
      </div>

      {/* Walls */}
      {(context.put_wall || context.call_wall) && (
        <div className="mt-3 pt-3 border-t border-gray-700/50">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <span className="text-red-400">Put Wall: ${context.put_wall?.toFixed(0) || '--'}</span>
              {context.distance_to_put_wall && (
                <span className="text-xs text-gray-500">({context.distance_to_put_wall.toFixed(1)} pts away)</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-400">Call Wall: ${context.call_wall?.toFixed(0) || '--'}</span>
              {context.distance_to_call_wall && (
                <span className="text-xs text-gray-500">({context.distance_to_call_wall.toFixed(1)} pts away)</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// SIGNAL COMPARISON PANEL
// =============================================================================

function SignalComparisonPanel({
  oracle,
  ml,
  winner,
  override,
  overrideReason,
  botName
}: {
  oracle?: SignalData
  ml?: SignalData
  winner?: string
  override?: boolean
  overrideReason?: string
  botName: BotName
}) {
  const brand = BOT_BRANDS[botName]

  const getSignalColor = (signal: string | undefined) => {
    if (!signal) return 'text-gray-400'
    if (signal.includes('TRADE') || signal === 'BUY' || signal === 'SELL') return 'text-green-400'
    if (signal.includes('HOLD') || signal === 'NO_TRADE') return 'text-red-400'
    return 'text-yellow-400'
  }

  return (
    <div className={`rounded-lg p-4 border ${brand.lightBorder} ${brand.lightBg}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Brain className={`w-4 h-4 ${brand.primaryText}`} />
          <h4 className={`text-sm font-semibold ${brand.lightText}`}>Signal Analysis</h4>
        </div>
        {override && (
          <span className="px-2 py-0.5 bg-amber-900/50 text-amber-400 text-xs rounded font-medium animate-pulse">
            OVERRIDE
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Oracle Signal */}
        <div className={`bg-gray-900/50 rounded-lg p-3 border ${winner === 'oracle' ? 'border-purple-500' : 'border-gray-700'}`}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-400" />
              <span className="text-sm font-medium text-purple-400">Oracle</span>
            </div>
            {winner === 'oracle' && (
              <span className="px-1.5 py-0.5 bg-purple-500/30 text-purple-300 text-xs rounded">WINNER</span>
            )}
          </div>
          <div className="space-y-1">
            <div className="flex justify-between">
              <span className="text-xs text-gray-500">Signal</span>
              <span className={`text-sm font-bold ${getSignalColor(oracle?.signal)}`}>
                {oracle?.signal?.replace(/_/g, ' ') || '--'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-gray-500">Confidence</span>
              <span className="text-sm text-white">{oracle?.confidence ? `${(oracle.confidence * 100).toFixed(0)}%` : '--'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-gray-500">Win Prob</span>
              <span className={`text-sm ${(oracle?.win_probability || 0) >= 0.55 ? 'text-green-400' : 'text-red-400'}`}>
                {oracle?.win_probability ? `${(oracle.win_probability * 100).toFixed(0)}%` : '--'}
              </span>
            </div>
          </div>
          {oracle?.reasoning && (
            <p className="mt-2 text-xs text-gray-400 italic border-t border-gray-700 pt-2">
              {oracle.reasoning}
            </p>
          )}
        </div>

        {/* ML Signal */}
        <div className={`bg-gray-900/50 rounded-lg p-3 border ${winner === 'ml' ? 'border-blue-500' : 'border-gray-700'}`}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-blue-400" />
              <span className="text-sm font-medium text-blue-400">ML Model</span>
            </div>
            {winner === 'ml' && (
              <span className="px-1.5 py-0.5 bg-blue-500/30 text-blue-300 text-xs rounded">WINNER</span>
            )}
          </div>
          <div className="space-y-1">
            <div className="flex justify-between">
              <span className="text-xs text-gray-500">Signal</span>
              <span className={`text-sm font-bold ${getSignalColor(ml?.signal)}`}>
                {ml?.signal?.replace(/_/g, ' ') || '--'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-gray-500">Confidence</span>
              <span className="text-sm text-white">{ml?.confidence ? `${(ml.confidence * 100).toFixed(0)}%` : '--'}</span>
            </div>
          </div>
          {ml?.reasoning && (
            <p className="mt-2 text-xs text-gray-400 italic border-t border-gray-700 pt-2">
              {ml.reasoning}
            </p>
          )}
        </div>
      </div>

      {/* Override explanation */}
      {override && overrideReason && (
        <div className="mt-3 p-2 bg-amber-900/20 border border-amber-700/50 rounded text-sm">
          <span className="text-amber-400 font-medium">Override Reason: </span>
          <span className="text-gray-300">{overrideReason}</span>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// CHECKS PERFORMED PANEL
// =============================================================================

function ChecksPerformedPanel({ checks, botName }: { checks?: ScanCheck[]; botName: BotName }) {
  const brand = BOT_BRANDS[botName]

  if (!checks || checks.length === 0) {
    return null
  }

  const passedCount = checks.filter(c => c.passed).length
  const failedCount = checks.filter(c => !c.passed).length

  return (
    <div className={`rounded-lg p-4 border ${brand.lightBorder} ${brand.lightBg}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield className={`w-4 h-4 ${brand.primaryText}`} />
          <h4 className={`text-sm font-semibold ${brand.lightText}`}>Validation Checks ({passedCount}/{checks.length} passed)</h4>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="flex items-center gap-1 text-green-400">
            <CheckCircle className="w-3 h-3" /> {passedCount}
          </span>
          <span className="flex items-center gap-1 text-red-400">
            <XCircle className="w-3 h-3" /> {failedCount}
          </span>
        </div>
      </div>

      <div className="space-y-2">
        {checks.map((check, i) => (
          <div
            key={i}
            className={`flex items-start gap-3 p-2 rounded ${
              check.passed ? 'bg-green-900/10 border border-green-900/30' : 'bg-red-900/10 border border-red-900/30'
            }`}
          >
            <div className="mt-0.5">
              {check.passed ? (
                <CheckCircle className="w-4 h-4 text-green-400" />
              ) : (
                <XCircle className="w-4 h-4 text-red-400" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className={`text-sm font-medium ${check.passed ? 'text-green-300' : 'text-red-300'}`}>
                  {check.name}
                </span>
                <div className="text-xs text-gray-400 font-mono">
                  {check.actual_value !== null && check.actual_value !== undefined && (
                    <span>
                      <span className="text-white">{String(check.actual_value)}</span>
                      {check.threshold !== null && check.threshold !== undefined && (
                        <span className="text-gray-500"> vs {String(check.threshold)}</span>
                      )}
                    </span>
                  )}
                </div>
              </div>
              {check.reason && (
                <p className="text-xs text-gray-400 mt-0.5">{check.reason}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// =============================================================================
// DECISION OUTCOME PANEL
// =============================================================================

function DecisionOutcomePanel({
  outcome,
  decision_type,
  primary_reason,
  all_reasons,
  trade,
  unlock_conditions,
  botName
}: {
  outcome: string
  decision_type?: string
  primary_reason?: string
  all_reasons?: string[]
  trade?: TradeDetails
  unlock_conditions?: Array<{ condition: string; current: string | number; required: string | number; probability?: number }>
  botName: BotName
}) {
  const brand = BOT_BRANDS[botName]
  const traded = outcome === 'TRADED'

  return (
    <div className={`rounded-lg p-4 border ${traded ? 'border-green-700/50 bg-green-900/10' : 'border-gray-700 bg-gray-900/30'}`}>
      <div className="flex items-center gap-2 mb-3">
        {traded ? (
          <Zap className="w-5 h-5 text-green-400" />
        ) : (
          <AlertTriangle className="w-5 h-5 text-yellow-400" />
        )}
        <h4 className={`text-sm font-semibold ${traded ? 'text-green-400' : 'text-yellow-400'}`}>
          Decision: {outcome.replace(/_/g, ' ')}
        </h4>
        {decision_type && (
          <span className={`px-2 py-0.5 rounded text-xs ${brand.badgeBg} ${brand.badgeText}`}>
            {decision_type.replace(/_/g, ' ')}
          </span>
        )}
      </div>

      {/* Primary Reason */}
      {primary_reason && (
        <div className="mb-3 p-2 bg-gray-900/50 rounded border border-gray-700">
          <span className="text-xs text-gray-500">Primary Reason: </span>
          <span className="text-sm text-white">{primary_reason}</span>
        </div>
      )}

      {/* All Contributing Reasons */}
      {all_reasons && all_reasons.length > 1 && (
        <div className="mb-3">
          <p className="text-xs text-gray-500 mb-2">All Contributing Factors:</p>
          <ul className="space-y-1">
            {all_reasons.map((reason, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                <span className="text-gray-500">•</span>
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Trade Details (if traded) */}
      {traded && trade && (
        <div className="mt-3 pt-3 border-t border-gray-700">
          <h5 className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Trade Executed</h5>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div className="bg-gray-900/50 rounded p-2">
              <p className="text-xs text-gray-500">Type</p>
              <p className="text-sm font-medium text-white">{trade.spread_type?.replace(/_/g, ' ')}</p>
            </div>
            <div className="bg-gray-900/50 rounded p-2">
              <p className="text-xs text-gray-500">Strikes</p>
              <p className="text-sm font-medium text-white">${trade.long_strike}/${trade.short_strike}</p>
            </div>
            <div className="bg-gray-900/50 rounded p-2">
              <p className="text-xs text-gray-500">Contracts</p>
              <p className="text-sm font-medium text-white">{trade.contracts}</p>
            </div>
            <div className="bg-gray-900/50 rounded p-2">
              <p className="text-xs text-gray-500">Entry</p>
              <p className="text-sm font-medium text-green-400">${trade.entry_price?.toFixed(2)}</p>
            </div>
          </div>
          {trade.strike_selection_reason && (
            <p className="mt-2 text-xs text-gray-400">
              <span className="text-gray-500">Strike Selection: </span>{trade.strike_selection_reason}
            </p>
          )}
          {trade.sizing_reason && (
            <p className="text-xs text-gray-400">
              <span className="text-gray-500">Position Sizing: </span>{trade.sizing_reason}
            </p>
          )}
        </div>
      )}

      {/* Unlock Conditions (if skipped) */}
      {!traded && unlock_conditions && unlock_conditions.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-700">
          <h5 className="text-xs text-gray-500 mb-2 uppercase tracking-wide">What Would Unlock Trading?</h5>
          <div className="space-y-2">
            {unlock_conditions.map((cond, i) => (
              <div key={i} className="flex items-center justify-between p-2 bg-gray-900/50 rounded text-sm">
                <span className="text-gray-300">{cond.condition}</span>
                <div className="text-right">
                  <span className="text-red-400">{String(cond.current)}</span>
                  <span className="text-gray-500"> → </span>
                  <span className="text-green-400">{String(cond.required)}</span>
                  {cond.probability !== undefined && (
                    <span className="ml-2 text-xs text-gray-500">({(cond.probability * 100).toFixed(0)}% likely)</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// TIMESTAMPS PANEL
// =============================================================================

function TimestampsPanel({ timestamps, scanDuration }: { timestamps?: ScanTimestamps; scanDuration?: number }) {
  if (!timestamps) return null

  return (
    <div className="bg-gray-900/30 rounded-lg p-3 border border-gray-700">
      <div className="flex items-center gap-2 mb-2">
        <Clock className="w-4 h-4 text-gray-400" />
        <h4 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Scan Timeline</h4>
        {scanDuration && (
          <span className="ml-auto text-xs text-gray-500">Total: {formatMs(scanDuration)}</span>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs overflow-x-auto">
        {timestamps.scan_started && (
          <div className="flex items-center gap-1 whitespace-nowrap">
            <span className="w-2 h-2 rounded-full bg-blue-500" />
            <span className="text-gray-500">Started:</span>
            <span className="text-white font-mono">{formatTime(timestamps.scan_started)}</span>
          </div>
        )}
        {timestamps.data_fetched && (
          <>
            <span className="text-gray-600">→</span>
            <div className="flex items-center gap-1 whitespace-nowrap">
              <span className="w-2 h-2 rounded-full bg-purple-500" />
              <span className="text-gray-500">Data:</span>
              <span className="text-white font-mono">{formatTime(timestamps.data_fetched)}</span>
            </div>
          </>
        )}
        {timestamps.analysis_complete && (
          <>
            <span className="text-gray-600">→</span>
            <div className="flex items-center gap-1 whitespace-nowrap">
              <span className="w-2 h-2 rounded-full bg-yellow-500" />
              <span className="text-gray-500">Analyzed:</span>
              <span className="text-white font-mono">{formatTime(timestamps.analysis_complete)}</span>
            </div>
          </>
        )}
        {timestamps.decision_logged && (
          <>
            <span className="text-gray-600">→</span>
            <div className="flex items-center gap-1 whitespace-nowrap">
              <span className="w-2 h-2 rounded-full bg-green-500" />
              <span className="text-gray-500">Logged:</span>
              <span className="text-white font-mono">{formatTime(timestamps.decision_logged)}</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function ScanDetailCard({ scan, botName, defaultExpanded = false }: ScanDetailCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const brand = BOT_BRANDS[botName]

  const outcomeColor = scan.outcome === 'TRADED' ? 'bg-green-500' :
                       scan.outcome === 'ERROR' ? 'bg-red-500' :
                       'bg-yellow-500'

  const outcomeBadge = scan.outcome === 'TRADED' ? 'bg-green-900/50 text-green-400 border-green-700/50' :
                       scan.outcome === 'ERROR' ? 'bg-red-900/50 text-red-400 border-red-700/50' :
                       'bg-yellow-900/50 text-yellow-400 border-yellow-700/50'

  return (
    <div className={`rounded-lg border ${brand.lightBorder} overflow-hidden transition-all duration-200`}>
      {/* Header - Always visible */}
      <div
        className={`p-4 cursor-pointer hover:bg-gray-800/50 transition-colors ${brand.lightBg}`}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* Status dot */}
            <div className={`w-3 h-3 rounded-full ${outcomeColor}`} />

            {/* Date/Time */}
            <div>
              <p className="text-sm font-medium text-white">{formatDateTime(scan.timestamp)}</p>
              {scan.scan_number && (
                <p className="text-xs text-gray-500">Scan #{scan.scan_number} of day</p>
              )}
            </div>

            {/* Duration */}
            {scan.scan_duration_ms && (
              <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                {formatMs(scan.scan_duration_ms)}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* Outcome badge */}
            <span className={`px-2 py-1 text-xs font-medium rounded border ${outcomeBadge}`}>
              {scan.outcome.replace(/_/g, ' ')}
            </span>

            {/* Quick info badges */}
            {scan.market_context?.vix && (
              <span className="text-xs text-gray-400 bg-gray-800 px-2 py-0.5 rounded">
                VIX: {scan.market_context.vix.toFixed(1)}
              </span>
            )}

            {/* Expand/collapse icon */}
            {isExpanded ? (
              <ChevronUp className="w-5 h-5 text-gray-400" />
            ) : (
              <ChevronDown className="w-5 h-5 text-gray-400" />
            )}
          </div>
        </div>

        {/* Brief summary when collapsed */}
        {!isExpanded && scan.primary_reason && (
          <p className="mt-2 text-sm text-gray-400 truncate">
            {scan.primary_reason}
          </p>
        )}
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="p-4 space-y-4 border-t border-gray-700/50 bg-gray-900/20">
          {/* Timestamps */}
          <TimestampsPanel timestamps={scan.timestamps} scanDuration={scan.scan_duration_ms} />

          {/* Market Context */}
          <MarketContextPanel context={scan.market_context} botName={botName} />

          {/* Signal Comparison */}
          <SignalComparisonPanel
            oracle={scan.oracle_signal}
            ml={scan.ml_signal}
            winner={scan.winning_signal}
            override={scan.override_occurred}
            overrideReason={scan.override_reason}
            botName={botName}
          />

          {/* Checks Performed */}
          <ChecksPerformedPanel checks={scan.checks} botName={botName} />

          {/* Decision Outcome */}
          <DecisionOutcomePanel
            outcome={scan.outcome}
            decision_type={scan.decision_type}
            primary_reason={scan.primary_reason}
            all_reasons={scan.all_reasons}
            trade={scan.trade}
            unlock_conditions={scan.unlock_conditions}
            botName={botName}
          />
        </div>
      )}
    </div>
  )
}
