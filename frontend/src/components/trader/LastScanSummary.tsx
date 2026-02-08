'use client'

import { useState } from 'react'
import { RefreshCw, CheckCircle, XCircle, AlertTriangle, Clock, Brain, Zap, Target, ChevronDown, ChevronUp, TrendingUp, TrendingDown, Lightbulb, Lock, Unlock, ArrowUp, ArrowDown, Minus } from 'lucide-react'

// Decision Factor Display Component
function FactorDisplay({ factors, title }: { factors: DecisionFactor[]; title: string }) {
  if (!factors || factors.length === 0) return null

  return (
    <div className="bg-black/30 rounded-lg p-3 border border-gray-700 mt-3">
      <div className="flex items-center gap-2 mb-2">
        <Lightbulb className="w-4 h-4 text-yellow-400" />
        <span className="text-yellow-400 text-sm font-bold">{title}</span>
      </div>
      <div className="space-y-2">
        {factors.slice(0, 4).map((factor, i) => (
          <div key={i} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              {factor.impact === 'positive' ? (
                <ArrowUp className="w-3 h-3 text-green-400" />
              ) : factor.impact === 'negative' ? (
                <ArrowDown className="w-3 h-3 text-red-400" />
              ) : (
                <Minus className="w-3 h-3 text-gray-400" />
              )}
              <span className={
                factor.impact === 'positive' ? 'text-green-300' :
                factor.impact === 'negative' ? 'text-red-300' : 'text-gray-300'
              }>
                {factor.factor}
              </span>
            </div>
            {factor.value && (
              <span className="text-gray-500 text-xs font-mono">{typeof factor.value === 'object' ? JSON.stringify(factor.value) : factor.value}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// Skip Reason Display - Shows WHY a trade was skipped with detailed explanation
function SkipReasonDisplay({
  outcome,
  skipReason,
  skipExplanation,
  failedChecks,
  checks
}: {
  outcome: string
  skipReason?: string
  skipExplanation?: string
  failedChecks?: Array<{ check_name: string; expected: string; actual: string; severity: 'blocking' | 'warning' }>
  checks?: ScanCheck[]
}) {
  if (outcome === 'TRADED') return null

  // Derive skip reason from checks if not provided
  const derivedReason = skipReason || deriveSkipReason(outcome, checks)
  const derivedExplanation = skipExplanation || deriveSkipExplanation(outcome, derivedReason, checks)

  // Get blocking checks from either failedChecks or derive from checks
  const blockingChecks = failedChecks?.filter(c => c.severity === 'blocking') ||
    checks?.filter(c => !c.passed).map(c => ({
      check_name: c.check,
      expected: c.threshold || 'Pass',
      actual: c.value || 'Fail',
      severity: 'blocking' as const
    })) || []

  const getReasonIcon = (reason: string) => {
    switch (reason) {
      case 'MARKET_CLOSED': return '🌙'
      case 'BEFORE_WINDOW': return '⏰'
      case 'AFTER_WINDOW': return '🔚'
      case 'VIX_TOO_HIGH': return '📈'
      case 'VIX_TOO_LOW': return '📉'
      case 'MAX_TRADES_REACHED': return '🛑'
      case 'NO_SIGNAL': return '📡'
      case 'LOW_CONFIDENCE': return '🎯'
      case 'RISK_CHECK_FAILED': return '⚠️'
      case 'ORACLE_SAYS_NO': return '🔮'
      case 'CONFLICTING_SIGNALS': return '⚔️'
      default: return '❌'
    }
  }

  const getReasonColor = (reason: string) => {
    switch (reason) {
      case 'MARKET_CLOSED':
      case 'BEFORE_WINDOW':
      case 'AFTER_WINDOW':
        return 'bg-gray-800 border-gray-600 text-gray-300'
      case 'MAX_TRADES_REACHED':
        return 'bg-blue-900/30 border-blue-500/50 text-blue-300'
      case 'VIX_TOO_HIGH':
      case 'RISK_CHECK_FAILED':
        return 'bg-red-900/30 border-red-500/50 text-red-300'
      case 'LOW_CONFIDENCE':
      case 'NO_SIGNAL':
        return 'bg-yellow-900/30 border-yellow-500/50 text-yellow-300'
      default:
        return 'bg-orange-900/30 border-orange-500/50 text-orange-300'
    }
  }

  return (
    <div className={`rounded-lg p-4 border-2 mb-4 ${getReasonColor(derivedReason)}`}>
      <div className="flex items-start gap-3">
        <span className="text-2xl">{getReasonIcon(derivedReason)}</span>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-bold text-lg">WHY {outcome === 'SKIP' ? 'SKIPPED' : 'NO TRADE'}</span>
            <span className="px-2 py-0.5 rounded text-xs font-mono bg-black/30">
              {derivedReason.replace(/_/g, ' ')}
            </span>
          </div>
          <p className="text-sm opacity-90">{derivedExplanation}</p>

          {/* Show blocking checks that prevented the trade */}
          {blockingChecks.length > 0 && (
            <div className="mt-3 space-y-1">
              <span className="text-xs font-bold opacity-70">BLOCKING CHECKS:</span>
              {blockingChecks.slice(0, 3).map((check, i) => (
                <div key={i} className="flex items-center gap-2 text-xs bg-black/20 rounded px-2 py-1">
                  <XCircle className="w-3 h-3 text-red-400 flex-shrink-0" />
                  <span className="font-medium">{check.check_name}:</span>
                  <span className="text-red-300">{check.actual}</span>
                  <span className="text-gray-500">→ need</span>
                  <span className="text-green-300">{check.expected}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Helper to derive skip reason from outcome and checks
function deriveSkipReason(outcome: string, checks?: ScanCheck[]): string {
  if (outcome === 'MARKET_CLOSED') return 'MARKET_CLOSED'
  if (outcome === 'BEFORE_WINDOW') return 'BEFORE_WINDOW'
  if (outcome === 'ERROR') return 'ERROR'

  if (!checks || checks.length === 0) return 'UNKNOWN'

  const failedChecks = checks.filter(c => !c.passed)
  if (failedChecks.length === 0) return 'NO_SIGNAL'

  // Check for specific failure patterns
  for (const check of failedChecks) {
    const checkLower = check.check.toLowerCase()
    if (checkLower.includes('vix') && checkLower.includes('high')) return 'VIX_TOO_HIGH'
    if (checkLower.includes('vix') && checkLower.includes('low')) return 'VIX_TOO_LOW'
    if (checkLower.includes('max') && checkLower.includes('trade')) return 'MAX_TRADES_REACHED'
    if (checkLower.includes('confidence')) return 'LOW_CONFIDENCE'
    if (checkLower.includes('prophet')) return 'ORACLE_SAYS_NO'
    if (checkLower.includes('market') && checkLower.includes('hour')) return 'BEFORE_WINDOW'
    if (checkLower.includes('conflict')) return 'CONFLICTING_SIGNALS'
  }

  return 'RISK_CHECK_FAILED'
}

// Helper to derive human-readable explanation
function deriveSkipExplanation(outcome: string, reason: string, checks?: ScanCheck[]): string {
  const failedCheck = checks?.find(c => !c.passed)

  switch (reason) {
    case 'MARKET_CLOSED':
      return 'The market is currently closed. Trading resumes during regular market hours (9:30 AM - 4:00 PM ET).'
    case 'BEFORE_WINDOW':
      return 'Outside the bot\'s trading window. The bot only scans during its configured active hours.'
    case 'AFTER_WINDOW':
      return 'Past the bot\'s trading cutoff time. No new positions will be opened this late in the session.'
    case 'VIX_TOO_HIGH':
      return `Volatility is too elevated for safe entry. ${failedCheck?.value ? `VIX at ${typeof failedCheck.value === 'object' ? JSON.stringify(failedCheck.value) : failedCheck.value}` : ''} exceeds the maximum threshold.`
    case 'VIX_TOO_LOW':
      return `Volatility is too low for profitable premium. ${failedCheck?.value ? `VIX at ${typeof failedCheck.value === 'object' ? JSON.stringify(failedCheck.value) : failedCheck.value}` : ''} is below the minimum threshold.`
    case 'MAX_TRADES_REACHED':
      return 'Maximum daily trade limit has been reached. No more trades will be opened today to manage risk.'
    case 'NO_SIGNAL':
      return 'No clear directional signal from ML or Prophet. The market conditions are ambiguous.'
    case 'LOW_CONFIDENCE':
      return `Signal confidence is below the required threshold. ${failedCheck?.value ? `Current: ${typeof failedCheck.value === 'object' ? JSON.stringify(failedCheck.value) : failedCheck.value}` : ''}`
    case 'ORACLE_SAYS_NO':
      return 'The Prophet advisor recommends skipping this opportunity due to unfavorable conditions.'
    case 'CONFLICTING_SIGNALS':
      return 'ML and Prophet signals are conflicting. Neither signal is strong enough to override the other.'
    case 'RISK_CHECK_FAILED':
      return `One or more risk checks failed. ${failedCheck ? `${failedCheck.check}: ${typeof failedCheck.value === 'object' ? JSON.stringify(failedCheck.value) : (failedCheck.value || 'failed')}` : ''}`
    case 'ERROR':
      return 'An error occurred during the scan. Check logs for details.'
    default:
      return 'Trade conditions were not met. See details below for specific check results.'
  }
}

// Helper to derive unlock conditions from failed checks
function deriveUnlockConditions(checks?: ScanCheck[]): TradeUnlockCondition[] {
  if (!checks) return []

  return checks
    .filter(c => !c.passed)
    .map(check => {
      // Try to parse numbers from value and threshold
      const currentVal = check.value || 'N/A'
      const requiredVal = check.threshold || 'Pass'

      // Estimate probability based on check type
      let probability: number | undefined
      const checkLower = check.check.toLowerCase()

      if (checkLower.includes('market') || checkLower.includes('hour') || checkLower.includes('window')) {
        // Time-based conditions have predictable unlock times
        probability = 0.95
      } else if (checkLower.includes('vix')) {
        // VIX changes frequently
        probability = 0.6
      } else if (checkLower.includes('max') || checkLower.includes('limit')) {
        // Daily limits reset tomorrow
        probability = 0.99
      }

      return {
        condition: check.check,
        current_value: currentVal,
        required_value: requiredVal,
        met: false,
        probability
      }
    })
}

// Trade Unlock Conditions Display
function UnlockConditionsDisplay({ conditions }: { conditions: TradeUnlockCondition[] }) {
  if (!conditions || conditions.length === 0) return null

  const unmetConditions = conditions.filter(c => !c.met)
  const metConditions = conditions.filter(c => c.met)

  return (
    <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-700/50">
      <div className="flex items-center gap-2 mb-3">
        <Lock className="w-5 h-5 text-blue-400" />
        <span className="text-blue-400 font-bold">WHAT WOULD UNLOCK A TRADE</span>
      </div>

      {/* Unmet conditions - what needs to change */}
      {unmetConditions.length > 0 && (
        <div className="space-y-2 mb-3">
          {unmetConditions.map((cond, i) => (
            <div key={i} className="bg-black/30 rounded p-2 border border-red-700/30">
              <div className="flex items-center justify-between mb-1">
                <span className="text-red-300 text-sm font-medium">{cond.condition}</span>
                {cond.probability !== undefined && (
                  <span className="text-xs text-gray-500">
                    ~{(cond.probability * 100).toFixed(0)}% likely
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-gray-500">Current:</span>
                <span className="text-red-400 font-mono">{cond.current_value}</span>
                <span className="text-gray-600">→</span>
                <span className="text-gray-500">Need:</span>
                <span className="text-green-400 font-mono">{cond.required_value}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Met conditions - what's already good */}
      {metConditions.length > 0 && (
        <div className="border-t border-blue-700/30 pt-2 mt-2">
          <span className="text-xs text-gray-500 mb-2 block">Already met:</span>
          <div className="flex flex-wrap gap-2">
            {metConditions.map((cond, i) => (
              <span key={i} className="flex items-center gap-1 text-xs bg-green-900/30 text-green-400 px-2 py-1 rounded">
                <CheckCircle className="w-3 h-3" />
                {cond.condition}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

interface ScanCheck {
  check: string
  passed: boolean
  value?: string
  threshold?: string
  reason?: string
}

interface DecisionFactor {
  factor: string
  impact: 'positive' | 'negative' | 'neutral'
  weight?: number
  value?: string
}

interface TradeUnlockCondition {
  condition: string
  current_value: string
  required_value: string
  met: boolean
  probability?: number
}

interface ScanResult {
  scan_id?: string
  timestamp: string
  outcome: 'TRADED' | 'NO_TRADE' | 'SKIP' | 'ERROR' | string
  decision_summary?: string

  // Skip/No-trade explanation - THE KEY WHY
  skip_reason?: string  // e.g., "MARKET_CLOSED", "BEFORE_WINDOW", "VIX_TOO_HIGH", "MAX_TRADES_REACHED"
  skip_explanation?: string  // Human-readable explanation
  failed_checks?: Array<{
    check_name: string
    expected: string
    actual: string
    severity: 'blocking' | 'warning'
  }>

  // Signal sources
  ml_signal?: {
    direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | string
    confidence: number
    advice: string
    top_factors?: DecisionFactor[]
  }
  oracle_signal?: {
    advice: string
    confidence: number
    win_probability: number
    reasoning?: string
    top_factors?: DecisionFactor[]
  }

  // Override tracking
  override_occurred?: boolean
  override_details?: {
    winner: 'ML' | 'Prophet' | string
    overridden_signal: string
    override_reason: string
  }

  // Checks performed
  checks?: ScanCheck[]

  // Top decision factors - WHY the decision was made
  top_factors?: DecisionFactor[]

  // Market context at scan
  market_context?: {
    spot_price: number
    vix: number
    gex_regime: string
    put_wall?: number
    call_wall?: number
    flip_point?: number
    flip_distance_pct?: number
  }

  // Trade unlock conditions
  unlock_conditions?: TradeUnlockCondition[]

  // What would trigger (legacy text field)
  what_would_trigger?: string
}

interface LastScanSummaryProps {
  botName: 'FORTRESS' | 'SOLOMON' | 'ANCHOR'
  lastScan: ScanResult | null
  isLoading: boolean
  nextScanIn?: number // seconds
  scansToday?: number
  tradesToday?: number
  onRefresh?: () => void
}

export default function LastScanSummary({
  botName,
  lastScan,
  isLoading,
  nextScanIn,
  scansToday = 0,
  tradesToday = 0,
  onRefresh
}: LastScanSummaryProps) {
  const [expanded, setExpanded] = useState(false)

  // Calculate trade rate
  const tradeRate = scansToday > 0 ? ((tradesToday / scansToday) * 100).toFixed(1) : '0.0'

  // Determine outcome styling
  const getOutcomeStyle = (outcome: string) => {
    switch (outcome.toUpperCase()) {
      case 'TRADED':
        return { bg: 'bg-green-900/30', border: 'border-green-500/50', text: 'text-green-400', icon: CheckCircle }
      case 'NO_TRADE':
        return { bg: 'bg-yellow-900/30', border: 'border-yellow-500/50', text: 'text-yellow-400', icon: XCircle }
      case 'SKIP':
        return { bg: 'bg-orange-900/30', border: 'border-orange-500/50', text: 'text-orange-400', icon: AlertTriangle }
      case 'ERROR':
        return { bg: 'bg-red-900/30', border: 'border-red-500/50', text: 'text-red-400', icon: AlertTriangle }
      default:
        return { bg: 'bg-gray-800', border: 'border-gray-700', text: 'text-gray-400', icon: Clock }
    }
  }

  const style = lastScan ? getOutcomeStyle(lastScan.outcome) : getOutcomeStyle('UNKNOWN')
  const OutcomeIcon = style.icon

  // Format time ago
  const getTimeAgo = (timestamp: string) => {
    const now = new Date()
    const scanTime = new Date(timestamp)
    const diffMs = now.getTime() - scanTime.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return 'just now'
    if (diffMins === 1) return '1 min ago'
    if (diffMins < 60) return `${diffMins} min ago`
    const diffHours = Math.floor(diffMins / 60)
    return `${diffHours}h ${diffMins % 60}m ago`
  }

  if (isLoading) {
    return (
      <div className="bg-[#0a0a0a] rounded-xl p-5 border border-gray-700 animate-pulse">
        <div className="h-6 bg-gray-800 rounded w-48 mb-3" />
        <div className="h-4 bg-gray-800 rounded w-full mb-2" />
        <div className="h-4 bg-gray-800 rounded w-3/4" />
      </div>
    )
  }

  return (
    <div className={`rounded-xl p-5 border ${style.bg} ${style.border}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <OutcomeIcon className={`w-6 h-6 ${style.text}`} />
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              LAST SCAN RESULT
              {onRefresh && (
                <button onClick={onRefresh} className="p-1 hover:bg-gray-700 rounded">
                  <RefreshCw className="w-4 h-4 text-gray-400" />
                </button>
              )}
            </h3>
            {lastScan && (
              <span className="text-gray-400 text-sm">
                {getTimeAgo(lastScan.timestamp)} • {new Date(lastScan.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/Chicago' })} {new Date(lastScan.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago' })} CT
              </span>
            )}
          </div>
        </div>

        {lastScan && (
          <span className={`px-3 py-1 rounded-full text-sm font-bold ${style.bg} ${style.text} border ${style.border}`}>
            {lastScan.outcome}
          </span>
        )}
      </div>

      {!lastScan ? (
        <div className="text-center py-4 text-gray-500">
          <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No scans recorded yet today</p>
        </div>
      ) : (
        <>
          {/* Main Summary */}
          <div className="mb-4">
            <p className="text-white text-lg">
              {lastScan.decision_summary || `Bot decided to ${lastScan.outcome.toLowerCase()}`}
            </p>
          </div>

          {/* WHY SKIPPED/NO TRADE - Prominent explanation for non-trades */}
          {lastScan.outcome !== 'TRADED' && (
            <SkipReasonDisplay
              outcome={lastScan.outcome}
              skipReason={lastScan.skip_reason}
              skipExplanation={lastScan.skip_explanation}
              failedChecks={lastScan.failed_checks}
              checks={lastScan.checks}
            />
          )}

          {/* ML vs Prophet Signals - THE KEY INSIGHT */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* ML Signal */}
            <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <Brain className="w-4 h-4 text-blue-400" />
                <span className="text-blue-400 text-sm font-bold">ML SIGNAL</span>
              </div>
              {lastScan.ml_signal ? (
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    {lastScan.ml_signal.direction === 'BULLISH' ? (
                      <TrendingUp className="w-4 h-4 text-green-400" />
                    ) : lastScan.ml_signal.direction === 'BEARISH' ? (
                      <TrendingDown className="w-4 h-4 text-red-400" />
                    ) : (
                      <Target className="w-4 h-4 text-gray-400" />
                    )}
                    <span className={`font-bold ${
                      lastScan.ml_signal.direction === 'BULLISH' ? 'text-green-400' :
                      lastScan.ml_signal.direction === 'BEARISH' ? 'text-red-400' : 'text-gray-400'
                    }`}>
                      {lastScan.ml_signal.direction}
                    </span>
                  </div>
                  <div className="text-sm text-gray-400">
                    Confidence: <span className="text-white font-mono">{(lastScan.ml_signal.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="text-xs text-gray-500">{lastScan.ml_signal.advice}</div>
                </div>
              ) : (
                <span className="text-gray-500 text-sm">No ML signal</span>
              )}
            </div>

            {/* Prophet Signal */}
            <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="w-4 h-4 text-purple-400" />
                <span className="text-purple-400 text-sm font-bold">PROPHET SIGNAL</span>
              </div>
              {lastScan.oracle_signal ? (
                <div className="space-y-1">
                  <span className={`font-bold ${
                    lastScan.oracle_signal.advice?.includes('TRADE') ? 'text-green-400' : 'text-yellow-400'
                  }`}>
                    {lastScan.oracle_signal.advice}
                  </span>
                  <div className="text-sm text-gray-400">
                    Win Prob: <span className="text-white font-mono">{(lastScan.oracle_signal.win_probability * 100).toFixed(0)}%</span>
                  </div>
                  <div className="text-sm text-gray-400">
                    Confidence: <span className="text-white font-mono">{(lastScan.oracle_signal.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ) : (
                <span className="text-gray-500 text-sm">No Prophet advice</span>
              )}
            </div>
          </div>

          {/* OVERRIDE ALERT - Very prominent if occurred */}
          {lastScan.override_occurred && lastScan.override_details && (
            <div className="bg-amber-900/30 border-2 border-amber-500/50 rounded-lg p-4 mb-4 animate-pulse">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <span className="text-amber-400 font-bold text-lg">SIGNAL OVERRIDE</span>
              </div>
              <p className="text-white">
                <span className="text-amber-300 font-bold">{lastScan.override_details.winner}</span> overrode the other signal
              </p>
              <p className="text-gray-400 text-sm mt-1">
                Original: {lastScan.override_details.overridden_signal}
              </p>
              <p className="text-gray-400 text-sm">
                Reason: {lastScan.override_details.override_reason}
              </p>
            </div>
          )}

          {/* TOP DECISION FACTORS - The WHY */}
          {lastScan.top_factors && lastScan.top_factors.length > 0 && (
            <FactorDisplay factors={lastScan.top_factors} title="TOP DECISION FACTORS" />
          )}

          {/* TRADE UNLOCK CONDITIONS - What needs to happen for a trade */}
          {lastScan.outcome !== 'TRADED' && (lastScan.unlock_conditions || lastScan.checks?.some(c => !c.passed)) && (
            <div className="mb-4">
              <UnlockConditionsDisplay
                conditions={lastScan.unlock_conditions || deriveUnlockConditions(lastScan.checks)}
              />
            </div>
          )}

          {/* Expandable Details */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center justify-between p-2 rounded-lg bg-black/20 hover:bg-black/40 transition"
          >
            <span className="text-sm text-gray-400">
              {expanded ? 'Hide Details' : 'Show Checks & Market Context'}
            </span>
            {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </button>

          {expanded && (
            <div className="mt-4 space-y-4">
              {/* Checks Performed */}
              {lastScan.checks && lastScan.checks.length > 0 && (
                <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
                  <h4 className="text-sm font-bold text-white mb-2">CHECKS PERFORMED</h4>
                  <div className="space-y-2">
                    {lastScan.checks.map((check, i) => (
                      <div key={i} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          {check.passed ? (
                            <CheckCircle className="w-4 h-4 text-green-400" />
                          ) : (
                            <XCircle className="w-4 h-4 text-red-400" />
                          )}
                          <span className={check.passed ? 'text-gray-300' : 'text-red-300'}>
                            {check.check}
                          </span>
                        </div>
                        <div className="text-right">
                          {check.value && (
                            <span className="text-gray-400 font-mono text-xs">
                              {typeof check.value === 'object' ? JSON.stringify(check.value) : check.value} {check.threshold && `(need ${typeof check.threshold === 'object' ? JSON.stringify(check.threshold) : check.threshold})`}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Market Context */}
              {lastScan.market_context && (
                <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
                  <h4 className="text-sm font-bold text-white mb-2">MARKET AT SCAN TIME</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                      <span className="text-gray-500">Spot:</span>
                      <span className="text-white ml-2 font-mono">${lastScan.market_context.spot_price?.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">VIX:</span>
                      <span className="text-white ml-2 font-mono">{lastScan.market_context.vix?.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">GEX:</span>
                      <span className={`ml-2 font-mono ${
                        lastScan.market_context.gex_regime === 'POSITIVE' ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {lastScan.market_context.gex_regime}
                      </span>
                    </div>
                    {lastScan.market_context.put_wall && (
                      <div>
                        <span className="text-gray-500">Walls:</span>
                        <span className="text-white ml-2 font-mono text-xs">
                          P{lastScan.market_context.put_wall?.toFixed(0)} / C{lastScan.market_context.call_wall?.toFixed(0)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* What Would Trigger */}
              {lastScan.what_would_trigger && (
                <div className="bg-blue-900/20 rounded-lg p-3 border border-blue-700/50">
                  <h4 className="text-sm font-bold text-blue-400 mb-2">WHAT WOULD TRIGGER A TRADE</h4>
                  <p className="text-gray-300 text-sm">{lastScan.what_would_trigger}</p>
                </div>
              )}
            </div>
          )}

          {/* Scan Health Stats */}
          <div className="mt-4 pt-3 border-t border-gray-700/50 flex flex-wrap gap-4 text-xs text-gray-500">
            <span>Scans today: <span className="text-white font-mono">{scansToday}</span></span>
            <span>Trades: <span className="text-white font-mono">{tradesToday}</span></span>
            <span>Trade rate: <span className="text-white font-mono">{tradeRate}%</span></span>
            {nextScanIn !== undefined && nextScanIn > 0 && (
              <span>Next scan: <span className="text-cyan-400 font-mono">{Math.floor(nextScanIn / 60)}:{String(nextScanIn % 60).padStart(2, '0')}</span></span>
            )}
          </div>
        </>
      )}
    </div>
  )
}
