'use client'

import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Brain, Activity, Shield, AlertTriangle, CheckCircle, XCircle,
  Clock, RefreshCw, ChevronDown, ChevronUp, ChevronRight,
  RotateCcw, Play, Pause, FileText, TrendingUp, TrendingDown,
  Settings, Eye, History, Zap, Target, Lock, Unlock,
  BarChart2, Calendar, Sun, Moon, GitBranch, Layers
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

// ==================== SPARKLINE COMPONENT ====================

const Sparkline = ({ data, color = '#8b5cf6', width = 100, height = 30 }: {
  data: number[]
  color?: string
  width?: number
  height?: number
}) => {
  if (!data || data.length === 0) {
    return <div className="text-gray-600 text-xs">No data</div>
  }

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const points = data.map((value, index) => {
    const x = (index / (data.length - 1)) * width
    const y = height - ((value - min) / range) * height
    return `${x},${y}`
  }).join(' ')

  const lastValue = data[data.length - 1]
  const firstValue = data[0]
  const trend = lastValue >= firstValue ? 'up' : 'down'
  const trendColor = trend === 'up' ? '#22c55e' : '#ef4444'

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={trendColor}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={(data.length - 1) / (data.length - 1) * width}
        cy={height - ((lastValue - min) / range) * height}
        r="3"
        fill={trendColor}
      />
    </svg>
  )
}

// ==================== P&L INDICATOR ====================

const RealTimePnL = ({ value, previousValue }: { value: number, previousValue?: number }) => {
  const isPositive = value >= 0
  const change = previousValue !== undefined ? value - previousValue : 0
  const showChange = previousValue !== undefined && change !== 0

  return (
    <div className="flex items-center gap-2">
      <span className={`text-2xl font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
        ${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
      {showChange && (
        <span className={`text-xs px-1.5 py-0.5 rounded ${change >= 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
          {change >= 0 ? '+' : ''}{change.toFixed(2)}
        </span>
      )}
    </div>
  )
}

// ==================== INTERFACES ====================

interface BotStatus {
  name: string
  is_killed: boolean
  performance: {
    total_trades: number
    wins: number
    losses: number
    win_rate: number
    total_pnl: number
  }
  active_version: {
    version_id: string
    version_number: string
    created_at: string
    approved_by: string
  } | null
  versions_count: number
  last_action: {
    timestamp: string
    action_type: string
    action_description: string
  } | null
}

interface Proposal {
  proposal_id: string
  created_at: string
  expires_at: string
  proposal_type: string
  bot_name: string
  title: string
  description: string
  current_value: Record<string, unknown>
  proposed_value: Record<string, unknown>
  change_summary: string
  reason: string
  supporting_metrics: Record<string, unknown>
  expected_improvement: Record<string, unknown>
  risk_level: string
  risk_factors: string[]
  rollback_plan: string
  status: string
  reviewed_by: string | null
  reviewed_at: string | null
  review_notes: string | null
}

interface AuditEntry {
  id: number
  timestamp: string
  bot_name: string
  actor: string
  session_id: string
  action_type: string
  action_description: string
  before_state: Record<string, unknown>
  after_state: Record<string, unknown>
  reason: string
  justification: Record<string, unknown>
  version_from: string
  version_to: string
  proposal_id: string | null
  success: boolean
  error_message: string
}

interface Version {
  version_id: string
  version_number: string
  created_at: string
  version_type: string
  artifact_name: string
  is_active: boolean
  approved_by: string | null
  performance_metrics: Record<string, unknown>
}

interface DashboardData {
  timestamp: string
  session_id: string
  bots: Record<string, BotStatus>
  pending_proposals: Proposal[]
  recent_actions: AuditEntry[]
  kill_switch_status: Record<string, unknown>
  health: {
    database: boolean
    oracle: boolean
    last_feedback_run: string | null
    pending_proposals_count: number
    degradation_alerts: number
  }
}

// ==================== COMPONENTS ====================

const StatusBadge = ({ status, size = 'md' }: { status: string, size?: 'sm' | 'md' | 'lg' }) => {
  const colors: Record<string, string> = {
    'PENDING': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50',
    'APPROVED': 'bg-green-500/20 text-green-400 border-green-500/50',
    'REJECTED': 'bg-red-500/20 text-red-400 border-red-500/50',
    'EXPIRED': 'bg-gray-500/20 text-gray-400 border-gray-500/50',
    'APPLIED': 'bg-blue-500/20 text-blue-400 border-blue-500/50',
    'LOW': 'bg-green-500/20 text-green-400 border-green-500/50',
    'MEDIUM': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50',
    'HIGH': 'bg-red-500/20 text-red-400 border-red-500/50',
  }

  const sizeClasses = {
    sm: 'px-1.5 py-0.5 text-xs',
    md: 'px-2 py-1 text-xs',
    lg: 'px-3 py-1.5 text-sm'
  }

  return (
    <span className={`${colors[status] || 'bg-gray-500/20 text-gray-400'} ${sizeClasses[size]} rounded border font-medium`}>
      {status}
    </span>
  )
}

