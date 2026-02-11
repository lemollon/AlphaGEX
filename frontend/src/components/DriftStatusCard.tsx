'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { api } from '@/lib/api'
import {
  Activity,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Info,
  ChevronDown,
  ChevronUp,
  Zap
} from 'lucide-react'

const fetcher = (url: string) => api.get(url).then(res => res.data)

interface DriftMetric {
  metric: string
  backtest: number
  live: number
  drift_pct: number
  severity: string
}

interface DriftReport {
  bot_name: string
  backtest_trades: number
  live_trades: number
  metrics: DriftMetric[]
  overall_severity: string
  recommendations: string[]
  analysis_date: string
}

interface DriftStatusCardProps {
  botName: string
  compact?: boolean
}

const severityConfig = {
  OUTPERFORM: {
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30',
    icon: TrendingUp,
    label: 'Outperforming'
  },
  NORMAL: {
    color: 'text-success',
    bgColor: 'bg-success/10',
    borderColor: 'border-success/30',
    icon: CheckCircle,
    label: 'On Track'
  },
  WARNING: {
    color: 'text-warning',
    bgColor: 'bg-warning/10',
    borderColor: 'border-warning/30',
    icon: AlertTriangle,
    label: 'Warning'
  },
  CRITICAL: {
    color: 'text-danger',
    bgColor: 'bg-danger/10',
    borderColor: 'border-danger/30',
    icon: XCircle,
    label: 'Critical'
  }
}

export default function DriftStatusCard({ botName, compact = false }: DriftStatusCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [showInfo, setShowInfo] = useState(false)

  const { data, error, isLoading } = useSWR<{ status: string; data?: DriftReport }>(
    `/api/drift/bot/${botName}`,
    fetcher,
    { refreshInterval: 300000 } // Refresh every 5 minutes
  )

  // Loading state
  if (isLoading) {
    return (
      <div className="card bg-background-secondary border border-border/50 animate-pulse">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-background-hover rounded-lg" />
          <div className="flex-1">
            <div className="h-4 w-24 bg-background-hover rounded mb-2" />
            <div className="h-3 w-32 bg-background-hover rounded" />
          </div>
        </div>
      </div>
    )
  }

  // Error or no data state — guard against missing data.data to prevent crash
  if (error || !data || data.status === 'no_data' || data.status === 'unavailable' || !data.data || !data.data.metrics) {
    return (
      <div className="card bg-background-secondary border border-border/50">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-background-hover">
            <Activity className="w-4 h-4 text-text-muted" />
          </div>
          <div>
            <h4 className="text-sm font-medium text-text-primary">Performance Drift</h4>
            <p className="text-xs text-text-muted">
              {data?.status === 'no_data'
                ? 'Insufficient data for analysis'
                : 'Drift detection unavailable'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const report = data.data
  const config = severityConfig[report.overall_severity as keyof typeof severityConfig] || severityConfig.NORMAL
  const Icon = config.icon

  // Find the main expectancy drift for display
  const expectancyMetric = report.metrics.find(m => m.metric === 'Expectancy %')
  const mainDrift = expectancyMetric?.drift_pct || 0

  return (
    <div className={`card ${config.bgColor} border ${config.borderColor}`}>
      {/* Header - always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${config.bgColor}`}>
            <Icon className={`w-4 h-4 ${config.color}`} />
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-medium text-text-primary">Performance Drift</h4>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setShowInfo(!showInfo)
                }}
                className="p-0.5 rounded hover:bg-background-hover"
              >
                <Info className="w-3 h-3 text-text-muted" />
              </button>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className={config.color}>{config.label}</span>
              <span className="text-text-muted">|</span>
              <span className={mainDrift > 0 ? 'text-danger' : 'text-success'}>
                {mainDrift > 0 ? '+' : ''}{mainDrift.toFixed(1)}% vs backtest
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted">
            {report.live_trades} trades
          </span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-text-muted" />
          ) : (
            <ChevronDown className="w-4 h-4 text-text-muted" />
          )}
        </div>
      </button>

      {/* Info tooltip */}
      {showInfo && (
        <div className="mt-3 p-3 bg-background-hover rounded-lg border border-border/50 text-xs text-text-secondary">
          <p className="font-medium text-text-primary mb-2">What is Performance Drift?</p>
          <p className="mb-2">
            Drift compares your <strong>live trading results</strong> to what the <strong>backtest predicted</strong>.
          </p>
          <ul className="space-y-1 ml-3">
            <li><span className="text-success">Outperforming:</span> Doing better than backtest expected</li>
            <li><span className="text-success">On Track:</span> Within 20% of backtest expectations</li>
            <li><span className="text-warning">Warning:</span> 20-40% worse than backtest</li>
            <li><span className="text-danger">Critical:</span> 40%+ worse - investigate immediately</li>
          </ul>
          <p className="mt-2 text-text-muted">
            High drift may indicate: market regime change, overfitted backtest, or execution issues.
          </p>
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/30 animate-fade-in">
          {/* Metrics grid */}
          <div className="grid grid-cols-2 gap-2 mb-4">
            {report.metrics.map((metric) => {
              const metricSeverity = severityConfig[metric.severity as keyof typeof severityConfig] || severityConfig.NORMAL
              return (
                <div
                  key={metric.metric}
                  className="p-2 rounded-lg bg-background-secondary border border-border/30"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-text-muted uppercase tracking-wide">
                      {metric.metric}
                    </span>
                    <span className={`text-[10px] ${metricSeverity.color}`}>
                      {metric.drift_pct > 0 ? '+' : ''}{metric.drift_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">
                      BT: {metric.backtest.toFixed(1)}
                    </span>
                    <span className="text-text-muted">vs</span>
                    <span className="text-text-primary font-medium">
                      Live: {metric.live.toFixed(1)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Trade counts */}
          <div className="flex items-center justify-between text-xs text-text-muted mb-3">
            <span>Backtest: {report.backtest_trades} trades</span>
            <span>Live: {report.live_trades} trades (90 days)</span>
          </div>

          {/* Recommendations */}
          {report.recommendations.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-text-primary flex items-center gap-1">
                <Zap className="w-3 h-3" />
                Recommendations
              </div>
              {report.recommendations.slice(0, 3).map((rec, i) => (
                <div
                  key={i}
                  className="text-xs text-text-secondary p-2 rounded bg-background-secondary border-l-2 border-info"
                >
                  {rec}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
