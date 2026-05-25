'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { ComparisonChart, type Period, type CompareSeries, type CompareMode, type CurvePoint } from '@/components/EquityChart'
import PerformanceCard from '@/components/PerformanceCard'

const REFRESH = 60_000

const BOTS = [
  { key: 'flame', label: 'FLAME (2DTE)', short: 'FLAME', color: '#f59e0b', accent: 'text-amber-400' },
  { key: 'spark', label: 'SPARK (1DTE)', short: 'SPARK', color: '#3b82f6', accent: 'text-blue-400' },
  { key: 'inferno', label: 'INFERNO (0DTE)', short: 'INFERNO', color: '#ef4444', accent: 'text-red-400' },
  { key: 'blaze', label: 'BLAZE (1DTE dir.)', short: 'BLAZE', color: '#fb923c', accent: 'text-orange-400' },
  { key: 'flare', label: 'FLARE (0DTE dir.)', short: 'FLARE', color: '#d946ef', accent: 'text-fuchsia-400' },
] as const

type BotKey = (typeof BOTS)[number]['key']

interface BotData {
  status?: any
  perf?: any
  hist?: any
  intra?: any
}

/** Per-bot data: status + performance always; chart data is either the
 *  historical equity-curve (period-filtered, carries the hypothetical line) or
 *  intraday snapshots. SWR skips a null key, so only the active chart source
 *  is fetched. Called once per bot at the top level (stable hook order). */
function useBotData(botKey: string, period: Period, personQ: string, isIntraday: boolean): BotData {
  const q = personQ ? `?${personQ}` : ''
  const status = useSWR(`/api/${botKey}/status${q}`, fetcher, { refreshInterval: REFRESH }).data
  const perf = useSWR(`/api/${botKey}/performance${q}`, fetcher, { refreshInterval: REFRESH }).data
  // Always fetch full history — the chart computes per-day returns over all
  // history (so the first day of any window has a correct prior-day baseline)
  // and windows the result client-side from the selected period.
  const hist = useSWR(
    !isIntraday ? `/api/${botKey}/equity-curve?period=all${personQ ? `&${personQ}` : ''}` : null,
    fetcher,
    { refreshInterval: REFRESH },
  ).data
  const intra = useSWR(
    isIntraday ? `/api/${botKey}/equity-curve/intraday${q}` : null,
    fetcher,
    { refreshInterval: REFRESH },
  ).data
  return { status, perf, hist, intra }
}

