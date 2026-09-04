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
 *  - The tooltip box is PINNED to the top of the chart, not floated at the touched
 *    point — a bubble that rides the line is exactly what a thumb parks on top of.
 *    Only the dashed guide and the on-line marker move with the finger. On release
 *    both fade out over 150ms instead of snapping away, so it never reads as a glitch.
 */
import { useMemo, useRef, useState } from 'react'
import { Animated, View, Text, StyleSheet, type LayoutChangeEvent } from 'react-native'
import Svg, { Polyline, Line, Circle } from 'react-native-svg'
import {
  chartGeometry,
  nearestIndex,
  tooltipX,
  formatPnl,
  type Point as SparkPointType,
} from '@/components/chart-geometry'
import { formatLocalClock } from '@/live/lifecycle'
import { color, space, radius, type, font, pnlColor } from '@/theme/tokens'

export type SparkPoint = SparkPointType

const HEIGHT = 88
const PAD_Y = 10

// The tooltip box's fixed geometry — pinned to the top of the plot, so the guide
// below it always starts from the same place regardless of which sample is touched.
const TIP_WIDTH = 88
const TIP_TOP = 2
const TIP_HEIGHT = 38
const TIP_INSET = 4

const AnimatedLine = Animated.createAnimatedComponent(Line)
const AnimatedCircle = Animated.createAnimatedComponent(Circle)

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
  // The touched sample index. Set on press/drag; kept (not nulled) through the
  // release fade so the guide and box have something to draw while they fade out.
  const [touch, setTouch] = useState<number | null>(null)
  // Shared by the box (Animated.View) and the SVG guide/marker (Animated react-native-svg
  // components) — react-native-svg's animated components don't support the native driver,
  // so this stays JS-driven throughout rather than mixing drivers on one Animated.Value.
  const opacity = useRef(new Animated.Value(0)).current

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)

  // The maths lives in components/chart-geometry.ts so the one rule that matters — the
  // y-domain always contains zero — is covered by tests rather than by a comment.
  const geom = useMemo(() => chartGeometry(series, width, HEIGHT, PAD_Y), [series, width])

  const active = touch != null ? series[touch] : null

  function showTouch(x: number) {
    const idx = nearestIndex(x, width, series.length)
    setTouch(idx)
    // A new touch shows immediately, even mid-fade from the last one.
    opacity.stopAnimation()
    opacity.setValue(1)
  }

  function releaseTouch() {
    Animated.timing(opacity, { toValue: 0, duration: 150, useNativeDriver: false }).start(
      ({ finished }) => {
        if (finished) setTouch(null)
      },
    )
  }

  // One sample is not a chart. Say so rather than drawing a dot and calling it a line.
  // With no series, there is also nothing for a touch to snap to — no responder is
  // attached below, so the tooltip can never show.
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
        onResponderGrant={(e) => showTouch(e.nativeEvent.locationX)}
        onResponderMove={(e) => showTouch(e.nativeEvent.locationX)}
        onResponderRelease={releaseTouch}
        onResponderTerminate={releaseTouch}
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
                {/* Guide drops from the pinned tooltip box down to the zero baseline —
                    never the full chart height, and never through the box above it. */}
                <AnimatedLine
                  x1={geom.x(touch)}
                  y1={TIP_TOP + TIP_HEIGHT}
                  x2={geom.x(touch)}
                  y2={geom.zeroY}
                  stroke={accent}
                  strokeWidth={1}
                  opacity={opacity.interpolate({ inputRange: [0, 1], outputRange: [0, 0.6] })}
                />
                <AnimatedCircle
                  cx={geom.x(touch)}
                  cy={geom.y(active.pnl)}
                  r={4}
                  fill={color.bg}
                  stroke={accent}
                  strokeWidth={2}
                  opacity={opacity}
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

        {active && touch != null ? (
          <Animated.View
            style={[
              s.tip,
              // Pinned to the top of the chart, slid inward near either edge so it
              // never clips — the point itself only ever moves the guide and marker.
              { left: tooltipX(geom?.x(touch) ?? 0, TIP_WIDTH, width, TIP_INSET), opacity },
            ]}
          >
            <Text style={[type.label, { color: color.textDim }]}>
              {formatLocalClock(active.timestamp) ?? ''}
            </Text>
            <Text style={[type.body, { color: pnlColor(active.pnl), fontFamily: font.bodyBold }]}>
              {formatPnl(active.pnl)}
            </Text>
          </Animated.View>
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
        {current == null ? '—' : formatPnl(current)}
      </Text>
    </View>
  )
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
    top: TIP_TOP,
    width: TIP_WIDTH,
    alignItems: 'center',
    backgroundColor: color.card,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingVertical: space.xs,
  },
})