const BotCard = ({
  bot,
  onKill,
  onResume,
  onViewVersions,
  sparklineData
}: {
  bot: BotStatus
  onKill: (name: string) => void
  onResume: (name: string) => void
  onViewVersions: (name: string) => void
  sparklineData?: number[]
}) => {
  const [showDetails, setShowDetails] = useState(false)

  const winRate = bot.performance?.win_rate || 0
  const totalPnl = bot.performance?.total_pnl || 0
  const wins = bot.performance?.wins || 0
  const losses = bot.performance?.losses || 0

  // Generate mock sparkline if none provided
  const chartData = sparklineData || Array.from({ length: 10 }, () => Math.random() * 100)

  // Calculate streak
  const streak = wins > losses ? `${wins - losses}W` : losses > wins ? `${losses - wins}L` : 'EVEN'
  const streakColor = wins > losses ? 'text-green-400' : losses > wins ? 'text-red-400' : 'text-gray-400'

  return (
    <div className={`bg-gray-800 rounded-lg border ${bot.is_killed ? 'border-red-500/50' : 'border-gray-700'} p-4`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${bot.is_killed ? 'bg-red-500' : 'bg-green-500'} animate-pulse`} />
          <h3 className="text-lg font-bold text-white">{bot.name}</h3>
          {bot.is_killed && (
            <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded border border-red-500/50">
              KILLED
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {bot.is_killed ? (
            <button
              onClick={() => onResume(bot.name)}
              className="p-1.5 bg-green-500/20 text-green-400 rounded hover:bg-green-500/30 transition-colors"
              title="Resume Bot"
            >
              <Unlock className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={() => onKill(bot.name)}
              className="p-1.5 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors"
              title="Kill Bot"
            >
              <Lock className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => onViewVersions(bot.name)}
            className="p-1.5 bg-blue-500/20 text-blue-400 rounded hover:bg-blue-500/30 transition-colors"
            title="View Versions"
          >
            <History className="w-4 h-4" />
          </button>
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="p-1.5 bg-gray-700 text-gray-400 rounded hover:bg-gray-600 transition-colors"
          >
            {showDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* P&L with Sparkline */}
      <div className="flex items-center justify-between mb-3 bg-gray-900/50 rounded-lg p-3">
        <div>
          <div className="text-xs text-gray-500 mb-1">Total P&L</div>
          <RealTimePnL value={totalPnl} />
        </div>
        <div className="flex flex-col items-end">
          <Sparkline data={chartData} width={80} height={24} />
          <div className={`text-xs mt-1 ${streakColor}`}>{streak}</div>
        </div>
      </div>

      {/* Performance Summary */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="bg-gray-900/50 rounded p-2 text-center">
          <div className="text-xs text-gray-500">Win Rate</div>
          <div className={`text-lg font-bold ${winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
            {winRate.toFixed(1)}%
          </div>
        </div>
        <div className="bg-gray-900/50 rounded p-2 text-center">
          <div className="text-xs text-gray-500">Wins</div>
          <div className="text-lg font-bold text-green-400">{wins}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2 text-center">
          <div className="text-xs text-gray-500">Losses</div>
          <div className="text-lg font-bold text-red-400">{losses}</div>
        </div>
      </div>

      {/* Active Version */}
      {bot.active_version && (
        <div className="text-xs text-gray-400 flex items-center justify-between px-1">
          <span>
            <GitBranch className="w-3 h-3 inline mr-1" />
            v{bot.active_version.version_number}
          </span>
          <span className="text-gray-600">{bot.versions_count} versions</span>
        </div>
      )}

      {/* Expanded Details */}
      {showDetails && (
        <div className="mt-3 pt-3 border-t border-gray-700 space-y-2">
          {bot.last_action && (
            <div className="text-xs">
              <div className="text-gray-500 mb-1">Last Action</div>
              <div className="bg-gray-900/50 rounded p-2">
                <div className="text-gray-300">{bot.last_action.action_description}</div>
                <div className="text-gray-500 mt-1">
                  {new Date(bot.last_action.timestamp).toLocaleString()}
                </div>
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500">Trades Today</div>
              <div className="text-white font-bold">{bot.performance?.total_trades || 0}</div>
            </div>
            <div className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500">Profit Factor</div>
              <div className="text-purple-400 font-bold">
                {wins && losses ? (wins / losses).toFixed(2) : '-'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const ProposalCard = ({
  proposal,
  onApprove,
  onReject
}: {
  proposal: Proposal
  onApprove: (id: string, notes: string) => void
  onReject: (id: string, notes: string) => void
}) => {
  const [showDetails, setShowDetails] = useState(false)
  const [notes, setNotes] = useState('')
  const [processing, setProcessing] = useState(false)

  const handleApprove = async () => {
    setProcessing(true)
    await onApprove(proposal.proposal_id, notes)
    setProcessing(false)
  }

  const handleReject = async () => {
    setProcessing(true)
    await onReject(proposal.proposal_id, notes)
    setProcessing(false)
  }

  const expiresAt = new Date(proposal.expires_at)
  const now = new Date()
  const hoursLeft = Math.max(0, Math.floor((expiresAt.getTime() - now.getTime()) / (1000 * 60 * 60)))

  return (
    <div className="bg-gray-800 rounded-lg border border-yellow-500/30 p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-bold text-yellow-400">{proposal.bot_name}</span>
            <StatusBadge status={proposal.risk_level} size="sm" />
          </div>
          <h4 className="text-white font-medium">{proposal.title}</h4>
        </div>
        <div className="text-right text-xs">
          <div className="text-gray-500">Expires in</div>
          <div className={`font-bold ${hoursLeft < 12 ? 'text-red-400' : 'text-yellow-400'}`}>
            {hoursLeft}h
          </div>
        </div>
      </div>

      <p className="text-sm text-gray-400 mb-3">{proposal.reason}</p>

      <div className="bg-gray-900/50 rounded p-2 mb-3 text-xs">
        <div className="text-gray-500 mb-1">Change Summary</div>
        <div className="text-gray-300 font-mono">{proposal.change_summary}</div>
      </div>

      <button
        onClick={() => setShowDetails(!showDetails)}
        className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 mb-3"
      >
        {showDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {showDetails ? 'Hide Details' : 'Show Details'}
      </button>

      {showDetails && (
        <div className="space-y-3 mb-3">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500 mb-1">Current Value</div>
              <pre className="text-gray-300 overflow-auto max-h-24">
                {JSON.stringify(proposal.current_value, null, 2)}
              </pre>
            </div>
            <div className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500 mb-1">Proposed Value</div>
              <pre className="text-green-400 overflow-auto max-h-24">
                {JSON.stringify(proposal.proposed_value, null, 2)}
              </pre>
            </div>
          </div>

          {proposal.risk_factors.length > 0 && (
            <div className="bg-red-500/10 border border-red-500/30 rounded p-2">
              <div className="text-xs text-red-400 font-medium mb-1">Risk Factors</div>
              <ul className="text-xs text-gray-300 list-disc list-inside">
                {proposal.risk_factors.map((factor, i) => (
                  <li key={i}>{factor}</li>
                ))}
              </ul>
            </div>
          )}

          {proposal.rollback_plan && (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded p-2">
              <div className="text-xs text-blue-400 font-medium mb-1">Rollback Plan</div>
              <div className="text-xs text-gray-300">{proposal.rollback_plan}</div>
            </div>
          )}
        </div>
      )}

      <div className="space-y-2">
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Review notes (optional)..."
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
        />
        <div className="flex gap-2">
          <button
            onClick={handleApprove}
            disabled={processing}
            className="flex-1 bg-green-500/20 text-green-400 border border-green-500/50 rounded py-2 text-sm font-medium hover:bg-green-500/30 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <CheckCircle className="w-4 h-4" />
            Approve
          </button>
          <button
            onClick={handleReject}
            disabled={processing}
            className="flex-1 bg-red-500/20 text-red-400 border border-red-500/50 rounded py-2 text-sm font-medium hover:bg-red-500/30 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <XCircle className="w-4 h-4" />
            Reject
          </button>
        </div>
      </div>
    </div>
  )
}

const AuditLogEntry = ({ entry }: { entry: AuditEntry }) => {
  const [expanded, setExpanded] = useState(false)

  const getActionIcon = (type: string) => {
    if (type.includes('RETRAIN') || type.includes('MODEL')) return <Brain className="w-4 h-4" />
    if (type.includes('ROLLBACK')) return <RotateCcw className="w-4 h-4" />
    if (type.includes('PROPOSAL')) return <FileText className="w-4 h-4" />
    if (type.includes('KILL')) return <AlertTriangle className="w-4 h-4" />
    if (type.includes('DEGRADATION')) return <TrendingDown className="w-4 h-4" />
    return <Activity className="w-4 h-4" />
  }

  const getActionColor = (type: string) => {
    if (type.includes('APPROVED') || type.includes('SUCCESS')) return 'text-green-400'
    if (type.includes('REJECTED') || type.includes('KILL') || type.includes('DEGRADATION')) return 'text-red-400'
    if (type.includes('PROPOSAL_CREATED') || type.includes('PENDING')) return 'text-yellow-400'
    return 'text-blue-400'
  }

  return (
    <div className="bg-gray-800/50 rounded p-3 border border-gray-700/50">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className={`mt-0.5 ${getActionColor(entry.action_type)}`}>
            {getActionIcon(entry.action_type)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white">{entry.bot_name}</span>
              <span className={`text-xs ${getActionColor(entry.action_type)}`}>
                {entry.action_type.replace(/_/g, ' ')}
              </span>
              {!entry.success && (
                <span className="px-1.5 py-0.5 bg-red-500/20 text-red-400 text-xs rounded">FAILED</span>
              )}
            </div>
            <div className="text-sm text-gray-400 mt-0.5">{entry.action_description}</div>
            <div className="text-xs text-gray-500 mt-1 flex items-center gap-2">
              <Clock className="w-3 h-3" />
              {new Date(entry.timestamp).toLocaleString()}
              <span className="text-gray-600">|</span>
              <span>by {entry.actor}</span>
            </div>
          </div>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-gray-500 hover:text-gray-300"
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-700 space-y-2 text-xs">
          {entry.reason && (
            <div>
              <span className="text-gray-500">Reason: </span>
              <span className="text-gray-300">{entry.reason}</span>
            </div>
          )}
          {entry.version_from && entry.version_to && (
            <div>
              <span className="text-gray-500">Version: </span>
              <span className="text-gray-400">{entry.version_from}</span>
              <span className="text-gray-600"> → </span>
              <span className="text-green-400">{entry.version_to}</span>
            </div>
          )}
          {Object.keys(entry.justification || {}).length > 0 && (
            <div className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500 mb-1">Justification</div>
              <pre className="text-gray-300 overflow-auto max-h-32">
                {JSON.stringify(entry.justification, null, 2)}
              </pre>
            </div>
          )}
          {entry.error_message && (
            <div className="bg-red-500/10 border border-red-500/30 rounded p-2 text-red-400">
              Error: {entry.error_message}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const VersionModal = ({
  botName,
  versions,
  onClose,
  onRollback,
  onActivate
}: {
  botName: string
  versions: Version[]
  onClose: () => void
  onRollback: (versionId: string, reason: string) => void
  onActivate: (versionId: string) => void
}) => {
  const [rollbackReason, setRollbackReason] = useState('')
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null)

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg border border-gray-700 max-w-2xl w-full max-h-[80vh] overflow-hidden">
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <h3 className="text-lg font-bold text-white">{botName} Version History</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto max-h-96 space-y-2">
          {versions.map((version) => (
            <div
              key={version.version_id}
              className={`bg-gray-900/50 rounded p-3 border ${
                version.is_active ? 'border-green-500/50' : 'border-gray-700'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-white">{version.version_number}</span>
                  {version.is_active && (
                    <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded border border-green-500/50">
                      ACTIVE
                    </span>
                  )}
                </div>
                {!version.is_active && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => setSelectedVersion(version.version_id)}
                      className="px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded hover:bg-yellow-500/30"
                    >
                      Rollback
                    </button>
                    <button
                      onClick={() => onActivate(version.version_id)}
                      className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded hover:bg-blue-500/30"
                    >
                      Activate
                    </button>
                  </div>
                )}
              </div>
              <div className="text-xs text-gray-400 space-y-1">
                <div>Created: {new Date(version.created_at).toLocaleString()}</div>
                <div>Type: {version.version_type} / {version.artifact_name}</div>
                {version.approved_by && <div>Approved by: {version.approved_by}</div>}
              </div>
            </div>
          ))}
        </div>

        {selectedVersion && (
          <div className="p-4 border-t border-gray-700 bg-gray-900/50">
            <div className="text-sm text-yellow-400 mb-2">Rollback to selected version</div>
            <input
              type="text"
              value={rollbackReason}
              onChange={(e) => setRollbackReason(e.target.value)}
              placeholder="Reason for rollback..."
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 mb-2"
            />
            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (rollbackReason) {
                    onRollback(selectedVersion, rollbackReason)
                    setSelectedVersion(null)
                    setRollbackReason('')
                  }
                }}
                disabled={!rollbackReason}
                className="flex-1 bg-yellow-500/20 text-yellow-400 border border-yellow-500/50 rounded py-2 text-sm font-medium hover:bg-yellow-500/30 disabled:opacity-50"
              >
                Confirm Rollback
              </button>
              <button
                onClick={() => {
                  setSelectedVersion(null)
                  setRollbackReason('')
                }}
                className="px-4 bg-gray-700 text-gray-300 rounded py-2 text-sm font-medium hover:bg-gray-600"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ==================== MAIN PAGE ====================

export default function SolomonPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Modal states
  const [versionModalBot, setVersionModalBot] = useState<string | null>(null)
  const [versions, setVersions] = useState<Version[]>([])

  // Tab states
  const [activeTab, setActiveTab] = useState<'overview' | 'proposals' | 'audit' | 'versions' | 'analytics'>('overview')

  // Analytics data
  const [analyticsBot, setAnalyticsBot] = useState<string>('ARES')
  const [dailyDigest, setDailyDigest] = useState<any>(null)
  const [correlations, setCorrelations] = useState<any>(null)
  const [timeAnalysis, setTimeAnalysis] = useState<any>(null)

  const fetchAnalytics = useCallback(async (bot: string) => {
    try {
      const [digestRes, corrRes, timeRes] = await Promise.all([
        apiClient.get('/api/solomon/enhanced/digest'),
        apiClient.get('/api/solomon/enhanced/correlations'),
        apiClient.get(`/api/solomon/enhanced/time-analysis/${bot}`)
      ])
      setDailyDigest(digestRes.data)
      setCorrelations(corrRes.data)
      setTimeAnalysis(timeRes.data)
    } catch (err) {
      console.error('Failed to fetch analytics:', err)
    }
  }, [])

  const fetchDashboard = useCallback(async () => {
    try {
      const response = await apiClient.get('/api/solomon/dashboard')
      setDashboard(response.data)
      setLastRefresh(new Date())
      setError(null)
    } catch (err) {
      console.error('Failed to fetch dashboard:', err)
      setError('Failed to load Solomon dashboard')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDashboard()
  }, [fetchDashboard])

  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(fetchDashboard, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [autoRefresh, fetchDashboard])

  const handleKillBot = async (botName: string) => {
    const reason = prompt(`Why are you killing ${botName}?`)
    if (!reason) return

    try {
      await apiClient.post(`/api/solomon/killswitch/${botName}/activate`, {
        reason,
        user: 'Dashboard User'
      })
      fetchDashboard()
    } catch (err) {
      console.error('Failed to kill bot:', err)
      alert('Failed to activate kill switch')
    }
  }

  const handleResumeBot = async (botName: string) => {
    try {
      await apiClient.post(`/api/solomon/killswitch/${botName}/deactivate`, {
        user: 'Dashboard User'
      })
      fetchDashboard()
    } catch (err) {
      console.error('Failed to resume bot:', err)
      alert('Failed to deactivate kill switch')
    }
  }

  const handleViewVersions = async (botName: string) => {
    try {
      const response = await apiClient.get(`/api/solomon/versions/${botName}`)
      setVersions(response.data.versions || [])
      setVersionModalBot(botName)
    } catch (err) {
      console.error('Failed to fetch versions:', err)
      alert('Failed to load version history')
    }
  }

  const handleApproveProposal = async (proposalId: string, notes: string) => {
    try {
      await apiClient.post(`/api/solomon/proposals/${proposalId}/approve`, {
        reviewer: 'Dashboard User',
        notes
      })
      fetchDashboard()
    } catch (err) {
      console.error('Failed to approve proposal:', err)
      alert('Failed to approve proposal')
    }
  }

  const handleRejectProposal = async (proposalId: string, notes: string) => {
    if (!notes) {
      alert('Please provide a reason for rejection')
      return
    }
    try {
      await apiClient.post(`/api/solomon/proposals/${proposalId}/reject`, {
        reviewer: 'Dashboard User',
        notes
      })
      fetchDashboard()
    } catch (err) {
      console.error('Failed to reject proposal:', err)
      alert('Failed to reject proposal')
    }
  }

  const handleRollback = async (versionId: string, reason: string) => {
    if (!versionModalBot) return
    try {
      await apiClient.post(`/api/solomon/rollback/${versionModalBot}`, {
        to_version_id: versionId,
        reason,
        user: 'Dashboard User'
      })
      setVersionModalBot(null)
      fetchDashboard()
    } catch (err) {
      console.error('Failed to rollback:', err)
      alert('Failed to rollback')
    }
  }

  const handleActivateVersion = async (versionId: string) => {
    try {
      await apiClient.post(`/api/solomon/versions/${versionId}/activate?user=Dashboard%20User`)
      handleViewVersions(versionModalBot!)
      fetchDashboard()
    } catch (err) {
      console.error('Failed to activate version:', err)
      alert('Failed to activate version')
    }
  }

  const handleTriggerFeedbackLoop = async () => {
    try {
      const response = await apiClient.post('/api/solomon/feedback-loop/run')
      alert(`Feedback loop completed!\n\nRun ID: ${response.data.run_id}\nProposals created: ${response.data.proposals_created?.length || 0}`)
      fetchDashboard()
    } catch (err) {
      console.error('Failed to trigger feedback loop:', err)
      alert('Failed to trigger feedback loop')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900">
        <Navigation />
        <main className="max-w-7xl mx-auto px-4 py-8">
          <div className="flex items-center justify-center h-64">
            <RefreshCw className="w-8 h-8 text-purple-400 animate-spin" />
          </div>
        </main>
      </div>
    )
  }

  if (error || !dashboard) {
    return (
      <div className="min-h-screen bg-gray-900">
        <Navigation />
        <main className="max-w-7xl mx-auto px-4 py-8">
          <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-6 text-center">
            <AlertTriangle className="w-12 h-12 text-red-400 mx-auto mb-4" />
            <h2 className="text-xl font-bold text-red-400 mb-2">Solomon Unavailable</h2>
            <p className="text-gray-400">{error || 'Could not load dashboard data'}</p>
            <button
              onClick={fetchDashboard}
              className="mt-4 px-4 py-2 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30"
            >
              Retry
            </button>
          </div>
        </main>
      </div>
    )
  }

  const bots = Object.values(dashboard.bots || {})
  const pendingProposals = dashboard.pending_proposals || []
  const recentActions = dashboard.recent_actions || []

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-purple-500/20 rounded-lg">
              <Brain className="w-8 h-8 text-purple-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">SOLOMON</h1>
              <p className="text-gray-400 italic">"Iron sharpens iron, and one man sharpens another."</p>
              <p className="text-gray-500 text-xs">Proverbs 27:17 — Feedback Loop Intelligence System</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleTriggerFeedbackLoop}
              className="px-4 py-2 bg-purple-500/20 text-purple-400 border border-purple-500/50 rounded-lg hover:bg-purple-500/30 transition-colors flex items-center gap-2"
            >
              <Zap className="w-4 h-4" />
              Run Feedback Loop
            </button>
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`p-2 rounded-lg transition-colors ${
                autoRefresh
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-gray-700 text-gray-400'
              }`}
              title={autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
            >
              {autoRefresh ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
            </button>
            <button
              onClick={fetchDashboard}
              className="p-2 bg-gray-700 text-gray-400 rounded-lg hover:bg-gray-600 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Health Banner */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${dashboard.health.database ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-sm text-gray-400">Database</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${dashboard.health.oracle ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-sm text-gray-400">Oracle</span>
              </div>
              {pendingProposals.length > 0 && (
                <div className="flex items-center gap-2 px-3 py-1 bg-yellow-500/20 rounded-lg">
                  <AlertTriangle className="w-4 h-4 text-yellow-400" />
                  <span className="text-sm text-yellow-400">{pendingProposals.length} pending proposals</span>
                </div>
              )}
              {dashboard.health.degradation_alerts > 0 && (
                <div className="flex items-center gap-2 px-3 py-1 bg-red-500/20 rounded-lg">
                  <TrendingDown className="w-4 h-4 text-red-400" />
                  <span className="text-sm text-red-400">{dashboard.health.degradation_alerts} degradation alerts</span>
                </div>
              )}
            </div>
            <div className="text-xs text-gray-500">
              Last refresh: {lastRefresh?.toLocaleTimeString()}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-gray-800 rounded-lg p-1 w-fit">
          {(['overview', 'proposals', 'audit', 'versions', 'analytics'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => {
                setActiveTab(tab)
                if (tab === 'analytics') {
                  fetchAnalytics(analyticsBot)
                }
              }}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-2 ${
                activeTab === tab
                  ? 'bg-purple-500/20 text-purple-400'
                  : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              {tab === 'analytics' && <BarChart2 className="w-4 h-4" />}
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
              {tab === 'proposals' && pendingProposals.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-yellow-500 text-black text-xs rounded-full">
                  {pendingProposals.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Bot Cards */}
            <div>
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <Target className="w-5 h-5 text-purple-400" />
                Bot Status
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {bots.map((bot) => (
                  <BotCard
                    key={bot.name}
                    bot={bot}
                    onKill={handleKillBot}
                    onResume={handleResumeBot}
                    onViewVersions={handleViewVersions}
                  />
                ))}
              </div>
            </div>

            {/* Pending Proposals Preview */}
            {pendingProposals.length > 0 && (
              <div>
                <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                  <FileText className="w-5 h-5 text-yellow-400" />
                  Pending Approvals
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {pendingProposals.slice(0, 2).map((proposal) => (
                    <ProposalCard
                      key={proposal.proposal_id}
                      proposal={proposal}
                      onApprove={handleApproveProposal}
                      onReject={handleRejectProposal}
                    />
                  ))}
                </div>
                {pendingProposals.length > 2 && (
                  <button
                    onClick={() => setActiveTab('proposals')}
                    className="mt-3 text-sm text-purple-400 hover:text-purple-300"
                  >
                    View all {pendingProposals.length} proposals →
                  </button>
                )}
              </div>
            )}

            {/* Recent Actions Preview */}
            <div>
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-400" />
                Recent Actions
              </h2>
              <div className="space-y-2">
                {recentActions.slice(0, 5).map((entry) => (
                  <AuditLogEntry key={entry.id} entry={entry} />
                ))}
              </div>
              {recentActions.length > 5 && (
                <button
                  onClick={() => setActiveTab('audit')}
                  className="mt-3 text-sm text-purple-400 hover:text-purple-300"
                >
                  View full audit log →
                </button>
              )}
            </div>
          </div>
        )}

        {activeTab === 'proposals' && (
          <div>
            <h2 className="text-lg font-bold text-white mb-4">All Pending Proposals</h2>
            {pendingProposals.length === 0 ? (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
                <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-white mb-2">All Clear!</h3>
                <p className="text-gray-400">No pending proposals at this time.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {pendingProposals.map((proposal) => (
                  <ProposalCard
                    key={proposal.proposal_id}
                    proposal={proposal}
                    onApprove={handleApproveProposal}
                    onReject={handleRejectProposal}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'audit' && (
          <div>
            <h2 className="text-lg font-bold text-white mb-4">Audit Log</h2>
            <div className="space-y-2">
              {recentActions.map((entry) => (
                <AuditLogEntry key={entry.id} entry={entry} />
              ))}
            </div>
          </div>
        )}

        {activeTab === 'versions' && (
          <div>
            <h2 className="text-lg font-bold text-white mb-4">Version Management</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {bots.map((bot) => (
                <div
                  key={bot.name}
                  className="bg-gray-800 rounded-lg border border-gray-700 p-4 cursor-pointer hover:border-purple-500/50 transition-colors"
                  onClick={() => handleViewVersions(bot.name)}
                >
                  <h3 className="text-lg font-bold text-white mb-2">{bot.name}</h3>
                  {bot.active_version ? (
                    <>
                      <div className="text-2xl font-bold text-purple-400 mb-2">
                        v{bot.active_version.version_number}
                      </div>
                      <div className="text-xs text-gray-400">
                        {bot.versions_count} total versions
                      </div>
                    </>
                  ) : (
                    <div className="text-gray-500">No versions</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'analytics' && (
          <div className="space-y-6">
            {/* Bot Selector */}
            <div className="flex items-center gap-4">
              <h2 className="text-lg font-bold text-white">Analytics</h2>
              <select
                value={analyticsBot}
                onChange={(e) => {
                  setAnalyticsBot(e.target.value)
                  fetchAnalytics(e.target.value)
                }}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
              >
                <option value="ARES">ARES</option>
                <option value="ATHENA">ATHENA</option>
                <option value="ATLAS">ATLAS</option>
                <option value="PHOENIX">PHOENIX</option>
              </select>
            </div>

            {/* Daily Digest Summary */}
            {dailyDigest && (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
                  <Calendar className="w-5 h-5 text-purple-400" />
                  Daily Digest - {dailyDigest.date || 'Today'}
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-900/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Total P&L</div>
                    <div className={`text-xl font-bold ${(dailyDigest.summary?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${(dailyDigest.summary?.total_pnl || 0).toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Total Trades</div>
                    <div className="text-xl font-bold text-white">{dailyDigest.summary?.total_trades || 0}</div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Win Rate</div>
                    <div className={`text-xl font-bold ${(dailyDigest.summary?.win_rate || 0) >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                      {(dailyDigest.summary?.win_rate || 0).toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">Total Wins</div>
                    <div className="text-xl font-bold text-green-400">{dailyDigest.summary?.total_wins || 0}</div>
                  </div>
                </div>

                {/* Per-Bot Breakdown */}
                {dailyDigest.bots && (
                  <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2">
                    {Object.entries(dailyDigest.bots).map(([botName, stats]: [string, any]) => (
                      <div key={botName} className="bg-gray-900/30 rounded p-2 text-xs">
                        <div className="font-bold text-white mb-1">{botName}</div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Trades:</span>
                          <span className="text-white">{stats.trades}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">P&L:</span>
                          <span className={stats.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                            ${stats.pnl?.toFixed(2) || '0.00'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Cross-Bot Correlations */}
            {correlations && correlations.correlations && (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
                  <Layers className="w-5 h-5 text-blue-400" />
                  Cross-Bot Correlations
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {correlations.correlations.map((corr: any, idx: number) => (
                    <div key={idx} className="bg-gray-900/50 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-white">{corr.bot_a} ↔ {corr.bot_b}</span>
                      </div>
                      <div className={`text-2xl font-bold ${
                        Math.abs(corr.correlation) > 0.7 ? 'text-red-400' :
                        Math.abs(corr.correlation) > 0.4 ? 'text-yellow-400' : 'text-green-400'
                      }`}>
                        {(corr.correlation * 100).toFixed(0)}%
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {corr.sample_size} samples
                      </div>
                    </div>
                  ))}
                </div>
                {correlations.analysis && (
                  <div className="mt-4 bg-gray-900/30 rounded p-3">
                    <div className="text-xs text-gray-400">
                      <span className="text-purple-400 font-medium">Diversification Score:</span>{' '}
                      {((correlations.analysis.diversification_score || 0) * 100).toFixed(0)}%
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      {correlations.analysis.recommendation}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Time of Day Analysis */}
            {timeAnalysis && timeAnalysis.hourly_performance && (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
                  <Clock className="w-5 h-5 text-yellow-400" />
                  Time of Day Performance - {analyticsBot}
                </h3>
                <div className="grid grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
                  {timeAnalysis.hourly_performance.map((hour: any) => (
                    <div
                      key={hour.hour}
                      className={`rounded-lg p-2 text-center ${
                        hour.best_performance ? 'bg-green-500/20 border border-green-500/50' :
                        hour.worst_performance ? 'bg-red-500/20 border border-red-500/50' :
                        'bg-gray-900/50'
                      }`}
                    >
                      <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
                        {hour.hour < 12 ? <Sun className="w-3 h-3" /> : <Moon className="w-3 h-3" />}
                        {hour.hour}:00
                      </div>
                      <div className={`text-sm font-bold ${hour.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${hour.avg_pnl?.toFixed(0) || 0}
                      </div>
                      <div className="text-xs text-gray-500">{hour.trades_count} trades</div>
                      {hour.best_performance && <div className="text-xs text-green-400 mt-1">BEST</div>}
                      {hour.worst_performance && <div className="text-xs text-red-400 mt-1">WORST</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Quick Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                  <Zap className="w-4 h-4 text-yellow-400" />
                  Quick Actions
                </h4>
                <div className="space-y-2">
                  <button
                    onClick={() => apiClient.get('/api/solomon/enhanced/weekend-precheck').then(r => alert(JSON.stringify(r.data, null, 2)))}
                    className="w-full text-left px-3 py-2 bg-gray-900/50 rounded text-sm text-gray-300 hover:bg-gray-700 transition-colors"
                  >
                    Weekend Pre-Check Analysis
                  </button>
                  <button
                    onClick={handleTriggerFeedbackLoop}
                    className="w-full text-left px-3 py-2 bg-purple-500/20 rounded text-sm text-purple-400 hover:bg-purple-500/30 transition-colors"
                  >
                    Run Feedback Loop Now
                  </button>
                </div>
              </div>

              <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-400" />
                  Risk Alerts
                </h4>
                <div className="space-y-2">
                  {dashboard?.health.degradation_alerts > 0 ? (
                    <div className="px-3 py-2 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-400">
                      {dashboard.health.degradation_alerts} degradation alerts in last 24h
                    </div>
                  ) : (
                    <div className="px-3 py-2 bg-green-500/10 border border-green-500/30 rounded text-sm text-green-400">
                      No risk alerts - all systems normal
                    </div>
                  )}
                </div>
              </div>

              <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-blue-400" />
                  System Status
                </h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Database</span>
                    <span className={dashboard?.health.database ? 'text-green-400' : 'text-red-400'}>
                      {dashboard?.health.database ? 'Connected' : 'Disconnected'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Oracle</span>
                    <span className={dashboard?.health.oracle ? 'text-green-400' : 'text-red-400'}>
                      {dashboard?.health.oracle ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Last Feedback Run</span>
                    <span className="text-gray-400 text-xs">
                      {dashboard?.health.last_feedback_run ?
                        new Date(dashboard.health.last_feedback_run).toLocaleString() :
                        'Never'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Version Modal */}
      {versionModalBot && (
        <VersionModal
          botName={versionModalBot}
          versions={versions}
          onClose={() => setVersionModalBot(null)}
          onRollback={handleRollback}
          onActivate={handleActivateVersion}
        />
      )}
    </div>
  )
}