export default function CompareContent() {
  const [selectedPerson, setSelectedPerson] = useState('all')
  const [period, setPeriod] = useState<Period>('all')
  const [chartMode, setChartMode] = useState<CompareMode>('daily')
  const [showHypo, setShowHypo] = useState(false)

  const { data: personsData } = useSWR('/api/persons', fetcher)
  const personEntries: Array<{ person: string; alias: string | null }> = personsData?.persons ?? []
  const persons: string[] = personEntries.map((pe) => pe.person)

  const personQ = selectedPerson !== 'all' ? `person=${encodeURIComponent(selectedPerson)}` : ''
  const isIntraday = period === 'intraday'

  const flame = useBotData('flame', period, personQ, isIntraday)
  const spark = useBotData('spark', period, personQ, isIntraday)
  const inferno = useBotData('inferno', period, personQ, isIntraday)
  const blaze = useBotData('blaze', period, personQ, isIntraday)
  const flare = useBotData('flare', period, personQ, isIntraday)
  const byKey: Record<BotKey, BotData> = { flame, spark, inferno, blaze, flare }

  const startOf = (k: BotKey): number =>
    byKey[k].status?.account?.starting_capital ?? byKey[k].hist?.starting_capital ?? 10000

  // Build the normalized series for the overlay. Intraday maps snapshots to the
  // {timestamp, equity} shape the chart expects; historical passes the curve
  // through directly (it already carries hypothetical_equity).
  const series: CompareSeries[] = BOTS.map((b) => {
    const d = byKey[b.key]
    const data: CurvePoint[] = isIntraday
      ? (d.intra?.snapshots ?? []).map((s: any) => ({
          timestamp: s.timestamp,
          equity: s.equity ?? s.balance ?? 0,
          pnl: 0,
          cumulative_pnl: 0,
        }))
      : (d.hist?.curve ?? [])
    return { key: b.key, label: b.short, color: b.color, start: startOf(b.key), data }
  })

  const allPerfReady = BOTS.every((b) => byKey[b.key].perf)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h1 className="text-2xl font-bold">
            <span className="text-amber-400">FLAME</span>
            <span className="text-forge-muted mx-1.5">vs</span>
            <span className="text-blue-400">SPARK</span>
            <span className="text-forge-muted mx-1.5">vs</span>
            <span className="text-red-400">INFERNO</span>
            <span className="text-forge-muted mx-1.5">vs</span>
            <span className="text-orange-400">BLAZE</span>
            <span className="text-forge-muted mx-1.5">vs</span>
            <span className="text-fuchsia-400">FLARE</span>
          </h1>
          <span className="text-forge-muted text-sm">2DTE · 1DTE IC · 0DTE IC · 1DTE dir. · 0DTE dir.</span>
        </div>
        {persons.length > 1 && (
          <select
            value={selectedPerson}
            onChange={(e) => setSelectedPerson(e.target.value)}
            className="bg-forge-card border border-gray-700 rounded px-3 py-1.5 text-sm text-white focus:border-amber-500 focus:outline-none"
          >
            <option value="all">All Accounts</option>
            {personEntries.map((pe) => (
              <option key={pe.person} value={pe.person}>{pe.alias || pe.person}</option>
            ))}
          </select>
        )}
      </div>

      {/* Normalized equity overlay with timeframe selector + hypothetical toggle */}
      <ComparisonChart
        series={series}
        period={period}
        onPeriodChange={setPeriod}
        mode={chartMode}
        onModeChange={setChartMode}
        showHypo={showHypo}
        onToggleHypo={() => setShowHypo((v) => !v)}
        allowHypo={!isIntraday}
      />

      {/* Side-by-side status — 2-up on smaller screens, 3-up on md, 5-up on xl;
          compact cards so the dollar values don't collide at narrow column widths. */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
        {BOTS.map((b) => {
          const d = byKey[b.key]
          return (
            <div key={b.key}>
              <h3 className={`text-sm font-medium ${b.accent} mb-2`}>{b.label}</h3>
              {d.status && <MiniStatus account={d.status.account} />}
              {d.perf && <PerformanceCard data={d.perf} label={b.short} compact />}
            </div>
          )
        })}
      </div>

      {/* Head-to-head table (normalized to % of each bot's capital) */}
      {allPerfReady && (
        <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-x-auto">
          <h3 className="text-sm font-medium text-gray-400 p-4 pb-2">Head-to-Head Metrics (% of capital)</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-forge-border text-forge-muted text-xs">
                <th className="text-left p-3">Metric</th>
                {BOTS.map((b) => (
                  <th key={b.key} className={`text-right p-3 ${b.accent}`}>{b.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metricRows(BOTS.map((b) => ({ perf: byKey[b.key].perf, start: startOf(b.key) }))).map((r) => {
                const nums = r.values.map((v) => parseFloat(String(v).replace(/[$%+,]/g, '')))
                const valid = nums.filter((n) => !Number.isNaN(n))
                const best = valid.length
                  ? r.higherBetter
                    ? Math.max(...valid)
                    : Math.min(...valid)
                  : NaN
                return (
                  <tr key={r.name} className="border-b border-forge-border/50">
                    <td className="p-3 font-medium">{r.name}</td>
                    {r.values.map((v, i) => (
                      <td
                        key={i}
                        className={`p-3 text-right ${nums[i] === best ? 'text-emerald-400 font-bold' : ''}`}
                      >
                        {v}
                      </td>
                    ))}
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
  items: { perf: any; start: number }[],
): { name: string; values: string[]; higherBetter: boolean }[] {
  // Dollar metrics are normalized to % of each bot's own starting capital so
  // bots of different sizes compare fairly. Win Rate / Total Trades are already
  // scale-independent.
  const asPct = (v: number, start: number) => (start > 0 ? (v / start) * 100 : 0)
  const fmtPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
  return [
    { name: 'Total Trades', values: items.map((it) => String(it.perf.total_trades)), higherBetter: true },
    { name: 'Win Rate', values: items.map((it) => `${it.perf.win_rate.toFixed(1)}%`), higherBetter: true },
    { name: 'Total Return', values: items.map((it) => fmtPct(asPct(it.perf.total_pnl, it.start))), higherBetter: true },
    { name: 'Avg Win (% cap)', values: items.map((it) => fmtPct(asPct(it.perf.avg_win, it.start))), higherBetter: true },
    { name: 'Avg Loss (% cap)', values: items.map((it) => fmtPct(asPct(it.perf.avg_loss, it.start))), higherBetter: false },
    { name: 'Best Trade (% cap)', values: items.map((it) => fmtPct(asPct(it.perf.best_trade, it.start))), higherBetter: true },
    { name: 'Worst Trade (% cap)', values: items.map((it) => fmtPct(asPct(it.perf.worst_trade, it.start))), higherBetter: false },
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
          <p className="text-base font-semibold">${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">P&L</p>
          <p className={`text-base font-semibold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
            {positive ? '+' : ''}${account.cumulative_pnl.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Return</p>
          <p className={`text-base font-semibold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
            {positive ? '+' : ''}{account.return_pct.toFixed(1)}%
          </p>
        </div>
      </div>
    </div>
  )
}
