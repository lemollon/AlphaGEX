'use client'

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
  sandbox_order_id?: string | null
}

const reasonColors: Record<string, string> = {
  profit_target: 'bg-emerald-500/20 text-emerald-400',
  stop_loss: 'bg-red-500/20 text-red-400',
  eod_safety: 'bg-amber-500/20 text-amber-400',
  EXPIRED: 'bg-blue-500/20 text-blue-400',
  expired_previous_day: 'bg-blue-500/20 text-blue-400',
}

function parseSandboxOrders(raw: string | null | undefined): Record<string, string> | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed === 'object' && parsed !== null) return parsed
  } catch { /* not valid JSON */ }
  return null
}

export default function TradeHistory({ trades, bot }: { trades: Trade[]; bot?: 'flame' | 'spark' }) {
  if (!trades.length) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center">
        <p className="text-forge-muted">No closed trades yet</p>
      </div>
    )
  }

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
            <th className="text-left p-3">Reason</th>
            {bot === 'flame' && <th className="text-left p-3">Sandbox</th>}
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => {
            const positive = trade.realized_pnl >= 0
            return (
              <tr key={trade.position_id} className="border-b border-forge-border/50 hover:bg-forge-border/20">
                <td className="p-3 text-xs text-gray-400">{trade.close_time?.slice(0, 16)}</td>
                <td className="p-3 font-mono">
                  {trade.put_long_strike}/{trade.put_short_strike}P-{trade.call_short_strike}/{trade.call_long_strike}C
                </td>
                <td className="p-3 text-right">x{trade.contracts}</td>
                <td className="p-3 text-right">${trade.total_credit.toFixed(2)}</td>
                <td className="p-3 text-right">${trade.close_price.toFixed(4)}</td>
                <td className={`p-3 text-right font-medium ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                  {positive ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                </td>
                <td className="p-3">
                  <span className={`text-xs px-2 py-0.5 rounded ${reasonColors[trade.close_reason] || 'bg-stone-600/30 text-gray-400'}`}>
                    {trade.close_reason}
                  </span>
                </td>
                {bot === 'flame' && (
                  <td className="p-3">
                    {(() => {
                      const orders = parseSandboxOrders(trade.sandbox_order_id)
                      if (!orders || Object.keys(orders).length === 0) {
                        return <span className="text-xs text-gray-600">--</span>
                      }
                      return (
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(orders).map(([name, id]) => (
                            <span key={name} className="text-[10px] bg-amber-500/10 text-amber-400 px-1.5 py-0.5 rounded font-mono">
                              {name} #{id}
                            </span>
                          ))}
                        </div>
                      )
                    })()}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
