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
  // BLAZE directional fields
  setup_type?: string | null
  direction?: 'call' | 'put' | string | null
  long_strike?: number
  short_strike?: number
  debit?: number
  // Tradier sandbox order IDs (FLAME only)
  sandbox_order_ids?: Record<string, string | { order_id: string; contracts: number }> | null
  // Counterfactual P&L if held to 2:59 PM CT instead of exiting via PT
  // tier. `null` for trades that haven't been computed yet (e.g. older
  // than Tradier's 40-day window).
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

  // "Hypo @ 2:59" column. Available for all three bots — surface it
  // whenever the API returned the field for at least one trade. The
  // hypothetical_eod_pnl backfill only covers Tradier's ~40-day window;
  // older rows stay null and render as em-dash.
  const showHypo = trades.some((t) => t.hypothetical_eod_pnl !== undefined)

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-x-auto">
      {showHypo && (
        <div className="border-b border-forge-border bg-forge-bg/40 px-4 py-2 text-[11px] leading-relaxed text-forge-muted">
          <span className="text-amber-400 font-medium">How to read the hypo columns:</span>{' '}
          <strong className="text-gray-300">Hypo @ 2:59</strong> is the P&L this trade <em>would have had</em> if held to 2:59 PM
          (a counterfactual outcome — <em>not</em> added to the actual P&L).{' '}
          <strong className="text-gray-300">Δ = Hypo − P&L</strong> is the gap between the two outcomes.{' '}
          <span className="text-red-300">Positive Δ (red)</span> = money left on the table by exiting early;{' '}
          <span className="text-emerald-300">negative Δ (green)</span> = early exit beat the hold.{' '}
          Example: P&L −$54 + Hypo +$30 → Δ = 30 − (−54) = <strong>+$84</strong> (held would have been $84 better).
        </div>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-forge-border text-forge-muted text-xs">
            <th className="text-left p-3">Closed</th>
            <th className="text-left p-3">Strikes</th>
            <th className="text-right p-3">Qty</th>
            <th className="text-right p-3" title="Credit (IC) or Debit (BLAZE) paid/received at open">Entry</th>
            <th className="hidden sm:table-cell text-right p-3">Close $</th>
            <th className="text-right p-3">P&L<div className="text-[10px] font-normal normal-case text-forge-muted">actual</div></th>
            {showHypo && (
              <th className="hidden md:table-cell text-right p-3" title="Counterfactual: P&L if the bot had held to 2:59 PM CT instead of exiting via PT tier">
                Hypo @ 2:59<div className="text-[10px] font-normal normal-case text-forge-muted">if held</div>
              </th>
            )}
            {showHypo && (
              <th className="hidden md:table-cell text-right p-3" title="Hypo − P&L. Positive = money left on the table by exiting early; negative = early exit beat the late-day hold">
                Δ vs Hypo<div className="text-[10px] font-normal normal-case text-forge-muted">Hypo − P&L</div>
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
            // Δ = hypo − actual: positive = money left on the table by
            // exiting early (RED, bad); negative = early exit beat
            // hypothetical (GREEN, good); within ±$5 = noise (AMBER).
            const delta = hypoAvailable ? hypo! - trade.realized_pnl : null
            const deltaColor = delta == null
              ? 'text-forge-muted'
              : Math.abs(delta) < 5
                ? 'text-amber-400'
                : delta > 0
                  ? 'text-red-400'
                  : 'text-emerald-400'
            return (
              <tr key={trade.position_id} className="border-b border-forge-border/50 hover:bg-forge-border/20">
                <td className="p-3 text-xs text-gray-400">{formatCT(trade.close_time)}</td>
                <td className="p-3 font-mono">
                  <div>
                    {trade.direction && trade.long_strike != null && trade.short_strike != null && trade.long_strike > 0
                      ? `${trade.long_strike}/${trade.short_strike}${trade.direction === 'call' ? 'C' : 'P'} ${trade.direction === 'call' ? '(Call DR)' : '(Put DR)'}`
                      : `${trade.put_long_strike}/${trade.put_short_strike}P-${trade.call_short_strike}/${trade.call_long_strike}C`}
                  </div>
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
                <td className="p-3 text-right">
                  {trade.direction && (trade.debit ?? 0) > 0
                    ? `−$${(trade.debit ?? 0).toFixed(2)}`
                    : `$${trade.total_credit.toFixed(2)}`}
                </td>
                <td className="hidden sm:table-cell p-3 text-right">${trade.close_price.toFixed(4)}</td>
                <td className={`p-3 text-right font-medium ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                  {positive ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                </td>
                {showHypo && (
                  <td className={`hidden md:table-cell p-3 text-right font-mono ${hypoAvailable ? (hypo! >= 0 ? 'text-emerald-300' : 'text-red-300') : 'text-forge-muted'}`}>
                    {hypoAvailable ? `${hypo! >= 0 ? '+' : ''}$${hypo!.toFixed(2)}` : '—'}
                  </td>
                )}
                {showHypo && (
                  <td className={`hidden md:table-cell p-3 text-right font-mono ${deltaColor}`}>
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
