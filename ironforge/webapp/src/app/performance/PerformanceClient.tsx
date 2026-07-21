'use client'

import useSWR from 'swr'
import { Area, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fetcher } from '@/lib/fetcher'
import { formatDollarPnl } from '@/lib/format'
import { BOT_COLORS } from '@/lib/botColors'
import type { LiveBot } from '@/lib/live/bots'
import type { PerformanceData } from '@/lib/live/performance'
import LiveSidebar from '../live/components/LiveSidebar'
import SparkMascot from '../live/components/SparkMascot'

type PerfResponse =
  | ({ empty?: false; viewer: { allowedBots: LiveBot[]; paperBots: LiveBot[] } } & PerformanceData)
  | { empty: true; viewer: { allowedBots: LiveBot[]; paperBots: LiveBot[] } }

function formatMoney(v: number | null | undefined): string {
  if (v == null) return '—'
  return `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatCT(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric' })
}

function signedDollars(v: number): string {
  const r = Math.round(v)
  return r > 0 ? `+$${r.toLocaleString('en-US')}` : r < 0 ? `-$${Math.abs(r).toLocaleString('en-US')}` : '$0'
}

export default function PerformanceClient() {
  const { data, error } = useSWR<PerfResponse>('/api/live/performance', fetcher, { refreshInterval: 60_000 })

  const allowedBots = (data?.viewer?.allowedBots ?? []) as LiveBot[]
  const paperBots = (data?.viewer?.paperBots ?? []) as LiveBot[]

  return (
    <div className="min-h-screen bg-forge-bg">
      <LiveSidebar membership={null} bots={allowedBots} paperBots={paperBots} />
      <div className="lg:pl-60">
        <div className="mx-auto max-w-[1200px] px-4 py-5">
          <h1 className="text-2xl font-bold text-white">Performance</h1>
          <p className="mt-1 text-sm text-gray-400">Your all-time results across every strategy you own.</p>

          {data && 'empty' in data && data.empty ? (
            <div className="mt-4 rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
              <h2 className="text-lg font-bold text-white">No performance history yet</h2>
              <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-400">
                Your performance appears here once a strategy is connected to your membership and starts trading.
              </p>
            </div>
          ) : error && !data ? (
            <div className="mt-4 rounded-xl border border-forge-border bg-forge-card/80 p-6 text-sm text-gray-400">
              Performance data is temporarily unavailable — try refreshing in a moment.
            </div>
          ) : !data ? (
            <div className="mt-4 h-40 animate-pulse rounded-xl border border-forge-border bg-forge-card/50" />
          ) : (
            <PerformanceBody data={data as PerformanceData} />
          )}
        </div>
      </div>
    </div>
  )
}

function PerformanceBody({ data }: { data: PerformanceData }) {
  const { bots, combined, equity_curve } = data
  const positive = combined.total_pnl >= 0
  // Single strategy → its own colour; multiple → the IronForge gold, since the
  // curve is the blend of every strategy, not any one of them.
  const curveHex = bots.length === 1 ? BOT_COLORS[bots[0].accent] : '#f59e0b'
  const curveFill = bots.length === 1
    ? (bots[0].accent === 'flame' ? 'rgba(255,85,0,0.18)' : 'rgba(59,130,246,0.18)')
    : 'rgba(245,158,11,0.16)'

  return (
    <div className="mt-4 flex flex-col gap-4">
      {/* Hero: the strategy mascots + combined account value */}
      <section className="rounded-xl border border-forge-border bg-forge-card/80 p-5">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <div className="flex shrink-0 gap-3">
            {bots.map((b) => (
              <div
                key={b.bot}
                className={`flex h-16 w-16 items-center justify-center rounded-2xl bg-forge-bg ring-1 sm:h-20 sm:w-20 ${
                  b.accent === 'flame' ? 'ring-flame/25' : 'ring-spark/25'
                }`}
              >
                <SparkMascot className="h-full w-full rounded-2xl mix-blend-screen" variant={b.accent} />
              </div>
            ))}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-widest text-gray-500">
              {bots.length > 1 ? 'Total Account Value' : 'Account Value'}
            </div>
            <div className="mt-1 font-mono text-4xl font-bold text-white">{formatMoney(combined.account_value)}</div>
            <div className="mt-1 text-sm text-gray-400">
              {bots.map((b) => b.label).join(' + ')} · started {formatMoney(combined.starting_capital)}
            </div>
            {combined.total_return_pct != null && (
              <div
                className={`mt-3 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1 text-sm font-semibold ${
                  positive
                    ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-400'
                    : 'border-red-500/25 bg-red-500/10 text-red-400'
                }`}
              >
                {positive ? '▲' : '▼'} {combined.total_return_pct > 0 ? '+' : ''}
                {combined.total_return_pct.toFixed(2)}% all time
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="Total P&L"
          value={formatDollarPnl(combined.total_pnl)}
          valueClass={positive ? 'text-emerald-400' : 'text-red-400'}
        />
        <StatTile label="Win Rate" value={combined.win_rate != null ? `${combined.win_rate.toFixed(1)}%` : '—'} sub={`${combined.wins} wins · ${combined.losses} losses`} />
        <StatTile label="Total Trades" value={String(combined.total_trades)} />
        <StatTile
          label="Best Day"
          value={combined.best_day != null ? formatDollarPnl(combined.best_day) : '—'}
          valueClass={combined.best_day != null && combined.best_day >= 0 ? 'text-emerald-400' : undefined}
        />
      </div>

      {/* Equity curve */}
      <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-amber-500">Equity Curve</h3>
        {equity_curve.length >= 2 ? (
          <div className="mt-3 h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={equity_curve} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                <XAxis dataKey="t" tickFormatter={formatCT} stroke="#44403c" tick={{ fill: '#a8a29e', fontSize: 11 }} minTickGap={56} />
                <YAxis
                  orientation="right"
                  tickFormatter={(v: number) => `$${Math.round(v).toLocaleString('en-US')}`}
                  stroke="transparent"
                  tick={{ fill: '#a8a29e', fontSize: 11 }}
                  domain={['auto', 'auto']}
                  width={72}
                />
                <ReferenceLine y={combined.starting_capital} stroke="#78716c" strokeDasharray="4 4" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #292524', borderRadius: 8, fontSize: 12 }}
                  labelFormatter={(iso: string) => formatCT(iso)}
                  formatter={(value: number) => [formatMoney(value), 'Equity']}
                />
                <Area type="monotone" dataKey="equity" stroke={curveHex} strokeWidth={2} fill={curveFill} isAnimationActive={false} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="mt-3 pb-2 text-sm text-gray-500">Your equity curve appears once trades close.</p>
        )}
      </section>

      {/* Per-strategy contribution — only when more than one strategy */}
      {bots.length > 1 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {bots.map((b) => {
            const bp = b.total_pnl >= 0
            return (
              <section key={b.bot} className="flex items-center gap-4 rounded-xl border border-forge-border bg-forge-card/80 p-4">
                <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-forge-bg ring-1 ${b.accent === 'flame' ? 'ring-flame/25' : 'ring-spark/25'}`}>
                  <SparkMascot className="h-full w-full rounded-xl mix-blend-screen" variant={b.accent} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-white">{b.label}</span>
                    {b.paper && (
                      <span className="rounded bg-gray-700 px-1.5 py-px text-[9px] font-bold uppercase tracking-wider text-gray-300">Paper</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500">
                    {b.win_rate != null ? `${b.win_rate.toFixed(1)}% win rate` : '—'} · {b.trades} trades
                  </div>
                </div>
                <div className="text-right">
                  <div className={`font-mono text-lg font-bold ${bp ? 'text-emerald-400' : 'text-red-400'}`}>{formatDollarPnl(b.total_pnl)}</div>
                  <div className="text-xs text-gray-500">{formatMoney(b.account_value)}</div>
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}

function StatTile({ label, value, sub, valueClass }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-1.5 font-mono text-2xl font-bold ${valueClass ?? 'text-white'}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-gray-500">{sub}</div>}
    </div>
  )
}
