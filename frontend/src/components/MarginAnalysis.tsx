'use client'

/**
 * MarginAnalysis - Embedded margin analysis for each bot's overview page.
 *
 * Displays: margin usage bar, account equity, available margin, effective leverage,
 * liquidation prices + distance, per-position breakdown, and funding costs (perps).
 *
 * Fetches from each bot's /margin endpoint (e.g. /api/valor/margin).
 */

import { useState, useEffect } from 'react'
import useSWR from 'swr'
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
  Info,
} from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''

const fetcher = async (url: string) => {
  const res = await fetch(`${API_BASE}${url}`)
  if (!res.ok) throw new Error(`Failed to fetch margin data`)
  return res.json()
}

// =============================================================================
// TYPES
// =============================================================================

interface MarginAnalysisProps {
  botName: string
  marketType: 'stock_futures' | 'crypto_futures' | 'crypto_perp'
  marginEndpoint: string
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
    case 'HEALTHY': return 'bg-green-500/20 text-green-400'
    case 'WARNING': return 'bg-yellow-500/20 text-yellow-400'
    case 'DANGER': return 'bg-orange-500/20 text-orange-400'
    case 'CRITICAL': return 'bg-red-500/20 text-red-400'
    default: return 'bg-slate-500/20 text-slate-400'
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

function fmt(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return '—'
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}

function pct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(decimals)}%`
}

// =============================================================================
// MARGIN BAR
// =============================================================================

function MarginBar({ usage }: { usage: number }) {
  const getBarColor = () => {
    if (usage >= 85) return 'bg-red-500'
    if (usage >= 70) return 'bg-orange-500'
    if (usage >= 50) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  return (
    <div className="w-full">
      <div className="w-full h-3 bg-slate-700/50 rounded-full overflow-hidden relative">
        <div
          className={`h-full ${getBarColor()} transition-all duration-500 rounded-full`}
          style={{ width: `${Math.min(usage, 100)}%` }}
        />
        {/* Threshold markers */}
        <div className="absolute top-0 left-[50%] h-full w-px bg-yellow-500/40" />
        <div className="absolute top-0 left-[70%] h-full w-px bg-orange-500/40" />
        <div className="absolute top-0 left-[85%] h-full w-px bg-red-500/40" />
      </div>
      <div className="flex justify-between mt-1 text-[10px] text-slate-500">
        <span>0%</span>
        <span className="text-yellow-500/70">50%</span>
        <span className="text-orange-500/70">70%</span>
        <span className="text-red-500/70">85%</span>
        <span>100%</span>
      </div>
    </div>
  )
}

// =============================================================================
// LIQUIDATION DISTANCE
// =============================================================================

function LiqDistance({ pctValue }: { pctValue: number | null | undefined }) {
  if (pctValue === null || pctValue === undefined) return <span className="text-slate-500">N/A</span>
  const color = pctValue < 5 ? 'text-red-400' : pctValue < 10 ? 'text-orange-400' : pctValue < 20 ? 'text-yellow-400' : 'text-green-400'
  const dotColor = pctValue < 5 ? 'bg-red-500' : pctValue < 10 ? 'bg-orange-500' : pctValue < 20 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${dotColor} ${pctValue < 5 ? 'animate-pulse' : ''}`} />
      <span className={`font-mono font-bold ${color}`}>{pctValue.toFixed(1)}%</span>
    </div>
  )
}

// =============================================================================
// LIQUIDATION PRICE VISUALIZATION
// =============================================================================

