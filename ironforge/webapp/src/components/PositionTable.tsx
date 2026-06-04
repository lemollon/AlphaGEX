'use client'

import { useState, useEffect } from 'react'
import { getCurrentPTTier, getCTNow, formatCloseReason, type PTTier } from '@/lib/pt-tiers'
import PositionDetail from './PositionDetail'

function formatTimeCT(ts: string | null): string {
  if (!ts) return '--'
  try {
    return new Date(ts).toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    })
  } catch { return ts.slice(0, 16) }
}

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
  // BLAZE directional fields (vertical debit spread)
  setup_type?: string | null
  direction?: 'call' | 'put' | string | null
  long_strike?: number
  short_strike?: number
  debit?: number
  long_symbol?: string | null
  short_symbol?: string | null
  // Tradier sandbox order IDs (FLAME only)
  // New format: {"User": {"order_id": "123", "contracts": 85}}
  // Legacy format: {"User": "123"}
  sandbox_order_ids?: Record<string, string | { order_id: string; contracts: number }> | null
}

interface ClosedTrade {
  position_id: string
  ticker: string
  expiration: string | null
  put_short_strike: number
  put_long_strike: number
  call_short_strike: number
  call_long_strike: number
  contracts: number
  spread_width: number
  total_credit: number
  collateral_required: number
  close_price: number
  close_reason: string
  realized_pnl: number
  return_on_credit_pct: number
  return_on_collateral_pct: number
  underlying_at_entry: number
  vix_at_entry: number
  open_time: string | null
  close_time: string | null
  wings_adjusted: boolean
  // BLAZE directional fields
  setup_type?: string | null
  direction?: 'call' | 'put' | string | null
  long_strike?: number
  short_strike?: number
  debit?: number
  sandbox_order_ids?: Record<string, string | { order_id: string; contracts: number }> | null
}

/**
 * Render leg description for the Strikes cell.
 *
 * IC bots (FLAME/SPARK/INFERNO):  "737/738P-742/743C"
 * BLAZE vertical debit spread:    "737/738 Call DR" (long_strike/short_strike + direction)
 */
