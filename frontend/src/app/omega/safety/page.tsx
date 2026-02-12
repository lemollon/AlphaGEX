'use client'

import React from 'react'
import {
  Shield, AlertOctagon, AlertTriangle, Lock,
  Activity, TrendingUp, TrendingDown, Minus,
  ChevronLeft, Eye, Power, FileText, RefreshCw
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  useOmegaBots,
  useOmegaCorrelations,
  useOmegaEquityScaling,
  useOmegaAuditLog,
} from '@/lib/hooks/useMarketData'

// ==================== TYPES ====================

interface KillSwitchState {
  db_is_killed: boolean
  is_bot_killed_returns: boolean
  mismatch: boolean
  killed_at?: string
  killed_reason?: string
}

interface ProverbsVerdict {
  consecutive_losses: number
  daily_loss_pct: number
}

interface BotData {
  kill_switch: KillSwitchState
  proverbs_verdict: ProverbsVerdict
  wiring: { wired_to_omega: boolean }
  recent_decisions: Array<{ final_decision: string }>
}

interface CorrelationData {
  correlation_matrix: Record<string, number>
  max_correlation_threshold: number
  active_positions_by_direction?: {
    bullish: number
    bearish: number
    neutral: number
  }
}

interface EquityScalingData {
  equity_scaling: {
    current_equity: number
    high_water_mark: number
    current_drawdown_pct: number
    multiplier: number
    note?: string
  }
}

interface AuditEntry {
  created_at: string
  action_type: string
  bot_name: string
  actor?: string
  action_description?: string
  reason?: string
}

// ==================== CONSTANTS ====================

const BOTS = ['FORTRESS', 'ANCHOR', 'SOLOMON', 'LAZARUS', 'CORNERSTONE'] as const

const STRATEGY_MAP: Record<string, string> = {
  FORTRESS: 'SPY 0DTE Iron Condor',
  ANCHOR: 'SPX Weekly Iron Condor',
  SOLOMON: 'SPY Directional',
  LAZARUS: 'SPY Call Entries',
  CORNERSTONE: 'SPY Cash-Secured Puts',
}

const ACTION_COLORS: Record<string, string> = {
  MANUAL_KILL: 'text-red-400 bg-red-500/10',
  MANUAL_REVIVE: 'text-green-400 bg-green-500/10',
  EMERGENCY_KILL_ALL: 'text-red-400 bg-red-500/20',
  AUTO_KILL: 'text-orange-400 bg-orange-500/10',
  SYSTEM: 'text-blue-400 bg-blue-500/10',
}

// ==================== KILL SWITCH CARD (REMOVED) ====================

const KillSwitchCard = ({
  botName,
}: {
  botName: string
  botData?: BotData | undefined
  onKill?: (bot: string) => void
  onRevive?: (bot: string) => void
}) => {
  return (
    <div className="bg-background-card border border-gray-700 rounded-xl p-5 shadow-card transition-all">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-bold text-text-primary">{botName}</h3>
          <p className="text-xs text-text-secondary">{STRATEGY_MAP[botName] || 'Unknown Strategy'}</p>
        </div>
        <div className="px-3 py-1.5 rounded-full text-xs font-semibold bg-gray-500/15 text-gray-400 border border-gray-500/30">
          REMOVED
        </div>
      </div>

      {/* Removed Notice */}
      <div className="p-3 bg-gray-800/50 rounded-lg text-center">
        <p className="text-sm text-text-secondary">
          Kill switches have been removed.
        </p>
        <p className="text-xs text-text-secondary/70 mt-1">
          All bots always trade. Oracle controls trade frequency.
        </p>
      </div>
    </div>
  )
}

// ==================== CORRELATION PAIR ROW ====================

