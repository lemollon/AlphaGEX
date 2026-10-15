'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { Area, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { LiveSummary } from '@/lib/live/types'
import type { LiveBot } from '@/lib/live/bots'
import type { AccentTheme } from './accent'
import { formatDollarPnl } from '@/lib/format'
import { fetcher } from '@/lib/fetcher'

type Period = 'today' | 'week' | 'month' | 'year' | 'all'

const PERIOD_LABEL: Record<Period, string> = {
  today: 'Today',
  week: 'Week',
  month: 'Month',
  year: 'Year',
  all: 'All',
}

const PERIOD_RESULT_LABEL: Record<Period, string> = {
  today: "Today's Result",
  week: "This Week's Result",
  month: "This Month's Result",
  year: "This Year's Result",
  all: 'All-Time Result',
}

interface EquityCurveResp {
  empty?: boolean
  points: Array<{ timestamp: string | null; equity: number }>
  period_pnl: number | null
  period_pnl_pct: number | null
}

type SeriesPoint = { timestamp: string; equity: number; delta: number }

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit',
  })
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-US', {
    timeZone: 'America/Chicago', month: 'short', day: 'numeric',
  })
}

function signedDollars(v: number): string {
  const r = Math.round(v)
  return r > 0 ? `+$${r}` : r < 0 ? `-$${Math.abs(r)}` : '$0'
}

/**
 * Builds the delta-from-open series the chart draws, from raw
 * `{ timestamp, equity }` points anchored at the FIRST point's equity. A
 * single point is padded with a synthetic one a minute earlier at the same
 * value — recharts needs two points to draw a line, and a lone dot reads as
 * broken (common-mistakes.md #16).
 */
function buildSeries(raw: Array<{ timestamp: string | null; equity: number }>): SeriesPoint[] {
  const points = raw.filter((p): p is { timestamp: string; equity: number } => !!p.timestamp)
  if (points.length === 0) return []
  const openEquity = points[0].equity
  const series = points.map((p) => ({
    timestamp: p.timestamp,
    equity: p.equity,
    delta: Math.round((p.equity - openEquity) * 100) / 100,
  }))
  if (series.length === 1) {
    const only = series[0]
    const padded = new Date(new Date(only.timestamp).getTime() - 60_000).toISOString()
    return [{ ...only, timestamp: padded }, only]
  }
  return series
}

