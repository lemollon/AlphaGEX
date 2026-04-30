'use client'

import { formatCloseReason } from '@/lib/pt-tiers'

interface Trade {
  position_id: string
  expiration: string
  put_long_strike: number
  put_short_strike: number
  call_short_strike: number
  call_long_strike: number
  contracts: number
  total_credit: number
  close_price: number
  close_reason: string
  realized_pnl: number
  close_time: string
  // Tradier sandbox order IDs (FLAME only)
  sandbox_order_ids?: Record<string, string | { order_id: string; contracts: number }> | null
  // Counterfactual P&L if held to 2:59 PM CT instead of exiting via PT tier.
  // `null` on trades that haven't been computed yet (e.g. older than Tradier's
  // 40-day window). Available on FLAME / SPARK / INFERNO.
  hypothetical_eod_pnl?: number | null
  hypothetical_eod_computed_at?: string | null
}

function formatCT(ts: string | null): string {
  if (!ts) return '--'
  try {
    const d = new Date(ts)
    return d.toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    })
  } catch { return ts.slice(0, 16) }
}

export default function TradeHistory({ trades, bot }: { trades: Trade[]; bot?: string }) {
  if (!trades.length) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center">
        <p className="text-forge-muted">No closed trades yet</p>
      </div>
    )
  }

  // "Hypo @ 2:59" column — show whenever any trade has a defined value
  // (covers FLAME / SPARK / INFERNO). Empty deploys with no hypo data yet
  // get the original 7-column table until the first daily compute lands.
  const showHypo = trades.some((t) => t.hypothetical_eod_pnl !== undefined && t.hypothetical_eod_pnl !== null)

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-forge-border text-forge-muted text-xs">
            <th className="text-left p-3">Closed</th>
            <th className="text-left p-3">Strikes</th>
            <th className="text-right p-3">Qty</th>
            <th className="text-right p-3">Credit</th>
            <th className="text-right p-3">Close $</th>
            <th className="text-right p-3">P&L</th>
            {showHypo && (
              <th className="text-right p-3" title="Counterfactual: P&L if the position had been held to 2:59 PM CT instead of exiting via PT tier">
                Hypo @ 2:59
              </th>
            )}
            {showHypo && (
              <th className="text-right p-3" title="Actual P&L − Hypothetical. Positive = early exit beat the late-day hold; negative = left money on the table">
                Δ vs Hypo
              </th>
            )}
            <th className="text-left p-3">Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => {
            const positive = trade.realized_pnl >= 0
            const hasSandbox = trade.sandbox_order_ids && Object.keys(trade.sandbox_order_ids).length > 0
            const reason = formatCloseReason(trade.close_reason, bot)
            const hypo = trade.hypothetical_eod_pnl
            const hypoAvailable = hypo != null && Number.isFinite(hypo)
            const delta = hypoAvailable ? trade.realized_pnl - hypo! : null
            // Color: green if early exit beat hypothetical (delta > 0),
            // amber if within ±$5 (≈ noise), red if hypothetical beat
            // actual (we left money on the table by exiting early).
            const deltaColor = delta == null
              ? 'text-forge-muted'
              : Math.abs(delta) < 5
                ? 'text-amber-400'
                : delta > 0
                  ? 'text-emerald-400'
                  : 'text-red-400'
            return (
              <tr key={trade.position_id} className="border-b border-forge-border/50 hover:bg-forge-border/20">
                <td className="p-3 text-xs text-gray-400">{formatCT(trade.close_time)}</td>
                <td className="p-3 font-mono">
                  <div>{trade.put_long_strike}/{trade.put_short_strike}P-{trade.call_short_strike}/{trade.call_long_strike}C</div>
                  {hasSandbox && (
                    <div className="flex gap-2 mt-1">
                      {Object.entries(trade.sandbox_order_ids!).map(([name, val]) => {
                        const isNew = typeof val === 'object' && val !== null
                        const orderId = isNew ? val.order_id : val
                        const qty = isNew ? val.contracts : null
                        return (
                          <span key={name} className="text-[10px] font-mono">
                            <span className="text-forge-muted">{name}:</span>{' '}
                            <span className="text-amber-400">#{orderId}</span>
                            {qty != null && (
                              <span className="text-forge-muted ml-0.5">x{qty}</span>
                            )}
                          </span>
                        )
                      })}
                    </div>
                  )}
                </td>
                <td className="p-3 text-right">x{trade.contracts}</td>
                <td className="p-3 text-right">${trade.total_credit.toFixed(2)}</td>
                <td className="p-3 text-right">${trade.close_price.toFixed(4)}</td>
                <td className={`p-3 text-right font-medium ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                  {positive ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                </td>
                {showHypo && (
                  <td className={`p-3 text-right font-mono ${hypoAvailable ? (hypo! >= 0 ? 'text-emerald-300' : 'text-red-300') : 'text-forge-muted'}`}>
                    {hypoAvailable ? `${hypo! >= 0 ? '+' : ''}$${hypo!.toFixed(2)}` : '—'}
                  </td>
                )}
                {showHypo && (
                  <td className={`p-3 text-right font-mono ${deltaColor}`}>
                    {delta == null ? '—' : `${delta >= 0 ? '+' : ''}$${delta.toFixed(2)}`}
                  </td>
                )}
                <td className="p-3">
                  <span className={`text-xs font-medium ${reason.color}`}>
                    {reason.text}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
