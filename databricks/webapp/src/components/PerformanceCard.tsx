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
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4">
      <h3 className="text-sm font-medium text-gray-400 mb-3">{label} Performance</h3>

      <div className="grid grid-cols-4 gap-4 mb-4">
        <div>
          <p className="text-xs text-gray-500">Win Rate</p>
          <p className="text-lg font-semibold">{data.win_rate.toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Total P&L</p>
          <p className={`text-lg font-semibold ${pnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {pnlPositive ? '+' : ''}${data.total_pnl.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Avg Win</p>
          <p className="text-lg font-semibold text-emerald-400">+${data.avg_win.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Avg Loss</p>
          <p className="text-lg font-semibold text-red-400">${data.avg_loss.toFixed(2)}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm border-t border-slate-700 pt-3">
        <div>
          <p className="text-xs text-gray-500">Record</p>
          <p className="font-medium">{data.wins}W / {data.losses}L</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Best</p>
          <p className="font-medium text-emerald-400">+${data.best_trade.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Worst</p>
          <p className="font-medium text-red-400">${data.worst_trade.toFixed(2)}</p>
        </div>
      </div>
    </div>
  )
}
