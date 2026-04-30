'use client'

interface PerfData {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  total_pnl: number
  avg_win: number
  avg_loss: number
  best_trade: number
  worst_trade: number
  profit_factor?: number | null
  current_streak?: string | null
  // Counterfactual aggregates if we'd held to 2:59 PM CT every day instead
  // of exiting via PT tier. `matched_trades` is the count of trades where
  // both actual AND hypothetical P&L exist (rows older than Tradier's
  // 40-day option window won't have hypo data). Available on FLAME / SPARK
  // / INFERNO.
  hypothetical_eod?: {
    hypo_total: number
    actual_pnl_compared: number
    delta: number
    matched_trades: number
  } | null
}

export default function PerformanceCard({
  data,
  label,
}: {
  data: PerfData
  label: string
}) {
  const pnlPositive = data.total_pnl >= 0

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className="text-sm font-medium text-gray-400 mb-3">{label} Performance</h3>

      <div className="grid grid-cols-4 gap-4 mb-4">
        <div>
          <p className="text-xs text-forge-muted">Win Rate</p>
          <p className="text-lg font-semibold">{data.win_rate.toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Total P&L</p>
          <p className={`text-lg font-semibold ${pnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {pnlPositive ? '+' : ''}${data.total_pnl.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Avg Win</p>
          <p className="text-lg font-semibold text-emerald-400">+${data.avg_win.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Avg Loss</p>
          <p className="text-lg font-semibold text-red-400">${data.avg_loss.toFixed(2)}</p>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-4 text-sm border-t border-forge-border pt-3">
        <div>
          <p className="text-xs text-forge-muted">Record</p>
          <p className="font-medium">{data.wins}W / {data.losses}L</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Best</p>
          <p className="font-medium text-emerald-400">+${data.best_trade.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Worst</p>
          <p className="font-medium text-red-400">${data.worst_trade.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Profit Factor</p>
          <p className={`font-medium ${(data.profit_factor ?? 0) >= 1 ? 'text-emerald-400' : 'text-red-400'}`}>
            {data.profit_factor != null ? data.profit_factor.toFixed(2) : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Streak</p>
          <p className={`font-medium ${data.current_streak?.endsWith('W') ? 'text-emerald-400' : data.current_streak?.endsWith('L') ? 'text-red-400' : ''}`}>
            {data.current_streak ?? '—'}
          </p>
        </div>
      </div>

      {/* SPARK-only counterfactual block: how would the bot have done if it
          had held every trade until 2:59 PM CT instead of exiting early via
          PT tier? Positive Δ = early exits beat the late-day hold (PT
          discipline paid off). Negative Δ = we left money on the table. */}
      {data.hypothetical_eod && data.hypothetical_eod.matched_trades > 0 && (
        <div className="grid grid-cols-3 gap-4 text-sm border-t border-forge-border mt-3 pt-3">
          <div>
            <p className="text-xs text-forge-muted">Hypothetical Total (held to 2:59 PM)</p>
            <p className={`font-medium ${data.hypothetical_eod.hypo_total >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {data.hypothetical_eod.hypo_total >= 0 ? '+' : ''}${data.hypothetical_eod.hypo_total.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-forge-muted">Actual (matched trades)</p>
            <p className={`font-medium ${data.hypothetical_eod.actual_pnl_compared >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {data.hypothetical_eod.actual_pnl_compared >= 0 ? '+' : ''}${data.hypothetical_eod.actual_pnl_compared.toFixed(2)}
            </p>
          </div>
          <div>
            <p
              className="text-xs text-forge-muted"
              title="Actual − Hypothetical. Positive = PT exits beat the late-day hold."
            >
              Δ (Actual − Hypo)
            </p>
            <p className={`font-medium ${data.hypothetical_eod.delta >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {data.hypothetical_eod.delta >= 0 ? '+' : ''}${data.hypothetical_eod.delta.toFixed(2)}
            </p>
            <p className="text-[10px] text-forge-muted mt-0.5">
              {data.hypothetical_eod.matched_trades} trade{data.hypothetical_eod.matched_trades === 1 ? '' : 's'} compared
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
