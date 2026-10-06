'use client'

import { useState } from 'react'
import { Area, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatDollarPnl } from '@/lib/format'
import type { PnlPoint } from '@/lib/live/trading-days'

/**
 * P&L chart with the 1D/1W/1M/All range toggle (dev-handoff §6 — gap-audit
 * "MISSING: P&L chart w/ 1D/1W/1M/All toggle"). Each range is a
 * cumulative-from-zero realized-P&L series (not an equity curve) built
 * server-side by `cumulativePnlSeries()` — the line always starts flat at
 * zero and turns green/red by whether the range ends up or down, per spec.
 */

const RANGES = [
  { key: '1D', label: '1D' },
  { key: '1W', label: '1W' },
  { key: '1M', label: '1M' },
  { key: 'ALL', label: 'All' },
] as const

export type RangeKey = (typeof RANGES)[number]['key']

function fmtTick(iso: string, range: RangeKey): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  if (range === '1D') {
    return d.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit' })
  }
  return d.toLocaleDateString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric' })
}

export default function PnlRangeChart({
  ranges,
  title,
  range: controlledRange,
  onRangeChange,
}: {
  ranges: { '1D': PnlPoint[]; '1W': PnlPoint[]; '1M': PnlPoint[]; ALL: PnlPoint[] }
  title?: string
  /** Controlled range (db-kpi #161 — a KPI tile elsewhere on the page can drive this
   *  chart too). Omit both props to keep the chart's own internal 1D/1W/1M/All state. */
  range?: RangeKey
  onRangeChange?: (r: RangeKey) => void
}) {
  const [internalRange, setInternalRange] = useState<RangeKey>('1W')
  const range = controlledRange ?? internalRange
  const setRange = onRangeChange ?? setInternalRange
  const series = ranges[range] ?? []
  const end = series.length ? series[series.length - 1].pnl : 0
  const up = end >= 0
  const stroke = up ? 'var(--up)' : 'var(--bad)'
  const fill = up ? 'rgba(47,207,147,0.16)' : 'rgba(255,107,90,0.16)'

  return (
    <section className="rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">
          {title ?? 'P&L'}
        </h3>
        <div className="flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--bg-2)] p-1">
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              onClick={() => setRange(r.key)}
              aria-pressed={range === r.key}
              className={
                range === r.key
                  ? 'rounded-md bg-[var(--bg)] px-2.5 py-1 text-xs font-semibold text-[var(--fg)]'
                  : 'rounded-md px-2.5 py-1 text-xs text-[var(--muted)] transition-colors hover:text-[var(--fg)]'
              }
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 flex items-baseline gap-2">
        <span className={`font-mono text-xl font-bold ${up ? 'text-[var(--up)]' : 'text-[var(--bad)]'}`}>
          {formatDollarPnl(end)}
        </span>
        <span className="text-xs text-[var(--muted)]">{range === 'ALL' ? 'all time' : `last ${range.toLowerCase()}`}</span>
      </div>

      {series.length >= 2 ? (
        <div className="mt-3 h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <XAxis dataKey="t" tickFormatter={(v: string) => fmtTick(v, range)} stroke="#44403c" tick={{ fill: '#a8a29e', fontSize: 11 }} minTickGap={56} />
              <YAxis
                orientation="right"
                tickFormatter={(v: number) => `$${Math.round(v).toLocaleString('en-US')}`}
                stroke="transparent"
                tick={{ fill: '#a8a29e', fontSize: 11 }}
                domain={['auto', 'auto']}
                width={72}
              />
              {/* db-charts #165: "Zero baseline is solid; other gridlines dashed." */}
              <ReferenceLine y={0} stroke="#78716c" />
              <Tooltip
                contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #292524', borderRadius: 8, fontSize: 12 }}
                labelFormatter={(iso: string) => fmtTick(iso, range)}
                formatter={(value: number) => [formatDollarPnl(value), 'P&L']}
              />
              <Area type="monotone" dataKey="pnl" stroke={stroke} strokeWidth={2} fill={fill} isAnimationActive={false} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-3 pb-2 text-sm text-[var(--muted)]">
          {range === '1D' ? 'No trade has closed in this range yet today.' : 'No closed trades in this range yet.'}
        </p>
      )}
    </section>
  )
}