export default function TodayPerformanceChart({
  bot,
  account,
  intraday,
  intradayPreviousDay,
  marketOpen,
  accent,
}: {
  bot: LiveBot
  account: LiveSummary['account'] | null
  intraday: LiveSummary['intraday'] | null
  intradayPreviousDay?: LiveSummary['intraday_previous_day']
  marketOpen: boolean
  accent: AccentTheme
}) {
  const [period, setPeriod] = useState<Period>('today')

  // --- Today: 5-min `equity_snapshots`, unchanged behavior, plus the
  // "never go blank" fallback to yesterday's full closing curve. ----------
  const rawToday = intraday ?? []
  const todayHasLine = rawToday.length >= 2
  const fallback = intradayPreviousDay ?? []
  const usingYesterday = period === 'today' && !todayHasLine && fallback.length > 0
  const todaySeries = todayHasLine ? rawToday : usingYesterday ? fallback : rawToday
  const todayChartSeries = buildSeries(todaySeries)

  // --- Week / Month / Year / All-time: day-granularity, fetched from the
  // customer-scoped equity-curve route (reuses the operator dashboard's own
  // query shape — see that route's comment). -----------------------------
  const curveKey = period !== 'today' ? `/api/live/equity-curve?account=${bot}&period=${period}` : null
  const { data: curveData } = useSWR<EquityCurveResp>(curveKey, fetcher, { refreshInterval: 60_000 })
  const periodChartSeries = period !== 'today' ? buildSeries(curveData?.points ?? []) : []

  const series = period === 'today' ? todayChartSeries : periodChartSeries
  // Chart is a text placeholder only when NO history exists anywhere for the
  // current selection: Today's own data, yesterday's fallback, AND (for the
  // longer views) the fetched period series all came back empty.
  const showChart = series.length >= 1
  const stillLoading = period !== 'today' && curveData === undefined

  const todayPositive = (account?.today_pnl ?? 0) >= 0
  const periodPnl = period === 'today' ? account?.today_pnl ?? null : curveData?.period_pnl ?? null
  const periodPnlPct = period === 'today' ? account?.today_pnl_pct ?? null : curveData?.period_pnl_pct ?? null
  const periodPositive = (periodPnl ?? 0) >= 0
  const tickFormatter = period === 'today' ? formatTime : formatDate

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className={`text-xs font-semibold uppercase tracking-widest ${accent.text}`}>
          {period === 'today' && usingYesterday ? "Yesterday's Performance" : "Today's Performance"}
        </h3>
        <div className="flex items-center gap-1 rounded-lg border border-forge-border bg-forge-bg/60 p-1">
          {(['today', 'week', 'month', 'year', 'all'] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              aria-pressed={period === p}
              className={
                period === p
                  ? `rounded-md px-2.5 py-1 text-xs font-semibold text-white ${accent.button}`
                  : 'rounded-md px-2.5 py-1 text-xs text-gray-400 transition-colors hover:text-white'
              }
            >
              {PERIOD_LABEL[p]}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="flex shrink-0 flex-wrap gap-x-10 gap-y-3 lg:w-[320px] lg:flex-col lg:gap-y-4">
          <div>
            <div className="text-xs text-gray-500">Account Value</div>
            <div className="mt-1 font-mono text-3xl font-semibold text-white">
              {account?.value != null
                ? `$${account.value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '—'}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">{PERIOD_RESULT_LABEL[period]}</div>
            <div className={`mt-1 font-mono text-2xl font-semibold ${periodPnl == null ? 'text-gray-400' : periodPositive ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatDollarPnl(periodPnl)}
              {periodPnlPct != null && (
                <span className="ml-2 text-base font-normal">
                  ({periodPnlPct > 0 ? '+' : ''}{periodPnlPct.toFixed(2)}%)
                </span>
              )}
            </div>
          </div>
        </div>

        {showChart ? (
          <div className="h-[220px] min-w-0 flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={series} margin={{ top: 8, right: 4, bottom: 0, left: 8 }}>
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={tickFormatter}
                  stroke="#44403c"
                  tick={{ fill: '#a8a29e', fontSize: 11 }}
                  minTickGap={48}
                />
                <YAxis
                  orientation="right"
                  tickFormatter={signedDollars}
                  stroke="transparent"
                  tick={{ fill: '#a8a29e', fontSize: 11 }}
                  domain={['auto', 'auto']}
                  width={56}
                />
                <ReferenceLine y={0} stroke="#78716c" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1c1917',
                    border: '1px solid #292524',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelFormatter={(iso: string) =>
                    period === 'today' ? `${formatTime(iso)} CT` : formatDate(iso)
                  }
                  formatter={(value: number, _name: string, entry: { payload?: { equity?: number } }) => [
                    `${signedDollars(value)} (value $${Number(entry?.payload?.equity ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`,
                    PERIOD_LABEL[period],
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="delta"
                  stroke={accent.chartHex}
                  strokeWidth={2}
                  fill={accent.chartFill}
                  isAnimationActive={false}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="flex-1 pb-2 text-sm text-gray-500">
            {stillLoading
              ? 'Loading…'
              : period !== 'today'
                ? `No trading history yet for this ${PERIOD_LABEL[period].toLowerCase()}.`
                : marketOpen
                  ? "Today's chart appears once Spark records its first check-in of the session."
                  : "Markets are closed — today's chart appears at the next market open (8:30 AM CT)."}
          </p>
        )}
      </div>
    </section>
  )
}