const CorrelationRow = ({ pair, value }: { pair: string; value: number }) => {
  const absVal = Math.abs(value)
  const isHigh = absVal > 0.7
  const isMedium = absVal > 0.3

  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="text-xs text-text-secondary w-44 truncate font-mono">
        {pair.replace(':', ' vs ')}
      </span>
      <div className="flex-1 bg-gray-700 rounded-full h-2 relative">
        <div
          className={`rounded-full h-2 transition-all ${
            isHigh ? 'bg-red-500' : isMedium ? 'bg-yellow-500' : 'bg-green-500'
          }`}
          style={{ width: `${absVal * 100}%` }}
        />
      </div>
      <span
        className={`text-xs font-mono w-14 text-right font-medium ${
          isHigh ? 'text-red-400' : isMedium ? 'text-yellow-400' : 'text-green-400'
        }`}
      >
        {value.toFixed(3)}
      </span>
      {isHigh && (
        <AlertTriangle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
      )}
    </div>
  )
}

// ==================== AUDIT LOG TABLE ====================

const AuditLogTable = ({ entries }: { entries: AuditEntry[] }) => {
  const getActionIcon = (action: string) => {
    switch (action) {
      case 'MANUAL_KILL':
        return <Lock className="w-3.5 h-3.5" />
      case 'MANUAL_REVIVE':
        return <Power className="w-3.5 h-3.5" />
      case 'EMERGENCY_KILL_ALL':
        return <AlertOctagon className="w-3.5 h-3.5" />
      default:
        return <Activity className="w-3.5 h-3.5" />
    }
  }

  if (!entries || entries.length === 0) {
    return (
      <div className="text-center py-8 text-text-secondary text-sm">
        No audit log entries found.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-700 bg-gray-800/50">
            <th className="text-left p-3 text-text-secondary font-medium w-44">Timestamp</th>
            <th className="text-left p-3 text-text-secondary font-medium w-40">Action</th>
            <th className="text-left p-3 text-text-secondary font-medium w-32">Bot</th>
            <th className="text-left p-3 text-text-secondary font-medium">Details</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, i) => {
            const actionStyle = ACTION_COLORS[entry.action_type] || 'text-gray-400 bg-gray-500/10'
            return (
              <tr key={i} className="border-b border-gray-700/50 hover:bg-gray-800/30">
                <td className="p-3 text-text-secondary font-mono">
                  {new Date(entry.created_at).toLocaleString()}
                </td>
                <td className="p-3">
                  <span
                    className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium ${actionStyle}`}
                  >
                    {getActionIcon(entry.action_type)}
                    {entry.action_type}
                  </span>
                </td>
                <td className="p-3 text-text-primary font-medium">
                  {entry.bot_name || 'ALL'}
                </td>
                <td className="p-3 text-text-secondary max-w-md truncate">
                  {entry.reason || entry.action_description || '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ==================== MAIN PAGE ====================

export default function OmegaSafetyPage() {
  const sidebarPadding = useSidebarPadding()
  const { data: botsData, isLoading: botsLoading, mutate: mutateBots } = useOmegaBots()
  const { data: correlationData } = useOmegaCorrelations()
  const { data: equityData } = useOmegaEquityScaling()
  const { data: auditData, mutate: mutateAudit } = useOmegaAuditLog(50)

  // Derive data
  const bots: Record<string, BotData> = botsData?.bots || {}
  const correlations: CorrelationData = correlationData || {
    correlation_matrix: {},
    max_correlation_threshold: 0.7,
  }
  const equityScaling = (equityData as EquityScalingData | undefined)?.equity_scaling || null
  const auditEntries: AuditEntry[] = auditData?.entries || auditData?.audit_log || []

  // Kill switches removed - counts are always 0
  const mismatchCount = 0
  const killedCount = 0

  // Direction counts from correlation data
  const directions = correlations.active_positions_by_direction || {
    bullish: 0,
    bearish: 0,
    neutral: 0,
  }

  return (
    <div className="min-h-screen bg-background-deep text-text-primary">
      <Navigation />
      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Back Link + Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <a
              href="/omega"
              className="inline-flex items-center gap-1 text-xs text-text-secondary hover:text-blue-400 transition-colors mb-2"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              Back to OMEGA Dashboard
            </a>
            <div className="flex items-center gap-3">
              <Shield className="w-7 h-7 text-cyan-400" />
              <h1 className="text-2xl font-bold">Safety &amp; Risk</h1>
            </div>
            <p className="text-sm text-text-secondary mt-1">
              Risk metrics, correlations, and audit trail
            </p>
          </div>
        </div>

        {/* ==================== KILL SWITCH REMOVED BANNER ==================== */}
        <div className="mb-6 p-4 bg-gray-500/10 border border-gray-500/30 rounded-lg">
          <div className="flex items-start gap-3">
            <Shield className="w-5 h-5 text-gray-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="text-sm font-bold text-gray-400 mb-1">
                Kill Switches Removed
              </div>
              <p className="text-xs text-gray-400/80 leading-relaxed">
                Kill switches have been removed from the backend. All bots always trade.
                Oracle now controls trade frequency and risk decisions.
              </p>
            </div>
          </div>
        </div>

        {/* ==================== KILL SWITCH DASHBOARD (REMOVED) ==================== */}
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Lock className="w-5 h-5 text-gray-500" />
          Kill Switch Dashboard
          <span className="text-xs text-text-secondary font-normal ml-2">
            Removed — all bots always trade
          </span>
        </h2>

        {botsLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-8">
            {BOTS.map((name) => (
              <div
                key={name}
                className="bg-background-card border border-gray-700 rounded-xl p-5 shadow-card animate-pulse"
              >
                <div className="h-6 bg-gray-700 rounded w-24 mb-3" />
                <div className="h-4 bg-gray-700 rounded w-32 mb-4" />
                <div className="h-20 bg-gray-700/50 rounded mb-3" />
                <div className="h-10 bg-gray-700 rounded" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-8">
            {BOTS.map((name) => (
              <KillSwitchCard
                key={name}
                botName={name}
              />
            ))}
          </div>
        )}

        {/* ==================== RISK METRICS PANEL ==================== */}
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-cyan-400" />
          Risk Metrics
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Pairwise Correlations */}
          <div className="lg:col-span-2 bg-background-card border border-gray-700 rounded-lg p-5 shadow-card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-cyan-400" />
                Bot Pairwise Correlations
              </h3>
              <div className="text-xs text-text-secondary">
                Max threshold:{' '}
                <span
                  className={`font-mono font-medium ${
                    correlations.max_correlation_threshold
                      ? 'text-yellow-400'
                      : 'text-text-primary'
                  }`}
                >
                  {((correlations.max_correlation_threshold || 0.7) * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            {correlations.correlation_matrix &&
            Object.keys(correlations.correlation_matrix).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(correlations.correlation_matrix)
                  .sort(([, a], [, b]) => Math.abs(b as number) - Math.abs(a as number))
                  .map(([pair, value]) => (
                    <CorrelationRow key={pair} pair={pair} value={value as number} />
                  ))}
              </div>
            ) : (
              <div className="text-center py-6 text-text-secondary text-sm">
                No correlation data available. Bots may not have overlapping trade history.
              </div>
            )}

            {/* High correlation warning */}
            {Object.values(correlations.correlation_matrix || {}).some(
              (v) => Math.abs(v as number) > (correlations.max_correlation_threshold || 0.7)
            ) && (
              <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                <div className="flex items-center gap-2 text-red-400 text-xs font-medium">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  One or more bot pairs exceed the {((correlations.max_correlation_threshold || 0.7) * 100).toFixed(0)}% correlation threshold.
                  Highly correlated bots amplify drawdown risk.
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Direction Breakdown + Equity Scaling */}
          <div className="space-y-6">
            {/* Active Positions by Direction */}
            <div className="bg-background-card border border-gray-700 rounded-lg p-5 shadow-card">
              <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
                <Eye className="w-4 h-4 text-purple-400" />
                Active Positions by Direction
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-green-400" />
                    <span className="text-xs text-text-secondary">Bullish</span>
                  </div>
                  <span className="text-lg font-bold text-green-400">{directions.bullish}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <TrendingDown className="w-4 h-4 text-red-400" />
                    <span className="text-xs text-text-secondary">Bearish</span>
                  </div>
                  <span className="text-lg font-bold text-red-400">{directions.bearish}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Minus className="w-4 h-4 text-gray-400" />
                    <span className="text-xs text-text-secondary">Neutral (IC)</span>
                  </div>
                  <span className="text-lg font-bold text-text-primary">{directions.neutral}</span>
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-gray-700">
                <div className="text-xs text-text-secondary">
                  Total open:{' '}
                  <span className="text-text-primary font-medium">
                    {directions.bullish + directions.bearish + directions.neutral}
                  </span>
                </div>
              </div>
            </div>

            {/* Equity Scaling */}
            <div className="bg-background-card border border-gray-700 rounded-lg p-5 shadow-card">
              <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
                <Activity className="w-4 h-4 text-green-400" />
                Equity Scaling
              </h3>
              {equityScaling ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-text-secondary">Current Equity</span>
                    <span className="text-sm font-bold text-text-primary font-mono">
                      ${equityScaling.current_equity.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-text-secondary">High Water Mark</span>
                    <span className="text-sm font-bold text-text-primary font-mono">
                      ${equityScaling.high_water_mark.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-text-secondary">Current Drawdown</span>
                    <span
                      className={`text-sm font-bold font-mono ${
                        equityScaling.current_drawdown_pct > 10
                          ? 'text-red-400'
                          : equityScaling.current_drawdown_pct > 5
                          ? 'text-yellow-400'
                          : 'text-green-400'
                      }`}
                    >
                      {equityScaling.current_drawdown_pct > 0
                        ? `-${equityScaling.current_drawdown_pct.toFixed(2)}%`
                        : '0.00%'}
                    </span>
                  </div>
                  {/* Drawdown visual bar */}
                  <div className="bg-gray-700 rounded-full h-2">
                    <div
                      className={`rounded-full h-2 transition-all ${
                        equityScaling.current_drawdown_pct > 10
                          ? 'bg-red-500'
                          : equityScaling.current_drawdown_pct > 5
                          ? 'bg-yellow-500'
                          : 'bg-green-500'
                      }`}
                      style={{
                        width: `${Math.min(equityScaling.current_drawdown_pct * 5, 100)}%`,
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-gray-700">
                    <span className="text-xs text-text-secondary">Size Multiplier</span>
                    <span
                      className={`text-lg font-bold font-mono ${
                        equityScaling.multiplier < 0.5
                          ? 'text-red-400'
                          : equityScaling.multiplier < 1.0
                          ? 'text-yellow-400'
                          : 'text-green-400'
                      }`}
                    >
                      {equityScaling.multiplier.toFixed(2)}x
                    </span>
                  </div>
                  {equityScaling.note && (
                    <p className="text-[10px] text-yellow-400/70 italic">{equityScaling.note}</p>
                  )}
                </div>
              ) : (
                <div className="text-center py-4 text-text-secondary text-sm">
                  No equity scaling data available.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ==================== AUDIT LOG ==================== */}
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FileText className="w-5 h-5 text-yellow-400" />
          Audit Log
          <span className="text-xs text-text-secondary font-normal ml-2">
            {auditEntries.length} entries
          </span>
          <button
            onClick={() => mutateAudit()}
            className="ml-auto text-text-secondary hover:text-blue-400 transition-colors"
            title="Refresh audit log"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </h2>

        <div className="bg-background-card border border-gray-700 rounded-lg shadow-card overflow-hidden mb-6">
          <AuditLogTable entries={auditEntries} />
        </div>

        </div>
      </main>
    </div>
  )
}
