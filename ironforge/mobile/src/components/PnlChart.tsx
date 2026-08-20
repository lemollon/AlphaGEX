/**
 * Intraday P&L chart — UX-003 / APP-051.
 *
 * The data for this has been served the whole time. `LiveTrade.spark_series` is built
 * in the webapp's lib/live/summary.ts and the web already draws it in LiveTradeCard;
 * this app declared the field in its own api/types.ts and never read it. No new
 * endpoint was needed — only this component.
 *
 * Deliberate choices:
 *  - The y-domain ALWAYS includes 0. A P&L chart that crops out breakeven can show a
 *    losing trade as a rising line, which is the single worst thing this chart could do.
 *  - The line is the agent's accent, but the CURRENT value is green/red. Colour means
 *    identity on the line and money in the number; never mix the two.
 *  - The touch readout snaps to a real sample and shows that sample's timestamp. It
 *    never interpolates a value the trade did not actually print.
 */
import { useMemo, useState } from 'react'
import { View, Text, StyleSheet, type LayoutChangeEvent } from 'react-native'
import Svg, { Polyline, Line, Circle } from 'react-native-svg'
import { color, space, radius, type, font, pnlColor } from '@/theme/tokens'

export interface SparkPoint {
  timestamp: string
  pnl: number
}

const HEIGHT = 88
const PAD_Y = 10

export function PnlChart({
  series,
  accent,
  status,
  current,
}: {
  series: SparkPoint[]
  accent: string
  /** "Monitoring", "Profit Target / Stop Loss" — the trade's lifecycle label. */
  status: string
  current: number | null
}) {
  const [width, setWidth] = useState(0)
  const [touch, setTouch] = useState<number | null>(null)

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)

  const geom = useMemo(() => {
    if (!series.length || width <= 0) return null
    const values = series.map((p) => p.pnl)
    // Breakeven is always in frame — see the note above.
    const lo = Math.min(0, ...values)
    const hi = Math.max(0, ...values)
    const span = hi - lo || 1
    const x = (i: number) =>
      series.length === 1 ? width / 2 : (i / (series.length - 1)) * width
    const y = (v: number) => PAD_Y + (1 - (v - lo) / span) * (HEIGHT - PAD_Y * 2)
    return {
      x,
      y,
      zeroY: y(0),
      points: series.map((p, i) => `${x(i).toFixed(2)},${y(p.pnl).toFixed(2)}`).join(' '),
    }
  }, [series, width])

  const active = touch != null ? series[touch] : null

  // One sample is not a chart. Say so rather than drawing a dot and calling it a line.
  if (series.length < 2) {
    return (
      <View style={s.wrap}>
        <Header status={status} current={current} accent={accent} />
        <View style={[s.plot, s.emptyPlot]}>
          <Text style={[type.label, { color: color.muted }]}>
            Waiting for the first few minutes of this trade.
          </Text>
        </View>
      </View>
    )
  }

  return (
    <View style={s.wrap}>
      <Header status={status} current={current} accent={accent} />

      <View
        style={s.plot}
        onLayout={onLayout}
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={(e) => setTouch(nearest(e.nativeEvent.locationX, width, series.length))}
        onResponderMove={(e) => setTouch(nearest(e.nativeEvent.locationX, width, series.length))}
        onResponderRelease={() => setTouch(null)}
        onResponderTerminate={() => setTouch(null)}
      >
        {geom ? (
          <Svg width={width} height={HEIGHT}>
            {/* Breakeven $0 */}
            <Line
              x1={0}
              y1={geom.zeroY}
              x2={width}
              y2={geom.zeroY}
              stroke={color.border}
              strokeWidth={1}
              strokeDasharray="4 4"
            />
            <Polyline
              points={geom.points}
              fill="none"
              stroke={accent}
              strokeWidth={1.8}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {/* Now */}
            <Circle
              cx={geom.x(series.length - 1)}
              cy={geom.y(series[series.length - 1].pnl)}
              r={3.5}
              fill={accent}
            />
            {active && touch != null ? (
              <>
                <Line
                  x1={geom.x(touch)}
                  y1={0}
                  x2={geom.x(touch)}
                  y2={HEIGHT}
                  stroke={accent}
                  strokeWidth={1}
                  opacity={0.6}
                />
                <Circle
                  cx={geom.x(touch)}
                  cy={geom.y(active.pnl)}
                  r={4}
                  fill={color.bg}
                  stroke={accent}
                  strokeWidth={2}
                />
              </>
            ) : null}
          </Svg>
        ) : null}

        {/* Sits ON the dashed line, as in UX-003 — not floated in a corner. */}
        {geom ? (
          <Text style={[s.beLabel, type.label, { top: Math.max(0, geom.zeroY - 15) }]}>
            Breakeven $0
          </Text>
        ) : null}

        {active ? (
          <View
            style={[
              s.tip,
              // Keep the bubble inside the plot at both ends.
              { left: clamp((geom?.x(touch ?? 0) ?? 0) - 44, 0, Math.max(0, width - 88)) },
            ]}
          >
            <Text style={[type.label, { color: color.textDim }]}>{clock(active.timestamp)}</Text>
            <Text style={[type.label, { color: pnlColor(active.pnl), fontFamily: font.bodyBold }]}>
              {money(active.pnl)}
            </Text>
          </View>
        ) : null}
      </View>

      <View style={s.axis}>
        <Text style={[type.label, { color: color.muted }]}>Open</Text>
        <Text style={[type.label, { color: color.muted }]}>Now</Text>
      </View>
    </View>
  )
}

function Header({
  status,
  current,
  accent,
}: {
  status: string
  current: number | null
  accent: string
}) {
  return (
    <View style={s.head}>
      <Text style={[type.label, { color: accent, fontFamily: font.bodyMedium }]}>{status}</Text>
      <Text style={[type.body, { color: pnlColor(current), fontFamily: font.bodyBold }]}>
        {current == null ? '—' : money(current)}
      </Text>
    </View>
  )
}

function nearest(x: number, width: number, n: number): number {
  if (width <= 0 || n < 2) return 0
  return clamp(Math.round((x / width) * (n - 1)), 0, n - 1)
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v))
}

function money(v: number): string {
  const sign = v >= 0 ? '+' : '-'
  return `${sign}$${Math.abs(v).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

/** Server timestamps are ISO; render them in the device's local clock. */
function clock(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

const s = StyleSheet.create({
  wrap: { marginTop: space.md },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  plot: { height: HEIGHT, marginTop: space.sm, justifyContent: 'center' },
  emptyPlot: { alignItems: 'center' },
  beLabel: { position: 'absolute', left: 0, color: color.muted },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: space.xs },
  tip: {
    position: 'absolute',
    top: -4,
    width: 88,
    alignItems: 'center',
    backgroundColor: color.card,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingVertical: space.xs,
  },
})