function renderStrikes(p: {
  put_long_strike?: number
  put_short_strike?: number
  call_short_strike?: number
  call_long_strike?: number
  direction?: string | null
  long_strike?: number
  short_strike?: number
}): string {
  if (p.direction && p.long_strike != null && p.short_strike != null && p.long_strike > 0) {
    const letter = p.direction === 'call' ? 'C' : p.direction === 'put' ? 'P' : '?'
    const label = p.direction === 'call' ? 'Call' : p.direction === 'put' ? 'Put' : ''
    return `${p.long_strike}/${p.short_strike}${letter} (${label} DR)`
  }
  return `${p.put_long_strike}/${p.put_short_strike}P-${p.call_short_strike}/${p.call_long_strike}C`
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DetailData = any

export default function PositionTable({
  positions,
  spotPrice,
  tradierConnected,
  detailData,
  bot,
  todaysClosedTrades,
}: {
  positions: Position[]
  spotPrice?: number | null
  tradierConnected?: boolean
  detailData?: { positions: DetailData[] } | null
  bot: 'flame' | 'spark' | 'inferno' | 'blaze' | 'flare'
  todaysClosedTrades?: ClosedTrade[]
}) {
  const hasOpenPositions = positions.length > 0
  const hasTodaysClosed = (todaysClosedTrades?.length ?? 0) > 0

  if (!hasOpenPositions && !hasTodaysClosed) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center">
        <p className="text-forge-muted">No open positions</p>
      </div>
    )
  }

  const hasLiveData = positions.some((p) => p.current_cost_to_close != null)

  // Build a lookup map from position_id to detail data
  const detailMap: Record<string, DetailData> = {}
  if (detailData?.positions) {
    for (const d of detailData.positions) {
      if (d?.position_id) detailMap[d.position_id] = d
    }
  }

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

      {/* Open position cards */}
      {positions.map((pos) => (
        <PositionCard
          key={pos.position_id}
          pos={pos}
          hasLiveData={hasLiveData}
          detail={detailMap[pos.position_id] ?? null}
          bot={bot}
        />
      ))}

      {/* Today's closed trades (persists all day until next position opens) */}
      {!hasOpenPositions && hasTodaysClosed && (
        <>
          <div className="flex items-center gap-2 text-xs text-forge-muted pt-1">
            <span className="text-emerald-400 font-medium">TODAY&apos;S CLOSED</span>
            <span className="flex-1 border-t border-forge-border/50" />
          </div>
          {todaysClosedTrades!.map((trade) => (
            <ClosedTradeCard key={trade.position_id} trade={trade} bot={bot} />
          ))}
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Position Card                                                      */
/* ------------------------------------------------------------------ */

/** Map tier name to Tailwind text color. */
function tierColor(tier: string | undefined, fallback: PTTier): string {
  if (!tier) return fallback.color
  if (tier === 'MORNING') return 'text-emerald-400'
  if (tier === 'MIDDAY') return 'text-yellow-400'
  return 'text-orange-400'
}

function PositionCard({
  pos,
  hasLiveData,
  detail,
  bot,
}: {
  pos: Position
  hasLiveData: boolean
  detail: DetailData | null
  bot: 'flame' | 'spark' | 'inferno' | 'blaze' | 'flare'
}) {
  const [expanded, setExpanded] = useState(true)
  const [closing, setClosing] = useState(false)
  const [confirmClose, setConfirmClose] = useState(false)
  const [closeResult, setCloseResult] = useState<{ pnl: number; price: number } | null>(null)

  async function handleForceClose() {
    setClosing(true)
    setConfirmClose(false)
    try {
      const res = await fetch(`/api/${bot}/force-close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position_id: pos.position_id }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setCloseResult({ pnl: data.realized_pnl, price: data.close_price })
    } catch (e: any) {
      console.error('Force close failed:', e)
      alert(`Force close failed: ${e.message}`)
    } finally {
      setClosing(false)
    }
  }

  const pnl = pos.unrealized_pnl
  const pnlPct = pos.unrealized_pnl_pct
  const pnlColor =
    pnl == null ? 'text-gray-400' : pnl >= 0 ? 'text-emerald-400' : 'text-red-400'

  // Client-side PT tier (ticks every 1s for live updates when tier changes)
  const [ptTier, setPtTier] = useState<PTTier>(() => getCurrentPTTier(undefined, bot))
  useEffect(() => {
    const timer = setInterval(() => setPtTier(getCurrentPTTier(getCTNow(), bot)), 1000)
    return () => clearInterval(timer)
  }, [bot])

  // ---- Directional debit spread (BLAZE/FLARE) vs IC (FLAME/SPARK/INFERNO) ----
  // A debit spread's VALUE rises toward the profit target (debit × (1+pt%)) and
  // falls toward the stop (debit × (1−sl%)) — the opposite direction from an
  // IC's cost-to-close. It also has no time-of-day PT tier, so the IC
  // MORNING/MIDDAY/AFTERNOON label must not leak into the directional card.
  const isDirectional = !!(pos.direction && (pos.debit ?? 0) > 0)
  const entryDebit = pos.debit ?? 0

  // Use API PT data if available, fall back to client-side calculation
  const ptPct = pos.profit_target_pct ?? ptTier.pct
  const ptLabel = pos.profit_target_tier ?? ptTier.label
  const ptClr = tierColor(pos.profit_target_tier, ptTier)
  const ptPrice = isDirectional
    ? (pos.profit_target_price ?? entryDebit * 1.2)
    : (pos.profit_target_price ?? pos.total_credit * (1 - ptPct))
  const slPrice = isDirectional
    ? (pos.stop_loss_price ?? entryDebit * (bot === 'flare' ? 0 : 0.7))
    : (pos.stop_loss_price ?? pos.total_credit * 2)

  // Directional PT/SL as a percentage of the debit paid, derived from the live
  // prices so they always match the active thresholds (fall back to canonical
  // values: PT +20%; SL −100% FLARE / −30% BLAZE).
  const dirPtPct = entryDebit > 0 ? Math.round((ptPrice / entryDebit - 1) * 100) : 20
  const dirSlPct = entryDebit > 0 ? Math.round((1 - slPrice / entryDebit) * 100) : (bot === 'flare' ? 100 : 30)

  // Progress bar. IC: cost-to-close travels PT (left/good) → SL (right/bad).
  // Directional: value travels SL (left/bad) → PT (right/good).
  // Before the first live quote a directional position falls back to its entry
  // debit (where the value starts) so the bar still renders at the entry marker;
  // IC keeps requiring live MTM (no meaningful pre-quote cost-to-close).
  const barValue = pos.current_cost_to_close ?? (isDirectional ? entryDebit : null)
  let progressPct: number | null = null
  if (barValue != null) {
    if (isDirectional) {
      const range = ptPrice - slPrice
      if (range > 0) {
        progressPct = Math.max(0, Math.min(100, ((barValue - slPrice) / range) * 100))
      }
    } else {
      const range = slPrice - ptPrice
      if (range > 0) {
        progressPct = Math.max(0, Math.min(100, ((barValue - ptPrice) / range) * 100))
      }
    }
  }

  if (closeResult) {
    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">
        <span className="text-emerald-400 font-medium">Position closed</span>
        <span className="ml-2 text-gray-300">
          @ ${closeResult.price.toFixed(4)} | P&L: {closeResult.pnl >= 0 ? '+' : ''}${closeResult.pnl.toFixed(2)}
        </span>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4 space-y-3">
      {/* Force close confirmation dialog */}
      {confirmClose && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-forge-card border border-forge-border rounded-xl p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-white mb-3">Force Close Position?</h3>
            <p className="text-sm text-gray-300 mb-2">
              Close <span className="font-mono text-amber-400">{pos.position_id}</span> at current market price.
            </p>
            {pos.current_cost_to_close != null && (
              <p className="text-sm text-gray-400 mb-4">
                Estimated close: ${pos.current_cost_to_close.toFixed(4)} | Est P&L:{' '}
                <span className={pos.unrealized_pnl != null && pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                  {pos.unrealized_pnl != null ? `$${pos.unrealized_pnl.toFixed(2)}` : 'unknown'}
                </span>
              </p>
            )}
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmClose(false)}
                className="px-4 py-2 text-sm rounded-lg border border-forge-border text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleForceClose}
                className="px-4 py-2 text-sm rounded-lg font-medium bg-red-600 hover:bg-red-500 text-white transition-colors"
              >
                Close Position
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-gray-400">{pos.position_id.slice(0, 20)}</span>
          <span className="text-xs bg-forge-border px-2 py-0.5 rounded">
            Exp: {pos.expiration}
          </span>
        </div>
        <div className="flex items-center gap-3">
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
          {/* Expand/collapse toggle */}
          {detail && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-forge-muted hover:text-gray-300 transition-colors text-xs px-2 py-1 rounded border border-forge-border/50 hover:border-forge-border"
              title={expanded ? 'Collapse details' : 'Expand details'}
            >
              {expanded ? 'Hide detail' : 'Show detail'}
            </button>
          )}
        </div>
      </div>

      {/* Strikes and metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <p className="text-xs text-forge-muted">Strikes</p>
          <p className="font-mono">{renderStrikes(pos)}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Qty</p>
          <p className="font-mono">x{pos.contracts}</p>
        </div>
        {pos.direction && pos.debit != null && pos.debit > 0 ? (
          <>
            <div>
              <p className="text-xs text-forge-muted">Entry Debit</p>
              <p className="font-mono text-red-300">${pos.debit.toFixed(2)}</p>
              <p className="text-[10px] text-forge-muted">${Math.round(pos.debit * 100).toLocaleString()} / contract</p>
            </div>
            <div>
              <p className="text-xs text-forge-muted">Total Cost</p>
              <p className="font-mono">${Math.round(pos.debit * pos.contracts * 100).toLocaleString()}</p>
              <p className="text-[10px] text-forge-muted">${Math.round(pos.debit * 100).toLocaleString()} × {pos.contracts}</p>
            </div>
          </>
        ) : (
          <>
            <div>
              <p className="text-xs text-forge-muted">Entry Credit</p>
              <p className="font-mono text-emerald-400">${pos.total_credit.toFixed(2)}</p>
              <p className="text-[10px] text-forge-muted">${Math.round(pos.total_credit * 100).toLocaleString()} / contract</p>
            </div>
            <div>
              <p className="text-xs text-forge-muted">Collateral (Cost)</p>
              <p className="font-mono">${Math.round(pos.collateral_required).toLocaleString()}</p>
              <p className="text-[10px] text-forge-muted">
                ${pos.contracts > 0 ? Math.round(pos.collateral_required / pos.contracts).toLocaleString() : '0'} / contract × {pos.contracts}
              </p>
            </div>
          </>
        )}
      </div>

      {/* Live monitoring row */}
      {hasLiveData && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm border-t border-forge-border/50 pt-3">
          <div>
            <p className="text-xs text-forge-muted">
              {pos.direction && (pos.debit ?? 0) > 0 ? 'Current Value' : 'Cost to Close'}
            </p>
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
            <p className={`font-mono ${isDirectional ? 'text-emerald-400' : ptClr}`}>
              ${ptPrice.toFixed(4)}{' '}
              <span className="text-[10px] opacity-75">
                {isDirectional ? `(+${dirPtPct}%)` : `(${Math.round(ptPct * 100)}% ${ptLabel})`}
              </span>
            </p>
          </div>
          <div>
            <p className="text-xs text-forge-muted">Stop Loss</p>
            <p className="font-mono text-red-400/70">
              ${slPrice.toFixed(4)}
              {isDirectional && (
                <span className="text-[10px] opacity-75"> (−{dirSlPct}%)</span>
              )}
            </p>
          </div>
        </div>
      )}

      {/* PT / SL progress bar with dollar labels */}
      {progressPct != null && (
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] text-forge-muted font-mono">
            {/* Left end: PT for IC (low cost = good), SL for directional (low value = bad) */}
            {isDirectional ? (
              <span className="text-red-400">SL ${slPrice.toFixed(2)}</span>
            ) : (
              <span className={ptClr}>PT ${ptPrice.toFixed(2)}</span>
            )}
            {barValue != null && (
              <span className="text-gray-300">
                ${barValue.toFixed(4)}
                {pos.current_cost_to_close == null && (
                  <span className="text-forge-muted"> entry</span>
                )}
              </span>
            )}
            {isDirectional ? (
              <span className="text-emerald-400">PT ${ptPrice.toFixed(2)}</span>
            ) : (
              <span className="text-red-400">SL ${slPrice.toFixed(2)}</span>
            )}
          </div>
          <div className="h-2.5 bg-forge-border rounded-full overflow-hidden relative">
            {/* Zones mirror by direction: good end is left (PT) for IC, right (PT) for directional. */}
            <div className={`absolute inset-y-0 left-0 ${isDirectional ? 'bg-red-500/20' : 'bg-emerald-500/20'}`} style={{ width: '30%' }} />
            <div className="absolute inset-y-0 left-[30%] bg-yellow-500/10" style={{ width: '40%' }} />
            <div className={`absolute inset-y-0 right-0 ${isDirectional ? 'bg-emerald-500/20' : 'bg-red-500/20'}`} style={{ width: '30%' }} />
            {/* Marker — color by "goodness" (proximity to PT), which flips by direction. */}
            <div
              className={`absolute top-0 h-full w-1.5 rounded ${
                (isDirectional ? progressPct : 100 - progressPct) > 70
                  ? 'bg-emerald-400'
                  : (isDirectional ? progressPct : 100 - progressPct) < 30
                    ? 'bg-red-400'
                    : 'bg-yellow-400'
              }`}
              style={{ left: `${progressPct}%`, transform: 'translateX(-50%)' }}
            />
          </div>
        </div>
      )}

      {/* Sandbox Order IDs (compact, when detail is collapsed) */}
      {!expanded && pos.sandbox_order_ids && Object.keys(pos.sandbox_order_ids).length > 0 && (
        <div className="border-t border-forge-border/50 pt-2 space-y-1">
          <p className="text-[10px] text-forge-muted uppercase tracking-wider">Tradier Sandbox Orders</p>
          <div className="flex flex-wrap gap-3">
            {Object.entries(pos.sandbox_order_ids).map(([name, val]) => {
              const isNew = typeof val === 'object' && val !== null
              const orderId = isNew ? val.order_id : val
              const qty = isNew ? val.contracts : null
              return (
                <span key={name} className="text-xs font-mono">
                  <span className="text-forge-muted">{name}:</span>{' '}
                  <span className="text-amber-400">#{orderId}</span>
                  {qty != null && (
                    <span className="text-forge-muted ml-1">x{qty}</span>
                  )}
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* Expanded: full position detail */}
      {expanded && detail && <PositionDetail data={detail} />}

      {/* Footer */}
      <div className="flex items-center gap-4 text-xs text-forge-muted">
        <span>Entry: ${pos.underlying_at_entry.toFixed(2)}</span>
        <span>Opened: {formatTimeCT(pos.open_time)}</span>
        <button
          onClick={() => setConfirmClose(true)}
          disabled={closing}
          className="ml-auto px-3 py-1 text-xs font-medium rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
        >
          {closing ? 'Closing...' : 'Force Close'}
        </button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Closed Trade Card — shows today's realized IC with position %     */
/* ------------------------------------------------------------------ */

function ClosedTradeCard({ trade, bot }: { trade: ClosedTrade; bot: string }) {
  const pnl = trade.realized_pnl
  const pnlColor = pnl >= 0 ? 'text-emerald-400' : 'text-red-400'

  // Use the shared formatter that maps close_reason → human-readable with PT %
  const reason = formatCloseReason(trade.close_reason, bot)
  const reasonBg = reason.color.includes('emerald')
    ? 'bg-emerald-500/20'
    : reason.color.includes('red')
      ? 'bg-red-500/20'
      : reason.color.includes('yellow')
        ? 'bg-yellow-500/20'
        : reason.color.includes('orange')
          ? 'bg-orange-500/20'
          : reason.color.includes('amber')
            ? 'bg-amber-500/20'
            : reason.color.includes('blue')
              ? 'bg-blue-500/20'
              : 'bg-gray-500/20'

  // Format time as HH:MM CT
  const formatTime = (t: string | null) => {
    if (!t) return '--'
    try {
      return new Date(t).toLocaleTimeString('en-US', {
        hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago',
      })
    } catch { return '--' }
  }

  return (
    <div className="rounded-xl border border-forge-border/60 bg-forge-card/60 p-4 space-y-3">
      {/* Header with P&L */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-gray-500">{trade.position_id.slice(0, 20)}</span>
          <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${reasonBg} ${reason.color}`}>
            {reason.text}
          </span>
        </div>
        <div className="text-right">
          <span className={`text-lg font-bold font-mono ${pnlColor}`}>
            {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Position return metrics — THIS is what you want to see */}
      <div className="grid grid-cols-3 gap-4 bg-forge-bg/50 rounded-lg p-3">
        {trade.direction && (trade.debit ?? 0) > 0 ? (
          <>
            <div>
              <p className="text-[10px] text-forge-muted uppercase tracking-wider">Return</p>
              <p className={`text-xl font-bold font-mono ${pnlColor}`}>
                {trade.return_on_credit_pct >= 0 ? '+' : ''}{trade.return_on_credit_pct.toFixed(1)}%
              </p>
              <p className="text-[10px] text-forge-muted">of debit paid</p>
            </div>
            <div>
              <p className="text-[10px] text-forge-muted uppercase tracking-wider">Return on Risk</p>
              <p className={`text-xl font-bold font-mono ${pnlColor}`}>
                {trade.return_on_collateral_pct >= 0 ? '+' : ''}{trade.return_on_collateral_pct.toFixed(1)}%
              </p>
              <p className="text-[10px] text-forge-muted">of capital risked</p>
            </div>
            <div>
              <p className="text-[10px] text-forge-muted uppercase tracking-wider">Debit → Close</p>
              <p className="text-sm font-mono text-gray-200">
                ${(trade.debit ?? 0).toFixed(4)} → ${trade.close_price.toFixed(4)}
              </p>
              <p className="text-[10px] text-forge-muted">
                {trade.close_price > (trade.debit ?? 0) ? 'closed above entry' : 'closed below entry'}
              </p>
            </div>
          </>
        ) : (
          <>
            <div>
              <p className="text-[10px] text-forge-muted uppercase tracking-wider">IC Return</p>
              <p className={`text-xl font-bold font-mono ${pnlColor}`}>
                {trade.return_on_credit_pct >= 0 ? '+' : ''}{trade.return_on_credit_pct.toFixed(1)}%
              </p>
              <p className="text-[10px] text-forge-muted">of credit received</p>
            </div>
            <div>
              <p className="text-[10px] text-forge-muted uppercase tracking-wider">Return on Risk</p>
              <p className={`text-xl font-bold font-mono ${pnlColor}`}>
                {trade.return_on_collateral_pct >= 0 ? '+' : ''}{trade.return_on_collateral_pct.toFixed(1)}%
              </p>
              <p className="text-[10px] text-forge-muted">of collateral</p>
            </div>
            <div>
              <p className="text-[10px] text-forge-muted uppercase tracking-wider">Credit → Close</p>
              <p className="text-sm font-mono text-gray-200">
                ${trade.total_credit.toFixed(4)} → ${trade.close_price.toFixed(4)}
              </p>
              <p className="text-[10px] text-forge-muted">
                kept ${trade.total_credit > 0 ? Math.round(((trade.total_credit - trade.close_price) / trade.total_credit) * 100) : 0}% of premium
              </p>
            </div>
          </>
        )}
      </div>

      {/* Strikes and details */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
        <div>
          <p className="text-xs text-forge-muted">Strikes</p>
          <p className="font-mono text-sm">{renderStrikes(trade)}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Qty</p>
          <p className="font-mono">x{trade.contracts}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">
            {trade.direction && (trade.debit ?? 0) > 0 ? 'Total Cost' : 'Collateral (Cost)'}
          </p>
          <p className="font-mono">
            ${trade.direction && (trade.debit ?? 0) > 0
              ? Math.round((trade.debit ?? 0) * trade.contracts * 100).toLocaleString()
              : Math.round(trade.collateral_required).toLocaleString()}
          </p>
          <p className="text-[10px] text-forge-muted">
            {trade.direction && (trade.debit ?? 0) > 0
              ? `$${Math.round((trade.debit ?? 0) * 100).toLocaleString()} / contract × ${trade.contracts}`
              : `$${trade.contracts > 0 ? Math.round(trade.collateral_required / trade.contracts).toLocaleString() : '0'} / contract × ${trade.contracts}`}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Opened</p>
          <p className="font-mono text-xs">{formatTime(trade.open_time)} CT</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Closed</p>
          <p className="font-mono text-xs">{formatTime(trade.close_time)} CT</p>
        </div>
      </div>
    </div>
  )
}
