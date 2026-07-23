'use client'

import { useState } from 'react'
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
  // Per-strategy toggle: 'all' shows the blended account; a bot shows only its
  // own numbers AND its own curve. Shown only when the viewer owns >1 strategy.
  const [sel, setSel] = useState<'all' | LiveBot>('all')
  const active = sel !== 'all' ? bots.find((b) => b.bot === sel) : undefined

  const view = active
    ? {
        account_value: active.account_value,
        starting_capital: active.starting_capital,
        total_pnl: active.total_pnl,
        return_pct: active.return_pct,
        win_rate: active.win_rate,
        trades: active.trades,
        weekly: active.weekly,
        monthly: active.monthly,
        best_day: null as number | null,
        curve: active.curve,
        accent: active.accent as 'spark' | 'flame' | null,
        label: active.label,
      }
    : {
        account_value: combined.account_value,
        starting_capital: combined.starting_capital,
        total_pnl: combined.total_pnl,
        return_pct: combined.total_return_pct,
        win_rate: combined.win_rate,
        trades: combined.total_trades,
        weekly: combined.weekly,
        monthly: combined.monthly,
        best_day: combined.best_day,
        curve: equity_curve,
        accent: bots.length === 1 ? bots[0].accent : null,
        label: bots.map((b) => b.label).join(' + '),
      }

  const positive = view.total_pnl >= 0
  const curveHex = view.accent ? BOT_COLORS[view.accent] : '#f59e0b'
  const curveFill = view.accent === 'flame'
    ? 'rgba(255,85,0,0.18)'
    : view.accent === 'spark'
      ? 'rgba(59,130,246,0.18)'
      : 'rgba(245,158,11,0.16)'
  const wins = view.win_rate != null ? Math.round((view.win_rate / 100) * view.trades) : null
  const pctLabel = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`)

  return (
    <div className="mt-4 flex flex-col gap-4">
      {/* Per-strategy toggle */}
      {bots.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <TogglePill label="All strategies" active={sel === 'all'} onClick={() => setSel('all')} accent={null} />
          {bots.map((b) => (
            <TogglePill key={b.bot} label={b.label} active={sel === b.bot} onClick={() => setSel(b.bot)} accent={b.accent} paper={b.paper} />
          ))}
        </div>
      )}

      {/* Hero: mascot(s) + account value for the current view */}
      <section className="rounded-xl border border-forge-border bg-forge-card/80 p-5">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <div className="flex shrink-0 gap-3">
            {(active ? [active] : bots).map((b) => (
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
              {active || bots.length === 1 ? 'Account Value' : 'Total Account Value'}
            </div>
            <div className="mt-1 font-mono text-4xl font-bold text-white">{formatMoney(view.account_value)}</div>
            <div className="mt-1 text-sm text-gray-400">{view.label} · started {formatMoney(view.starting_capital)}</div>
            {view.return_pct != null && (
              <div
                className={`mt-3 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1 text-sm font-semibold ${
                  positive ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-400' : 'border-red-500/25 bg-red-500/10 text-red-400'
                }`}
              >
                {positive ? '▲' : '▼'} {pctLabel(view.return_pct)} all time
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Wealth KPIs — moved here from the Home dashboard */}
      <div className="grid grid-cols-3 gap-4">
        <StatTile label="This Week" value={formatDollarPnl(view.weekly)} valueClass={view.weekly >= 0 ? 'text-emerald-400' : 'text-red-400'} sub="Realized income" />
        <StatTile label="This Month" value={formatDollarPnl(view.monthly)} valueClass={view.monthly >= 0 ? 'text-emerald-400' : 'text-red-400'} sub="Realized income" />
        <StatTile label="Lifetime Return" value={pctLabel(view.return_pct)} valueClass={(view.return_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'} sub="All time" />
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Total P&L" value={formatDollarPnl(view.total_pnl)} valueClass={positive ? 'text-emerald-400' : 'text-red-400'} />
        <StatTile label="Win Rate" value={view.win_rate != null ? `${view.win_rate.toFixed(1)}%` : '—'} sub={wins != null ? `${wins} wins · ${view.trades - wins} losses` : undefined} />
        <StatTile label="Total Trades" value={String(view.trades)} />
        <StatTile
          label="Best Day"
          value={view.best_day != null ? formatDollarPnl(view.best_day) : '—'}
          valueClass={view.best_day != null && view.best_day >= 0 ? 'text-emerald-400' : undefined}
        />
      </div>

      {/* Equity curve — follows the selected strategy, refreshes every 60s (live) */}
      <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-amber-500">
          Equity Curve{active ? ` · ${active.label}` : ''}
        </h3>
        {view.curve.length >= 2 ? (
          <div className="mt-3 h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={view.curve} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                <XAxis dataKey="t" tickFormatter={formatCT} stroke="#44403c" tick={{ fill: '#a8a29e', fontSize: 11 }} minTickGap={56} />
                <YAxis
                  orientation="right"
                  tickFormatter={(v: number) => `$${Math.round(v).toLocaleString('en-US')}`}
                  stroke="transparent"
                  tick={{ fill: '#a8a29e', fontSize: 11 }}
                  domain={['auto', 'auto']}
                  width={72}
                />
                <ReferenceLine y={view.starting_capital} stroke="#78716c" strokeDasharray="4 4" />
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
    </div>
  )
}

function TogglePill({ label, active, onClick, accent, paper }: { label: string; active: boolean; onClick: () => void; accent: 'spark' | 'flame' | null; paper?: boolean }) {
  const activeClass = accent === 'flame'
    ? 'border-flame/40 bg-flame/15 text-flame'
    : accent === 'spark'
      ? 'border-spark/40 bg-spark/15 text-spark'
      : 'border-amber-500/40 bg-amber-500/15 text-amber-400'
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
        active ? activeClass : 'border-forge-border text-gray-400 hover:text-white'
      }`}
    >
      {label}
      {paper && <span className="rounded bg-gray-700 px-1 py-px text-[9px] font-bold uppercase tracking-wider text-gray-300">Paper</span>}
    </button>
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
