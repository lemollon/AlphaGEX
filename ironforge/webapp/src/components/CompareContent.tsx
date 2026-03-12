'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { ComparisonChart } from '@/components/EquityChart'
import PerformanceCard from '@/components/PerformanceCard'

const REFRESH = 60_000

function fmtPnl(v: number) {
  return `$${v >= 0 ? '+' : ''}${v.toFixed(2)}`
}

export default function CompareContent() {
  const { data: flameStatus } = useSWR('/api/flame/status', fetcher, { refreshInterval: REFRESH })
  const { data: sparkStatus } = useSWR('/api/spark/status', fetcher, { refreshInterval: REFRESH })
  const { data: infernoStatus } = useSWR('/api/inferno/status', fetcher, { refreshInterval: REFRESH })
  const { data: flameEquity } = useSWR('/api/flame/equity-curve', fetcher, { refreshInterval: REFRESH })
  const { data: sparkEquity } = useSWR('/api/spark/equity-curve', fetcher, { refreshInterval: REFRESH })
  const { data: infernoEquity } = useSWR('/api/inferno/equity-curve', fetcher, { refreshInterval: REFRESH })
  const { data: flamePerf } = useSWR('/api/flame/performance', fetcher, { refreshInterval: REFRESH })
  const { data: sparkPerf } = useSWR('/api/spark/performance', fetcher, { refreshInterval: REFRESH })
  const { data: infernoPerf } = useSWR('/api/inferno/performance', fetcher, { refreshInterval: REFRESH })

  const startingCapital = flameEquity?.starting_capital || sparkEquity?.starting_capital || infernoEquity?.starting_capital || 5000

  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-2">
        <h1 className="text-2xl font-bold">
          <span className="text-amber-400">FLAME</span>
          <span className="text-forge-muted mx-2">vs</span>
          <span className="text-blue-400">SPARK</span>
          <span className="text-forge-muted mx-2">vs</span>
          <img src="/inferno-icon.svg" alt="" className="h-5 w-5 inline-block align-[-2px]" />
          <span className="text-red-400">INFERNO</span>
        </h1>
        <span className="text-forge-muted">2DTE vs 1DTE vs 0DTE Comparison</span>
      </div>

      {/* Equity overlay */}
      <ComparisonChart
        flameData={flameEquity?.curve || []}
        sparkData={sparkEquity?.curve || []}
        infernoData={infernoEquity?.curve || []}
        startingCapital={startingCapital}
      />

      {/* Side-by-side status */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* FLAME */}
        <div>
          <h3 className="text-sm font-medium text-amber-400 mb-2">FLAME (2DTE)</h3>
          {flameStatus && <MiniStatus account={flameStatus.account} />}
          {flamePerf && <PerformanceCard data={flamePerf} label="FLAME" />}
        </div>
        <div>
          <h3 className="text-sm font-medium text-blue-400 mb-2">SPARK (1DTE)</h3>
          {sparkStatus && <MiniStatus account={sparkStatus.account} />}
          {sparkPerf && <PerformanceCard data={sparkPerf} label="SPARK" />}
        </div>
        {/* INFERNO */}
        <div>
          <h3 className="text-sm font-medium text-red-400 mb-2">
            <img src="/inferno-icon.svg" alt="" className="h-4 w-4 inline-block mr-1 align-[-2px]" />
            INFERNO (0DTE)
          </h3>
          {infernoStatus && <MiniStatus account={infernoStatus.account} />}
          {infernoPerf && <PerformanceCard data={infernoPerf} label="INFERNO" />}
        </div>
      </div>

      {/* Head-to-head table */}
      {flamePerf && sparkPerf && infernoPerf && (
        <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-x-auto">
          <h3 className="text-sm font-medium text-gray-400 p-4 pb-2">Head-to-Head Metrics</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-forge-border text-forge-muted text-xs">
                <th className="text-left p-3">Metric</th>
                <th className="text-right p-3 text-amber-400">FLAME (2DTE)</th>
                <th className="text-right p-3 text-blue-400">SPARK (1DTE)</th>
                <th className="text-right p-3 text-red-400">INFERNO (0DTE)</th>
              </tr>
            </thead>
            <tbody>
              {metricRows(flamePerf, sparkPerf, infernoPerf).map(([name, fv, sv, iv, higherBetter]) => {
                const fNum = parseFloat(String(fv).replace(/[$%+,]/g, ''))
                const sNum = parseFloat(String(sv).replace(/[$%+,]/g, ''))
                const iNum = parseFloat(String(iv).replace(/[$%+,]/g, ''))
                const best = higherBetter
                  ? Math.max(fNum, sNum, iNum)
                  : Math.min(fNum, sNum, iNum)
                return (
                  <tr key={name} className="border-b border-forge-border/50">
                    <td className="p-3 font-medium">{name}</td>
                    <td className={`p-3 text-right ${fNum === best ? 'text-emerald-400 font-bold' : ''}`}>{fv}</td>
                    <td className={`p-3 text-right ${sNum === best ? 'text-emerald-400 font-bold' : ''}`}>{sv}</td>
                    <td className={`p-3 text-right ${iNum === best ? 'text-emerald-400 font-bold' : ''}`}>{iv}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function metricRows(
  flame: any,
  spark: any,
  inferno: any,
): [string, string, string, string, boolean][] {
  return [
    ['Total Trades', String(flame.total_trades), String(spark.total_trades), String(inferno.total_trades), true],
    ['Win Rate', `${flame.win_rate.toFixed(1)}%`, `${spark.win_rate.toFixed(1)}%`, `${inferno.win_rate.toFixed(1)}%`, true],
    ['Total P&L', fmtPnl(flame.total_pnl), fmtPnl(spark.total_pnl), fmtPnl(inferno.total_pnl), true],
    ['Avg Win', `$+${flame.avg_win.toFixed(2)}`, `$+${spark.avg_win.toFixed(2)}`, `$+${inferno.avg_win.toFixed(2)}`, true],
    ['Avg Loss', `$${flame.avg_loss.toFixed(2)}`, `$${spark.avg_loss.toFixed(2)}`, `$${inferno.avg_loss.toFixed(2)}`, false],
    ['Best Trade', `$+${flame.best_trade.toFixed(2)}`, `$+${spark.best_trade.toFixed(2)}`, `$+${inferno.best_trade.toFixed(2)}`, true],
    ['Worst Trade', `$${flame.worst_trade.toFixed(2)}`, `$${spark.worst_trade.toFixed(2)}`, `$${inferno.worst_trade.toFixed(2)}`, false],
  ]
}

function MiniStatus({ account }: { account: any }) {
  if (!account) return null
  const positive = account.cumulative_pnl >= 0
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3 mb-3">
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-forge-muted">Balance</p>
          <p className="text-lg font-semibold">${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">P&L</p>
          <p className={`text-lg font-semibold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
            {positive ? '+' : ''}${account.cumulative_pnl.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Return</p>
          <p className={`text-lg font-semibold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
            {positive ? '+' : ''}{account.return_pct.toFixed(1)}%
          </p>
        </div>
      </div>
    </div>
  )
}
