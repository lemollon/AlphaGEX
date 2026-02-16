'use client'

/**
 * BotMarginWidget - Reusable margin status display for any leveraged bot.
 *
 * Shows: margin usage bar, account equity, available margin, effective leverage,
 * liquidation distance, unrealized P&L, funding costs (perps), and per-position
 * margin breakdown.
 *
 * Usage:
 *   <BotMarginWidget botName="AGAPE_BTC_PERP" />
 */

import { useState } from 'react'
import {
  Shield,
  AlertTriangle,
  TrendingUp,
  DollarSign,
  Gauge,
  Target,
  ChevronDown,
  ChevronUp,
  Clock,
  Wallet,
} from 'lucide-react'
import { useMarginBotStatus } from '@/lib/hooks/useMarketData'

// =============================================================================
// TYPES
// =============================================================================

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

function healthBorder(status: string): string {
  switch (status) {
    case 'HEALTHY': return 'border-green-800'
    case 'WARNING': return 'border-yellow-800'
    case 'DANGER': return 'border-orange-800'
    case 'CRITICAL': return 'border-red-800'
    default: return 'border-gray-800'
  }
}

function formatUsd(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return '—'
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}

function formatPct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(decimals)}%`
}

// =============================================================================
// MARGIN USAGE BAR
// =============================================================================

function MarginBar({ usage, warning, danger, critical }: {
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
    <div className="w-full">
      <div className="w-full h-3 bg-slate-700/50 rounded-full overflow-hidden">
        <div
          className={`h-full ${getBarColor()} transition-all duration-500 rounded-full`}
          style={{ width: `${Math.min(usage, 100)}%` }}
        />
      </div>
      <div className="flex justify-between mt-1 text-[10px] text-slate-500">
        <span>0%</span>
        <span className="text-yellow-500/70">{warning}%</span>
        <span className="text-orange-500/70">{danger}%</span>
        <span className="text-red-500/70">{critical}%</span>
        <span>100%</span>
      </div>
    </div>
  )
}

// =============================================================================
// LIQUIDATION DISTANCE INDICATOR
// =============================================================================

function LiqDistanceIndicator({ pct }: { pct: number | null }) {
  if (pct === null || pct === undefined) return <span className="text-slate-500">N/A</span>

  const color = pct < 5 ? 'text-red-400' : pct < 10 ? 'text-orange-400' : pct < 20 ? 'text-yellow-400' : 'text-green-400'
  const bgColor = pct < 5 ? 'bg-red-500' : pct < 10 ? 'bg-orange-500' : pct < 20 ? 'bg-yellow-500' : 'bg-green-500'

  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${bgColor} ${pct < 5 ? 'animate-pulse' : ''}`} />
      <span className={`font-mono font-bold ${color}`}>{pct.toFixed(1)}%</span>
    </div>
  )
}

// =============================================================================
// MAIN WIDGET
// =============================================================================

