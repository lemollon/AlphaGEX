'use client'

interface StatusData {
  bot_name: string
  strategy: string
  is_active: boolean
  account: {
    balance: number
    cumulative_pnl: number
    return_pct: number
    buying_power: number
    total_trades: number
  }
  open_positions: number
  last_scan: string | null
  scan_count: number
}

export default function StatusCard({
  data,
  accent,
}: {
  data: StatusData
  accent: 'amber' | 'blue'
}) {
  const { account } = data
  const pnlPositive = account.cumulative_pnl >= 0

  const accentBorder = accent === 'amber' ? 'border-amber-500/30' : 'border-blue-500/30'
  const accentBg = accent === 'amber' ? 'bg-amber-500/10' : 'bg-blue-500/10'
  const accentText = accent === 'amber' ? 'text-amber-400' : 'text-blue-400'

  return (
    <div className={`rounded-lg border ${accentBorder} ${accentBg} p-4`}>
      <div className="flex items-center gap-3 mb-4">
        <h2 className={`text-lg font-bold ${accentText}`}>{data.bot_name}</h2>
        <span className="text-xs text-gray-400 bg-slate-800 px-2 py-0.5 rounded">
          {data.strategy}
        </span>
        <span
          className={`text-xs px-2 py-0.5 rounded ${
            data.is_active
              ? 'bg-emerald-500/20 text-emerald-400'
              : 'bg-gray-600/20 text-gray-400'
          }`}
        >
          {data.is_active ? 'ACTIVE' : 'INACTIVE'}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <p className="text-xs text-gray-500">Balance</p>
          <p className="text-xl font-semibold">${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">P&L</p>
          <p className={`text-xl font-semibold ${pnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {pnlPositive ? '+' : ''}${account.cumulative_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Return</p>
          <p className={`text-xl font-semibold ${pnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {pnlPositive ? '+' : ''}{account.return_pct.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-xs text-gray-500">Open</p>
          <p className="font-medium">{data.open_positions}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Total Trades</p>
          <p className="font-medium">{account.total_trades}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Buying Power</p>
          <p className="font-medium">${account.buying_power.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Scans</p>
          <p className="font-medium">{data.scan_count}</p>
        </div>
      </div>

      {data.last_scan && (
        <p className="text-xs text-gray-600 mt-3">
          Last scan: {data.last_scan}
        </p>
      )}
    </div>
  )
}
