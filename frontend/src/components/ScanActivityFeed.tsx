'use client'

import { Activity, CheckCircle, XCircle, AlertTriangle, Clock, TrendingUp, TrendingDown, Ban, Zap } from 'lucide-react'

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
  signal_source?: string
  signal_direction?: string
  signal_confidence?: number
  signal_win_probability?: number
  oracle_advice?: string
  trade_executed: boolean
  risk_reward_ratio?: number
  gex_regime?: string
  call_wall?: number
  put_wall?: number
  error_message?: string
  error_type?: string
  // Enhanced skip/no-trade explanation
  skip_reason?: string  // e.g., "MARKET_CLOSED", "VIX_TOO_HIGH", "MAX_TRADES_REACHED"
  skip_explanation?: string  // Human-readable explanation
  checks_performed?: Array<{
    check_name: string
    passed: boolean
    value?: string
    reason?: string
  }>
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
                      {new Date(scan.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} • {scan.time_ct}
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
              {scan.underlying_price && (
                <span>SPY: ${scan.underlying_price.toFixed(2)}</span>
              )}
              {scan.vix && (
                <span>VIX: {scan.vix.toFixed(1)}</span>
              )}
              {scan.gex_regime && (
                <span className={`px-1.5 py-0.5 rounded ${
                  scan.gex_regime === 'POSITIVE' ? 'bg-green-500/20 text-green-400' :
                  scan.gex_regime === 'NEGATIVE' ? 'bg-red-500/20 text-red-400' : 'bg-gray-500/20'
                }`}>
                  GEX: {scan.gex_regime}
                </span>
              )}
              {scan.risk_reward_ratio && (
                <span className={scan.risk_reward_ratio >= 1.5 ? 'text-green-400' : 'text-yellow-400'}>
                  R:R {scan.risk_reward_ratio.toFixed(2)}:1
                </span>
              )}
            </div>

            {/* GEX Walls (if available) */}
            {(scan.call_wall || scan.put_wall) && (
              <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-gray-500">
                {scan.put_wall && <span>Put Wall: ${scan.put_wall.toFixed(0)}</span>}
                {scan.call_wall && <span>Call Wall: ${scan.call_wall.toFixed(0)}</span>}
              </div>
            )}

            {/* Signal Details Row */}
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
              {scan.signal_source && (
                <span>Signal: {scan.signal_source}</span>
              )}
              {scan.signal_confidence && (
                <span>Confidence: {(scan.signal_confidence * 100).toFixed(0)}%</span>
              )}
              {scan.signal_win_probability && (
                <span>Win Prob: {(scan.signal_win_probability * 100).toFixed(0)}%</span>
              )}
              {scan.oracle_advice && (
                <span>Oracle: {scan.oracle_advice}</span>
              )}
            </div>

            {/* Checks Summary (if available) */}
            {scan.checks_performed && scan.checks_performed.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {scan.checks_performed.map((check, i) => (
                  <span
                    key={i}
                    className={`text-xs px-1.5 py-0.5 rounded ${
                      check.passed ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}
                    title={check.reason || `${check.value || 'N/A'}`}
                  >
                    {check.passed ? '✓' : '✗'} {check.check_name}
                  </span>
                ))}
              </div>
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
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Export Button */}
      <div className="mt-4 pt-3 border-t border-gray-700 flex justify-end">
        <button
          onClick={() => {
            const csv = [
              ['Scan #', 'Time', 'Outcome', 'Summary', 'R:R', 'SPY', 'VIX', 'What Would Trigger', 'Market Insight'].join(','),
              ...scans.map(s => [
                s.scan_number,
                s.time_ct,
                s.outcome,
                `"${(s.decision_summary || '').replace(/"/g, '""')}"`,
                s.risk_reward_ratio?.toFixed(2) || '',
                s.underlying_price?.toFixed(2) || '',
                s.vix?.toFixed(1) || '',
                `"${(s.what_would_trigger || '').replace(/"/g, '""')}"`,
                `"${(s.market_insight || '').replace(/"/g, '""')}"`
              ].join(','))
            ].join('\n')
            const blob = new Blob([csv], { type: 'text/csv' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${botName.toLowerCase()}-scan-activity-${new Date().toISOString().split('T')[0]}.csv`
            a.click()
            URL.revokeObjectURL(url)
          }}
          className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded flex items-center gap-1"
        >
          📥 Export CSV
        </button>
      </div>
    </div>
  )
}
