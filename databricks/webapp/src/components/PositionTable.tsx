'use client'

import { useState, useEffect } from 'react'
import { getCurrentPTTier, getCTNow, type PTTier } from '@/lib/pt-tiers'

interface Position {
  position_id: string
  expiration: string
  put_long_strike: number
  put_short_strike: number
  call_short_strike: number
  call_long_strike: number
  contracts: number
  total_credit: number
  collateral_required: number
  underlying_at_entry: number
  open_time: string
  sandbox_order_id?: string | null
  // Live data from position-monitor
  current_cost_to_close?: number | null
  spot_price?: number | null
  unrealized_pnl?: number | null
  unrealized_pnl_pct?: number | null
  profit_target_price?: number
  profit_target_pct?: number
  profit_target_tier?: string
  stop_loss_price?: number
  distance_to_pt?: number | null
  distance_to_sl?: number | null
}

export default function PositionTable({
  positions,
  spotPrice,
  tradierConnected,
  bot,
}: {
  positions: Position[]
  spotPrice?: number | null
  tradierConnected?: boolean
  bot?: 'flame' | 'spark'
}) {
  if (!positions.length) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center">
        <p className="text-forge-muted">No open positions</p>
      </div>
    )
  }

  const hasLiveData = positions.some((p) => p.current_cost_to_close != null)

  return (
    <div className="space-y-4">
      {/* Spot price banner */}
      {spotPrice && (
        <div className="flex items-center gap-4 text-xs text-forge-muted">
          <span>
            SPY: <span className="text-white font-mono">${spotPrice.toFixed(2)}</span>
          </span>
          {tradierConnected && (
            <span className="text-emerald-500">Live quotes</span>
          )}
        </div>
      )}

      {/* Position cards */}
      {positions.map((pos) => (
        <PositionCard key={pos.position_id} pos={pos} hasLiveData={hasLiveData} showSandbox={bot === 'flame'} />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Position Card                                                      */
/* ------------------------------------------------------------------ */

function parseSandboxOrders(raw: string | null | undefined): Record<string, string> | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed === 'object' && parsed !== null) return parsed
  } catch { /* not valid JSON */ }
  return null
}

/** Map tier name to Tailwind text color. */
function tierColor(tier: string | undefined, fallback: PTTier): string {
  if (!tier) return fallback.color
  if (tier === 'MORNING') return 'text-emerald-400'
  if (tier === 'MIDDAY') return 'text-yellow-400'
  return 'text-orange-400'
}

function PositionCard({ pos, hasLiveData, showSandbox }: { pos: Position; hasLiveData: boolean; showSandbox?: boolean }) {
  const pnl = pos.unrealized_pnl
  const pnlPct = pos.unrealized_pnl_pct
  const pnlColor =
    pnl == null ? 'text-gray-400' : pnl >= 0 ? 'text-emerald-400' : 'text-red-400'

  // Client-side PT tier (ticks every 1s for live updates when tier changes)
  const [ptTier, setPtTier] = useState<PTTier>(getCurrentPTTier)
  useEffect(() => {
    const timer = setInterval(() => setPtTier(getCurrentPTTier(getCTNow())), 1000)
    return () => clearInterval(timer)
  }, [])

  // Use API PT data if available, fall back to client-side calculation
  const ptPct = pos.profit_target_pct ?? ptTier.pct
  const ptLabel = pos.profit_target_tier ?? ptTier.label
  const ptClr = tierColor(pos.profit_target_tier, ptTier)
  const ptPrice = pos.profit_target_price ?? pos.total_credit * (1 - ptPct)
  const slPrice = pos.stop_loss_price ?? pos.total_credit * 2

  // Progress bar: how far between profit target (left=0%) and stop loss (right=100%)
  let progressPct: number | null = null
  if (pos.current_cost_to_close != null) {
    const range = slPrice - ptPrice
    if (range > 0) {
      progressPct = Math.max(
        0,
        Math.min(100, ((pos.current_cost_to_close - ptPrice) / range) * 100),
      )
    }
  }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-gray-400">{pos.position_id.slice(0, 20)}</span>
          <span className="text-xs bg-forge-border px-2 py-0.5 rounded">
            Exp: {pos.expiration}
          </span>
        </div>
        {hasLiveData && pnl != null && (
          <div className="text-right">
            <span className={`text-lg font-bold font-mono ${pnlColor}`}>
              {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
            </span>
            {pnlPct != null && (
              <span className={`ml-2 text-xs ${pnlColor}`}>
                ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%)
              </span>
            )}
          </div>
        )}
      </div>

      {/* Strikes and metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <p className="text-xs text-forge-muted">Strikes</p>
          <p className="font-mono">
            {pos.put_long_strike}/{pos.put_short_strike}P-{pos.call_short_strike}/{pos.call_long_strike}C
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Qty</p>
          <p className="font-mono">x{pos.contracts}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Entry Credit</p>
          <p className="font-mono text-emerald-400">${pos.total_credit.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Collateral</p>
          <p className="font-mono">${pos.collateral_required.toFixed(0)}</p>
        </div>
      </div>

      {/* Live monitoring row */}
      {hasLiveData && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm border-t border-forge-border/50 pt-3">
          <div>
            <p className="text-xs text-forge-muted">Cost to Close</p>
            <p className="font-mono">
              {pos.current_cost_to_close != null
                ? `$${pos.current_cost_to_close.toFixed(4)}`
                : '--'}
            </p>
          </div>
          <div>
            <p className="text-xs text-forge-muted">Spot Price</p>
            <p className="font-mono">
              {pos.spot_price != null ? `$${pos.spot_price.toFixed(2)}` : '--'}
            </p>
          </div>
          <div>
            <p className="text-xs text-forge-muted">Profit Target</p>
            <p className={`font-mono ${ptClr}`}>
              ${ptPrice.toFixed(4)}{' '}
              <span className="text-[10px] opacity-75">
                ({Math.round(ptPct * 100)}% {ptLabel})
              </span>
            </p>
          </div>
          <div>
            <p className="text-xs text-forge-muted">Stop Loss</p>
            <p className="font-mono text-red-400/70">
              ${slPrice.toFixed(4)}
            </p>
          </div>
        </div>
      )}

      {/* PT / SL progress bar with dollar labels */}
      {progressPct != null && (
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] text-forge-muted font-mono">
            <span className={ptClr}>PT ${ptPrice.toFixed(2)}</span>
            {pos.current_cost_to_close != null && (
              <span className="text-gray-300">
                ${pos.current_cost_to_close.toFixed(4)}
              </span>
            )}
            <span className="text-red-400">SL ${slPrice.toFixed(2)}</span>
          </div>
          <div className="h-2.5 bg-forge-border rounded-full overflow-hidden relative">
            {/* Green zone (left 30%) */}
            <div className="absolute inset-y-0 left-0 bg-emerald-500/20" style={{ width: '30%' }} />
            {/* Yellow zone (middle 40%) */}
            <div className="absolute inset-y-0 left-[30%] bg-yellow-500/10" style={{ width: '40%' }} />
            {/* Red zone (right 30%) */}
            <div className="absolute inset-y-0 right-0 bg-red-500/20" style={{ width: '30%' }} />
            {/* Marker */}
            <div
              className={`absolute top-0 h-full w-1.5 rounded ${
                progressPct < 30
                  ? 'bg-emerald-400'
                  : progressPct > 70
                    ? 'bg-red-400'
                    : 'bg-yellow-400'
              }`}
              style={{ left: `${progressPct}%`, transform: 'translateX(-50%)' }}
            />
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex gap-4 text-xs text-forge-muted">
        <span>Entry: ${pos.underlying_at_entry.toFixed(2)}</span>
        <span>Opened: {pos.open_time?.slice(0, 16)}</span>
      </div>

      {/* Sandbox orders (FLAME only) */}
      {showSandbox && (() => {
        const orders = parseSandboxOrders(pos.sandbox_order_id)
        if (!orders || Object.keys(orders).length === 0) return null
        return (
          <div className="flex items-center gap-3 text-xs border-t border-forge-border/50 pt-2">
            <span className="text-forge-muted">Sandbox:</span>
            {Object.entries(orders).map(([name, id]) => (
              <span key={name} className="bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded font-mono">
                {name} #{id}
              </span>
            ))}
          </div>
        )
      })()}
    </div>
  )
}
