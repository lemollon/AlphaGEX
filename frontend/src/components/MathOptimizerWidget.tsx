'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { api } from '@/lib/api'
import {
  Calculator,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Brain,
  Activity,
  TrendingUp,
  GitBranch,
  Target,
  Layers
} from 'lucide-react'

const fetcher = (url: string) => api.get(url).then(res => res.data)

interface RegimeData {
  current: string
  probability: number
  is_favorable: boolean
}

interface BotAllocation {
  bot: string
  expected_win_rate: number
  allocation_pct: number
  integrated: boolean
}

interface MathOptimizerStatus {
  available: boolean
  optimizers: Record<string, any>
}

interface LiveDashboardData {
  status: string
  regime: RegimeData
  thompson: {
    bot_stats: Record<string, {
      expected_win_rate: number
      uncertainty: number
      allocation_pct: number
      integrated: boolean
    }>
    total_outcomes_recorded: number
  }
  kalman: {
    smoothed_greeks: Record<string, number>
    active: boolean
  }
  optimization_counts: Record<string, number>
}

export default function MathOptimizerWidget() {
  const [expanded, setExpanded] = useState(true)

  const { data: statusData, isLoading, mutate } = useSWR<MathOptimizerStatus>(
    '/api/math-optimizer/status',
    fetcher,
    { refreshInterval: 30000 }
  )

  const { data: liveDashboard } = useSWR<LiveDashboardData>(
    '/api/math-optimizer/live-dashboard',
    fetcher,
    { refreshInterval: 60000 }
  )

  // Live dashboard is the primary data source
  const live = liveDashboard

  // Extract regime from live-dashboard (uses "regime.current", not "regime_detection")
  const regime: RegimeData | undefined = live?.regime
  const kalmanActive = live?.kalman?.active || false

  // Build bot array from thompson.bot_stats
  const botStats = live?.thompson?.bot_stats || {}
  const bots: BotAllocation[] = Object.entries(botStats).map(([name, stats]) => ({
    bot: name,
    expected_win_rate: (stats as any).expected_win_rate || 0.5,
    allocation_pct: ((stats as any).allocation_pct || 0.2) * 100,
    integrated: (stats as any).integrated || false
  }))
  const integratedBots = bots.filter((b: BotAllocation) => b.integrated).length
  const totalDecisions = live?.optimization_counts
    ? Object.values(live.optimization_counts).reduce((sum: number, v: any) => sum + (Number(v) || 0), 0)
    : 0

  // Overall health
  const isAvailable = statusData?.available !== false && live?.status !== 'error'
  const regimeDetected = regime?.current && regime.current !== 'Unknown'

  // Regime colors (match backend format: "Trending Bullish", "Mean Reverting", etc.)
  const getRegimeColor = (regimeName: string): string => {
    const lower = regimeName.toLowerCase()
    if (lower.includes('trending')) return 'text-success'
    if (lower.includes('mean')) return 'text-cyan-400'
    if (lower.includes('high') && lower.includes('vol')) return 'text-warning'
    if (lower.includes('low') && lower.includes('vol')) return 'text-info'
    if (lower.includes('squeeze')) return 'text-danger'
    if (lower.includes('pinned')) return 'text-purple-400'
    return 'text-text-muted'
  }

  if (isLoading) {
    return (
      <div className="card bg-gradient-to-r from-emerald-500/5 to-transparent border border-emerald-500/20 animate-pulse">
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
    <div className="card bg-gradient-to-r from-emerald-500/5 to-transparent border border-emerald-500/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/10">
            <Calculator className="w-5 h-5 text-emerald-500" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary">Math Optimizer</h3>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              {regimeDetected ? (
                <span className={`flex items-center gap-1 ${getRegimeColor(regime?.current || '')}`}>
                  <GitBranch className="w-3 h-3" />
                  {regime?.current}
                </span>
              ) : (
                <span className="flex items-center gap-1 text-text-muted">
                  <Activity className="w-3 h-3" />
                  Initializing
                </span>
              )}
              {regime?.probability && (
                <span className="text-emerald-400">
                  {(regime.probability * 100).toFixed(0)}% conf
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
            className="p-1.5 rounded-lg hover:bg-emerald-500/10 transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-emerald-500" />
          </button>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-emerald-500" />
          ) : (
            <ChevronDown className="w-5 h-5 text-emerald-500" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {/* Algorithm Status */}
          <div className="grid grid-cols-3 gap-2 mb-4">
            <div className={`p-2 rounded-lg border ${
              regimeDetected
                ? 'bg-success/10 border-success/30'
                : 'bg-background-hover border-border/50'
            }`}>
              <div className="flex items-center gap-1 mb-1">
                <GitBranch className="w-3 h-3 text-emerald-400" />
                <span className="text-[10px] text-text-muted">HMM</span>
              </div>
              <div className="text-xs font-medium text-text-primary">
                {regimeDetected ? 'Active' : 'Init'}
              </div>
            </div>
            <div className={`p-2 rounded-lg border ${
              kalmanActive
                ? 'bg-success/10 border-success/30'
                : 'bg-background-hover border-border/50'
            }`}>
              <div className="flex items-center gap-1 mb-1">
                <Activity className="w-3 h-3 text-cyan-400" />
                <span className="text-[10px] text-text-muted">Kalman</span>
              </div>
              <div className="text-xs font-medium text-text-primary">
                {kalmanActive ? 'Active' : 'Init'}
              </div>
            </div>
            <div className={`p-2 rounded-lg border ${
              bots.length > 0
                ? 'bg-success/10 border-success/30'
                : 'bg-background-hover border-border/50'
            }`}>
              <div className="flex items-center gap-1 mb-1">
                <Target className="w-3 h-3 text-purple-400" />
                <span className="text-[10px] text-text-muted">Thompson</span>
              </div>
              <div className="text-xs font-medium text-text-primary">
                {integratedBots} bots
              </div>
            </div>
          </div>

          {/* Regime Display */}
          {regime && (
            <div className={`p-3 rounded-lg mb-4 ${
              regime.is_favorable
                ? 'bg-success/10 border border-success/30'
                : 'bg-warning/10 border border-warning/30'
            }`}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs text-text-muted mb-1">Current Regime</div>
                  <div className={`text-sm font-bold capitalize ${getRegimeColor(regime.current || '')}`}>
                    {regime.current || 'Unknown'}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-text-muted mb-1">Favorable</div>
                  <div className={`text-sm font-bold ${regime.is_favorable ? 'text-success' : 'text-warning'}`}>
                    {regime.is_favorable ? 'Yes' : 'No'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Bot Allocations Preview */}
          {bots.length > 0 && (
            <div className="mb-4">
              <div className="text-xs font-medium text-text-muted mb-2 flex items-center gap-1">
                <Layers className="w-3 h-3" />
                Capital Allocation
              </div>
              <div className="space-y-1">
                {bots.slice(0, 3).map((bot: BotAllocation) => (
                  <div key={bot.bot} className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">{bot.bot}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 bg-background-hover rounded-full overflow-hidden">
                        <div
                          className="h-full bg-emerald-500 rounded-full"
                          style={{ width: `${bot.allocation_pct}%` }}
                        />
                      </div>
                      <span className="text-emerald-400 w-10 text-right">
                        {bot.allocation_pct.toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Stats */}
          <div className="flex items-center justify-between text-xs text-text-muted mb-4">
            <span>Recent Decisions: {totalDecisions}</span>
            <span className="flex items-center gap-1">
              {isAvailable ? (
                <>
                  <CheckCircle className="w-3 h-3 text-success" />
                  System Online
                </>
              ) : (
                <>
                  <XCircle className="w-3 h-3 text-danger" />
                  Unavailable
                </>
              )}
            </span>
          </div>

          {/* Quick Link */}
          <Link
            href="/math-optimizer"
            className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium text-emerald-400 bg-emerald-500/10 rounded-lg hover:bg-emerald-500/20 transition-colors"
          >
            <Calculator className="w-4 h-4" />
            Open Math Optimizer
          </Link>
        </div>
      )}
    </div>
  )
}
