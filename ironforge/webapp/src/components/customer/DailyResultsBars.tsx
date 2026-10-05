'use client'

import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { formatDollarPnl } from '@/lib/format'

/**
 * "Daily results" bars — last 20 trading days, up/down from a center
 * baseline (dev-handoff §6, gap-audit "MISSING: Daily results bars").
 * Zero-filled per day by `dailyResultBars()` so a no-trade session still
 * draws a (flat) bar instead of leaving a gap.
 */
export default function DailyResultsBars({ bars }: { bars: Array<{ day: string; pnl: number }> }) {
  const hasData = bars.some((b) => b.pnl !== 0)

  return (
    <section className="rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">
        Daily Results · Last {bars.length} Trading Days
      </h3>
      {hasData ? (
        <div className="mt-3 h-[140px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bars} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <XAxis
                dataKey="day"
                tickFormatter={(d: string) => {
                  const dt = new Date(`${d}T12:00:00`)
                  return isNaN(dt.getTime()) ? '' : dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                }}
                stroke="#44403c"
                tick={{ fill: '#a8a29e', fontSize: 10 }}
                interval={Math.max(0, Math.floor(bars.length / 6) - 1)}
              />
              <ReferenceLine y={0} stroke="#78716c" />
              <Tooltip
                contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #292524', borderRadius: 8, fontSize: 12 }}
                labelFormatter={(d: string) => {
                  const dt = new Date(`${d}T12:00:00`)
                  return isNaN(dt.getTime()) ? d : dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                }}
                formatter={(value: number) => [formatDollarPnl(value), 'P&L']}
              />
              <Bar dataKey="pnl" radius={[4, 4, 4, 4]} isAnimationActive={false}>
                {bars.map((b, i) => (
                  <Cell key={i} fill={b.pnl > 0 ? 'var(--up)' : b.pnl < 0 ? 'var(--bad)' : 'var(--line-2)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-3 pb-2 text-sm text-[var(--muted)]">No closed trades in the last {bars.length} trading days.</p>
      )}
    </section>
  )
}
