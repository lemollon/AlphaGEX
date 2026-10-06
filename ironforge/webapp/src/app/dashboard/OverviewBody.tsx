'use client'

import { useState } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { Area, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fetcher } from '@/lib/fetcher'
import { formatDollarPnl } from '@/lib/format'
import { BOT_COLORS } from '@/lib/botColors'
import type { LiveBot } from '@/lib/live/bots'
import type { LiveSummary } from '@/lib/live/types'
import type { PerformanceData } from '@/lib/live/performance'
import { BOT_PLANS } from '@/lib/billing/plans'
import PnlRangeChart, { type RangeKey as PnlRangeKey } from '@/components/customer/PnlRangeChart'
import DailyResultsBars from '@/components/customer/DailyResultsBars'
import AgentLeadTile from '@/components/customer/AgentLeadTile'
import SparkMascot from '../live/components/SparkMascot'
import { OpenTradesSection, RecentTradesSection } from './OverviewTradeWidgets'

type PerfResponse =
  | ({ empty?: false; viewer: { allowedBots: LiveBot[]; paperBots: LiveBot[] } } & PerformanceData)
  | { empty: true; viewer: { allowedBots: LiveBot[]; paperBots: LiveBot[] } }

function formatMoney(v: number | null | undefined): string {
  if (v == null) return '—'
  return `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** Time-of-day greeting in Central time — no name field exists on the summary
 *  payload to personalize with, so this stays generic rather than fabricate one. */
function greeting(): string {
  const ctHour = Number(
    new Date().toLocaleString('en-US', { timeZone: 'America/Chicago', hour: 'numeric', hour12: false }),
  )
  if (ctHour < 12) return 'Good morning'
  if (ctHour < 17) return 'Good afternoon'
  return 'Good evening'
}

/**
 * Overview tab (dev-handoff §6): greeting/market status → KPI row → P&L
 * chart → Daily results → your agents. This is the enhanced successor to
 * /performance's body — same `/api/live/performance` payload, now carrying
 * the trading-day-correct KPIs, chart ranges, daily bars and lead tiles the
 * gap audit flagged MISSING. `/performance` redirects here.
 */
export default function OverviewBody() {
  const { data, error } = useSWR<PerfResponse>('/api/live/performance', fetcher, { refreshInterval: 60_000 })
  // Separate, already-used-elsewhere endpoint — just for the market status pill
  // (db-ia #144: "Greeting + market status"). Cached/shared with other dashboard
  // tabs that fetch the same key, so this adds no extra network cost in practice.
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher, { refreshInterval: 60_000 })

  const allowedBots = (data?.viewer?.allowedBots ?? []) as LiveBot[]

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-[var(--fg)]">{greeting()}</h1>
        {summary?.market?.label && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
              summary.market.open ? 'bg-emerald-500/15 text-emerald-400' : 'bg-forge-border/60 text-forge-muted'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${summary.market.open ? 'bg-emerald-400' : 'bg-forge-muted'}`} />
            {summary.market.label}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-[var(--muted)]">Your all-time results across every strategy you own.</p>

      {data && 'empty' in data && data.empty ? (
        <ActivateCard />
      ) : error && !data ? (
        <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-6 text-sm text-[var(--muted)]">
          Performance data is temporarily unavailable — try refreshing in a moment.
        </div>
      ) : !data ? (
        <div className="mt-4 h-40 animate-pulse rounded-xl border border-[var(--line)] bg-[var(--bg)]/50" />
      ) : (
        <OverviewContent data={data as PerformanceData} allowedBots={allowedBots} />
      )}
    </>
  )
}

