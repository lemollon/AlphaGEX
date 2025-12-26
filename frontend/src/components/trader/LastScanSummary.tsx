'use client'

import { useState } from 'react'
import { RefreshCw, CheckCircle, XCircle, AlertTriangle, Clock, Brain, Zap, Target, ChevronDown, ChevronUp, TrendingUp, TrendingDown } from 'lucide-react'

interface ScanCheck {
  check: string
  passed: boolean
  value?: string
  threshold?: string
  reason?: string
}

interface ScanResult {
  scan_id?: string
  timestamp: string
  outcome: 'TRADED' | 'NO_TRADE' | 'SKIP' | 'ERROR' | string
  decision_summary?: string

  // Signal sources
  ml_signal?: {
    direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | string
    confidence: number
    advice: string
  }
  oracle_signal?: {
    advice: string
    confidence: number
    win_probability: number
  }

  // Override tracking
  override_occurred?: boolean
  override_details?: {
    winner: 'ML' | 'Oracle' | string
    overridden_signal: string
    override_reason: string
  }

  // Checks performed
  checks?: ScanCheck[]

  // Market context at scan
  market_context?: {
    spot_price: number
    vix: number
    gex_regime: string
    put_wall?: number
    call_wall?: number
  }

  // What would trigger
  what_would_trigger?: string
}

interface LastScanSummaryProps {
  botName: 'ARES' | 'ATHENA'
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
                {getTimeAgo(lastScan.timestamp)} • {new Date(lastScan.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
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

          {/* ML vs Oracle Signals - THE KEY INSIGHT */}
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

            {/* Oracle Signal */}
            <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="w-4 h-4 text-purple-400" />
                <span className="text-purple-400 text-sm font-bold">ORACLE SIGNAL</span>
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
                <span className="text-gray-500 text-sm">No Oracle advice</span>
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
                              {check.value} {check.threshold && `(need ${check.threshold})`}
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
