'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { ComparisonChart } from '@/components/EquityChart'
import PerformanceCard from '@/components/PerformanceCard'

const REFRESH = 60_000

export default function ComparePage() {
  const { data: flameStatus } = useSWR('/api/flame/status', fetcher, { refreshInterval: REFRESH })
  const { data: sparkStatus } = useSWR('/api/spark/status', fetcher, { refreshInterval: REFRESH })
  const { data: flameEquity } = useSWR('/api/flame/equity-curve', fetcher, { refreshInterval: REFRESH })
  const { data: sparkEquity } = useSWR('/api/spark/equity-curve', fetcher, { refreshInterval: REFRESH })
  const { data: flamePerf } = useSWR('/api/flame/performance', fetcher, { refreshInterval: REFRESH })
  const { data: sparkPerf } = useSWR('/api/spark/performance', fetcher, { refreshInterval: REFRESH })

  const startingCapital = flameEquity?.starting_capital || sparkEquity?.starting_capital || 5000

  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-2">
        <h1 className="text-2xl font-bold">
          <span className="text-amber-400">FLAME</span>
          <span className="text-gray-500 mx-2">vs</span>
          <span className="text-blue-400">SPARK</span>
        </h1>
        <span className="text-gray-500">2DTE vs 1DTE Comparison</span>
      </div>

      {/* Equity overlay */}
      <ComparisonChart
        flameData={flameEquity?.curve || []}
        sparkData={sparkEquity?.curve || []}
        startingCapital={startingCapital}
      />

      {/* Side-by-side status */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* FLAME */}
        <div>
          <h3 className="text-sm font-medium text-amber-400 mb-2">FLAME (2DTE)</h3>
          {flameStatus && <MiniStatus account={flameStatus.account} />}
          {flamePerf && <PerformanceCard data={flamePerf} label="FLAME" />}
        </div>
        {/* SPARK */}
        <div>
          <h3 className="text-sm font-medium text-blue-400 mb-2">SPARK (1DTE)</h3>
          {sparkStatus && <MiniStatus account={sparkStatus.account} />}
          {sparkPerf && <PerformanceCard data={sparkPerf} label="SPARK" />}
        </div>
      </div>

      {/* Head-to-head table */}
      {flamePerf && sparkPerf && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/50 overflow-x-auto">
          <h3 className="text-sm font-medium text-gray-400 p-4 pb-2">Head-to-Head Metrics</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-gray-400 text-xs">
                <th className="text-left p-3">Metric</th>
                <th className="text-right p-3 text-amber-400">FLAME (2DTE)</th>
                <th className="text-right p-3 text-blue-400">SPARK (1DTE)</th>
              </tr>
            </thead>
            <tbody>
              {metricRows(flamePerf, sparkPerf).map(([name, fv, sv, higherBetter]) => {
                const fNum = parseFloat(String(fv).replace(/[$%+,]/g, ''))
                const sNum = parseFloat(String(sv).replace(/[$%+,]/g, ''))
                const flameWins = higherBetter ? fNum > sNum : fNum < sNum
                const sparkWins = higherBetter ? sNum > fNum : sNum < fNum
                return (
                  <tr key={name} className="border-b border-slate-800">
                    <td className="p-3 font-medium">{name}</td>
                    <td className={`p-3 text-right ${flameWins ? 'text-emerald-400 font-bold' : ''}`}>{fv}</td>
                    <td className={`p-3 text-right ${sparkWins ? 'text-emerald-400 font-bold' : ''}`}>{sv}</td>
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
): [string, string, string, boolean][] {
  return [
    ['Total Trades', String(flame.total_trades), String(spark.total_trades), true],
    ['Win Rate', `${flame.win_rate.toFixed(1)}%`, `${spark.win_rate.toFixed(1)}%`, true],
    ['Total P&L', `$${flame.total_pnl >= 0 ? '+' : ''}${flame.total_pnl.toFixed(2)}`, `$${spark.total_pnl >= 0 ? '+' : ''}${spark.total_pnl.toFixed(2)}`, true],
    ['Avg Win', `$+${flame.avg_win.toFixed(2)}`, `$+${spark.avg_win.toFixed(2)}`, true],
    ['Avg Loss', `$${flame.avg_loss.toFixed(2)}`, `$${spark.avg_loss.toFixed(2)}`, false],
    ['Best Trade', `$+${flame.best_trade.toFixed(2)}`, `$+${spark.best_trade.toFixed(2)}`, true],
    ['Worst Trade', `$${flame.worst_trade.toFixed(2)}`, `$${spark.worst_trade.toFixed(2)}`, false],
  ]
}

function MiniStatus({ account }: { account: any }) {
  const positive = account.cumulative_pnl >= 0
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3 mb-3">
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-gray-500">Balance</p>
          <p className="text-lg font-semibold">${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">P&L</p>
          <p className={`text-lg font-semibold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
            {positive ? '+' : ''}${account.cumulative_pnl.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Return</p>
          <p className={`text-lg font-semibold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
            {positive ? '+' : ''}{account.return_pct.toFixed(1)}%
          </p>
        </div>
      </div>
    </div>
  )
}
