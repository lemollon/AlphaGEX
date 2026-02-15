'use client'

import { useState, useCallback } from 'react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  useMarginHealth,
  useMarginBotStatus,
  useMarginBotPositions,
  useMarginAlerts,
  useMarginHistory,
  useMarginBots,
} from '@/lib/hooks/useMarketData'
import { apiClient } from '@/lib/api'
import {
  Shield,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Activity,
  DollarSign,
  BarChart3,
  Wallet,
  Gauge,
  Target,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Sliders,
  Clock,
  Zap,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  BarChart,
  Bar,
  Cell,
} from 'recharts'

// =============================================================================
// TYPES
// =============================================================================

interface BotInfo {
  bot_name: string
  instrument: string
  market_type: string
  exchange: string
  has_funding_rate: boolean
}

interface PositionMetrics {
  position_id: string
  symbol: string
  side: string
  quantity: number
  entry_price: number
  current_price: number
  notional_value: number
  initial_margin_required: number
  maintenance_margin_required: number
  liquidation_price: number | null
  distance_to_liq_pct: number | null
  unrealized_pnl: number
  funding_rate: number | null
  funding_cost_projection_daily: number | null
  funding_cost_projection_30d: number | null
}

interface AccountMetrics {
  bot_name: string
  account_equity: number
  total_margin_used: number
  available_margin: number
  margin_usage_pct: number
  margin_ratio: number
  effective_leverage: number
  total_unrealized_pnl: number
  total_notional_value: number
  position_count: number
  health_status: string
  positions: PositionMetrics[]
  total_funding_cost_daily: number | null
  total_funding_cost_30d: number | null
  warning_threshold: number
  danger_threshold: number
  critical_threshold: number
}

// =============================================================================
// HELPERS
// =============================================================================

function healthColor(status: string): string {
  switch (status) {
    case 'HEALTHY': return 'text-green-400'
    case 'WARNING': return 'text-yellow-400'
    case 'DANGER': return 'text-orange-400'
    case 'CRITICAL': return 'text-red-400'
    default: return 'text-slate-400'
  }
}

function healthBg(status: string): string {
  switch (status) {
    case 'HEALTHY': return 'bg-green-500/20 border-green-500/50'
    case 'WARNING': return 'bg-yellow-500/20 border-yellow-500/50'
    case 'DANGER': return 'bg-orange-500/20 border-orange-500/50'
    case 'CRITICAL': return 'bg-red-500/20 border-red-500/50'
    default: return 'bg-slate-500/20 border-slate-500/50'
  }
}

function healthDot(status: string): string {
  switch (status) {
    case 'HEALTHY': return 'bg-green-500'
    case 'WARNING': return 'bg-yellow-500'
    case 'DANGER': return 'bg-orange-500'
    case 'CRITICAL': return 'bg-red-500'
    default: return 'bg-slate-500'
  }
}

function formatUsd(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return '-'
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}

function formatPct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return '-'
  return `${value.toFixed(decimals)}%`
}

function marketTypeLabel(type: string): string {
  switch (type) {
    case 'stock_futures': return 'Stock Futures'
    case 'crypto_futures': return 'Crypto Futures'
    case 'crypto_perpetual': return 'Crypto Perp'
    case 'options': return 'Options'
    case 'crypto_spot': return 'Crypto Spot'
    default: return type
  }
}

// =============================================================================
// MARGIN USAGE BAR
// =============================================================================

