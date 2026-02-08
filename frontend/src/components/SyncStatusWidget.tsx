'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { api } from '@/lib/api'
import {
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Database,
  Zap,
  Clock,
  Activity
} from 'lucide-react'

const fetcher = (url: string) => api.get(url).then(res => res.data)

interface SyncStatus {
  success: boolean
  data: {
    timestamp: string
    stale_positions: Record<string, number>
    missing_pnl: Record<string, number>
    unified_sync: {
      open_positions?: number
      recent_closed?: number
      error?: string
    }
    recommendations: string[]
  }
}

export default function SyncStatusWidget() {
  const [expanded, setExpanded] = useState(true)
  const [syncing, setSyncing] = useState(false)

  const { data: statusData, isLoading, mutate } = useSWR<SyncStatus>(
    '/api/trader/sync/status',
    fetcher,
    { refreshInterval: 60000 } // Refresh every minute
  )

  const status = statusData?.data

  // Calculate totals
  const totalStale = status?.stale_positions
    ? Object.values(status.stale_positions).reduce((a, b) => a + b, 0)
    : 0
  const totalMissingPnl = status?.missing_pnl
    ? Object.values(status.missing_pnl).reduce((a, b) => a + b, 0)
    : 0

  const hasIssues = totalStale > 0 || totalMissingPnl > 0
  const isHealthy = !hasIssues && statusData?.success

  const runFullSync = async () => {
    setSyncing(true)
    try {
      await api.post('/api/trader/sync/full')
      await mutate()
    } catch (error) {
      console.error('Sync failed:', error)
    } finally {
      setSyncing(false)
    }
  }

  if (isLoading) {
    return (
      <div className="card bg-gradient-to-r from-blue-500/5 to-transparent border border-blue-500/20 animate-pulse">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-background-hover rounded-lg" />
          <div className="flex-1">
            <div className="h-4 w-32 bg-background-hover rounded mb-2" />
            <div className="h-3 w-24 bg-background-hover rounded" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="card bg-gradient-to-r from-blue-500/5 to-transparent border border-blue-500/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-blue-500/10">
            <Database className="w-5 h-5 text-blue-500" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              Trade Sync Status
              {isHealthy && <CheckCircle className="w-3 h-3 text-success" />}
            </h3>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              {isHealthy ? (
                <span className="flex items-center gap-1 text-success">
                  <CheckCircle className="w-3 h-3" />
                  All synced
                </span>
              ) : hasIssues ? (
                <span className="flex items-center gap-1 text-warning">
                  <AlertTriangle className="w-3 h-3" />
                  {totalStale + totalMissingPnl} issues
                </span>
              ) : (
                <span className="flex items-center gap-1 text-text-muted">
                  <Clock className="w-3 h-3" />
                  Checking...
                </span>
              )}
              {status?.unified_sync?.open_positions !== undefined && (
                <span className="text-blue-400">
                  {status.unified_sync.open_positions} open
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              mutate()
            }}
            className="p-1.5 rounded-lg hover:bg-blue-500/10 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 text-blue-500 ${syncing ? 'animate-spin' : ''}`} />
          </button>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-blue-500" />
          ) : (
            <ChevronDown className="w-5 h-5 text-blue-500" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {/* Status Grid */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="p-3 bg-background-hover rounded-lg text-center">
              <div className="text-xs text-text-muted mb-1">Open Positions</div>
              <div className="text-sm font-bold text-text-primary">
                {status?.unified_sync?.open_positions ?? '-'}
              </div>
            </div>
            <div className="p-3 bg-background-hover rounded-lg text-center">
              <div className="text-xs text-text-muted mb-1">Recent Closed</div>
              <div className="text-sm font-bold text-text-primary">
                {status?.unified_sync?.recent_closed ?? '-'}
              </div>
            </div>
            <div className={`p-3 rounded-lg text-center ${
              hasIssues ? 'bg-warning/10' : 'bg-success/10'
            }`}>
              <div className="text-xs text-text-muted mb-1">Issues</div>
              <div className={`text-sm font-bold ${
                hasIssues ? 'text-warning' : 'text-success'
              }`}>
                {totalStale + totalMissingPnl}
              </div>
            </div>
          </div>

          {/* Bot Status Breakdown */}
          {(totalStale > 0 || totalMissingPnl > 0) && (
            <div className="mb-4 space-y-2">
              <div className="text-xs text-text-muted font-medium">Bot Issues:</div>
              <div className="grid grid-cols-5 gap-1">
                {['fortress', 'solomon', 'samson', 'anchor', 'gideon'].map(bot => {
                  const stale = status?.stale_positions?.[bot] || 0
                  const pnl = status?.missing_pnl?.[bot] || 0
                  const botIssues = stale + pnl
                  return (
                    <div
                      key={bot}
                      className={`p-2 rounded text-center ${
                        botIssues > 0 ? 'bg-warning/10' : 'bg-success/10'
                      }`}
                    >
                      <div className="text-[10px] text-text-muted uppercase">{bot}</div>
                      <div className={`text-xs font-bold ${
                        botIssues > 0 ? 'text-warning' : 'text-success'
                      }`}>
                        {botIssues > 0 ? botIssues : '✓'}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {status?.recommendations && status.recommendations.length > 0 && (
            <div className={`p-3 rounded-lg mb-4 ${
              isHealthy
                ? 'bg-success/10 border border-success/30'
                : 'bg-warning/10 border border-warning/30'
            }`}>
              <div className="flex items-start gap-2">
                {isHealthy ? (
                  <CheckCircle className="w-4 h-4 text-success mt-0.5 flex-shrink-0" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-warning mt-0.5 flex-shrink-0" />
                )}
                <div className="text-xs text-text-secondary space-y-1">
                  {status.recommendations.map((rec, i) => (
                    <div key={i}>{rec}</div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Sync Button */}
          <button
            onClick={runFullSync}
            disabled={syncing}
            className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium text-blue-400 bg-blue-500/10 rounded-lg hover:bg-blue-500/20 transition-colors disabled:opacity-50"
          >
            {syncing ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Syncing...
              </>
            ) : (
              <>
                <Zap className="w-4 h-4" />
                Run Full Sync
              </>
            )}
          </button>

          {/* Last Updated */}
          {status?.timestamp && (
            <div className="mt-3 text-[10px] text-text-muted text-center">
              Last checked: {new Date(status.timestamp).toLocaleTimeString()}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
