'use client'

import { Bar, BarChart, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { formatDollarPnl } from '@/lib/format'

/**
 * Tiny +/− glyph just outside each bar's end (ds-color #6: "gain and loss
 * always pair color with a sign ... and a label" — color alone used to be
 * the only signal here; the tooltip's sign doesn't help a sighted-but-
 * colorblind reader scanning the chart without hovering every bar).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- Recharts' LabelList
// `content` callback type is a large union of possible renders; this component only
// ever receives numeric geometry + value from this one Bar, so a loose prop type here
// is the pragmatic choice over fighting Recharts' Props union.
function SignGlyph(props: any) {
  const x = Number(props.x)
  const y = Number(props.y)
  const width = Number(props.width)
  const height = Number(props.height)
  const value = typeof props.value === 'number' ? props.value : Number(props.value)
  if ([x, y, width, height].some((n) => isNaN(n)) || isNaN(value) || value === 0) return null
  const positive = value > 0
  // Recharts gives the rect's top-left corner regardless of sign — a positive
  // bar's top edge is above the zero baseline, a negative bar's top edge IS
  // the baseline (it extends downward by `height`). Put the glyph just
  // outside whichever edge is the bar's visual "end".
  return (
    <text
      x={x + width / 2}
      y={positive ? y - 3 : y + height + 10}
      textAnchor="middle"
      fontSize={9}
      fontWeight={700}
      fill={positive ? 'var(--up)' : 'var(--bad)'}
    >
      {positive ? '+' : '−'}
    </text>
  )
}

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
      <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--accent-text)]">
        Daily Results · Last {bars.length} Trading Days
      </h3>
      {hasData ? (
        <div
          className="mt-3 h-[140px]"
          role="img"
          aria-label={`Daily results chart, last ${bars.length} trading days, most recent day ${formatDollarPnl(bars[bars.length - 1].pnl)}`}
        >
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
                <LabelList dataKey="pnl" content={SignGlyph} />
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
