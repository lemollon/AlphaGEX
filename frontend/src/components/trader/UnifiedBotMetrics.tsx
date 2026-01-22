'use client'

/**
 * Unified Bot Metrics Component
 *
 * This component provides consistent, authoritative metrics display for all trading bots.
 * It uses the unified metrics API which is THE single source of truth.
 *
 * Key features:
 * - Consistent starting capital (from database/Tradier/default)
 * - All stats calculated server-side (never frontend calculations)
 * - Win rate displayed as percentage (0-100), not decimal
 * - Historical and intraday charts aligned
 *
 * Usage:
 * <UnifiedBotMetrics botName="ARES" />
 *
 * Created: January 2025
 * Purpose: Fix data reconciliation issues in bot frontends
 */

import { useState } from 'react'
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Target,
  Activity,
  Crosshair,
  AlertTriangle,
  CheckCircle,
  Info,
  RefreshCw,
  Settings,
} from 'lucide-react'
import {
  useUnifiedBotSummary,
  useUnifiedBotCapital,
  useUnifiedReconcile,
  BotMetricsSummary,
  BotCapitalConfig,
} from '@/lib/hooks/useMarketData'

// =============================================================================
// TYPES
// =============================================================================

interface UnifiedBotMetricsProps {
  botName: 'ARES' | 'ATHENA' | 'ICARUS' | 'TITAN' | 'PEGASUS'
  showCapitalSource?: boolean
  showReconciliation?: boolean
  compact?: boolean
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

function formatPercent(value: number, decimals: number = 1): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`
}

// Bot brand colors
const BOT_COLORS: Record<string, { primary: string; light: string; dark: string }> = {
  ARES: { primary: 'amber', light: 'amber-400', dark: 'amber-600' },
  ATHENA: { primary: 'cyan', light: 'cyan-400', dark: 'cyan-600' },
  ICARUS: { primary: 'orange', light: 'orange-400', dark: 'orange-600' },
  TITAN: { primary: 'violet', light: 'violet-400', dark: 'violet-600' },
  PEGASUS: { primary: 'blue', light: 'blue-400', dark: 'blue-600' },
}

// =============================================================================
// STAT CARD COMPONENT
// =============================================================================

interface StatCardProps {
  label: string
  value: string
  subValue?: string
  icon: React.ReactNode
  color: 'green' | 'red' | 'yellow' | 'gray' | 'amber' | 'cyan' | 'orange' | 'violet' | 'blue'
  tooltip?: string
}

function StatCard({ label, value, subValue, icon, color, tooltip }: StatCardProps) {
  const colorClasses = {
    green: 'text-green-400 bg-green-500/10 border-green-500/30',
    red: 'text-red-400 bg-red-500/10 border-red-500/30',
    yellow: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
    gray: 'text-gray-400 bg-gray-500/10 border-gray-500/30',
    amber: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    cyan: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
    orange: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
    violet: 'text-violet-400 bg-violet-500/10 border-violet-500/30',
    blue: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  }

  return (
    <div
      className={`rounded-lg border p-4 ${colorClasses[color]}`}
      title={tooltip}
    >
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-gray-400 text-sm">{label}</span>
      </div>
      <div className={`text-xl font-bold ${colorClasses[color].split(' ')[0]}`}>
        {value}
      </div>
      {subValue && (
        <div className="text-xs text-gray-500 mt-1">{subValue}</div>
      )}
    </div>
  )
}

// =============================================================================
// CAPITAL SOURCE BADGE
// =============================================================================

function CapitalSourceBadge({ config }: { config: BotCapitalConfig }) {
  const sourceInfo = {
    database: {
      label: 'Database Config',
      color: 'text-green-400 bg-green-500/20',
      icon: <CheckCircle className="w-3 h-3" />,
    },
    tradier: {
      label: 'Tradier Balance',
      color: 'text-blue-400 bg-blue-500/20',
      icon: <Info className="w-3 h-3" />,
    },
    default: {
      label: 'Default',
      color: 'text-yellow-400 bg-yellow-500/20',
      icon: <AlertTriangle className="w-3 h-3" />,
    },
  }

  const info = sourceInfo[config.capital_source] || sourceInfo.default

  return (
    <div className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs ${info.color}`}>
      {info.icon}
      <span>{info.label}</span>
      {config.capital_source === 'default' && (
        <span className="ml-1 opacity-70">(Configure to fix)</span>
      )}
    </div>
  )
}

// =============================================================================
// RECONCILIATION STATUS
// =============================================================================

