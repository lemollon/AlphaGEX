'use client'

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ComposedChart,
} from 'recharts'

interface CurvePoint {
  timestamp: string
  pnl: number
  cumulative_pnl: number
  equity: number
}

export default function EquityChart({
  data,
  startingCapital,
  color = '#3b82f6',
  title,
}: {
  data: CurvePoint[]
  startingCapital: number
  color?: string
  title?: string
}) {
  if (!data.length) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-8 text-center">
        <p className="text-gray-500">No closed trades yet</p>
      </div>
    )
  }

  // Prepend starting point
  const chartData = [
    { timestamp: data[0].timestamp, equity: startingCapital, pnl: 0 },
    ...data,
  ]

  const lastEquity = data[data.length - 1].equity
  const fillColor =
    lastEquity >= startingCapital
      ? 'rgba(16, 185, 129, 0.15)'
      : 'rgba(239, 68, 68, 0.15)'

  const formatDate = (ts: string) => {
    if (!ts) return ''
    const d = new Date(ts)
    return `${d.getMonth() + 1}/${d.getDate()}`
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4">
      {title && <h3 className="text-sm font-medium text-gray-400 mb-3">{title}</h3>}
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartData}>
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatDate}
            stroke="#475569"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(v) => `$${v.toLocaleString()}`}
            stroke="#475569"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
            labelFormatter={(label) => {
              if (!label) return ''
              return new Date(label).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
              })
            }}
          />
          <ReferenceLine
            y={startingCapital}
            stroke="#6b7280"
            strokeDasharray="4 4"
            label={{
              value: `Start: $${startingCapital.toLocaleString()}`,
              position: 'insideTopLeft',
              fill: '#6b7280',
              fontSize: 11,
            }}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke={color}
            strokeWidth={2}
            fill={fillColor}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Overlay two equity curves for comparison. */
export function ComparisonChart({
  flameData,
  sparkData,
  startingCapital,
}: {
  flameData: CurvePoint[]
  sparkData: CurvePoint[]
  startingCapital: number
}) {
  if (!flameData.length && !sparkData.length) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-8 text-center">
        <p className="text-gray-500">No closed trades yet for either bot</p>
      </div>
    )
  }

  // Merge into a unified timeline
  const map = new Map<string, { flame?: number; spark?: number }>()

  // Add starting points
  const allTimestamps = [
    ...flameData.map((d) => d.timestamp),
    ...sparkData.map((d) => d.timestamp),
  ].sort()
  if (allTimestamps.length) {
    map.set(allTimestamps[0], { flame: startingCapital, spark: startingCapital })
  }

  let flameCum = startingCapital
  for (const pt of flameData) {
    flameCum = pt.equity
    const existing = map.get(pt.timestamp) || {}
    map.set(pt.timestamp, { ...existing, flame: flameCum })
  }

  let sparkCum = startingCapital
  for (const pt of sparkData) {
    sparkCum = pt.equity
    const existing = map.get(pt.timestamp) || {}
    map.set(pt.timestamp, { ...existing, spark: sparkCum })
  }

  // Fill forward missing values
  const sorted = Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))

  let lastFlame = startingCapital
  let lastSpark = startingCapital
  const chartData = sorted.map(([ts, vals]) => {
    if (vals.flame !== undefined) lastFlame = vals.flame
    if (vals.spark !== undefined) lastSpark = vals.spark
    return {
      timestamp: ts,
      flame: vals.flame ?? lastFlame,
      spark: vals.spark ?? lastSpark,
    }
  })

  const formatDate = (ts: string) => {
    if (!ts) return ''
    const d = new Date(ts)
    return `${d.getMonth() + 1}/${d.getDate()}`
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4">
      <h3 className="text-sm font-medium text-gray-400 mb-3">Equity Comparison</h3>
      <ResponsiveContainer width="100%" height={380}>
        <ComposedChart data={chartData}>
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatDate}
            stroke="#475569"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(v) => `$${v.toLocaleString()}`}
            stroke="#475569"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
            formatter={(value: number, name: string) => [
              `$${value.toFixed(2)}`,
              name === 'flame' ? 'FLAME' : 'SPARK',
            ]}
          />
          <ReferenceLine
            y={startingCapital}
            stroke="#6b7280"
            strokeDasharray="4 4"
          />
          <Area
            type="monotone"
            dataKey="flame"
            stroke="#f59e0b"
            strokeWidth={2}
            fill="rgba(245, 158, 11, 0.1)"
          />
          <Area
            type="monotone"
            dataKey="spark"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="rgba(59, 130, 246, 0.1)"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