function ActivateCard() {
  const strategies = [
    { ...BOT_PLANS.spark, accent: '#3B82F6' },
    { ...BOT_PLANS.flame, accent: '#EE5A24' },
  ]
  return (
    <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-6 sm:p-8">
      <h2 className="text-lg font-bold text-[var(--fg)]">Let's get your first strategy trading</h2>
      <p className="mt-1 max-w-xl text-sm leading-relaxed text-[var(--muted)]">
        Your results show up here once a strategy is live. Two quick steps:
      </p>

      <div className="mt-5 grid gap-3">
        <div className="flex items-start gap-3 rounded-lg border border-[var(--line)] bg-[var(--bg)]/50 p-4">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/15 text-xs font-bold text-[var(--accent-text)]">1</span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-[var(--fg)]">Connect a brokerage</div>
            <p className="mt-0.5 text-xs text-[var(--muted)]">Link the account your strategy will trade through. Takes a minute.</p>
          </div>
          <Link href="/onboarding/brokerage" className="shrink-0 self-center rounded-lg border border-[var(--line)] px-3 py-2 text-xs font-semibold text-[var(--fg)] transition hover:bg-[var(--bg-2)]">Connect</Link>
        </div>

        <div className="rounded-lg border border-[var(--line)] bg-[var(--bg)]/50 p-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/15 text-xs font-bold text-[var(--accent-text)]">2</span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-[var(--fg)]">Open a strategy account</div>
              <p className="mt-0.5 text-xs text-[var(--muted)]">Starts a 5-day free trial — no charge today, cancel anytime.</p>
            </div>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {strategies.map((s) => (
              <Link key={s.slug} href={`/live/${s.slug}/open`}
                className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line)] bg-[var(--bg-2)] px-3 py-2.5 transition hover:border-[var(--line-2)]"
                style={{ borderLeft: `3px solid ${s.accent}` }}>
                <span className="text-sm font-semibold text-[var(--fg)]">Open {s.name}</span>
                <span className="text-xs font-medium" style={{ color: s.accent }}>${s.priceMonthly}/mo</span>
              </Link>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-[var(--muted)]">A second strategy is its own ${BOT_PLANS.flame.priceMonthly}/mo subscription, billed separately.</p>
        </div>
      </div>
    </div>
  )
}

function OverviewContent({ data, allowedBots }: { data: PerformanceData; allowedBots: LiveBot[] }) {
  const { bots, combined, equity_curve } = data
  const [sel, setSel] = useState<'all' | LiveBot>('all')
  const active = sel !== 'all' ? bots.find((b) => b.bot === sel) : undefined
  // db-kpi #161: "Clicking a period tile also switches the chart." Lifted up here
  // (rather than kept as PnlRangeChart's own internal state) so the KPI tiles above
  // the chart can drive it too, not just its own 1D/1W/1M/All buttons.
  const [chartRange, setChartRange] = useState<PnlRangeKey>('1W')

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
        capital_available: active.capital_available,
        held_for_open_trades: active.held_for_open_trades,
        today_pnl: active.today_pnl,
        curve: active.curve,
        daily_bars: active.daily_bars,
        pnl_ranges: active.pnl_ranges,
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
        capital_available: combined.capital_available,
        held_for_open_trades: combined.held_for_open_trades,
        today_pnl: combined.today_pnl,
        curve: equity_curve,
        daily_bars: data.daily_bars,
        pnl_ranges: data.pnl_ranges,
        accent: bots.length === 1 ? bots[0].accent : null,
        label: bots.map((b) => b.label).join(' + '),
      }

  const positive = view.total_pnl >= 0
  const curveHex = view.accent ? BOT_COLORS[view.accent] : '#f59e0b'
  const wins = view.win_rate != null ? Math.round((view.win_rate / 100) * view.trades) : null
  const pctLabel = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`)

  return (
    <div className="mt-4 flex flex-col gap-4">
      {bots.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <TogglePill label="All strategies" active={sel === 'all'} onClick={() => setSel('all')} accent={null} />
          {bots.map((b) => (
            <TogglePill key={b.bot} label={b.label} active={sel === b.bot} onClick={() => setSel(b.bot)} accent={b.accent} paper={b.paper} />
          ))}
        </div>
      )}

      <section className="rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-5">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <div className="flex shrink-0 gap-3">
            {(active ? [active] : bots).map((b) => (
              <div key={b.bot}
                className={`flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--bg)] ring-1 sm:h-20 sm:w-20 ${
                  b.accent === 'flame' ? 'ring-flame/25' : 'ring-spark/25'
                }`}>
                <SparkMascot className="h-full w-full rounded-2xl mix-blend-screen" variant={b.accent} />
              </div>
            ))}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-widest text-[var(--muted)]">
              {active || bots.length === 1 ? 'Account Value' : 'Total Account Value'}
            </div>
            <div className="mt-1 font-mono text-4xl font-bold text-[var(--fg)]">{formatMoney(view.account_value)}</div>
            <div className="mt-1 text-sm text-[var(--muted)]">{view.label} · started {formatMoney(view.starting_capital)}</div>
            {view.return_pct != null && (
              <div className={`mt-3 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1 text-sm font-semibold ${
                positive ? 'border-[var(--up)]/25 bg-[var(--up)]/10 text-[var(--up)]' : 'border-[var(--bad)]/25 bg-[var(--bad)]/10 text-[var(--bad)]'
              }`}>
                {positive ? '▲' : '▼'} {pctLabel(view.return_pct)} all time
              </div>
            )}
          </div>
        </div>
      </section>

      {/* db-dash #148/#150: open-trade card + recent-trades list, right on
          Overview — previously only visible after drilling into an agent page. */}
      <OpenTradesSection bots={active ? [active.bot] : bots.map((b) => b.bot)} />
      <RecentTradesSection />

      {/* KPI row — dev-handoff §6 contract: Today / Past week (5 trading days) /
          Past month (21 trading days) / Lifetime. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="Today"
          value={view.today_pnl != null ? formatDollarPnl(view.today_pnl) : '—'}
          valueClass={view.today_pnl != null ? (view.today_pnl >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]') : undefined}
          sub="Realized + unrealized on open trades"
          onClick={() => setChartRange('1D')}
          active={chartRange === '1D'}
        />
        <StatTile label="Past Week" value={formatDollarPnl(view.weekly)} valueClass={view.weekly >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]'} sub="Last 5 trading days" onClick={() => setChartRange('1W')} active={chartRange === '1W'} />
        <StatTile label="Past Month" value={formatDollarPnl(view.monthly)} valueClass={view.monthly >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]'} sub="Last 21 trading days" onClick={() => setChartRange('1M')} active={chartRange === '1M'} />
        <StatTile label="Lifetime P&L" value={formatDollarPnl(view.total_pnl)} valueClass={positive ? 'text-[var(--up)]' : 'text-[var(--bad)]'} onClick={() => setChartRange('ALL')} active={chartRange === 'ALL'} />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="Capital available"
          value={view.capital_available != null ? formatMoney(view.capital_available) : '—'}
          sub={view.held_for_open_trades != null ? `${formatMoney(view.held_for_open_trades)} held for open trades` : undefined}
        />
        <StatTile label="Lifetime Return" value={pctLabel(view.return_pct)} valueClass={(view.return_pct ?? 0) >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]'} sub="All time" />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Win Rate" value={view.win_rate != null ? `${view.win_rate.toFixed(1)}%` : '—'} sub={wins != null ? `${wins} wins · ${view.trades - wins} losses` : undefined} />
        <StatTile label="Total Trades" value={String(view.trades)} />
        <StatTile
          label="Best Day"
          value={view.best_day != null ? formatDollarPnl(view.best_day) : '—'}
          valueClass={view.best_day != null && view.best_day >= 0 ? 'text-[var(--up)]' : undefined}
        />
      </div>

      {/* Per-agent lead tiles — only meaningful per strategy, so render them
          whenever we have per-bot data (combined view shows all owned). */}
      {!active && bots.length > 0 && (
        <div className={`grid gap-4 ${bots.length > 1 ? 'sm:grid-cols-2' : ''}`}>
          {bots.map((b) => (
            <AgentLeadTile key={b.bot} label={b.label} lead={b.lead}
              accentClass={b.accent === 'flame' ? 'text-flame' : 'text-spark'} />
          ))}
        </div>
      )}
      {active && <AgentLeadTile label={active.label} lead={active.lead} accentClass={active.accent === 'flame' ? 'text-flame' : 'text-spark'} />}

      <PnlRangeChart
        ranges={view.pnl_ranges}
        title={active ? `P&L · ${active.label}` : 'P&L'}
        range={chartRange}
        onRangeChange={setChartRange}
      />
      <DailyResultsBars bars={view.daily_bars} />

      {/* Equity curve — the account's actual balance history, distinct from the
          cumulative-from-zero P&L chart above. */}
      {view.curve.length >= 2 && (
        <section className="rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--accent-text)]">
            Equity Curve{active ? ` · ${active.label}` : ''}
          </h3>
          <EquityCurveMini curve={view.curve} hex={curveHex} baseline={view.starting_capital} />
        </section>
      )}

      {/* Your agents — owned + add-agent cards. Owned cards show Today/Month/
          Lifetime $ (gap audit PARTIAL — previously name + badge only, full
          detail lived only on the agent's own page). */}
      <section className="rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--accent-text)]">Your Agents</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {(['spark', 'flame'] as LiveBot[]).map((b) => {
            const owned = allowedBots.includes(b)
            const plan = BOT_PLANS[b]
            const perf = bots.find((x) => x.bot === b)
            return (
              <Link key={b} href={owned ? `/dashboard?tab=${b}` : `/live/${b}/open`}
                className={`flex flex-col gap-2 rounded-lg border px-3 py-2.5 transition hover:border-[var(--line-2)] ${
                  owned ? 'border-[var(--line)] bg-[var(--bg-2)]' : 'border-dashed border-[var(--line-2)]'
                }`}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-[var(--fg)]">{owned ? plan.name : `+ Add ${plan.name}`}</span>
                  <span className={`rounded px-1.5 py-px text-[9px] font-bold uppercase tracking-wider ${
                    owned ? (b === 'flame' ? 'bg-flame/15 text-flame' : 'bg-spark/15 text-spark') : 'bg-[var(--bg)] text-[var(--muted)]'
                  }`}>
                    {owned ? 'Active' : `$${plan.priceMonthly}/mo`}
                  </span>
                </div>
                {owned && perf && (
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Today</div>
                      <div className={`font-mono font-semibold ${perf.today_pnl == null ? 'text-[var(--muted)]' : perf.today_pnl >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]'}`}>
                        {formatDollarPnl(perf.today_pnl)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Month</div>
                      <div className={`font-mono font-semibold ${perf.monthly >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]'}`}>
                        {formatDollarPnl(perf.monthly)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Lifetime</div>
                      <div className={`font-mono font-semibold ${perf.total_pnl >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]'}`}>
                        {formatDollarPnl(perf.total_pnl)}
                      </div>
                    </div>
                  </div>
                )}
              </Link>
            )
          })}
        </div>
      </section>
    </div>
  )
}

