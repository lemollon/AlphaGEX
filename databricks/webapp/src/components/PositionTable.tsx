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
}

export default function PositionTable({ positions }: { positions: Position[] }) {
  if (!positions.length) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-6 text-center">
        <p className="text-gray-500">No open positions</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-700 text-gray-400 text-xs">
            <th className="text-left p-3">ID</th>
            <th className="text-left p-3">Exp</th>
            <th className="text-left p-3">Strikes</th>
            <th className="text-right p-3">Qty</th>
            <th className="text-right p-3">Credit</th>
            <th className="text-right p-3">Collateral</th>
            <th className="text-right p-3">Entry Price</th>
            <th className="text-left p-3">Opened</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => (
            <tr key={pos.position_id} className="border-b border-slate-800 hover:bg-slate-800/80">
              <td className="p-3 font-mono text-xs">{pos.position_id.slice(0, 16)}</td>
              <td className="p-3">{pos.expiration}</td>
              <td className="p-3 font-mono">
                {pos.put_long_strike}/{pos.put_short_strike}P-{pos.call_short_strike}/{pos.call_long_strike}C
              </td>
              <td className="p-3 text-right">x{pos.contracts}</td>
              <td className="p-3 text-right text-emerald-400">${pos.total_credit.toFixed(2)}</td>
              <td className="p-3 text-right">${pos.collateral_required.toFixed(0)}</td>
              <td className="p-3 text-right">${pos.underlying_at_entry.toFixed(2)}</td>
              <td className="p-3 text-xs text-gray-400">{pos.open_time?.slice(0, 16)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
