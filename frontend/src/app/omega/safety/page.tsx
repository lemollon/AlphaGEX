'use client'

import React, { useState } from 'react'
import {
  Shield, AlertOctagon, AlertTriangle, Lock,
  Activity, TrendingUp, TrendingDown, Minus,
  ChevronLeft, Eye, Power, FileText, RefreshCw
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
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

// ==================== KILL SWITCH CARD ====================

const KillSwitchCard = ({
  botName,
  botData,
  onKill,
  onRevive,
}: {
  botName: string
  botData: BotData | undefined
  onKill: (bot: string) => void
  onRevive: (bot: string) => void
}) => {
  const killSwitch = botData?.kill_switch || {
    db_is_killed: false,
    is_bot_killed_returns: false,
    mismatch: false,
  }
  const verdict = botData?.proverbs_verdict || {
    consecutive_losses: 0,
    daily_loss_pct: 0,
  }
  const hasMismatch = killSwitch.mismatch === true
  const dbKilled = killSwitch.db_is_killed === true
  const fnReturns = killSwitch.is_bot_killed_returns === true

  return (
    <div
      className={`bg-background-card border rounded-xl p-5 shadow-card transition-all ${
        hasMismatch
          ? 'border-red-500/60 ring-2 ring-red-500/20'
          : dbKilled
          ? 'border-red-500/30'
          : 'border-gray-700'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-bold text-text-primary">{botName}</h3>
          <p className="text-xs text-text-secondary">{STRATEGY_MAP[botName] || 'Unknown Strategy'}</p>
        </div>
        <div
          className={`px-3 py-1.5 rounded-full text-xs font-semibold ${
            dbKilled
              ? 'bg-red-500/15 text-red-400 border border-red-500/30'
              : 'bg-green-500/15 text-green-400 border border-green-500/30'
          }`}
        >
          {dbKilled ? 'KILLED' : 'ACTIVE'}
        </div>
      </div>

      {/* Mismatch Warning */}
      {hasMismatch && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/40 rounded-lg">
          <div className="flex items-center gap-2 text-red-400 font-bold text-sm mb-1">
            <AlertOctagon className="w-4 h-4 flex-shrink-0" />
            KILL SWITCH MISMATCH
          </div>
          <p className="text-xs text-red-300/80 leading-relaxed">
            Database says <span className="font-mono font-bold">is_killed = TRUE</span> but{' '}
            <span className="font-mono font-bold">is_bot_killed()</span> returns{' '}
            <span className="font-mono font-bold">FALSE</span>.
            Bot continues trading despite being &quot;killed&quot;.
          </p>
        </div>
      )}

      {/* Kill Switch State Grid */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-gray-800/50 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1">DB State</div>
          <div className={`text-sm font-bold font-mono ${dbKilled ? 'text-red-400' : 'text-green-400'}`}>
            {dbKilled ? 'TRUE' : 'FALSE'}
          </div>
          {killSwitch.killed_at && (
            <div className="text-[10px] text-text-secondary mt-1">
              {new Date(killSwitch.killed_at).toLocaleString()}
            </div>
          )}
        </div>
        <div className="bg-gray-800/50 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1">
            is_bot_killed()
          </div>
          <div className={`text-sm font-bold font-mono ${fnReturns ? 'text-red-400' : 'text-green-400'}`}>
            {fnReturns ? 'TRUE' : 'FALSE'}
          </div>
          <div className="text-[10px] text-yellow-400/70 mt-1">
            {hasMismatch ? 'Check DB sync' : fnReturns ? 'Enforced' : 'Trading allowed'}
          </div>
        </div>
      </div>

      {/* Risk Metrics */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-gray-800/50 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1">
            Consecutive Losses
          </div>
          <div
            className={`text-xl font-bold ${
              verdict.consecutive_losses >= 3
                ? 'text-red-400'
                : verdict.consecutive_losses >= 2
                ? 'text-yellow-400'
                : 'text-text-primary'
            }`}
          >
            {verdict.consecutive_losses}
          </div>
        </div>
        <div className="bg-gray-800/50 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1">
            Daily Loss %
          </div>
          <div
            className={`text-xl font-bold ${
              verdict.daily_loss_pct >= 3
                ? 'text-red-400'
                : verdict.daily_loss_pct >= 1.5
                ? 'text-yellow-400'
                : 'text-text-primary'
            }`}
          >
            {verdict.daily_loss_pct > 0 ? `-${verdict.daily_loss_pct.toFixed(1)}%` : '0.0%'}
          </div>
        </div>
      </div>

      {/* Kill Reason (if killed) */}
      {dbKilled && killSwitch.killed_reason && (
        <div className="mb-4 p-2 bg-gray-800/50 rounded text-xs text-text-secondary">
          <span className="text-text-secondary/70">Reason: </span>
          <span className="text-text-primary">{killSwitch.killed_reason}</span>
        </div>
      )}

      {/* Action Button */}
      <div className="mt-auto">
        {dbKilled ? (
          <button
            onClick={() => onRevive(botName)}
            className="w-full px-4 py-2.5 text-sm font-medium bg-green-600/20 text-green-400 border border-green-500/30 rounded-lg hover:bg-green-600/30 transition-colors flex items-center justify-center gap-2"
          >
            <Power className="w-4 h-4" />
            Revive Bot
          </button>
        ) : (
          <button
            onClick={() => onKill(botName)}
            className="w-full px-4 py-2.5 text-sm font-medium bg-red-600/20 text-red-400 border border-red-500/30 rounded-lg hover:bg-red-600/30 transition-colors flex items-center justify-center gap-2"
          >
            <Lock className="w-4 h-4" />
            Kill Bot
          </button>
        )}
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
  const { data: botsData, isLoading: botsLoading, mutate: mutateBots } = useOmegaBots()
  const { data: correlationData } = useOmegaCorrelations()
  const { data: equityData } = useOmegaEquityScaling()
  const { data: auditData, mutate: mutateAudit } = useOmegaAuditLog(50)

  const [killModal, setKillModal] = useState<{ bot: string; action: 'kill' | 'revive' } | null>(null)
  const [killReason, setKillReason] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [killAllModal, setKillAllModal] = useState(false)
  const [killAllReason, setKillAllReason] = useState('')

  // Derive data
  const bots: Record<string, BotData> = botsData?.bots || {}
  const correlations: CorrelationData = correlationData || {
    correlation_matrix: {},
    max_correlation_threshold: 0.7,
  }
  const equityScaling = (equityData as EquityScalingData | undefined)?.equity_scaling || null
  const auditEntries: AuditEntry[] = auditData?.entries || auditData?.audit_log || []

  // Count mismatches
  const mismatchCount = Object.values(bots).filter(
    (b) => (b as BotData)?.kill_switch?.mismatch === true
  ).length
  const killedCount = Object.values(bots).filter(
    (b) => (b as BotData)?.kill_switch?.db_is_killed === true
  ).length

  // Direction counts from correlation data
  const directions = correlations.active_positions_by_direction || {
    bullish: 0,
    bearish: 0,
    neutral: 0,
  }

  // Handle kill/revive
  const handleKillRevive = async () => {
    if (!killModal || killReason.length < 5) return
    setIsSubmitting(true)
    try {
      if (killModal.action === 'kill') {
        await apiClient.killOmegaBot(killModal.bot, { reason: killReason })
      } else {
        await apiClient.reviveOmegaBot(killModal.bot, { reason: killReason })
      }
      setKillModal(null)
      setKillReason('')
      mutateBots()
      mutateAudit()
    } catch (err) {
      alert(`Failed to ${killModal.action} ${killModal.bot}: ${err}`)
    } finally {
      setIsSubmitting(false)
    }
  }

  // Handle kill all
  const handleKillAll = async () => {
    if (killAllReason.length < 5) return
    setIsSubmitting(true)
    try {
      await apiClient.killAllOmegaBots({ reason: killAllReason })
      setKillAllModal(false)
      setKillAllReason('')
      mutateBots()
      mutateAudit()
    } catch (err) {
      alert(`Failed to kill all bots: ${err}`)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-background-deep text-text-primary">
      <Navigation />
      <div className="flex-1 p-6">
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
              <Shield className="w-7 h-7 text-red-400" />
              <h1 className="text-2xl font-bold">Safety &amp; Risk</h1>
              {mismatchCount > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                  {mismatchCount} MISMATCH{mismatchCount > 1 ? 'ES' : ''}
                </span>
              )}
            </div>
            <p className="text-sm text-text-secondary mt-1">
              Kill switch management, risk metrics, and audit trail
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setKillAllModal(true)}
              className="px-4 py-2 text-sm bg-red-600/20 text-red-400 border border-red-500/40 rounded-lg hover:bg-red-600/30 transition-colors font-medium flex items-center gap-2"
            >
              <AlertOctagon className="w-4 h-4" />
              KILL ALL BOTS
            </button>
          </div>
        </div>

        {/* ==================== KILL SWITCH STATUS BANNER ==================== */}
        <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
          <div className="flex items-start gap-3">
            <Shield className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="text-sm font-bold text-green-400 mb-1">
                Kill Switch Operational
              </div>
              <p className="text-xs text-green-300/80 leading-relaxed">
                <span className="font-mono bg-green-500/20 px-1 py-0.5 rounded">is_bot_killed()</span>{' '}
                queries the <span className="font-mono font-bold">proverbs_kill_switch</span> table
                and returns the correct state. Kill/Revive actions below will take immediate effect.
                Bots check this function before every trade cycle.
              </p>
            </div>
          </div>
        </div>

        {/* ==================== KILL SWITCH DASHBOARD ==================== */}
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Lock className="w-5 h-5 text-red-400" />
          Kill Switch Dashboard
          <span className="text-xs text-text-secondary font-normal ml-2">
            {killedCount} of {BOTS.length} killed
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
                botData={bots[name]}
                onKill={(bot) => setKillModal({ bot, action: 'kill' })}
                onRevive={(bot) => setKillModal({ bot, action: 'revive' })}
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

        {/* ==================== KILL/REVIVE MODAL ==================== */}
        {killModal && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-background-card border border-gray-700 rounded-lg p-6 w-[420px] shadow-modal">
              <h3 className="text-lg font-bold text-text-primary mb-2 flex items-center gap-2">
                {killModal.action === 'kill' ? (
                  <Lock className="w-5 h-5 text-red-400" />
                ) : (
                  <Power className="w-5 h-5 text-green-400" />
                )}
                {killModal.action === 'kill' ? 'Kill' : 'Revive'} {killModal.bot}?
              </h3>
              <p className="text-sm text-text-secondary mb-2">
                {STRATEGY_MAP[killModal.bot]} bot
              </p>
              {killModal.action === 'kill' ? (
                <div className="text-xs text-yellow-400/80 bg-yellow-500/10 border border-yellow-500/20 rounded p-2 mb-4">
                  <AlertTriangle className="w-3 h-3 inline mr-1" />
                  The kill switch will be activated. The bot will stop entering new trades
                  at its next scan cycle (within 5 minutes).
                </div>
              ) : (
                <p className="text-xs text-text-secondary mb-4">
                  This will deactivate the kill switch and allow the bot to resume trading.
                </p>
              )}
              <label className="block text-xs text-text-secondary mb-1.5">Reason (required)</label>
              <input
                type="text"
                value={killReason}
                onChange={(e) => setKillReason(e.target.value)}
                placeholder="Enter reason (min 5 characters)..."
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-sm text-text-primary mb-4 focus:border-blue-500 focus:outline-none"
                autoFocus
              />
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setKillModal(null)
                    setKillReason('')
                  }}
                  className="flex-1 px-4 py-2 text-sm bg-gray-700 text-text-secondary rounded hover:bg-gray-600 transition-colors"
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  onClick={handleKillRevive}
                  disabled={killReason.length < 5 || isSubmitting}
                  className={`flex-1 px-4 py-2 text-sm rounded transition-colors font-medium ${
                    killModal.action === 'kill'
                      ? 'bg-red-600 text-white hover:bg-red-500 disabled:bg-red-900 disabled:text-red-300'
                      : 'bg-green-600 text-white hover:bg-green-500 disabled:bg-green-900 disabled:text-green-300'
                  }`}
                >
                  {isSubmitting
                    ? 'Processing...'
                    : killModal.action === 'kill'
                    ? 'Kill Bot'
                    : 'Revive Bot'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ==================== KILL ALL MODAL ==================== */}
        {killAllModal && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-background-card border border-red-500/30 rounded-lg p-6 w-[420px] shadow-modal">
              <h3 className="text-lg font-bold text-red-400 mb-2 flex items-center gap-2">
                <AlertOctagon className="w-5 h-5" />
                EMERGENCY: Kill All Bots?
              </h3>
              <p className="text-sm text-text-secondary mb-2">
                This will activate the kill switch for ALL {BOTS.length} trading bots.
              </p>
              <div className="text-xs text-red-300/80 bg-red-500/10 border border-red-500/20 rounded p-2 mb-4">
                <AlertTriangle className="w-3 h-3 inline mr-1" />
                This action is irreversible without manually reviving each bot individually.
                All bots will stop entering new trades at their next scan cycle.
              </div>
              <div className="mb-4 p-2 bg-gray-800/50 rounded text-xs text-text-secondary">
                <div className="font-medium text-text-primary mb-1">Bots to be killed:</div>
                {BOTS.map((name) => (
                  <div key={name} className="flex items-center gap-2 py-0.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                    <span>{name}</span>
                    <span className="text-text-secondary/70">- {STRATEGY_MAP[name]}</span>
                  </div>
                ))}
              </div>
              <label className="block text-xs text-text-secondary mb-1.5">Reason (required)</label>
              <input
                type="text"
                value={killAllReason}
                onChange={(e) => setKillAllReason(e.target.value)}
                placeholder="Enter reason (min 5 characters)..."
                className="w-full px-3 py-2 bg-gray-800 border border-red-500/30 rounded text-sm text-text-primary mb-4 focus:border-red-500 focus:outline-none"
                autoFocus
              />
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setKillAllModal(false)
                    setKillAllReason('')
                  }}
                  className="flex-1 px-4 py-2 text-sm bg-gray-700 text-text-secondary rounded hover:bg-gray-600 transition-colors"
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  onClick={handleKillAll}
                  disabled={killAllReason.length < 5 || isSubmitting}
                  className="flex-1 px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-500 disabled:bg-red-900 disabled:text-red-300 transition-colors font-medium"
                >
                  {isSubmitting ? 'Processing...' : 'KILL ALL BOTS'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
