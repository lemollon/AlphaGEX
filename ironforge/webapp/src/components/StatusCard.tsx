'use client'

interface StatusData {
  bot_name: string
  strategy: string
  is_active: boolean
  account: {
    balance: number
    cumulative_pnl: number
    unrealized_pnl: number
    total_pnl: number
    return_pct: number
    buying_power: number
    total_trades: number
    collateral_in_use: number
  }
  open_positions: number
  last_scan: string | null
  last_snapshot: string | null
  scan_count: number
}

interface ConfigData {
  sd_multiplier?: number
  spread_width?: number
  buying_power_usage_pct?: number
  profit_target_pct?: number
  stop_loss_pct?: number
  vix_skip?: number
  max_contracts?: number
}

export default function StatusCard({
  data,
  accent,
  config,
}: {
  data: StatusData
  accent: 'amber' | 'blue'
  config?: ConfigData | null
}) {
  const { account } = data
  const realizedPositive = account.cumulative_pnl >= 0
  const unrealized = account.unrealized_pnl || 0
  const unrealizedPositive = unrealized >= 0
  const totalPnl = account.total_pnl || account.cumulative_pnl + unrealized
  const totalPositive = totalPnl >= 0

  const accentBorder = accent === 'amber' ? 'border-amber-500/30' : 'border-blue-500/30'
  const accentText = accent === 'amber' ? 'text-amber-400' : 'text-blue-400'

  return (
    <div className={`rounded-xl border ${accentBorder} bg-forge-card/80 p-4`}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <h2 className={`text-lg font-bold ${accentText}`}>{data.bot_name}</h2>
        <span className="text-xs text-gray-400 bg-forge-border px-2 py-0.5 rounded">
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

      {/* Main metrics: Balance | Realized | Unrealized | Total */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <div>
          <p className="text-xs text-forge-muted">Balance</p>
          <p className="text-xl font-semibold">
            ${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Realized P&L</p>
          <p
            className={`text-xl font-semibold ${realizedPositive ? 'text-emerald-400' : 'text-red-400'}`}
          >
            {realizedPositive ? '+' : ''}$
            {account.cumulative_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Unrealized P&L</p>
          <p
            className={`text-xl font-semibold ${
              unrealized === 0
                ? 'text-gray-400'
                : unrealizedPositive
                  ? 'text-emerald-400'
                  : 'text-red-400'
            }`}
          >
            {unrealized === 0
              ? '$0.00'
              : `${unrealizedPositive ? '+' : ''}$${unrealized.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                })}`}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Total P&L</p>
          <p
            className={`text-xl font-bold ${totalPositive ? 'text-emerald-400' : 'text-red-400'}`}
          >
            {totalPositive ? '+' : ''}$
            {totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            <span className="text-sm ml-1">
              ({totalPositive ? '+' : ''}
              {account.return_pct.toFixed(1)}%)
            </span>
          </p>
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-5 gap-4 text-sm">
        <div>
          <p className="text-xs text-forge-muted">Open</p>
          <p className="font-medium">{data.open_positions}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Total Trades</p>
          <p className="font-medium">{account.total_trades}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Collateral</p>
          <p className="font-medium">
            ${account.collateral_in_use.toLocaleString(undefined, { minimumFractionDigits: 0 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Buying Power</p>
          <p className="font-medium">
            ${account.buying_power.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Scans</p>
          <p className="font-medium">{data.scan_count}</p>
        </div>
      </div>

      {/* Config summary */}
      {config && (
        <div className="flex flex-wrap gap-3 mt-3 pt-3 border-t border-forge-border/50">
          <span className="text-[10px] text-forge-muted uppercase tracking-wider">Config</span>
          <span className="text-xs font-mono text-gray-400">{config.sd_multiplier ?? 1.2}x SD</span>
          <span className="text-xs font-mono text-gray-400">${config.spread_width ?? 5} wings</span>
          <span className="text-xs font-mono text-gray-400">{((config.buying_power_usage_pct ?? 0.85) * 100).toFixed(0)}% BP</span>
          <span className="text-xs font-mono text-gray-400">PT {config.profit_target_pct ?? 30}%</span>
          <span className="text-xs font-mono text-gray-400">SL {config.stop_loss_pct ?? 100}%</span>
          <span className="text-xs font-mono text-gray-400">VIX&gt;{config.vix_skip ?? 32} skip</span>
          <span className="text-xs font-mono text-gray-400">max {config.max_contracts ?? 10}x</span>
        </div>
      )}

      {data.last_scan && (
        <p className="text-xs text-forge-muted mt-3">Last scan: {data.last_scan}</p>
      )}
    </div>
  )
}