function ReconciliationStatus({ botName }: { botName: string }) {
  const { data, isLoading } = useUnifiedReconcile(botName)

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 text-sm">
        <RefreshCw className="w-4 h-4 animate-spin" />
        <span>Checking data consistency...</span>
      </div>
    )
  }

  const result = data?.data
  if (!result) return null

  const criticalIssues = result.issues?.filter((i: any) => i.severity === 'critical') || []
  const warningIssues = result.issues?.filter((i: any) => i.severity === 'warning') || []
  const infoIssues = result.issues?.filter((i: any) => i.severity === 'info') || []

  if (result.is_consistent && result.issues?.length === 0) {
    return (
      <div className="flex items-center gap-2 text-green-400 text-sm">
        <CheckCircle className="w-4 h-4" />
        <span>Data is consistent</span>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {criticalIssues.length > 0 && (
        <div className="flex items-start gap-2 text-red-400 text-sm">
          <AlertTriangle className="w-4 h-4 mt-0.5" />
          <div>
            <span className="font-medium">Critical Issues:</span>
            {criticalIssues.map((issue: any, i: number) => (
              <div key={i} className="text-xs opacity-80">{issue.message}</div>
            ))}
          </div>
        </div>
      )}
      {warningIssues.length > 0 && (
        <div className="flex items-start gap-2 text-yellow-400 text-sm">
          <AlertTriangle className="w-4 h-4 mt-0.5" />
          <div>
            <span className="font-medium">Warnings:</span>
            {warningIssues.map((issue: any, i: number) => (
              <div key={i} className="text-xs opacity-80">{issue.message}</div>
            ))}
          </div>
        </div>
      )}
      {infoIssues.length > 0 && (
        <div className="flex items-start gap-2 text-gray-400 text-sm">
          <Info className="w-4 h-4 mt-0.5" />
          <div>
            {infoIssues.map((issue: any, i: number) => (
              <div key={i} className="text-xs opacity-80">{issue.message}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function UnifiedBotMetrics({
  botName,
  showCapitalSource = true,
  showReconciliation = false,
  compact = false,
}: UnifiedBotMetricsProps) {
  const { data: summaryData, error: summaryError, isLoading: summaryLoading, mutate: refreshSummary } = useUnifiedBotSummary(botName)
  const { data: capitalData } = useUnifiedBotCapital(botName)

  const summary: BotMetricsSummary | null = summaryData?.data || null
  const capitalConfig: BotCapitalConfig | null = capitalData?.data || null

  const botColor = BOT_COLORS[botName]?.primary || 'gray'

  if (summaryLoading) {
    return (
      <div className="animate-pulse">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-24 bg-gray-800 rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  if (summaryError || !summary) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5" />
          <span>Failed to load {botName} metrics</span>
        </div>
      </div>
    )
  }

  // Determine colors based on values
  const pnlColor = summary.total_pnl >= 0 ? 'green' : 'red'
  const winRateColor = summary.win_rate >= 60 ? 'green' : summary.win_rate >= 50 ? 'yellow' : 'red'
  const todayPnlColor = summary.today_pnl >= 0 ? 'green' : 'red'

  return (
    <div className="space-y-4">
      {/* Capital Source Info */}
      {showCapitalSource && capitalConfig && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-gray-400 text-sm">Capital Source:</span>
            <CapitalSourceBadge config={capitalConfig} />
          </div>
          <button
            onClick={() => refreshSummary()}
            className="flex items-center gap-1 text-gray-400 hover:text-white text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Refresh</span>
          </button>
        </div>
      )}

      {/* Main Stats Grid */}
      <div className={`grid ${compact ? 'grid-cols-3' : 'grid-cols-2 md:grid-cols-5'} gap-4`}>
        <StatCard
          label="Current Equity"
          value={formatCurrency(summary.current_equity)}
          subValue={`Started: ${formatCurrency(summary.starting_capital)}`}
          icon={<DollarSign className="w-4 h-4" />}
          color={botColor as any}
          tooltip={`Starting capital from ${summary.capital_source}`}
        />
        <StatCard
          label="Total P&L"
          value={`${summary.total_pnl >= 0 ? '+' : ''}${formatCurrency(summary.total_pnl)}`}
          subValue={formatPercent(summary.total_return_pct)}
          icon={summary.total_pnl >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          color={pnlColor}
          tooltip={`Realized: ${formatCurrency(summary.total_realized_pnl)} | Unrealized: ${formatCurrency(summary.total_unrealized_pnl)}`}
        />
        <StatCard
          label="Win Rate"
          value={`${summary.win_rate.toFixed(1)}%`}
          subValue={`${summary.winning_trades}W / ${summary.losing_trades}L`}
          icon={<Target className="w-4 h-4" />}
          color={winRateColor}
          tooltip="Calculated from all closed trades (server-side)"
        />
        <StatCard
          label="Total Trades"
          value={summary.total_trades.toString()}
          subValue={`${summary.open_positions} open`}
          icon={<Activity className="w-4 h-4" />}
          color={botColor as any}
        />
        {!compact && (
          <StatCard
            label="Today's P&L"
            value={`${summary.today_pnl >= 0 ? '+' : ''}${formatCurrency(summary.today_pnl)}`}
            subValue={`Realized: ${formatCurrency(summary.today_realized_pnl)}`}
            icon={<Crosshair className="w-4 h-4" />}
            color={todayPnlColor}
            tooltip="Includes both realized and unrealized P&L for today"
          />
        )}
      </div>

      {/* Additional Stats */}
      {!compact && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <span className="text-gray-500 text-xs">Max Drawdown</span>
            <div className="text-red-400 font-bold">{summary.max_drawdown_pct.toFixed(1)}%</div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <span className="text-gray-500 text-xs">High Water Mark</span>
            <div className="text-white font-bold">{formatCurrency(summary.high_water_mark)}</div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <span className="text-gray-500 text-xs">Unrealized P&L</span>
            <div className={`font-bold ${summary.total_unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatCurrency(summary.total_unrealized_pnl)}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <span className="text-gray-500 text-xs">Open Positions</span>
            <div className="text-white font-bold">{summary.open_positions}</div>
          </div>
        </div>
      )}

      {/* Reconciliation Status */}
      {showReconciliation && (
        <div className="bg-gray-800/30 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Settings className="w-4 h-4 text-gray-400" />
            <span className="text-gray-400 text-sm font-medium">Data Consistency Check</span>
          </div>
          <ReconciliationStatus botName={botName} />
        </div>
      )}

      {/* Data Source Note */}
      <div className="text-xs text-gray-600 text-center">
        All metrics calculated server-side from database aggregates.
        Last updated: {new Date(summary.calculated_at).toLocaleTimeString()}
      </div>
    </div>
  )
}

// =============================================================================
// EXPORTS
// =============================================================================

export { StatCard, CapitalSourceBadge, ReconciliationStatus }