function LiqVisualization({ liqPrice, entryPrice, currentPrice, side }: {
  liqPrice: number
  entryPrice: number
  currentPrice: number
  side: string
}) {
  // Determine range
  const prices = [liqPrice, entryPrice, currentPrice]
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || 1

  const liqPct = ((liqPrice - min) / range) * 100
  const entryPct = ((entryPrice - min) / range) * 100
  const currentPct = ((currentPrice - min) / range) * 100

  return (
    <div className="relative h-6 mt-2 mb-1">
      {/* Track */}
      <div className="absolute top-2.5 left-0 right-0 h-1 bg-slate-700 rounded" />
      {/* Danger zone from liq to entry */}
      <div
        className="absolute top-2.5 h-1 bg-red-900/40 rounded"
        style={{
          left: `${Math.min(liqPct, entryPct)}%`,
          width: `${Math.abs(entryPct - liqPct)}%`,
        }}
      />
      {/* Liq marker */}
      <div className="absolute top-0" style={{ left: `${liqPct}%`, transform: 'translateX(-50%)' }}>
        <div className="w-1.5 h-5 bg-red-500 rounded-sm" />
        <div className="text-[9px] text-red-400 mt-0.5 whitespace-nowrap">LIQ</div>
      </div>
      {/* Entry marker */}
      <div className="absolute top-0" style={{ left: `${entryPct}%`, transform: 'translateX(-50%)' }}>
        <div className="w-1.5 h-5 bg-slate-400 rounded-sm" />
        <div className="text-[9px] text-slate-400 mt-0.5 whitespace-nowrap">ENTRY</div>
      </div>
      {/* Current price marker */}
      <div className="absolute top-0" style={{ left: `${currentPct}%`, transform: 'translateX(-50%)' }}>
        <div className="w-2 h-5 bg-blue-400 rounded-sm" />
        <div className="text-[9px] text-blue-400 mt-0.5 whitespace-nowrap">NOW</div>
      </div>
    </div>
  )
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function MarginAnalysis({ botName, marketType, marginEndpoint }: MarginAnalysisProps) {
  const { data: response, error, isLoading } = useSWR(marginEndpoint, fetcher, {
    refreshInterval: 15000,
    revalidateOnFocus: false,
  })
  const [showPositions, setShowPositions] = useState(false)

  const d = response?.data

  // Loading state
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

  // Error state
  if (error || !response?.success) {
    return (
      <div className="rounded-lg border border-gray-800 bg-[#0a0a0a] p-4">
        <div className="flex items-center gap-2 text-slate-500">
          <Shield className="w-4 h-4" />
          <span className="text-sm">Margin analysis unavailable</span>
        </div>
      </div>
    )
  }

  if (!d) return null

  // ===================== NO POSITIONS STATE =====================
  if (!d.has_positions) {
    const spec = d.spec || d.contract_specs
    return (
      <div className="rounded-lg border border-gray-800 bg-[#0a0a0a] p-4">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-5 h-5 text-slate-400" />
          <span className="text-sm font-semibold text-white">Margin Analysis</span>
        </div>
        <p className="text-sm text-slate-400 mb-3">
          No open positions. Margin analysis appears when positions are active.
        </p>
        <div className="text-sm text-slate-400">
          <span className="text-slate-500">Account Equity:</span>{' '}
          <span className="text-white font-mono">{fmt(d.account_equity)}</span>
        </div>
        {/* Show contract specs for reference */}
        {spec && marketType !== 'crypto_perp' && (
          <div className="mt-3 bg-slate-800/30 rounded p-3">
            <div className="text-xs text-slate-500 mb-2">Contract Specs</div>
            {typeof spec === 'object' && !spec.name && (
              // Multiple specs (VALOR)
              <div className="space-y-1.5">
                {Object.entries(spec as Record<string, any>).map(([key, s]: [string, any]) => (
                  <div key={key} className="flex justify-between text-xs">
                    <span className="text-white">{key}</span>
                    <span className="text-slate-400">
                      {fmt(s.initial_margin)} initial / {fmt(s.maintenance_margin)} maint
                      {' '}&middot;{' '}max {s.recommended_max || s.max_contracts_at_equity} contracts (50%)
                    </span>
                  </div>
                ))}
              </div>
            )}
            {spec.name && (
              <div className="text-xs space-y-1">
                <div><span className="text-slate-500">{spec.name}:</span> {fmt(spec.initial_margin)} initial / {fmt(spec.maintenance_margin)} maint</div>
                {d.max_contracts_recommended !== undefined && (
                  <div>
                    <span className="text-slate-500">Max contracts:</span>{' '}
                    {d.max_contracts_at_100pct} at 100% &middot; <span className="text-green-400">{d.max_contracts_recommended} recommended (50%)</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        {spec && marketType === 'crypto_perp' && (
          <div className="mt-3 bg-slate-800/30 rounded p-3 text-xs space-y-1">
            <div className="text-slate-500 mb-1">Perpetual Specs</div>
            <div><span className="text-slate-500">Default Leverage:</span> <span className="text-white">{spec.default_leverage}x</span> (max {spec.max_leverage}x)</div>
            <div><span className="text-slate-500">Maint. Margin Rate:</span> <span className="text-white">{(spec.maintenance_margin_rate * 100).toFixed(1)}%</span></div>
            <div><span className="text-slate-500">Funding:</span> <span className="text-white">Every {spec.funding_interval_hours}h</span></div>
          </div>
        )}
        {d.paper_trading && (
          <div className="mt-2 text-[10px] text-slate-500 flex items-center gap-1">
            <Info className="w-3 h-3" /> Paper Trading — margin uses configured specs, not live broker data
          </div>
        )}
      </div>
    )
  }

  // ===================== HAS POSITIONS STATE =====================
  const closestLiq = d.positions
    ?.filter((p: any) => p.distance_to_liquidation_pct !== null && p.distance_to_liquidation_pct !== undefined)
    .sort((a: any, b: any) => a.distance_to_liquidation_pct - b.distance_to_liquidation_pct)[0]

  return (
    <div className={`rounded-lg border p-4 ${healthBorder(d.margin_health)} bg-[#0a0a0a]`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield className={`w-5 h-5 ${healthColor(d.margin_health)}`} />
          <span className="text-sm font-semibold text-white">Margin Analysis</span>
          {d.paper_trading && <span className="text-[10px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">PAPER</span>}
        </div>
        <span className={`px-2 py-1 rounded text-xs font-bold ${healthBg(d.margin_health)}`}>
          {d.margin_health}
        </span>
      </div>

      {/* Margin Usage Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-slate-400">Margin Usage</span>
          <span className={`font-mono font-bold ${healthColor(d.margin_health)}`}>
            {pct(d.margin_usage_pct)}
          </span>
        </div>
        <MarginBar usage={d.margin_usage_pct || 0} />
      </div>

      {/* Key Metrics Row 1 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1"><Wallet className="w-3 h-3" /> Equity</div>
          <div className="text-white font-mono text-sm font-bold mt-0.5">{fmt(d.account_equity)}</div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1"><DollarSign className="w-3 h-3" /> Margin Used</div>
          <div className="text-yellow-400 font-mono text-sm font-bold mt-0.5">{fmt(d.margin_used)}</div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1"><TrendingUp className="w-3 h-3" /> Available</div>
          <div className="text-green-400 font-mono text-sm font-bold mt-0.5">{fmt(d.available_margin)}</div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1"><Gauge className="w-3 h-3" /> Leverage</div>
          <div className="text-white font-mono text-sm font-bold mt-0.5">{d.effective_leverage?.toFixed(2) || '—'}x</div>
        </div>
      </div>

      {/* Key Metrics Row 2 */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Nearest Liquidation</div>
          <div className="mt-0.5">
            {closestLiq ? (
              <>
                <LiqDistance pctValue={closestLiq.distance_to_liquidation_pct} />
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {closestLiq.symbol} @ {fmt(closestLiq.liquidation_price)}
                </div>
              </>
            ) : (
              <span className="text-slate-500 text-sm">N/A</span>
            )}
          </div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400 flex items-center gap-1"><Target className="w-3 h-3" /> Unrealized P&L</div>
          <div className={`font-mono text-sm font-bold mt-0.5 ${(d.total_unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {(d.total_unrealized_pnl || 0) >= 0 ? '+' : ''}{fmt(d.total_unrealized_pnl)}
          </div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5">
          <div className="text-[11px] text-slate-400">Positions</div>
          <div className="text-white font-mono text-sm font-bold mt-0.5">{d.position_count} open</div>
        </div>
      </div>

      {/* Funding Costs (perps only) */}
      {d.total_funding_cost_daily !== undefined && d.total_funding_cost_daily !== null && (
        <div className="bg-slate-800/30 rounded-lg p-2.5 mb-3">
          <div className="text-[11px] text-slate-400 flex items-center gap-1 mb-1">
            <Clock className="w-3 h-3" /> Funding Costs (Perpetuals)
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <span className="text-slate-500">Daily:</span>
              <span className={`ml-2 font-mono font-bold ${(d.total_funding_cost_daily || 0) <= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {fmt(d.total_funding_cost_daily, 4)}
              </span>
            </div>
            <div>
              <span className="text-slate-500">30-Day Projection:</span>
              <span className={`ml-2 font-mono font-bold ${(d.total_funding_cost_30d || 0) <= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {fmt(d.total_funding_cost_30d)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Warning Banners */}
      {d.margin_health === 'CRITICAL' && (
        <div className="bg-red-500/20 border border-red-500/50 rounded p-2 mb-3 text-red-400 text-xs font-bold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          CRITICAL: Margin at {pct(d.margin_usage_pct)}. Close positions or add capital immediately.
        </div>
      )}
      {d.margin_health === 'DANGER' && (
        <div className="bg-orange-500/20 border border-orange-500/50 rounded p-2 mb-3 text-orange-400 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Margin usage elevated at {pct(d.margin_usage_pct)}. Consider reducing exposure.
        </div>
      )}
      {closestLiq?.distance_to_liquidation_pct != null && closestLiq.distance_to_liquidation_pct < 5 && (
        <div className="bg-red-500/20 border border-red-500/50 rounded p-2 mb-3 text-red-400 text-xs font-bold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 animate-pulse flex-shrink-0" />
          LIQUIDATION RISK: {closestLiq.symbol} only {closestLiq.distance_to_liquidation_pct?.toFixed(1)}% from liq ({fmt(closestLiq.liquidation_price)})
        </div>
      )}

      {/* Expandable Position Details */}
      {d.positions?.length > 0 && (
        <div>
          <button
            onClick={() => setShowPositions(!showPositions)}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors"
          >
            {showPositions ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {showPositions ? 'Hide' : 'Show'} per-position margin details
          </button>

          {showPositions && (
            <div className="mt-3 space-y-3">
              {d.positions.map((pos: any) => (
                <div key={pos.position_id} className="bg-slate-800/20 border border-slate-700/50 rounded-lg p-3">
                  {/* Position header */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-white font-medium text-sm">{pos.symbol}</span>
                      <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${pos.side?.toLowerCase() === 'long' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                        {pos.side?.toUpperCase()}
                      </span>
                      <span className="text-xs text-slate-400">
                        {pos.contracts ? `${pos.contracts}x` : `${pos.quantity}`} @ {fmt(pos.entry_price)}
                      </span>
                    </div>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${healthBg(pos.margin_health)}`}>
                      {pos.margin_health}
                    </span>
                  </div>

                  {/* Position metrics */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs mb-2">
                    <div>
                      <span className="text-slate-500">Current Price</span>
                      <p className="text-white font-mono">{fmt(pos.current_price)}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Unrealized P&L</span>
                      <p className={`font-mono font-bold ${pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}{fmt(pos.unrealized_pnl)}
                      </p>
                    </div>
                    <div>
                      <span className="text-slate-500">Margin Required</span>
                      <p className="text-yellow-400 font-mono">{fmt(pos.initial_margin_required)}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Eff. Leverage</span>
                      <p className="text-white font-mono">{pos.effective_leverage?.toFixed(2) || '—'}x</p>
                    </div>
                  </div>

                  {/* Liquidation info */}
                  <div className="grid grid-cols-2 gap-2 text-xs mb-1">
                    <div>
                      <span className="text-slate-500">Liquidation Price</span>
                      <p className="text-red-400 font-mono font-bold">{fmt(pos.liquidation_price)}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Distance to Liquidation</span>
                      <LiqDistance pctValue={pos.distance_to_liquidation_pct} />
                    </div>
                  </div>

                  {/* Visual price line */}
                  {pos.liquidation_price && pos.entry_price && pos.current_price && (
                    <LiqVisualization
                      liqPrice={pos.liquidation_price}
                      entryPrice={pos.entry_price}
                      currentPrice={pos.current_price}
                      side={pos.side}
                    />
                  )}

                  {/* Funding info (perps only) */}
                  {pos.funding_rate !== undefined && pos.funding_rate !== null && (
                    <div className="mt-2 bg-slate-900/50 rounded p-2 text-xs">
                      <div className="flex items-center gap-1 text-slate-400 mb-1">
                        <Clock className="w-3 h-3" /> Funding
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <span className="text-slate-500">Rate:</span>{' '}
                          <span className="text-white font-mono">{(pos.funding_rate * 100).toFixed(4)}%</span>
                        </div>
                        <div>
                          <span className="text-slate-500">8h cost:</span>{' '}
                          <span className={`font-mono ${(pos.funding_cost_8h || 0) <= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {fmt(pos.funding_cost_8h, 4)}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500">Daily:</span>{' '}
                          <span className={`font-mono ${(pos.funding_cost_daily || 0) <= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {fmt(pos.funding_cost_daily, 4)}
                          </span>
                        </div>
                      </div>
                      <div className="mt-1">
                        <span className="text-slate-500">30-day projection:</span>{' '}
                        <span className={`font-mono font-bold ${(pos.funding_cost_30d_projected || 0) <= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {fmt(pos.funding_cost_30d_projected)}
                        </span>
                      </div>
                      <div className="mt-1">
                        <span className="text-slate-500">Leverage:</span>{' '}
                        <span className="text-white font-mono">{pos.leverage}x</span>
                        <span className="text-slate-500 ml-3">Mode:</span>{' '}
                        <span className="text-white capitalize">{pos.margin_mode}</span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Paper trading note */}
      {d.paper_trading && (
        <div className="mt-2 text-[10px] text-slate-500 flex items-center gap-1">
          <Info className="w-3 h-3" /> Paper Trading — margin uses configured specs, not live broker data
        </div>
      )}
    </div>
  )
}