function MarginUsageBar({ usage, warning, danger, critical }: {
  usage: number
  warning: number
  danger: number
  critical: number
}) {
  const getBarColor = () => {
    if (usage >= critical) return 'bg-red-500'
    if (usage >= danger) return 'bg-orange-500'
    if (usage >= warning) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  return (
    <div className="relative w-full">
      <div className="w-full h-4 bg-slate-700/50 rounded-full overflow-hidden">
        <div
          className={`h-full ${getBarColor()} transition-all duration-500 rounded-full`}
          style={{ width: `${Math.min(usage, 100)}%` }}
        />
      </div>
      <div className="flex justify-between mt-1 text-xs text-slate-500">
        <span>0%</span>
        <span className="text-yellow-500">{warning}%</span>
        <span className="text-orange-500">{danger}%</span>
        <span className="text-red-500">{critical}%</span>
        <span>100%</span>
      </div>
    </div>
  )
}

// =============================================================================
// LIQUIDATION PRICE VISUAL
// =============================================================================

function LiquidationPriceBar({ entry, current, liquidation, side }: {
  entry: number
  current: number
  liquidation: number | null
  side: string
}) {
  if (!liquidation || liquidation <= 0) return <span className="text-slate-500 text-xs">N/A</span>

  const min = Math.min(entry, current, liquidation) * 0.95
  const max = Math.max(entry, current, liquidation) * 1.05
  const range = max - min
  if (range <= 0) return null

  const entryPct = ((entry - min) / range) * 100
  const currentPct = ((current - min) / range) * 100
  const liqPct = ((liquidation - min) / range) * 100

  return (
    <div className="relative w-full h-6">
      <div className="absolute inset-0 bg-slate-700/30 rounded">
        {/* Liquidation marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-red-500"
          style={{ left: `${liqPct}%` }}
        />
        {/* Entry marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-blue-400"
          style={{ left: `${entryPct}%` }}
        />
        {/* Current price marker */}
        <div
          className="absolute top-1 bottom-1 w-2 h-2 rounded-full bg-white border border-slate-300"
          style={{ left: `${currentPct}%`, transform: 'translateX(-50%)' }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-500 mt-7">
        <span className="text-red-400">LIQ ${liquidation.toFixed(0)}</span>
        <span className="text-blue-400">Entry ${entry.toFixed(0)}</span>
        <span className="text-white">Now ${current.toFixed(0)}</span>
      </div>
    </div>
  )
}

// =============================================================================
// SCENARIO SIMULATOR
// =============================================================================

function ScenarioSimulator({ botName }: { botName: string }) {
  const [priceChangePct, setPriceChangePct] = useState(0)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const simulate = useCallback(async () => {
    setLoading(true)
    try {
      const response = await apiClient.postMarginSimulatePrice(botName, {
        price_change_pct: priceChangePct,
      })
      setResult(response.data?.data)
    } catch (e) {
      console.error('Simulation failed:', e)
    }
    setLoading(false)
  }, [botName, priceChangePct])

  return (
    <div className="bg-background-card border border-slate-700/50 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <Sliders className="w-4 h-4 text-purple-400" />
        <h3 className="text-sm font-medium text-text-primary">Scenario Simulator</h3>
      </div>

      <div className="space-y-3">
        <div>
          <label className="text-xs text-text-secondary block mb-1">
            What if price moves...
          </label>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min="-20"
              max="20"
              step="0.5"
              value={priceChangePct}
              onChange={(e) => setPriceChangePct(parseFloat(e.target.value))}
              className="flex-1 accent-purple-500"
            />
            <span className={`text-sm font-mono w-16 text-right ${priceChangePct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {priceChangePct >= 0 ? '+' : ''}{priceChangePct.toFixed(1)}%
            </span>
          </div>
        </div>

        <button
          onClick={simulate}
          disabled={loading}
          className="w-full px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded disabled:opacity-50"
        >
          {loading ? 'Simulating...' : 'Run Scenario'}
        </button>

        {result && (
          <div className="space-y-2 mt-3">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-slate-800/50 rounded p-2">
                <div className="text-text-secondary">Current Usage</div>
                <div className="text-text-primary font-medium">
                  {formatPct(result.current_margin_usage_pct)}
                </div>
              </div>
              <div className="bg-slate-800/50 rounded p-2">
                <div className="text-text-secondary">Projected Usage</div>
                <div className={`font-medium ${
                  result.projected_margin_usage_pct > 80 ? 'text-red-400' :
                  result.projected_margin_usage_pct > 60 ? 'text-yellow-400' : 'text-green-400'
                }`}>
                  {formatPct(result.projected_margin_usage_pct)}
                </div>
              </div>
            </div>
            {result.would_trigger_liquidation && (
              <div className="bg-red-500/20 border border-red-500/50 rounded p-2 text-red-400 text-xs">
                This scenario would trigger LIQUIDATION
              </div>
            )}
            {result.would_trigger_margin_call && !result.would_trigger_liquidation && (
              <div className="bg-orange-500/20 border border-orange-500/50 rounded p-2 text-orange-400 text-xs">
                This scenario would trigger a margin call
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// MARGIN HISTORY CHART
// =============================================================================

function MarginHistoryChart({ botName }: { botName: string }) {
  const { data, isLoading } = useMarginHistory(botName, 24)

  if (isLoading) return <div className="h-48 flex items-center justify-center text-slate-500">Loading...</div>
  if (!data?.snapshots?.length) return <div className="h-48 flex items-center justify-center text-slate-500">No history data</div>

  const chartData = data.snapshots.map((s: any) => ({
    time: new Date(s.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    usage: s.margin_usage_pct,
    equity: s.account_equity,
    leverage: s.effective_leverage,
  }))

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={chartData}>
        <defs>
          <linearGradient id="marginUsageGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey="time" stroke="#64748b" fontSize={10} />
        <YAxis stroke="#64748b" fontSize={10} domain={[0, 100]} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
          labelStyle={{ color: '#94a3b8' }}
        />
        <ReferenceLine y={60} stroke="#eab308" strokeDasharray="3 3" label={{ value: 'Warn', fill: '#eab308', fontSize: 10 }} />
        <ReferenceLine y={80} stroke="#f97316" strokeDasharray="3 3" label={{ value: 'Danger', fill: '#f97316', fontSize: 10 }} />
        <ReferenceLine y={90} stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'Critical', fill: '#ef4444', fontSize: 10 }} />
        <Area
          type="monotone"
          dataKey="usage"
          stroke="#8b5cf6"
          fill="url(#marginUsageGrad)"
          name="Margin Usage %"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// =============================================================================
// BOT DETAIL PANEL
// =============================================================================

function BotDetailPanel({ botName, onClose }: { botName: string; onClose: () => void }) {
  const { data: status, isLoading: statusLoading } = useMarginBotStatus(botName)
  const { data: alertsData } = useMarginAlerts(botName, 10)

  if (statusLoading) {
    return (
      <div className="bg-background-card border border-slate-700/50 rounded-lg p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700 rounded w-1/3" />
          <div className="h-32 bg-slate-700 rounded" />
        </div>
      </div>
    )
  }

  if (!status || status.status === 'no_data') {
    return (
      <div className="bg-background-card border border-slate-700/50 rounded-lg p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-bold text-text-primary">{botName}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">Close</button>
        </div>
        <p className="text-slate-500">No margin data available. Bot may not be active.</p>
      </div>
    )
  }

  const metrics = status as AccountMetrics

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-background-card border border-slate-700/50 rounded-lg p-4">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${healthDot(metrics.health_status)} animate-pulse`} />
            <h2 className="text-lg font-bold text-text-primary">{metrics.bot_name}</h2>
            <span className={`text-sm px-2 py-0.5 rounded ${healthBg(metrics.health_status)} ${healthColor(metrics.health_status)}`}>
              {metrics.health_status}
            </span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">Close</button>
        </div>

        {/* Key Metrics Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-text-secondary text-xs flex items-center gap-1">
              <Wallet className="w-3 h-3" /> Account Equity
            </div>
            <div className="text-text-primary text-lg font-bold">{formatUsd(metrics.account_equity)}</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-text-secondary text-xs flex items-center gap-1">
              <DollarSign className="w-3 h-3" /> Margin Used
            </div>
            <div className="text-text-primary text-lg font-bold">
              {formatUsd(metrics.total_margin_used)}
              <span className="text-xs text-text-secondary ml-1">({formatPct(metrics.margin_usage_pct)})</span>
            </div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-text-secondary text-xs flex items-center gap-1">
              <TrendingUp className="w-3 h-3" /> Available
            </div>
            <div className="text-green-400 text-lg font-bold">{formatUsd(metrics.available_margin)}</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-text-secondary text-xs flex items-center gap-1">
              <Gauge className="w-3 h-3" /> Eff. Leverage
            </div>
            <div className="text-text-primary text-lg font-bold">{metrics.effective_leverage.toFixed(2)}x</div>
          </div>
        </div>

        {/* Margin Usage Bar */}
        <MarginUsageBar
          usage={metrics.margin_usage_pct}
          warning={metrics.warning_threshold}
          danger={metrics.danger_threshold}
          critical={metrics.critical_threshold}
        />
      </div>

      {/* Positions Table */}
      {metrics.positions.length > 0 && (
        <div className="bg-background-card border border-slate-700/50 rounded-lg p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
            <Target className="w-4 h-4 text-blue-400" />
            Position Margin Details ({metrics.position_count})
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-text-secondary border-b border-slate-700">
                  <th className="text-left py-2 pr-2">Symbol</th>
                  <th className="text-left py-2 pr-2">Side</th>
                  <th className="text-right py-2 pr-2">Size</th>
                  <th className="text-right py-2 pr-2">Entry</th>
                  <th className="text-right py-2 pr-2">Current</th>
                  <th className="text-right py-2 pr-2">Notional</th>
                  <th className="text-right py-2 pr-2">Margin Req</th>
                  <th className="text-right py-2 pr-2">Liq Price</th>
                  <th className="text-right py-2 pr-2">Dist to Liq</th>
                  <th className="text-right py-2">Unrealized P&L</th>
                </tr>
              </thead>
              <tbody>
                {metrics.positions.map((pos) => (
                  <tr key={pos.position_id} className="border-b border-slate-800 hover:bg-slate-800/30">
                    <td className="py-2 pr-2 text-text-primary font-medium">{pos.symbol}</td>
                    <td className={`py-2 pr-2 ${pos.side === 'long' ? 'text-green-400' : 'text-red-400'}`}>
                      {pos.side.toUpperCase()}
                    </td>
                    <td className="py-2 pr-2 text-right text-text-primary">{pos.quantity}</td>
                    <td className="py-2 pr-2 text-right text-text-secondary">{formatUsd(pos.entry_price)}</td>
                    <td className="py-2 pr-2 text-right text-text-primary">{formatUsd(pos.current_price)}</td>
                    <td className="py-2 pr-2 text-right text-text-primary">{formatUsd(pos.notional_value)}</td>
                    <td className="py-2 pr-2 text-right text-yellow-400">{formatUsd(pos.initial_margin_required)}</td>
                    <td className="py-2 pr-2 text-right text-red-400">
                      {pos.liquidation_price ? formatUsd(pos.liquidation_price) : '-'}
                    </td>
                    <td className={`py-2 pr-2 text-right ${
                      pos.distance_to_liq_pct !== null
                        ? pos.distance_to_liq_pct < 5 ? 'text-red-400' : pos.distance_to_liq_pct < 10 ? 'text-yellow-400' : 'text-green-400'
                        : 'text-slate-500'
                    }`}>
                      {pos.distance_to_liq_pct !== null ? formatPct(pos.distance_to_liq_pct) : '-'}
                    </td>
                    <td className={`py-2 text-right font-medium ${pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatUsd(pos.unrealized_pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Liquidation visualizations */}
          {metrics.positions.some(p => p.liquidation_price) && (
            <div className="mt-4 space-y-3">
              <h4 className="text-xs text-text-secondary">Liquidation Risk Visualization</h4>
              {metrics.positions
                .filter(p => p.liquidation_price)
                .map(pos => (
                  <div key={pos.position_id} className="bg-slate-800/30 rounded p-2">
                    <div className="text-xs text-text-secondary mb-1">
                      {pos.symbol} {pos.side.toUpperCase()} @ {formatUsd(pos.entry_price)}
                    </div>
                    <LiquidationPriceBar
                      entry={pos.entry_price}
                      current={pos.current_price}
                      liquidation={pos.liquidation_price}
                      side={pos.side}
                    />
                  </div>
                ))
              }
            </div>
          )}

          {/* Funding rate tracker (perps only) */}
          {metrics.total_funding_cost_daily !== null && (
            <div className="mt-4 bg-slate-800/30 rounded-lg p-3">
              <h4 className="text-xs text-text-secondary mb-2 flex items-center gap-1">
                <Clock className="w-3 h-3" /> Funding Rate Tracker (Perpetuals)
              </h4>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-text-secondary">Daily Cost:</span>
                  <span className={`ml-2 font-medium ${(metrics.total_funding_cost_daily || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatUsd(metrics.total_funding_cost_daily, 4)}
                  </span>
                </div>
                <div>
                  <span className="text-text-secondary">30-Day Projection:</span>
                  <span className={`ml-2 font-medium ${(metrics.total_funding_cost_30d || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatUsd(metrics.total_funding_cost_30d)}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Two-column: History Chart + Scenario Simulator */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-background-card border border-slate-700/50 rounded-lg p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-purple-400" />
            Margin Usage History (24h)
          </h3>
          <MarginHistoryChart botName={botName} />
        </div>
        <ScenarioSimulator botName={botName} />
      </div>

      {/* Recent Alerts */}
      {alertsData?.alerts?.length > 0 && (
        <div className="bg-background-card border border-slate-700/50 rounded-lg p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-yellow-400" />
            Recent Alerts
          </h3>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {alertsData.alerts.slice(0, 10).map((alert: any, i: number) => (
              <div
                key={i}
                className={`text-xs p-2 rounded ${
                  alert.level === 'CRITICAL' ? 'bg-red-500/10 border border-red-500/30 text-red-400' :
                  alert.level === 'DANGER' ? 'bg-orange-500/10 border border-orange-500/30 text-orange-400' :
                  alert.level === 'WARNING' ? 'bg-yellow-500/10 border border-yellow-500/30 text-yellow-400' :
                  'bg-slate-500/10 border border-slate-500/30 text-slate-400'
                }`}
              >
                <div className="flex justify-between">
                  <span className="font-medium">{alert.level}</span>
                  <span className="text-slate-500">
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <div className="mt-1">{alert.message}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function MarginDashboard() {
  const sidebarPadding = useSidebarPadding()
  const { data: health, isLoading: healthLoading, mutate: refreshHealth } = useMarginHealth()
  const { data: botsData, isLoading: botsLoading } = useMarginBots()
  const [selectedBot, setSelectedBot] = useState<string | null>(null)

  const bots: BotInfo[] = botsData?.bots || []

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-6">

          {/* Page Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Shield className="w-8 h-8 text-purple-400" />
              <div>
                <h1 className="text-2xl font-bold text-text-primary">Margin Management</h1>
                <p className="text-sm text-text-secondary">
                  Real-time margin monitoring across all market types
                </p>
              </div>
            </div>
            <button
              onClick={() => refreshHealth()}
              className="flex items-center gap-2 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>

          {/* Portfolio Overview */}
          {healthLoading ? (
            <div className="bg-background-card border border-slate-700/50 rounded-lg p-6 mb-6">
              <div className="animate-pulse space-y-4">
                <div className="h-6 bg-slate-700 rounded w-1/4" />
                <div className="grid grid-cols-4 gap-4">
                  {[1,2,3,4].map(i => <div key={i} className="h-20 bg-slate-700 rounded" />)}
                </div>
              </div>
            </div>
          ) : health ? (
            <div className="bg-background-card border border-slate-700/50 rounded-lg p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-text-primary flex items-center gap-2">
                  <Activity className="w-5 h-5 text-purple-400" />
                  Portfolio Margin Overview
                </h2>
                <span className={`text-sm px-3 py-1 rounded ${healthBg(health.worst_health)} ${healthColor(health.worst_health)}`}>
                  {health.worst_health}
                </span>
              </div>

              <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-4">
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-text-secondary text-xs">Total Equity</div>
                  <div className="text-text-primary text-xl font-bold">{formatUsd(health.total_equity)}</div>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-text-secondary text-xs">Total Margin Used</div>
                  <div className="text-yellow-400 text-xl font-bold">{formatUsd(health.total_margin_used)}</div>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-text-secondary text-xs">Available Margin</div>
                  <div className="text-green-400 text-xl font-bold">{formatUsd(health.total_available)}</div>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-text-secondary text-xs">Overall Usage</div>
                  <div className="text-text-primary text-xl font-bold">{formatPct(health.overall_margin_usage_pct)}</div>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-text-secondary text-xs">Unrealized P&L</div>
                  <div className={`text-xl font-bold ${health.total_unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatUsd(health.total_unrealized_pnl)}
                  </div>
                </div>
              </div>

              {/* Overall margin bar */}
              <MarginUsageBar usage={health.overall_margin_usage_pct || 0} warning={60} danger={80} critical={90} />
            </div>
          ) : null}

          {/* Bot Grid */}
          <div className="mb-6">
            <h2 className="text-lg font-bold text-text-primary mb-4 flex items-center gap-2">
              <Zap className="w-5 h-5 text-yellow-400" />
              Bot-by-Bot Margin Status
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {botsLoading ? (
                [1,2,3,4].map(i => (
                  <div key={i} className="bg-background-card border border-slate-700/50 rounded-lg p-4 animate-pulse">
                    <div className="h-5 bg-slate-700 rounded w-1/2 mb-3" />
                    <div className="h-8 bg-slate-700 rounded mb-2" />
                    <div className="h-4 bg-slate-700 rounded" />
                  </div>
                ))
              ) : (
                bots.map(bot => {
                  const botHealth = health?.bots?.find((b: any) => b.bot_name === bot.bot_name)
                  const isSelected = selectedBot === bot.bot_name
                  return (
                    <button
                      key={bot.bot_name}
                      onClick={() => setSelectedBot(isSelected ? null : bot.bot_name)}
                      className={`text-left bg-background-card border rounded-lg p-4 transition-all hover:border-purple-500/50 ${
                        isSelected ? 'border-purple-500 ring-1 ring-purple-500/30' : 'border-slate-700/50'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${healthDot(botHealth?.health_status || 'UNKNOWN')}`} />
                          <span className="text-sm font-bold text-text-primary">{bot.bot_name}</span>
                        </div>
                        <span className="text-xs text-text-secondary px-1.5 py-0.5 bg-slate-800 rounded">
                          {marketTypeLabel(bot.market_type)}
                        </span>
                      </div>

                      <div className="text-xs text-text-secondary mb-1">
                        {bot.instrument} @ {bot.exchange}
                      </div>

                      {botHealth ? (
                        <>
                          <div className="flex justify-between items-center mb-1">
                            <span className="text-xs text-text-secondary">Equity</span>
                            <span className="text-sm text-text-primary font-medium">{formatUsd(botHealth.equity)}</span>
                          </div>
                          <div className="flex justify-between items-center mb-2">
                            <span className="text-xs text-text-secondary">Margin Used</span>
                            <span className={`text-sm font-medium ${
                              botHealth.margin_used_pct > 80 ? 'text-red-400' :
                              botHealth.margin_used_pct > 60 ? 'text-yellow-400' : 'text-green-400'
                            }`}>
                              {formatPct(botHealth.margin_used_pct)}
                            </span>
                          </div>
                          <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                botHealth.margin_used_pct > 80 ? 'bg-red-500' :
                                botHealth.margin_used_pct > 60 ? 'bg-yellow-500' : 'bg-green-500'
                              }`}
                              style={{ width: `${Math.min(botHealth.margin_used_pct || 0, 100)}%` }}
                            />
                          </div>
                          <div className="flex justify-between items-center mt-1">
                            <span className="text-[10px] text-text-secondary">
                              {botHealth.position_count} position{botHealth.position_count !== 1 ? 's' : ''}
                            </span>
                            <span className={`text-[10px] ${(botHealth.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              P&L: {formatUsd(botHealth.unrealized_pnl)}
                            </span>
                          </div>
                        </>
                      ) : (
                        <div className="text-xs text-slate-500 mt-2">No data available</div>
                      )}
                    </button>
                  )
                })
              )}
            </div>
          </div>

          {/* Selected Bot Detail Panel */}
          {selectedBot && (
            <BotDetailPanel
              botName={selectedBot}
              onClose={() => setSelectedBot(null)}
            />
          )}

        </div>
      </main>
    </div>
  )
}
