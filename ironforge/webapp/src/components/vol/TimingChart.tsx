'use client'

import {
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  AreaChart,
} from 'recharts'
import { timingAreaData } from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

export default function TimingChart({
  cdf,
  p75,
}: {
  cdf?: number[]
  p75?: number
}) {
  const data = timingAreaData(cdf)
  if (data.length === 0) return null

  const hasTarget = p75 !== null && p75 !== undefined && !Number.isNaN(p75)

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className={`${LABEL} mb-3`}>Timing — cumulative probability</div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data}>
          <XAxis
            dataKey="day"
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
            tickFormatter={(v) => `${v}d`}
          />
          <YAxis
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1c1917',
              border: '1px solid #292524',
              borderRadius: 8,
            }}
            labelStyle={{ color: '#a8a29e' }}
            formatter={(value: number) => [
              `${(typeof value === 'number' ? value : 0).toFixed(0)}%`,
              'Cumulative',
            ]}
            labelFormatter={(label) => `Day ${label}`}
          />
          {hasTarget && (
            <ReferenceLine
              x={p75}
              stroke="#f59e0b"
              strokeDasharray="4 4"
              label={{
                value: 'target',
                position: 'top',
                fill: '#f59e0b',
                fontSize: 11,
              }}
            />
          )}
          <Area
            type="monotone"
            dataKey="pct"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="rgba(59, 130, 246, 0.15)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </section>
  )
}
