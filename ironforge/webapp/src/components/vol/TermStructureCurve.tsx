'use client'

import {
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  LineChart,
} from 'recharts'
import {
  termStructurePoints,
  isBackwardation,
  type AdvisorInputs,
} from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

export default function TermStructureCurve({
  inputs,
}: {
  inputs?: AdvisorInputs
}) {
  const points = termStructurePoints(inputs)
  const back = isBackwardation(inputs)
  const lineColor = back ? '#ef4444' : '#34d399'

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <div className={LABEL}>VIX term structure</div>
        <span
          className={`text-xs font-semibold uppercase tracking-wider ${
            back ? 'text-red-400' : 'text-emerald-400'
          }`}
        >
          {back ? 'BACKWARDATION' : 'contango'}
        </span>
      </div>
      {points.length >= 2 ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={points}>
            <XAxis
              dataKey="label"
              stroke="#44403c"
              tick={{ fill: '#a8a29e', fontSize: 11 }}
            />
            <YAxis
              stroke="#44403c"
              tick={{ fill: '#a8a29e', fontSize: 11 }}
              domain={['auto', 'auto']}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1c1917',
                border: '1px solid #292524',
                borderRadius: 8,
              }}
              labelStyle={{ color: '#a8a29e' }}
              formatter={(value: number) => [
                (typeof value === 'number' ? value : 0).toFixed(2),
                'Vol',
              ]}
            />
            <Line
              type="monotone"
              dataKey="vol"
              stroke={lineColor}
              strokeWidth={2}
              dot={{ r: 3, fill: lineColor }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="flex h-[220px] items-center justify-center">
          <p className="text-sm text-forge-muted">Term structure unavailable</p>
        </div>
      )}
    </section>
  )
}