export default function BotMarginWidget({ botName }: { botName: string }) {
  const { data: status, isLoading } = useMarginBotStatus(botName)
  const [showPositions, setShowPositions] = useState(false)

  if (isLoading) {
    return (
      <div className="rounded-lg border border-gray-800 bg-[#0a0a0a] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-5 bg-slate-700 rounded w-1/3" />
          <div className="h-3 bg-slate-700 rounded w-full" />
          <div className="grid grid-cols-3 gap-3">
            {[1,2,3].map(i => <div key={i} className="h-12 bg-slate-700 rounded" />)}
          </div>
        </div>
      </div>
    )
  }

  if (!status || status.status === 'no_data') {
    return (
      <div className="rounded-lg border border-gray-800 bg-[#0a0a0a] p-4">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-slate-500" />
          <span className="text-sm text-slate-500">Margin data not available</span>
        </div>
      </div>
    )
  }

  const m = status as AccountMetrics

  // Closest liquidation across all positions
  const closestLiq = m.positions
    .filter(p => p.distance_to_liq_pct !== null)
    .sort((a, b) => (a.distance_to_liq_pct || 999) - (b.distance_to_liq_pct || 999))[0]

  return (
    <div className={`rounded-lg border p-4 ${healthBorder(m.health_status)} bg-[#0a0a0a]`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield className={`w-5 h-5 ${healthColor(m.health_status)}`} />
          <span className="text-sm font-semibold text-white">Margin Status</span>
        </div>
        <span className={`px-2 py-1 rounded text-xs font-bold ${healthBg(m.health_status)} ${healthColor(m.health_status)}`}>
          {m.health_status}
        </span>
      </div>

      {/* Margin Usage Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-slate-400">Margin Usage</span>
          <span className={`font-mono font-bold ${healthColor(m.health_status)}`}>
            {formatPct(m.margin_usage_pct)}
          </span>
        </div>
        <MarginBar
          usage={m.margin_usage_pct}
          warning={m.warning_threshold || 60}
          danger={m.danger_threshold || 80}
          critical={m.critical_threshold || 90}
        />
      </div>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <Wallet className="w-3 h-3" /> Equity
          </div>
          <div className="text-white font-mono text-sm font-bold mt-0.5">{formatUsd(m.account_equity)}</div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <DollarSign className="w-3 h-3" /> Margin Used
          </div>
          <div className="text-yellow-400 font-mono text-sm font-bold mt-0.5">{formatUsd(m.total_margin_used)}</div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> Available
          </div>
          <div className="text-green-400 font-mono text-sm font-bold mt-0.5">{formatUsd(m.available_margin)}</div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <Gauge className="w-3 h-3" /> Leverage
          </div>
          <div className="text-white font-mono text-sm font-bold mt-0.5">{m.effective_leverage?.toFixed(2) || '—'}x</div>
        </div>
      </div>

      {/* Second Row: Liquidation + Unrealized P&L */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Nearest Liquidation
          </div>
          <div className="mt-0.5">
            {closestLiq ? (
              <div>
                <LiqDistanceIndicator pct={closestLiq.distance_to_liq_pct} />
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {closestLiq.symbol} @ {formatUsd(closestLiq.liquidation_price)}
                </div>
              </div>
            ) : (
              <span className="text-slate-500 text-sm">No positions</span>
            )}
          </div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <Target className="w-3 h-3" /> Unrealized P&L
          </div>
          <div className={`font-mono text-sm font-bold mt-0.5 ${m.total_unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {m.total_unrealized_pnl >= 0 ? '+' : ''}{formatUsd(m.total_unrealized_pnl)}
          </div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400">Positions</div>
          <div className="text-white font-mono text-sm font-bold mt-0.5">
            {m.position_count} open
          </div>
        </div>
      </div>

      {/* Funding Costs (perps only) */}
      {m.total_funding_cost_daily !== null && m.total_funding_cost_daily !== undefined && (
        <div className="bg-slate-800/30 rounded-lg p-2.5 mb-3">
          <div className="text-[11px] text-slate-400 flex items-center gap-1 mb-1">
            <Clock className="w-3 h-3" /> Funding Costs (Perpetuals)
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <span className="text-slate-500">Daily:</span>
              <span className={`ml-2 font-mono font-bold ${(m.total_funding_cost_daily || 0) <= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {formatUsd(m.total_funding_cost_daily, 4)}
              </span>
            </div>
            <div>
              <span className="text-slate-500">30-Day Projection:</span>
              <span className={`ml-2 font-mono font-bold ${(m.total_funding_cost_30d || 0) <= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {formatUsd(m.total_funding_cost_30d)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Warning Banners */}
      {m.health_status === 'CRITICAL' && (
        <div className="bg-red-500/20 border border-red-500/50 rounded p-2 mb-3 text-red-400 text-xs font-bold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          CRITICAL: Margin usage at {formatPct(m.margin_usage_pct)}. Close positions or add capital immediately.
        </div>
      )}
      {m.health_status === 'DANGER' && (
        <div className="bg-orange-500/20 border border-orange-500/50 rounded p-2 mb-3 text-orange-400 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          Margin usage elevated at {formatPct(m.margin_usage_pct)}. Consider reducing exposure.
        </div>
      )}
      {closestLiq && closestLiq.distance_to_liq_pct !== null && closestLiq.distance_to_liq_pct < 5 && (
        <div className="bg-red-500/20 border border-red-500/50 rounded p-2 mb-3 text-red-400 text-xs font-bold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 animate-pulse" />
          LIQUIDATION RISK: {closestLiq.symbol} is only {closestLiq.distance_to_liq_pct?.toFixed(1)}% from liquidation price ({formatUsd(closestLiq.liquidation_price)})
        </div>
      )}

      {/* Expandable Position Details */}
      {m.positions.length > 0 && (
        <div>
          <button
            onClick={() => setShowPositions(!showPositions)}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors"
          >
            {showPositions ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {showPositions ? 'Hide' : 'Show'} per-position margin details
          </button>

          {showPositions && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-700">
                    <th className="text-left py-1.5 pr-2">Symbol</th>
                    <th className="text-left py-1.5 pr-2">Side</th>
                    <th className="text-right py-1.5 pr-2">Qty</th>
                    <th className="text-right py-1.5 pr-2">Entry</th>
                    <th className="text-right py-1.5 pr-2">Current</th>
                    <th className="text-right py-1.5 pr-2">Margin Req</th>
                    <th className="text-right py-1.5 pr-2">Liq Price</th>
                    <th className="text-right py-1.5 pr-2">Dist to Liq</th>
                    <th className="text-right py-1.5">Unreal. P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {m.positions.map((pos) => (
                    <tr key={pos.position_id} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                      <td className="py-1.5 pr-2 text-white font-medium">{pos.symbol}</td>
                      <td className={`py-1.5 pr-2 ${pos.side === 'long' ? 'text-green-400' : 'text-red-400'}`}>
                        {pos.side.toUpperCase()}
                      </td>
                      <td className="py-1.5 pr-2 text-right text-white">{pos.quantity}</td>
                      <td className="py-1.5 pr-2 text-right text-slate-400">{formatUsd(pos.entry_price)}</td>
                      <td className="py-1.5 pr-2 text-right text-white">{formatUsd(pos.current_price)}</td>
                      <td className="py-1.5 pr-2 text-right text-yellow-400">{formatUsd(pos.initial_margin_required)}</td>
                      <td className="py-1.5 pr-2 text-right text-red-400">
                        {pos.liquidation_price ? formatUsd(pos.liquidation_price) : '—'}
                      </td>
                      <td className="py-1.5 pr-2 text-right">
                        <LiqDistanceIndicator pct={pos.distance_to_liq_pct} />
                      </td>
                      <td className={`py-1.5 text-right font-medium ${pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatUsd(pos.unrealized_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
