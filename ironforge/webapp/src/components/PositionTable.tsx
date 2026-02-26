'use client'

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
  stop_loss_price?: number
  distance_to_pt?: number | null
  distance_to_sl?: number | null
  // Tradier sandbox order IDs (FLAME only)
  sandbox_order_ids?: Record<string, string> | null
}

export default function PositionTable({
  positions,
  spotPrice,
  tradierConnected,
}: {
  positions: Position[]
  spotPrice?: number | null
  tradierConnected?: boolean
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
        <PositionCard key={pos.position_id} pos={pos} hasLiveData={hasLiveData} />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Position Card                                                      */
/* ------------------------------------------------------------------ */

function PositionCard({ pos, hasLiveData }: { pos: Position; hasLiveData: boolean }) {
  const pnl = pos.unrealized_pnl
  const pnlPct = pos.unrealized_pnl_pct
  const pnlColor =
    pnl == null ? 'text-gray-400' : pnl >= 0 ? 'text-emerald-400' : 'text-red-400'

  // Progress bar: how far between profit target (left) and stop loss (right)
  let progressPct: number | null = null
  if (pos.current_cost_to_close != null && pos.profit_target_price && pos.stop_loss_price) {
    const range = pos.stop_loss_price - pos.profit_target_price
    if (range > 0) {
      progressPct = Math.max(
        0,
        Math.min(100, ((pos.current_cost_to_close - pos.profit_target_price) / range) * 100),
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
            <p className="text-xs text-forge-muted">PT Target</p>
            <p className="font-mono text-emerald-400/70">
              ${pos.profit_target_price?.toFixed(4) ?? '--'}
            </p>
          </div>
          <div>
            <p className="text-xs text-forge-muted">SL Trigger</p>
            <p className="font-mono text-red-400/70">
              ${pos.stop_loss_price?.toFixed(4) ?? '--'}
            </p>
          </div>
        </div>
      )}

      {/* PT / SL progress bar */}
      {progressPct != null && (
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] text-forge-muted">
            <span>Profit Target</span>
            <span>Stop Loss</span>
          </div>
          <div className="h-2 bg-forge-border rounded-full overflow-hidden relative">
            {/* Green zone (left 30%) */}
            <div className="absolute inset-y-0 left-0 bg-emerald-500/20" style={{ width: '30%' }} />
            {/* Red zone (right 30%) */}
            <div className="absolute inset-y-0 right-0 bg-red-500/20" style={{ width: '30%' }} />
            {/* Marker */}
            <div
              className={`absolute top-0 h-full w-1 rounded ${
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

      {/* Sandbox Order IDs (FLAME only) */}
      {pos.sandbox_order_ids && Object.keys(pos.sandbox_order_ids).length > 0 && (
        <div className="border-t border-forge-border/50 pt-2 space-y-1">
          <p className="text-[10px] text-forge-muted uppercase tracking-wider">Tradier Sandbox Orders</p>
          <div className="flex flex-wrap gap-3">
            {Object.entries(pos.sandbox_order_ids).map(([name, orderId]) => (
              <span key={name} className="text-xs font-mono">
                <span className="text-forge-muted">{name}:</span>{' '}
                <span className="text-amber-400">#{orderId}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex gap-4 text-xs text-forge-muted">
        <span>Entry: ${pos.underlying_at_entry.toFixed(2)}</span>
        <span>Opened: {pos.open_time?.slice(0, 16)}</span>
      </div>
    </div>
  )
}