/** Lightweight equity curve — same visual as the old /performance chart. */
function EquityCurveMini({ curve, hex, baseline }: { curve: PerformanceData['equity_curve']; hex: string; baseline: number }) {
  const fmtMoney = (v: number) => `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const fmtDate = (iso: string) => {
    const d = new Date(iso)
    return isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric' })
  }
  const currentEquity = curve.length ? curve[curve.length - 1].equity : baseline
  return (
    <div className="mt-3 h-[220px]" role="img" aria-label={`Equity curve chart, currently ${fmtMoney(currentEquity)}`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={curve} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <XAxis dataKey="t" tickFormatter={fmtDate} stroke="#44403c" tick={{ fill: '#a8a29e', fontSize: 11 }} minTickGap={56} />
          <YAxis orientation="right" tickFormatter={(v: number) => `$${Math.round(v).toLocaleString('en-US')}`} stroke="transparent" tick={{ fill: '#a8a29e', fontSize: 11 }} domain={['auto', 'auto']} width={72} />
          <ReferenceLine y={baseline} stroke="#78716c" strokeDasharray="4 4" />
          <Tooltip contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #292524', borderRadius: 8, fontSize: 12 }} labelFormatter={fmtDate} formatter={(value: number) => [fmtMoney(value), 'Equity']} />
          <Area type="monotone" dataKey="equity" stroke={hex} strokeWidth={2} fill={`${hex}2e`} isAnimationActive={false} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function TogglePill({ label, active, onClick, accent, paper }: { label: string; active: boolean; onClick: () => void; accent: 'spark' | 'flame' | null; paper?: boolean }) {
  const activeClass = accent === 'flame'
    ? 'border-flame/40 bg-flame/15 text-flame'
    : accent === 'spark'
      ? 'border-spark/40 bg-spark/15 text-spark'
      : 'border-[var(--accent)]/40 bg-[var(--accent)]/15 text-[var(--accent-text)]'
  return (
    <button type="button" onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
        active ? activeClass : 'border-[var(--line)] text-[var(--muted)] hover:text-[var(--fg)]'
      }`}>
      {label}
      {paper && <span className="rounded bg-[var(--bg-2)] px-1 py-px text-[9px] font-bold uppercase tracking-wider text-[var(--muted)]">Paper</span>}
    </button>
  )
}

function StatTile({ label, value, sub, valueClass, onClick, active }: {
  label: string
  value: string
  sub?: string
  valueClass?: string
  /** db-kpi #161: when present, the tile is clickable and drives the P&L chart's range. */
  onClick?: () => void
  active?: boolean
}) {
  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
      aria-pressed={onClick ? active : undefined}
      className={`rounded-xl border bg-[var(--bg)]/80 p-4 text-left ${
        onClick ? 'cursor-pointer transition-colors hover:border-[var(--line-2)]' : ''
      } ${active ? 'border-[var(--accent)]' : 'border-[var(--line)]'}`}
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className={`mt-1.5 font-mono text-2xl font-bold ${valueClass ?? 'text-[var(--fg)]'}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-[var(--muted)]">{sub}</div>}
    </div>
  )
}
