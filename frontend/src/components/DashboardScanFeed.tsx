'use client'

import { useState, useMemo, useCallback, memo } from 'react'
import Link from 'next/link'
import {
  Activity,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  Clock,
  Sword,
  Target,
  Shield,
  AlertTriangle,
  Ban,
  Flame,
  Rocket
} from 'lucide-react'
import { useScanActivityAres, useScanActivityAthena, useScanActivityAnchor, useICARUSScanActivity, useScanActivityTitan } from '@/lib/hooks/useMarketData'

// PERFORMANCE FIX: Move helper functions outside component (no re-creation per render)
const getBotIcon = (botName: string) => {
  switch (botName?.toUpperCase()) {
    case 'FORTRESS':
      return <Sword className="w-4 h-4 text-blue-500" />
    case 'SOLOMON':
      return <Target className="w-4 h-4 text-purple-500" />
    case 'ANCHOR':
      return <Shield className="w-4 h-4 text-amber-500" />
    case 'GIDEON':
      return <Flame className="w-4 h-4 text-cyan-500" />
    case 'SAMSON':
      return <Rocket className="w-4 h-4 text-rose-500" />
    default:
      return <Activity className="w-4 h-4 text-text-muted" />
  }
}

const getOutcomeConfig = (outcome: string, tradeExecuted: boolean) => {
  if (tradeExecuted || outcome === 'TRADED') {
    return {
      icon: <CheckCircle className="w-4 h-4 text-success" />,
      bg: 'bg-success/10',
      border: 'border-success/20',
      text: 'text-success',
      label: 'Traded'
    }
  }
  switch (outcome) {
    case 'NO_TRADE':
    case 'SKIP':
      return {
        icon: <Ban className="w-4 h-4 text-warning" />,
        bg: 'bg-warning/10',
        border: 'border-warning/20',
        text: 'text-warning',
        label: 'Skipped'
      }
    case 'ERROR':
      return {
        icon: <XCircle className="w-4 h-4 text-danger" />,
        bg: 'bg-danger/10',
        border: 'border-danger/20',
        text: 'text-danger',
        label: 'Error'
      }
    case 'MARKET_CLOSED':
    case 'BEFORE_WINDOW':
      return {
        icon: <Clock className="w-4 h-4 text-text-muted" />,
        bg: 'bg-background-hover',
        border: 'border-border',
        text: 'text-text-muted',
        label: outcome.replace(/_/g, ' ')
      }
    default:
      return {
        icon: <Activity className="w-4 h-4 text-text-muted" />,
        bg: 'bg-background-hover',
        border: 'border-border',
        text: 'text-text-muted',
        label: outcome
      }
  }
}

