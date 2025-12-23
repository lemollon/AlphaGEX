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
  underlying_price?: number
  vix?: number
  signal_source?: string
  signal_direction?: string
  signal_confidence?: number
  signal_win_probability?: number
  oracle_advice?: string
  trade_executed: boolean
  checks_performed?: Array<{
    check_name: string
    passed: boolean
    value?: string
    reason?: string
  }>
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
                    <span className="text-sm text-gray-400">{scan.time_ct}</span>
                    {scan.signal_direction && getDirectionIcon(scan.signal_direction)}
                  </div>
                  <p className="text-sm text-gray-300 mt-0.5">
                    {scan.decision_summary}
                  </p>
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

            {/* Details Row */}
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
              {scan.underlying_price && (
                <span>SPY: ${scan.underlying_price.toFixed(2)}</span>
              )}
              {scan.vix && (
                <span>VIX: {scan.vix.toFixed(1)}</span>
              )}
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
                {scan.checks_performed.slice(0, 5).map((check, i) => (
                  <span
                    key={i}
                    className={`text-xs px-1.5 py-0.5 rounded ${
                      check.passed ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}
                  >
                    {check.passed ? '\u2713' : '\u2717'} {check.check_name}
                  </span>
                ))}
              </div>
            )}

            {/* Full Reasoning (expandable in future) */}
            {scan.full_reasoning && (
              <p className="mt-2 text-xs text-gray-500 line-clamp-2">
                {scan.full_reasoning}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
