'use client'

import {
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  LineChart,
} from 'recharts'
import { seriesForChart, type VolSeriesPoint } from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

const VIX_COLOR = '#3b82f6'
const VVIX_COLOR = '#06b6d4'

function formatDate(d: string) {
  if (!d) return ''
  const parsed = new Date(d)
  if (Number.isNaN(parsed.getTime())) return d
  return parsed.toLocaleDateString('en-US', {
    month: 'numeric',
    day: 'numeric',
    timeZone: 'America/Chicago',
  })
}

/**
 * Normalized VIX vs VVIX overlay — both as z-scores on a shared axis so the
 * divergence between them is the read: when the lines spread apart, VIX and
 * VVIX disagree (e.g. price fear without vol-of-vol confirmation).
 */
export default function VixVvixChart({ series }: { series?: VolSeriesPoint[] }) {
  const data = seriesForChart(series)
  if (data.length < 2) {
    return (
      <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
        <div className={`${LABEL} mb-2`}>VIX vs VVIX (normalized)</div>
        <p className="text-sm text-forge-muted">Insufficient history.</p>
      </section>
    )
  }

  // Sparse date ticks: ~6 evenly spaced labels across the window.
  const step = Math.max(1, Math.ceil(data.length / 6))
  const ticks = data.filter((_, i) => i % step === 0).map((p) => p.d)

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className={LABEL}>VIX vs VVIX (normalized)</div>
        <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider">
          <span className="flex items-center gap-1 text-forge-muted">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: VIX_COLOR }} />
            VIX z
          </span>
          <span className="flex items-center gap-1 text-forge-muted">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: VVIX_COLOR }} />
            VVIX z
          </span>
        </div>
      </div>
      <p className="mb-3 text-xs text-forge-muted">
        Normalized VIX vs VVIX — divergence shows when they disagree.
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <XAxis
            dataKey="d"
            ticks={ticks}
            tickFormatter={formatDate}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
          />
          <YAxis
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
            domain={['auto', 'auto']}
            tickFormatter={(v) => (typeof v === 'number' ? v.toFixed(1) : v)}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1c1917',
              border: '1px solid #292524',
              borderRadius: 8,
            }}
            labelStyle={{ color: '#a8a29e' }}
            formatter={(value: number, name: string) => {
              const v = typeof value === 'number' ? value : 0
              const label = name === 'vix_z' ? 'VIX z' : name === 'vvix_z' ? 'VVIX z' : name
              return [v.toFixed(2), label]
            }}
            labelFormatter={(label) => formatDate(String(label))}
          />
          <ReferenceLine y={0} stroke="#78716c" strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="vix_z"
            stroke={VIX_COLOR}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="vvix_z"
            stroke={VVIX_COLOR}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </section>
  )
}
