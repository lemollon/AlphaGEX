'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { Area, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fetcher } from '@/lib/fetcher'
import { EMBER_AGENT } from '@/lib/agents/ember'

type Period = 'day' | 'week' | 'month' | 'year' | 'all'

const PERIOD_LABEL: Record<Period, string> = { day: 'Day', week: 'Week', month: 'Month', year: 'Year', all: 'All' }
const PERIOD_RESULT_LABEL: Record<Period, string> = {
  day: "Today's Result",
  week: "This Week's Result",
  month: "This Month's Result",
  year: "This Year's Result",
  all: 'All-Time Result',
}

interface EquityCurvePoint {
  timestamp: string
  cumulative_pnl: number
}
interface EquityCurveResp {
  ok: boolean
  points: EquityCurvePoint[]
  period_pnl: number | null
}

type SeriesPoint = { timestamp: string; delta: number }

function formatDay(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric' })
}
function formatDayTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
function signedDollars(v: number): string {
  const r = Math.round(v)
  return r > 0 ? `+$${r}` : r < 0 ? `-$${Math.abs(r)}` : '$0'
}
function signedDollarsFull(v: number): string {
  const a = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? `+$${a}` : v < 0 ? `-$${a}` : '$0.00'
}

/** Rebases the curve onto its own first point, same "delta from start" shape
 *  as ironforge/webapp's TodayPerformanceChart.tsx — a lone point is padded
 *  a minute earlier at the same value so recharts always has a line, never a
 *  single dot (common-mistakes.md #16). */
function buildSeries(raw: EquityCurvePoint[]): SeriesPoint[] {
  if (raw.length === 0) return []
  const base = raw[0].cumulative_pnl
  const series = raw.map((p) => ({ timestamp: p.timestamp, delta: Math.round((p.cumulative_pnl - base) * 100) / 100 }))
  if (series.length === 1) {
    const only = series[0]
    const padded = new Date(new Date(only.timestamp).getTime() - 60_000).toISOString()
    return [{ ...only, timestamp: padded }, only]
  }
  return series
}

/**
 * Ember's persistent performance chart.
 *
 * This is a PARALLEL component to Spark/Flame's TodayPerformanceChart.tsx,
 * not a reuse of it — Ember's real data shape is fundamentally different and
 * reusing that component would fabricate fields it doesn't have:
 *   - No `ember_equity_snapshots` table, no `starting_capital`, no live
 *     Tradier/broker balance read. REFLEX, CINDER, and TALON (Ember's three
 *     execution sleeves, BUILD_SPEC_SHARED_SLEEVE.md Part 3) each sync their
 *     own trade log into the SAME ember_trades book, tagged by `strategy`
 *     (see /api/ember/equity-curve's own comment for the full trail).
 *   - This component never passes `strategy` to the API, so it always draws
 *     the COMBINED curve across all three sleeves — that's the default this
 *     task shipped, not a per-sleeve chart; the API supports per-strategy
 *     filtering for a future rebuild if one is ever needed.
 *   - So this charts CUMULATIVE REALIZED P&L from Ember's own closed trades
 *     — the only honest $ figure that exists — never an "Account Value",
 *     which would imply a balance this pipeline doesn't track.
 *   - "Day" always exists as a toggle option (Leron, 2026-10-15, binding)
 *     even though REFLEX's own trade timestamps are date-precision only: it
 *     anchors on the running total right before today's first closed trade,
 *     then steps through today's trades — the finest real resolution, not a
 *     fabricated intraday bucket.
 */
export default function EmberPerformanceChart() {
  const [period, setPeriod] = useState<Period>('day')

  const { data: allData } = useSWR<EquityCurveResp>('/api/ember/equity-curve?period=all', fetcher, {
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  })
  const periodKey = period !== 'all' ? `/api/ember/equity-curve?period=${period}` : null
  const { data: periodData } = useSWR<EquityCurveResp>(periodKey, fetcher, {
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  })

  const curveData = period === 'all' ? allData : periodData
  const series = buildSeries(curveData?.points ?? [])
  const showChart = series.length >= 1
  const stillLoading = curveData === undefined

  const totalPnl = allData?.points.length ? allData.points[allData.points.length - 1].cumulative_pnl : 0
  const totalPositive = totalPnl >= 0
  const periodPnl = curveData?.period_pnl ?? null
  const periodPositive = (periodPnl ?? 0) >= 0
  const tickFormatter = period === 'day' ? formatDayTime : formatDay

  return (
    <section className="rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: EMBER_AGENT.accent }}>
          Performance
        </h3>
        <div className="flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--bg-2)] p-1">
          {(['day', 'week', 'month', 'year', 'all'] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              aria-pressed={period === p}
              className={
                period === p
                  ? 'rounded-md px-2.5 py-1 text-xs font-semibold text-[var(--fg)]'
                  : 'rounded-md px-2.5 py-1 text-xs text-[var(--muted)] transition-colors hover:text-[var(--fg)]'
              }
              style={period === p ? { backgroundColor: EMBER_AGENT.accent } : undefined}
            >
              {PERIOD_LABEL[p]}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="flex shrink-0 flex-wrap gap-x-10 gap-y-3 lg:w-[260px] lg:flex-col lg:gap-y-4">
          <div>
            <div className="text-xs text-[var(--muted)]">Total P&amp;L (realized)</div>
            <div className={`mt-1 font-mono text-2xl font-semibold ${totalPositive ? 'text-[var(--up)]' : 'text-[var(--bad)]'}`}>
              {signedDollarsFull(totalPnl)}
            </div>
          </div>
          <div>
            <div className="text-xs text-[var(--muted)]">{PERIOD_RESULT_LABEL[period]}</div>
            <div className={`mt-1 font-mono text-xl font-semibold ${periodPnl == null ? 'text-[var(--muted)]' : periodPositive ? 'text-[var(--up)]' : 'text-[var(--bad)]'}`}>
              {periodPnl != null ? signedDollarsFull(periodPnl) : '—'}
            </div>
          </div>
        </div>

        {showChart ? (
          <div className="h-[200px] min-w-0 flex-1">
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
                  contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #292524', borderRadius: 8, fontSize: 12 }}
                  labelFormatter={(iso: string) => (period === 'day' ? formatDayTime(iso) : formatDay(iso))}
                  formatter={(value: number) => [signedDollars(value), 'Change']}
                />
                <Area
                  type="monotone"
                  dataKey="delta"
                  stroke={EMBER_AGENT.accent}
                  strokeWidth={2}
                  fill={`${EMBER_AGENT.accent}33`}
                  isAnimationActive={false}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="flex-1 pb-2 text-sm text-[var(--muted)]">
            {stillLoading ? 'Loading…' : `No closed trades yet for this ${PERIOD_LABEL[period].toLowerCase()}.`}
          </p>
        )}
      </div>
    </section>
  )
}
