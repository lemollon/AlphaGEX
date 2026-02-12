'use client'

import React, { useState } from 'react'
import {
  Eye, ChevronDown, ChevronRight, Shield, Layers, Brain, Target,
  Filter, Clock, ArrowLeft, AlertTriangle, CheckCircle, XCircle,
  MinusCircle, Info, Activity, TrendingUp, List
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { useOmegaDecisionHistory } from '@/lib/hooks/useMarketData'

// =============================================================================
// CONSTANTS
// =============================================================================

const BOT_OPTIONS = [
  { value: '', label: 'All Bots' },
  { value: 'FORTRESS', label: 'FORTRESS' },
  { value: 'ANCHOR', label: 'ANCHOR' },
  { value: 'SOLOMON', label: 'SOLOMON' },
  { value: 'LAZARUS', label: 'LAZARUS' },
  { value: 'CORNERSTONE', label: 'CORNERSTONE' },
]

const LIMIT_OPTIONS = [20, 50, 100, 200]

const DECISION_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  TRADE_FULL: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30' },
  TRADE_REDUCED: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  SKIP_TODAY: { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/30' },
  BLOCKED_BY_PROVERBS: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30' },
}

const LAYER_ICONS: Record<string, React.ElementType> = {
  L1: Shield,
  L2: Layers,
  L3: Brain,
  L4: Target,
}

// =============================================================================
// HELPER COMPONENTS
// =============================================================================

function DecisionBadge({ decision }: { decision: string }) {
  const colors = DECISION_COLORS[decision] || DECISION_COLORS.SKIP_TODAY
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${colors.bg} ${colors.text} border ${colors.border}`}>
      {decision === 'TRADE_FULL' && <CheckCircle className="w-3 h-3" />}
      {decision === 'TRADE_REDUCED' && <AlertTriangle className="w-3 h-3" />}
      {decision === 'SKIP_TODAY' && <MinusCircle className="w-3 h-3" />}
      {decision === 'BLOCKED_BY_PROVERBS' && <XCircle className="w-3 h-3" />}
      {decision.replace(/_/g, ' ')}
    </span>
  )
}

function LayerDot({ passed, label }: { passed: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5" title={label}>
      <span className={`w-2.5 h-2.5 rounded-full ${passed ? 'bg-green-400' : 'bg-red-400'}`} />
      <span className="text-xs text-text-secondary hidden lg:inline">{passed ? 'PASS' : 'BLOCK'}</span>
    </div>
  )
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    })
  } catch {
    return iso
  }
}

function formatFactors(factors: Array<[string, number]> | undefined): React.ReactNode {
  if (!factors || factors.length === 0) return <span className="text-gray-500">None</span>
  return (
    <div className="space-y-1">
      {factors.map(([name, importance], i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="text-xs text-text-secondary w-40 truncate">{name}</span>
          <div className="flex-1 bg-gray-700 rounded-full h-1.5 max-w-[120px]">
            <div
              className="bg-blue-500 rounded-full h-1.5"
              style={{ width: `${Math.min(Math.abs(importance) * 100, 100)}%` }}
            />
          </div>
          <span className="text-xs text-text-primary w-12 text-right">{(importance * 100).toFixed(1)}%</span>
        </div>
      ))}
    </div>
  )
}

// =============================================================================
// EXPANDED ROW DETAIL
// =============================================================================

function DecisionDetail({ decision }: { decision: any }) {
  const proverbs = decision.proverbs_verdict || {}
  const ensemble = decision.ensemble_context || {}
  const ml = decision.ml_decision || {}
  const prophet = decision.prophet_adaptation || {}
  const correlation = decision.correlation_check || {}
  const path = decision.decision_path || []

  return (
    <div className="bg-gray-800/50 border-t border-gray-700 px-6 py-5 space-y-5">
      {/* Decision Path */}
      <div>
        <h4 className="text-sm font-semibold text-text-primary mb-2 flex items-center gap-2">
          <List className="w-4 h-4 text-blue-400" />
          Decision Path
        </h4>
        {path.length > 0 ? (
          <ol className="space-y-1.5 ml-1">
            {path.map((step: string, i: number) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center font-mono text-[10px]">
                  {i + 1}
                </span>
                <span className="text-text-secondary pt-0.5">{step}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs text-gray-500">No path recorded</p>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {/* L1: Proverbs Verdict */}
        <div className="bg-background-card border border-gray-700 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Shield className="w-4 h-4 text-purple-400" />
            L1: PROVERBS (Safety)
          </h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-text-secondary">Can Trade</span>
              <span className={proverbs.can_trade ? 'text-green-400 font-medium' : 'text-red-400 font-medium'}>
                {proverbs.can_trade ? 'YES' : 'NO'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Consecutive Losses</span>
              <span className={`font-medium ${(proverbs.consecutive_losses || 0) > 2 ? 'text-yellow-400' : 'text-text-primary'}`}>
                {proverbs.consecutive_losses || 0}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Daily Loss %</span>
              <span className={`font-medium ${(proverbs.daily_loss_pct || 0) > 3 ? 'text-red-400' : 'text-text-primary'}`}>
                {(proverbs.daily_loss_pct || 0).toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Is Killed</span>
              <span className={proverbs.is_killed ? 'text-red-400 font-medium' : 'text-green-400 font-medium'}>
                {proverbs.is_killed ? 'YES' : 'NO'}
              </span>
            </div>
            {proverbs.reason && (
              <div className="pt-2 border-t border-gray-700">
                <span className="text-text-secondary">Reason: </span>
                <span className="text-text-primary">{proverbs.reason}</span>
              </div>
            )}
          </div>
        </div>

        {/* L2: Ensemble Context */}
        <div className="bg-background-card border border-gray-700 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            L2: Ensemble (Market Context)
          </h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-text-secondary">Signal</span>
              <span className={`font-medium ${
                ensemble.signal === 'BUY' ? 'text-green-400' :
                ensemble.signal === 'SELL' ? 'text-red-400' :
                'text-gray-400'
              }`}>
                {ensemble.signal || 'NEUTRAL'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Confidence</span>
              <span className="text-text-primary font-medium">{(ensemble.confidence || 0).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Regime</span>
              <span className="text-text-primary font-medium">{ensemble.regime || 'UNKNOWN'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Size Multiplier</span>
              <span className="text-text-primary font-medium">{(ensemble.position_size_multiplier || 0).toFixed(2)}x</span>
            </div>
            <div className="pt-2 border-t border-gray-700">
              <span className="text-text-secondary block mb-1">Weights</span>
              <div className="flex gap-3">
                <span className="text-green-400">Bull: {(ensemble.bullish_weight || 0).toFixed(2)}</span>
                <span className="text-red-400">Bear: {(ensemble.bearish_weight || 0).toFixed(2)}</span>
                <span className="text-gray-400">Neut: {(ensemble.neutral_weight || 0).toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* L3: ML Advisor Decision */}
        <div className="bg-background-card border border-gray-700 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Brain className="w-4 h-4 text-blue-400" />
            L3: WISDOM (ML Advisor)
          </h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-text-secondary">Advice</span>
              <span className={`font-medium ${
                ml.advice === 'TRADE_FULL' ? 'text-green-400' :
                ml.advice === 'TRADE_REDUCED' ? 'text-yellow-400' :
                'text-gray-400'
              }`}>
                {ml.advice || 'N/A'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Win Probability</span>
              <span className="text-text-primary font-medium">{((ml.win_probability || 0) * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Confidence</span>
              <span className="text-text-primary font-medium">{(ml.confidence || 0).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Suggested Risk</span>
              <span className="text-text-primary font-medium">{(ml.suggested_risk_pct || 0).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">SD Multiplier</span>
              <span className="text-text-primary font-medium">{(ml.suggested_sd_multiplier || 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Model Version</span>
              <span className="text-text-primary font-mono">{ml.model_version || 'N/A'}</span>
            </div>
            {ml.needs_retraining && (
              <div className="mt-1 p-1.5 bg-yellow-500/10 border border-yellow-500/20 rounded text-yellow-400">
                <AlertTriangle className="w-3 h-3 inline mr-1" />
                Needs retraining
              </div>
            )}
            {ml.top_factors && ml.top_factors.length > 0 && (
              <div className="pt-2 border-t border-gray-700">
                <span className="text-text-secondary block mb-1.5">Top Factors</span>
                {formatFactors(ml.top_factors)}
              </div>
            )}
          </div>
        </div>

        {/* L4: Prophet Adaptation */}
        <div className="bg-background-card border border-gray-700 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Target className="w-4 h-4 text-green-400" />
            L4: Prophet (Bot Adaptation)
          </h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-text-secondary">Bot</span>
              <span className="text-text-primary font-medium">{prophet.bot_name || decision.bot_name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Risk Adjustment</span>
              <span className={`font-medium ${
                (prophet.risk_adjustment || 1.0) < 1.0 ? 'text-yellow-400' :
                (prophet.risk_adjustment || 1.0) > 1.0 ? 'text-green-400' :
                'text-text-primary'
              }`}>
                {(prophet.risk_adjustment || 1.0).toFixed(2)}x
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Use GEX Walls</span>
              <span className="text-text-primary font-medium">{prophet.use_gex_walls ? 'YES' : 'NO'}</span>
            </div>
            {prophet.suggested_put_strike && (
              <div className="flex justify-between">
                <span className="text-text-secondary">Put Strike</span>
                <span className="text-red-400 font-medium">${prophet.suggested_put_strike.toFixed(2)}</span>
              </div>
            )}
            {prophet.suggested_call_strike && (
              <div className="flex justify-between">
                <span className="text-text-secondary">Call Strike</span>
                <span className="text-green-400 font-medium">${prophet.suggested_call_strike.toFixed(2)}</span>
              </div>
            )}
            {prophet.reasoning && (
              <div className="pt-2 border-t border-gray-700">
                <span className="text-text-secondary">Reasoning: </span>
                <span className="text-text-primary">{prophet.reasoning}</span>
              </div>
            )}
          </div>
        </div>

        {/* Correlation Check */}
        <div className="bg-background-card border border-gray-700 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Activity className="w-4 h-4 text-orange-400" />
            Correlation Check
          </h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-text-secondary">Allowed</span>
              <span className={correlation.allowed !== false ? 'text-green-400 font-medium' : 'text-red-400 font-medium'}>
                {correlation.allowed !== false ? 'YES' : 'NO'}
              </span>
            </div>
            {correlation.max_correlation !== undefined && (
              <div className="flex justify-between">
                <span className="text-text-secondary">Max Correlation</span>
                <span className="text-text-primary font-medium">{(correlation.max_correlation || 0).toFixed(3)}</span>
              </div>
            )}
            {correlation.correlated_bots && correlation.correlated_bots.length > 0 && (
              <div className="flex justify-between">
                <span className="text-text-secondary">Correlated With</span>
                <span className="text-yellow-400 font-medium">{correlation.correlated_bots.join(', ')}</span>
              </div>
            )}
            {correlation.reason && (
              <div className="pt-2 border-t border-gray-700">
                <span className="text-text-secondary">Reason: </span>
                <span className="text-text-primary">{correlation.reason}</span>
              </div>
            )}
            {Object.keys(correlation).length === 0 && (
              <p className="text-gray-500">No correlation data</p>
            )}
          </div>
        </div>

        {/* Equity Scaling & Capital */}
        <div className="bg-background-card border border-gray-700 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-purple-400" />
            Equity & Capital
          </h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-text-secondary">Equity-Scaled Risk</span>
              <span className="text-text-primary font-medium">{(decision.equity_scaled_risk || 0).toFixed(2)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Final Risk %</span>
              <span className="text-text-primary font-medium">{(decision.final_risk_pct || 0).toFixed(2)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Position Size Mult</span>
              <span className="text-text-primary font-medium">{(decision.final_position_size_multiplier || 0).toFixed(2)}x</span>
            </div>
            {decision.regime_transition && (
              <div className="flex justify-between">
                <span className="text-text-secondary">Regime Transition</span>
                <span className="text-yellow-400 font-medium">{decision.regime_transition.replace(/_/g, ' ')}</span>
              </div>
            )}
            {decision.capital_allocation && Object.keys(decision.capital_allocation).length > 0 && (
              <div className="pt-2 border-t border-gray-700">
                <span className="text-text-secondary block mb-1">Capital Allocation</span>
                <div className="space-y-1">
                  {Object.entries(decision.capital_allocation).map(([bot, pct]) => (
                    <div key={bot} className="flex justify-between">
                      <span className="text-text-secondary">{bot}</span>
                      <span className="text-text-primary font-medium">{((pct as number) * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function OmegaDecisionExplorer() {
  const sidebarPadding = useSidebarPadding()
  const [selectedBot, setSelectedBot] = useState<string>('')
  const [limit, setLimit] = useState<number>(50)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  const { data, error, isLoading } = useOmegaDecisionHistory(
    selectedBot || undefined,
    limit
  )

  const decisions = data?.decisions || []
  const total = data?.total || 0

  const handleRowClick = (index: number) => {
    setExpandedRow(expandedRow === index ? null : index)
  }

  // Compute summary stats from visible decisions
  const decisionCounts = decisions.reduce((acc: Record<string, number>, d: any) => {
    acc[d.final_decision] = (acc[d.final_decision] || 0) + 1
    return acc
  }, {})

  return (
    <div className="min-h-screen bg-background-deep text-text-primary">
      <Navigation />
      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <a
                href="/omega"
                className="text-text-secondary hover:text-blue-400 transition-colors"
                title="Back to OMEGA Dashboard"
              >
                <ArrowLeft className="w-5 h-5" />
              </a>
              <Eye className="w-7 h-7 text-blue-400" />
              <h1 className="text-2xl font-bold">Decision Explorer</h1>
            </div>
            <p className="text-sm text-text-secondary mt-1 ml-8">
              Browse historical OMEGA 4-layer decision pipeline traces
            </p>
          </div>
          <div className="text-right text-xs text-text-secondary">
            {data?.timestamp && (
              <span>Updated: {formatTimestamp(data.timestamp)}</span>
            )}
          </div>
        </div>

        {/* Filter Panel */}
        <div className="bg-background-card border border-gray-700 rounded-lg p-4 mb-6 shadow-card">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-text-secondary" />
              <span className="text-sm text-text-secondary font-medium">Filters</span>
            </div>

            {/* Bot Selector */}
            <div className="flex items-center gap-2">
              <label className="text-xs text-text-secondary">Bot:</label>
              <select
                value={selectedBot}
                onChange={(e) => {
                  setSelectedBot(e.target.value)
                  setExpandedRow(null)
                }}
                className="bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-text-primary focus:border-blue-500 focus:outline-none cursor-pointer"
              >
                {BOT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Limit Selector */}
            <div className="flex items-center gap-2">
              <label className="text-xs text-text-secondary">Limit:</label>
              <select
                value={limit}
                onChange={(e) => {
                  setLimit(Number(e.target.value))
                  setExpandedRow(null)
                }}
                className="bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-text-primary focus:border-blue-500 focus:outline-none cursor-pointer"
              >
                {LIMIT_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>

            {/* Summary Chips */}
            <div className="flex items-center gap-2 ml-auto">
              {Object.entries(decisionCounts).map(([decision, count]) => {
                const colors = DECISION_COLORS[decision] || DECISION_COLORS.SKIP_TODAY
                return (
                  <span
                    key={decision}
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}`}
                  >
                    {String(count)}
                    <span className="hidden sm:inline">{decision.replace(/_/g, ' ')}</span>
                  </span>
                )
              })}
            </div>
          </div>
        </div>

        {/* Pagination Info */}
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-text-secondary">
            Showing <span className="text-text-primary font-medium">{decisions.length}</span> of{' '}
            <span className="text-text-primary font-medium">{total}</span> total decisions
            {selectedBot && (
              <span className="ml-1">
                for <span className="text-blue-400 font-medium">{selectedBot}</span>
              </span>
            )}
          </p>
          {isLoading && (
            <span className="text-xs text-blue-400 animate-pulse">Loading...</span>
          )}
        </div>

        {/* Error State */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-4">
            <div className="flex items-center gap-2 text-red-400 text-sm">
              <AlertTriangle className="w-4 h-4" />
              Failed to load decision history: {error.message || 'Unknown error'}
            </div>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && decisions.length === 0 && (
          <div className="bg-background-card border border-gray-700 rounded-lg p-12 text-center shadow-card">
            <Eye className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-text-primary mb-2">No decisions recorded yet</h3>
            <p className="text-sm text-text-secondary max-w-md mx-auto">
              OMEGA stores decisions in memory &mdash; they reset on server restart.
              Decisions are created when bots consult the OMEGA pipeline or when you run simulations.
            </p>
          </div>
        )}

        {/* Decision Table */}
        {decisions.length > 0 && (
          <div className="bg-background-card border border-gray-700 rounded-lg shadow-card overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-700 bg-gray-800/50">
                  <th className="w-8 p-3" />
                  <th className="text-left p-3 text-text-secondary font-medium">
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Timestamp
                    </div>
                  </th>
                  <th className="text-left p-3 text-text-secondary font-medium">Bot</th>
                  <th className="text-center p-3 text-text-secondary font-medium">
                    <div className="flex items-center justify-center gap-1" title="L1: PROVERBS Safety">
                      <Shield className="w-3 h-3" />
                      L1
                    </div>
                  </th>
                  <th className="text-center p-3 text-text-secondary font-medium">
                    <div className="flex items-center justify-center gap-1" title="L2: Ensemble Context">
                      <Layers className="w-3 h-3" />
                      L2
                    </div>
                  </th>
                  <th className="text-center p-3 text-text-secondary font-medium">
                    <div className="flex items-center justify-center gap-1" title="L3: WISDOM ML">
                      <Brain className="w-3 h-3" />
                      L3
                    </div>
                  </th>
                  <th className="text-center p-3 text-text-secondary font-medium">
                    <div className="flex items-center justify-center gap-1" title="L4: Prophet Adaptation">
                      <Target className="w-3 h-3" />
                      L4
                    </div>
                  </th>
                  <th className="text-left p-3 text-text-secondary font-medium">Final Decision</th>
                  <th className="text-left p-3 text-text-secondary font-medium hidden xl:table-cell">Decision Path</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d: any, i: number) => {
                  const isExpanded = expandedRow === i
                  const proverbs = d.proverbs_verdict || {}
                  const ml = d.ml_decision || {}
                  const ensemble = d.ensemble_context || {}
                  const prophet = d.prophet_adaptation || {}
                  const path = d.decision_path || []

                  // Determine layer pass/block status
                  const l1Pass = proverbs.can_trade !== false
                  const l2Signal = ensemble.signal || 'NEUTRAL'
                  const l3Advice = ml.advice || 'N/A'
                  const l4Risk = prophet.risk_adjustment ?? 1.0

                  return (
                    <React.Fragment key={i}>
                      <tr
                        onClick={() => handleRowClick(i)}
                        className={`border-b border-gray-700/50 cursor-pointer transition-colors ${
                          isExpanded ? 'bg-gray-800/60' : 'hover:bg-gray-800/30'
                        }`}
                      >
                        {/* Expand icon */}
                        <td className="p-3 text-center">
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-blue-400" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-gray-500" />
                          )}
                        </td>

                        {/* Timestamp */}
                        <td className="p-3 text-text-secondary whitespace-nowrap font-mono">
                          {formatTimestamp(d.timestamp)}
                        </td>

                        {/* Bot */}
                        <td className="p-3">
                          <span className="text-text-primary font-medium">{d.bot_name}</span>
                        </td>

                        {/* L1: Proverbs */}
                        <td className="p-3 text-center">
                          <LayerDot passed={l1Pass} label={l1Pass ? 'Can trade' : `Blocked: ${proverbs.reason || 'safety'}`} />
                        </td>

                        {/* L2: Ensemble */}
                        <td className="p-3 text-center">
                          <span className={`text-xs font-medium ${
                            l2Signal === 'BUY' ? 'text-green-400' :
                            l2Signal === 'SELL' ? 'text-red-400' :
                            'text-gray-400'
                          }`}>
                            {l2Signal}
                          </span>
                        </td>

                        {/* L3: ML Advisor */}
                        <td className="p-3 text-center">
                          <span className={`text-xs font-medium ${
                            l3Advice === 'TRADE_FULL' ? 'text-green-400' :
                            l3Advice === 'TRADE_REDUCED' ? 'text-yellow-400' :
                            l3Advice === 'SKIP_TODAY' ? 'text-gray-400' :
                            'text-gray-500'
                          }`}>
                            {l3Advice === 'TRADE_FULL' ? 'FULL' :
                             l3Advice === 'TRADE_REDUCED' ? 'REDUCED' :
                             l3Advice === 'SKIP_TODAY' ? 'SKIP' :
                             l3Advice}
                          </span>
                        </td>

                        {/* L4: Prophet */}
                        <td className="p-3 text-center">
                          <span className={`text-xs font-medium ${
                            l4Risk > 1.0 ? 'text-green-400' :
                            l4Risk < 1.0 ? 'text-yellow-400' :
                            'text-text-primary'
                          }`}>
                            {l4Risk.toFixed(1)}x
                          </span>
                        </td>

                        {/* Final Decision */}
                        <td className="p-3">
                          <DecisionBadge decision={d.final_decision} />
                        </td>

                        {/* Decision Path (abbreviated) */}
                        <td className="p-3 hidden xl:table-cell">
                          <span className="text-text-secondary truncate block max-w-xs" title={path.join(' -> ')}>
                            {path.length > 0
                              ? path.length <= 2
                                ? path.join(' -> ')
                                : `${path[0]} -> ... -> ${path[path.length - 1]}`
                              : <span className="text-gray-500">--</span>
                            }
                          </span>
                        </td>
                      </tr>

                      {/* Expanded Detail Row */}
                      {isExpanded && (
                        <tr>
                          <td colSpan={9}>
                            <DecisionDetail decision={d} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Info Footer */}
        <div className="mt-6 p-4 bg-blue-500/5 border border-blue-500/20 rounded-lg">
          <div className="flex items-start gap-2">
            <Info className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
            <div className="text-xs text-text-secondary space-y-1">
              <p>
                <strong className="text-text-primary">Decision Pipeline:</strong>{' '}
                L1 (PROVERBS) checks safety limits, L2 (Ensemble) reads market context,
                L3 (WISDOM) provides ML win probability, L4 (Prophet) adapts per-bot.
              </p>
              <p>
                <strong className="text-text-primary">Storage:</strong>{' '}
                Decisions are stored in memory on the OMEGA singleton and reset on server restart.
                They are not persisted to the database.
              </p>
              <p>
                <strong className="text-text-primary">Note:</strong>{' '}
                OMEGA is not currently wired into trading bots. These decisions reflect what OMEGA
                would decide during simulations or direct API calls, not actual bot trading decisions.
              </p>
            </div>
          </div>
        </div>
        </div>
      </main>
    </div>
  )
}
