'use client'
import type { ReactNode } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'

export interface NetGexChartStrike {
  strike: number
  net_gamma: number
}

interface Props {
  title: string
  strikes: NetGexChartStrike[]
  price?: number | null
  flip?: number | null
  upper1sd?: number | null
  lower1sd?: number | null
  loading?: boolean
  emptyMessage?: string
  subtitle?: ReactNode
  /** Half-width of the strike window around price, as a fraction (e.g. 0.05 = ±5%). */
  windowPct?: number
}

function fmt(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return n.toFixed(1)
}

export default function NetGexChart({
  title, strikes, price, flip, upper1sd, lower1sd, loading, emptyMessage, subtitle,
  windowPct = 0.06,
}: Props) {
  const sorted = [...strikes].sort((a, b) => a.strike - b.strike)

  // Center the view on price (fallback: median strike) and window the strikes to a
  // FIXED band around it. This keeps the y-axis domain stable across 30s refreshes
  // (no more auto-rescaling to dataMin/dataMax) and drops the long empty tails that
  // made the chart look like it was expanding/collapsing.
  const center = price && price > 0 ? price : (sorted.length ? sorted[Math.floor(sorted.length / 2)].strike : 0)
  const lo = center > 0 ? center * (1 - windowPct) : undefined
  const hi = center > 0 ? center * (1 + windowPct) : undefined
  const data = lo != null && hi != null
    ? sorted.filter((s) => s.strike >= lo && s.strike <= hi)
    : sorted
  const yDomain: [number | string, number | string] = lo != null && hi != null
    ? [Math.floor(lo), Math.ceil(hi)]
    : ['dataMin', 'dataMax']

  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-1">{title}</h3>
      {subtitle && <div className="mb-2">{subtitle}</div>}
      {loading ? (
        <div className="h-[480px] flex items-center justify-center text-gray-500 text-sm">Loading…</div>
      ) : data.length === 0 ? (
        <div className="h-[480px] flex items-center justify-center text-amber-300 text-sm text-center px-6">
          {emptyMessage || 'No data (market may be closed).'}
        </div>
      ) : (
        <div className="h-[480px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart layout="vertical" data={data} margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
              <XAxis
                type="number"
                tick={{ fill: '#9ca3af', fontSize: 10 }}
                tickFormatter={(v) => fmt(v as number)}
              />
              <YAxis
                type="number"
                dataKey="strike"
                domain={yDomain}
                reversed
                allowDataOverflow
                tick={{ fill: '#9ca3af', fontSize: 10 }}
                width={48}
              />
              <Tooltip
                contentStyle={{ background: '#0b0b0f', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [fmt(v), 'Net Gamma']}
                labelFormatter={(l) => `Strike ${l}`}
              />
              <ReferenceLine x={0} stroke="#4b5563" />
              {price != null && (
                <ReferenceLine y={price} stroke="#3b82f6" strokeWidth={1.5}
                  label={{ value: 'Price', fill: '#3b82f6', fontSize: 10, position: 'right' }} />
              )}
              {flip != null && (
                <ReferenceLine y={flip} stroke="#eab308" strokeDasharray="4 3"
                  label={{ value: 'Flip', fill: '#eab308', fontSize: 10, position: 'right' }} />
              )}
              {upper1sd != null && (
                <ReferenceLine y={upper1sd} stroke="#f59e0b" strokeDasharray="2 4"
                  label={{ value: '+1σ', fill: '#f59e0b', fontSize: 10, position: 'right' }} />
              )}
              {lower1sd != null && (
                <ReferenceLine y={lower1sd} stroke="#f59e0b" strokeDasharray="2 4"
                  label={{ value: '−1σ', fill: '#f59e0b', fontSize: 10, position: 'right' }} />
              )}
              <Bar dataKey="net_gamma" barSize={6} isAnimationActive={false}>
                {data.map((d, i) => (
                  <Cell key={i} fill={d.net_gamma >= 0 ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
