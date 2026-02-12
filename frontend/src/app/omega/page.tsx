'use client'

import React from 'react'
import {
  Brain, Activity, AlertTriangle, CheckCircle,
  Shield, Layers, Target, BarChart2, RefreshCw,
  Zap, TrendingUp, Clock, Eye,
  GitBranch, Cpu,
  ChevronRight
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  useOmegaStatus,
  useOmegaBots,
  useOmegaLayers,
  useOmegaRegime,
  useOmegaCapitalAllocation,
  useOmegaCorrelations,
  useOmegaRetrainStatus,
  useOmegaMLSystems,
} from '@/lib/hooks/useMarketData'

// ==================== STATUS BADGE ====================

const StatusBadge = ({ status }: { status: string }) => {
  const config: Record<string, { bg: string; text: string; dot: string }> = {
    ACTIVE: { bg: 'bg-green-500/10', text: 'text-green-400', dot: 'bg-green-400' },
    DEGRADED: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', dot: 'bg-yellow-400' },
    DOWN: { bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-400' },
    GUTTED: { bg: 'bg-gray-500/10', text: 'text-gray-400', dot: 'bg-gray-500' },
    UNAVAILABLE: { bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-400' },
    NOT_WIRED: { bg: 'bg-orange-500/10', text: 'text-orange-400', dot: 'bg-orange-400' },
    FIXED: { bg: 'bg-green-500/10', text: 'text-green-400', dot: 'bg-green-400' },
    OPERATIONAL: { bg: 'bg-green-500/10', text: 'text-green-400', dot: 'bg-green-400' },
    PARTIALLY_BROKEN: { bg: 'bg-orange-500/10', text: 'text-orange-400', dot: 'bg-orange-400' },
  }
  const c = config[status] || config.DOWN
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${c.bg} ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot} animate-pulse`} />
      {status}
    </span>
  )
}

// ==================== LAYER CARD ====================

const LayerCard = ({ layer }: { layer: any }) => {
  const layerIcons: Record<number, any> = {
    1: Shield,
    2: Layers,
    3: Brain,
    4: Target,
  }
  const Icon = layerIcons[layer.layer_number] || Cpu

  const statusColor = layer.enabled !== false && layer.available !== false
    ? 'border-green-500/30'
    : layer.status === 'GUTTED'
    ? 'border-gray-600'
    : 'border-red-500/30'

  return (
    <div className={`bg-background-card border ${statusColor} rounded-lg p-4 shadow-card`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon className="w-5 h-5 text-blue-400" />
          <span className="text-sm font-semibold text-text-primary">L{layer.layer_number}</span>
        </div>
        <StatusBadge status={
          layer.status === 'GUTTED' ? 'GUTTED' :
          layer.available === false ? 'UNAVAILABLE' :
          layer.enabled === false ? 'DOWN' : 'ACTIVE'
        } />
      </div>
      <h3 className="text-sm font-medium text-text-primary mb-1">{layer.name}</h3>
      <p className="text-xs text-text-secondary mb-2">{layer.authority}</p>
      {layer.known_bugs && layer.known_bugs.length > 0 && (
        <div className="mt-2 p-2 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">
          <AlertTriangle className="w-3 h-3 inline mr-1" />
          {layer.known_bugs[0]}
        </div>
      )}
      {layer.note && (
        <p className="mt-2 text-xs text-yellow-400/70 italic">{layer.note}</p>
      )}
    </div>
  )
}

// ==================== BOT CARD ====================

const BotCard = ({ botName, botData }: {
  botName: string
  botData: any
  onKill?: (bot: string) => void
  onRevive?: (bot: string) => void
}) => {
  const wiring = botData?.wiring || {}
  const verdict = botData?.proverbs_verdict || {}

  const strategyMap: Record<string, string> = {
    FORTRESS: 'SPY 0DTE IC',
    ANCHOR: 'SPX Weekly IC',
    SOLOMON: 'SPY Directional',
    LAZARUS: 'SPY Call Entries',
    CORNERSTONE: 'SPY Cash-Secured Puts',
  }

  return (
    <div className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-bold text-text-primary">{botName}</h3>
          <p className="text-xs text-text-secondary">{strategyMap[botName] || 'Unknown'}</p>
        </div>
        <div className="flex items-center gap-2">
          {!wiring.wired_to_omega && (
            <span className="text-xs px-2 py-0.5 bg-orange-500/10 text-orange-400 rounded">
              NOT WIRED
            </span>
          )}
        </div>
      </div>

      {/* Kill Switch Removed Notice */}
      <div className="p-2 rounded text-xs mb-3 bg-gray-500/10 border border-gray-600/30">
        <span className="text-gray-400">
          <CheckCircle className="w-3 h-3 inline mr-1" />ALWAYS TRADING
        </span>
        <p className="mt-1 text-gray-500 text-[10px]">Kill switches removed</p>
      </div>

      {/* Proverbs Verdict */}
      {verdict && (
        <div className="text-xs text-text-secondary mb-3">
          <span className="text-text-secondary/70">Consecutive losses: </span>
          <span className={verdict.consecutive_losses > 0 ? 'text-yellow-400' : 'text-text-primary'}>
            {verdict.consecutive_losses || 0}
          </span>
          {verdict.daily_loss_pct > 0 && (
            <>
              <span className="mx-1">|</span>
              <span className="text-text-secondary/70">Daily loss: </span>
              <span className="text-red-400">{(verdict.daily_loss_pct || 0).toFixed(1)}%</span>
            </>
          )}
        </div>
      )}

      {/* Recent Decisions */}
      <div className="flex items-center gap-1 mb-3">
        <span className="text-xs text-text-secondary mr-1">Decisions:</span>
        {(botData?.recent_decisions || []).slice(0, 5).map((d: any, i: number) => (
          <span
            key={i}
            className={`w-3 h-3 rounded-full ${
              d.final_decision === 'TRADE_FULL' ? 'bg-green-400' :
              d.final_decision === 'TRADE_REDUCED' ? 'bg-yellow-400' :
              d.final_decision === 'BLOCKED_BY_PROVERBS' ? 'bg-red-400' :
              'bg-gray-500'
            }`}
            title={d.final_decision}
          />
        ))}
        {(!botData?.recent_decisions || botData.recent_decisions.length === 0) && (
          <span className="text-xs text-gray-500">No decisions yet</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <a
          href={`/omega/safety`}
          className="flex-1 px-3 py-1.5 text-xs text-center bg-gray-700/50 text-text-secondary border border-gray-600 rounded hover:bg-gray-700 transition-colors"
        >
          Safety Details
        </a>
      </div>
    </div>
  )
}

// ==================== MAIN PAGE ====================

export default function OmegaDashboard() {
  const sidebarPadding = useSidebarPadding()
  const { data: statusData, error: statusError, isLoading: statusLoading } = useOmegaStatus()
  const { data: botsData } = useOmegaBots()
  const { data: layersData } = useOmegaLayers()
  const { data: regimeData } = useOmegaRegime()
  const { data: capitalData } = useOmegaCapitalAllocation()
  const { data: correlationData } = useOmegaCorrelations()
  const { data: retrainData } = useOmegaRetrainStatus()
  const { data: mlData } = useOmegaMLSystems()

  const health = statusData?.health || 'UNKNOWN'
  const wiredCount = statusData?.wired_bot_count || 0
  const totalBots = statusData?.total_bot_count || 5
  const healthIssues = statusData?.health_issues || []

  // Regime info
  const currentRegimes = regimeData?.current_regimes || {}
  const gexRegime = currentRegimes.gex_regime || 'UNKNOWN'
  const vixRegime = currentRegimes.vix_regime || 'UNKNOWN'

  const regimeColors: Record<string, string> = {
    LOW: 'text-green-400 bg-green-500/10',
    NORMAL: 'text-blue-400 bg-blue-500/10',
    ELEVATED: 'text-yellow-400 bg-yellow-500/10',
    HIGH: 'text-orange-400 bg-orange-500/10',
    EXTREME: 'text-red-400 bg-red-500/10',
    POSITIVE: 'text-green-400 bg-green-500/10',
    NEGATIVE: 'text-red-400 bg-red-500/10',
    NEUTRAL: 'text-gray-400 bg-gray-500/10',
    UNKNOWN: 'text-gray-500 bg-gray-500/10',
  }

  return (
    <div className="min-h-screen bg-background-deep text-text-primary">
      <Navigation />
      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <Cpu className="w-7 h-7 text-blue-400" />
              <h1 className="text-2xl font-bold">OMEGA Orchestrator</h1>
              <StatusBadge status={health} />
            </div>
            <p className="text-sm text-text-secondary mt-1">
              Central Trading Decision Coordination Hub
            </p>
          </div>
          <div className="text-right">
            <div className="text-xs text-text-secondary">
              {statusData?.timestamp ? new Date(statusData.timestamp).toLocaleTimeString() : '--:--'}
            </div>
          </div>
        </div>

        {/* Critical Warning Banner */}
        {wiredCount === 0 && (
          <div className="mb-6 p-4 bg-orange-500/10 border border-orange-500/30 rounded-lg">
            <div className="flex items-center gap-2 text-orange-400 font-semibold text-sm">
              <AlertTriangle className="w-5 h-5" />
              OMEGA NOT WIRED — No trading bots are currently calling OMEGA for decisions
            </div>
            <p className="text-xs text-orange-300/70 mt-1">
              All {totalBots} bots make decisions independently via Prophet (direct call in trader.py).
              OMEGA exists but is completely bypassed. This dashboard shows what OMEGA WOULD decide.
            </p>
          </div>
        )}

        {/* Health Issues */}
        {healthIssues.length > 0 && wiredCount > 0 && (
          <div className="mb-6 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
            {healthIssues.map((issue: string, i: number) => (
              <div key={i} className="flex items-center gap-2 text-yellow-400 text-xs">
                <AlertTriangle className="w-3 h-3" />
                {issue}
              </div>
            ))}
          </div>
        )}

        {/* Stats Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card">
            <div className="flex items-center gap-2 mb-2">
              <GitBranch className="w-4 h-4 text-blue-400" />
              <span className="text-xs text-text-secondary">Bots Wired</span>
            </div>
            <div className="text-2xl font-bold text-text-primary">{wiredCount}/{totalBots}</div>
            <div className="text-xs text-orange-400 mt-1">
              {wiredCount === 0 ? 'None wired' : `${wiredCount} active`}
            </div>
          </div>

          <div className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-4 h-4 text-purple-400" />
              <span className="text-xs text-text-secondary">GEX Regime</span>
            </div>
            <div className={`text-lg font-bold px-2 py-0.5 rounded inline-block ${regimeColors[gexRegime] || regimeColors.UNKNOWN}`}>
              {gexRegime}
            </div>
          </div>

          <div className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card">
            <div className="flex items-center gap-2 mb-2">
              <BarChart2 className="w-4 h-4 text-cyan-400" />
              <span className="text-xs text-text-secondary">VIX Regime</span>
            </div>
            <div className={`text-lg font-bold px-2 py-0.5 rounded inline-block ${regimeColors[vixRegime] || regimeColors.UNKNOWN}`}>
              {vixRegime}
            </div>
          </div>

          <div className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-4 h-4 text-green-400" />
              <span className="text-xs text-text-secondary">Decisions</span>
            </div>
            <div className="text-2xl font-bold text-text-primary">
              {statusData?.recent_decision_count || 0}
            </div>
            <div className="text-xs text-text-secondary mt-1">in memory</div>
          </div>
        </div>

        {/* 4-Layer Status Cards */}
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Layers className="w-5 h-5 text-blue-400" />
          Decision Pipeline (4 Layers)
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          {(layersData?.layers || []).map((layer: any) => (
            <LayerCard key={layer.layer_number} layer={layer} />
          ))}
          {(!layersData?.layers || layersData.layers.length === 0) && statusLoading && (
            <div className="col-span-4 text-center text-text-secondary py-8">Loading layers...</div>
          )}
        </div>

        {/* Bot Grid */}
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Target className="w-5 h-5 text-green-400" />
          Trading Bots
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
          {Object.entries(botsData?.bots || {}).map(([name, data]: [string, any]) => (
            <BotCard
              key={name}
              botName={name}
              botData={data}
            />
          ))}
          {(!botsData?.bots || Object.keys(botsData.bots).length === 0) && (
            <div className="col-span-5 text-center text-text-secondary py-8">
              {statusLoading ? 'Loading bots...' : 'No bot data available'}
            </div>
          )}
        </div>

        {/* Bottom Panels */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Capital Allocation */}
          <div className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-purple-400" />
              Capital Allocation
            </h3>
            {capitalData?.capital_allocation?.allocations && (
              <div className="space-y-2">
                {Object.entries(capitalData.capital_allocation.allocations).map(([bot, pct]: [string, any]) => (
                  <div key={bot} className="flex items-center gap-2">
                    <span className="text-xs text-text-secondary w-28">{bot}</span>
                    <div className="flex-1 bg-gray-700 rounded-full h-2">
                      <div
                        className="bg-blue-500 rounded-full h-2 transition-all"
                        style={{ width: `${(pct as number) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-text-primary w-12 text-right">
                      {((pct as number) * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
            {capitalData?.capital_allocation?.note && (
              <p className="mt-2 text-xs text-yellow-400/70">{capitalData.capital_allocation.note}</p>
            )}
            <div className="mt-3 text-xs text-text-secondary">
              Total: ${(capitalData?.capital_allocation?.total_capital || 100000).toLocaleString()}
            </div>
          </div>

          {/* Correlation Matrix */}
          <div className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-cyan-400" />
              Bot Correlations
            </h3>
            {correlationData?.correlation_matrix && (
              <div className="space-y-1.5">
                {Object.entries(correlationData.correlation_matrix).map(([pair, corr]: [string, any]) => {
                  const corrVal = corr as number
                  return (
                    <div key={pair} className="flex items-center gap-2">
                      <span className="text-xs text-text-secondary w-36 truncate">{pair.replace(':', ' vs ')}</span>
                      <div className="flex-1 bg-gray-700 rounded-full h-1.5">
                        <div
                          className={`rounded-full h-1.5 ${
                            Math.abs(corrVal) > 0.7 ? 'bg-red-500' :
                            Math.abs(corrVal) > 0.3 ? 'bg-yellow-500' : 'bg-green-500'
                          }`}
                          style={{ width: `${Math.abs(corrVal) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-text-primary w-10 text-right">
                        {corrVal.toFixed(2)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
            <div className="mt-3 text-xs text-text-secondary">
              Max threshold: {(correlationData?.max_correlation_threshold || 0.7) * 100}%
            </div>
          </div>

          {/* Retrain Status */}
          <div className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card">
            <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-green-400" />
              Training Schedule
            </h3>
            {statusData?.training_schedule && (
              <div className="space-y-1.5">
                {statusData.training_schedule.map((item: any, i: number) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span className="text-text-primary">{item.model}</span>
                    <span className="text-text-secondary">{item.day} {item.time_ct}</span>
                  </div>
                ))}
              </div>
            )}
            {retrainData?.auto_retrain && (
              <div className="mt-3 pt-3 border-t border-gray-700">
                <div className="text-xs text-text-secondary">
                  Predictions tracked: {retrainData.auto_retrain.predictions_tracked || 0}
                </div>
                <div className="text-xs text-text-secondary">
                  Outcomes tracked: {retrainData.auto_retrain.outcomes_tracked || 0}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ML Systems Inventory */}
        {mlData?.systems && (
          <div className="mt-6">
            <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
              <Cpu className="w-5 h-5 text-purple-400" />
              ML System Inventory ({mlData.system_count} systems, {mlData.total_lines?.toLocaleString()} lines)
            </h2>
            <div className="bg-background-card border border-gray-700 rounded-lg shadow-card overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-700 bg-gray-800/50">
                    <th className="text-left p-3 text-text-secondary font-medium">System</th>
                    <th className="text-left p-3 text-text-secondary font-medium">Type</th>
                    <th className="text-left p-3 text-text-secondary font-medium">Role</th>
                    <th className="text-right p-3 text-text-secondary font-medium">Lines</th>
                    <th className="text-center p-3 text-text-secondary font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {mlData.systems.map((sys: any, i: number) => (
                    <tr key={i} className="border-b border-gray-700/50 hover:bg-gray-800/30">
                      <td className="p-3 text-text-primary font-medium">{sys.name}</td>
                      <td className="p-3 text-text-secondary">{sys.type}</td>
                      <td className="p-3 text-text-secondary truncate max-w-xs">{sys.role}</td>
                      <td className="p-3 text-text-primary text-right">{sys.lines?.toLocaleString()}</td>
                      <td className="p-3 text-center">
                        <StatusBadge status={sys.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Quick Nav */}
        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { href: '/omega/decisions', icon: Eye, label: 'Decision Explorer', desc: 'Browse decision history' },
            { href: '/omega/safety', icon: Shield, label: 'Safety & Risk', desc: 'Kill switch & risk management' },
            { href: '/omega/regime', icon: TrendingUp, label: 'Regime Monitor', desc: 'Market regime tracking' },
            { href: '/omega/simulate', icon: Zap, label: 'Simulator', desc: 'What-if analysis' },
          ].map(({ href, icon: NavIcon, label, desc }) => (
            <a
              key={href}
              href={href}
              className="bg-background-card border border-gray-700 rounded-lg p-4 shadow-card hover:border-blue-500/30 transition-colors group"
            >
              <NavIcon className="w-5 h-5 text-blue-400 mb-2 group-hover:text-blue-300" />
              <h3 className="text-sm font-semibold text-text-primary group-hover:text-blue-300">{label}</h3>
              <p className="text-xs text-text-secondary mt-1">{desc}</p>
              <ChevronRight className="w-4 h-4 text-gray-500 mt-2 group-hover:text-blue-400" />
            </a>
          ))}
        </div>
        </div>
      </main>
    </div>
  )
}
