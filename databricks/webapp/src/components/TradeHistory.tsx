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
  sandbox_order_id?: string | null
  scanner_close_price?: number | null
  sandbox_fill_price?: number | null
  fill_delta_pct?: number | null
}

interface SandboxEntry {
  orderId: string
  contracts?: number
}

function parseSandboxOrders(raw: string | null | undefined): Record<string, SandboxEntry> | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return null
    const result: Record<string, SandboxEntry> = {}
    for (const [name, value] of Object.entries(parsed)) {
      if (typeof value === 'object' && value !== null && 'order_id' in value) {
        // New format: {"User": {"order_id": 25827435, "contracts": 189}}
        const v = value as { order_id: number | string; contracts?: number }
        result[name] = { orderId: String(v.order_id), contracts: v.contracts }
      } else {
        // Old format: {"User": 25827435}
        result[name] = { orderId: String(value) }
      }
    }
    return Object.keys(result).length > 0 ? result : null
  } catch { /* not valid JSON */ }
  return null
}

export default function TradeHistory({ trades, bot }: { trades: Trade[]; bot?: 'flame' | 'spark' | 'inferno' }) {
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
            const reason = formatCloseReason(trade.close_reason)
            return (
              <tr key={trade.position_id} className="border-b border-forge-border/50 hover:bg-forge-border/20">
                <td className="p-3 text-xs text-gray-400">{trade.close_time?.slice(0, 16)}</td>
                <td className="p-3 font-mono">
                  {trade.put_long_strike}/{trade.put_short_strike}P-{trade.call_short_strike}/{trade.call_long_strike}C
                </td>
                <td className="p-3 text-right">x{trade.contracts}</td>
                <td className="p-3 text-right">${trade.total_credit.toFixed(2)}</td>
                <td className="p-3 text-right">
                  <span className="font-mono">${trade.close_price.toFixed(4)}</span>
                  {trade.sandbox_fill_price != null && trade.fill_delta_pct != null && (
                    <div className="text-[10px] text-forge-muted mt-0.5">
                      SB: ${trade.sandbox_fill_price.toFixed(4)}{' '}
                      <span className={trade.fill_delta_pct > 5 ? 'text-amber-400' : 'text-gray-500'}>
                        ({trade.fill_delta_pct.toFixed(1)}%)
                      </span>
                    </div>
                  )}
                </td>
                <td className={`p-3 text-right font-medium ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                  {positive ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                </td>
                <td className="p-3">
                  <span className={`text-xs font-medium ${reason.color}`}>
                    {reason.text}
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
                          {Object.entries(orders).map(([name, entry]) => (
                            <span key={name} className="text-[10px] bg-amber-500/10 text-amber-400 px-1.5 py-0.5 rounded font-mono">
                              {name} #{entry.orderId}{entry.contracts != null ? ` (${entry.contracts}x)` : ''}
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