export default function DashboardScanFeed() {
  const [expanded, setExpanded] = useState(false)

  // Live bots
  const { data: aresScans, isLoading: aresLoading, mutate: refreshAres } = useScanActivityAres(10)
  const { data: solomonScans, isLoading: solomonLoading, mutate: refreshAthena } = useScanActivityAthena(10)
  const { data: anchorScans, isLoading: anchorLoading, mutate: refreshAnchor } = useScanActivityAnchor(10)

  // Paper bots
  const { data: icarusScans, isLoading: icarusLoading, mutate: refreshIcarus } = useICARUSScanActivity(10)
  const { data: titanScans, isLoading: titanLoading, mutate: refreshTitan } = useScanActivityTitan(10)

  const isLoading = aresLoading || solomonLoading || anchorLoading || icarusLoading || titanLoading

  // PERFORMANCE FIX: useCallback for refreshAll to prevent child re-renders
  const refreshAll = useCallback(() => {
    refreshAres()
    refreshAthena()
    refreshAnchor()
    refreshIcarus()
    refreshTitan()
  }, [refreshAres, refreshAthena, refreshAnchor, refreshIcarus, refreshTitan])

  // PERFORMANCE FIX: useMemo for allScans array (was creating new arrays every render)
  const allScans = useMemo(() => {
    return [
      ...(aresScans?.data?.scans || []).map((s: any) => ({ ...s, bot: 'FORTRESS' })),
      ...(solomonScans?.data?.scans || []).map((s: any) => ({ ...s, bot: 'SOLOMON' })),
      ...(anchorScans?.data?.scans || []).map((s: any) => ({ ...s, bot: 'ANCHOR' })),
      ...(icarusScans?.data?.scans || []).map((s: any) => ({ ...s, bot: 'GIDEON' })),
      ...(titanScans?.data?.scans || []).map((s: any) => ({ ...s, bot: 'SAMSON' }))
    ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 10)
  }, [aresScans, solomonScans, anchorScans, icarusScans, titanScans])

  // PERFORMANCE FIX: useMemo for stats (single pass instead of 3 filter operations)
  const { tradesCount, skipsCount, errorsCount } = useMemo(() => {
    return allScans.reduce((acc, scan: any) => {
      if (scan.trade_executed || scan.outcome === 'TRADED') {
        acc.tradesCount++
      } else if (scan.outcome === 'NO_TRADE' || scan.outcome === 'SKIP') {
        acc.skipsCount++
      } else if (scan.outcome === 'ERROR') {
        acc.errorsCount++
      }
      return acc
    }, { tradesCount: 0, skipsCount: 0, errorsCount: 0 })
  }, [allScans])

  // Helper functions getBotIcon and getOutcomeConfig moved outside component

  return (
    <div className="card bg-gradient-to-r from-text-muted/5 to-transparent border border-border">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-text-muted/10">
            <Activity className="w-5 h-5 text-text-muted" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary">Recent Scan Activity</h3>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              {isLoading ? (
                <span>Loading...</span>
              ) : (
                <>
                  <span className="text-success">{tradesCount} trades</span>
                  <span>{skipsCount} skips</span>
                  {errorsCount > 0 && (
                    <span className="text-danger">{errorsCount} errors</span>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              refreshAll()
            }}
            className={`p-1.5 rounded-lg hover:bg-background-hover transition-colors ${isLoading ? 'animate-spin' : ''}`}
          >
            <RefreshCw className="w-4 h-4 text-text-muted" />
          </button>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-text-muted" />
          ) : (
            <ChevronDown className="w-5 h-5 text-text-muted" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-16 bg-background-hover animate-pulse rounded-lg" />
              ))}
            </div>
          ) : allScans.length === 0 ? (
            <div className="p-4 bg-background-hover rounded-lg text-center">
              <p className="text-text-muted text-sm">No scan activity today</p>
              <p className="text-text-secondary text-xs mt-1">Bots will scan during market hours</p>
            </div>
          ) : (
            <div className="space-y-2">
              {allScans.map((scan: any, idx: number) => {
                const config = getOutcomeConfig(scan.outcome, scan.trade_executed)
                return (
                  <div
                    key={scan.scan_id || idx}
                    className={`p-3 rounded-lg border ${config.bg} ${config.border}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2 min-w-0">
                        {getBotIcon(scan.bot)}
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-text-primary">{scan.bot}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded ${config.bg} ${config.text}`}>
                              {config.label}
                            </span>
                            {scan.gex_regime && (
                              <span className={`text-xs px-1.5 py-0.5 rounded ${
                                scan.gex_regime === 'POSITIVE' ? 'bg-success/20 text-success' :
                                scan.gex_regime === 'NEGATIVE' ? 'bg-danger/20 text-danger' :
                                'bg-text-muted/20 text-text-muted'
                              }`}>
                                GEX: {scan.gex_regime}
                              </span>
                            )}
                          </div>
                          {scan.decision_summary && (
                            <p className="text-xs text-text-secondary mt-1 break-words line-clamp-2">{scan.decision_summary}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 text-xs text-text-muted flex-shrink-0">
                        <Clock className="w-3 h-3" />
                        {scan.time_ct || (new Date(scan.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true, timeZone: 'America/Chicago' }) + ' CT')}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <Link
            href="/logs"
            className="block mt-3 text-center text-xs text-primary hover:underline"
          >
            View All Activity Logs
          </Link>
        </div>
      )}
    </div>
  )
}
