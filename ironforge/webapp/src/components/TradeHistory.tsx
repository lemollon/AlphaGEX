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
  sandbox_order_ids?: Record<string, string> | null
}

export default function TradeHistory({ trades }: { trades: Trade[] }) {
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
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => {
            const positive = trade.realized_pnl >= 0
            const hasSandbox = trade.sandbox_order_ids && Object.keys(trade.sandbox_order_ids).length > 0
            const reason = formatCloseReason(trade.close_reason)
            return (
              <tr key={trade.position_id} className="border-b border-forge-border/50 hover:bg-forge-border/20">
                <td className="p-3 text-xs text-gray-400">{trade.close_time?.slice(0, 16)}</td>
                <td className="p-3 font-mono">
                  <div>{trade.put_long_strike}/{trade.put_short_strike}P-{trade.call_short_strike}/{trade.call_long_strike}C</div>
                  {hasSandbox && (
                    <div className="flex gap-2 mt-1">
                      {Object.entries(trade.sandbox_order_ids!).map(([name, orderId]) => (
                        <span key={name} className="text-[10px] font-mono">
                          <span className="text-forge-muted">{name}:</span>{' '}
                          <span className="text-amber-400">#{orderId}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="p-3 text-right">x{trade.contracts}</td>
                <td className="p-3 text-right">${trade.total_credit.toFixed(2)}</td>
                <td className="p-3 text-right">${trade.close_price.toFixed(4)}</td>
                <td className={`p-3 text-right font-medium ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                  {positive ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                </td>
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
