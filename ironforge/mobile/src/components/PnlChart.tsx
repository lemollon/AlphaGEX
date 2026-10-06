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
 *  - When `autoCloseAt` is known (a live trade), the x-axis is the session's real
 *    clock (10.4 design `drawTradeChart`): a dollar axis on the left, a tick every 30
 *    minutes, and the untraded remainder of the session shaded through the scheduled
 *    close. A closed trade's sheet never passes `autoCloseAt` — there is no "rest of
 *    session" left to shade — and falls back to the original index-spaced chart.
 */
import { useMemo, useRef, useState } from 'react'
import { Animated, View, Text, StyleSheet, type LayoutChangeEvent } from 'react-native'
import Svg, { Polyline, Line, Circle, Rect, Text as SvgText } from 'react-native-svg'
import {
  chartGeometry,
  timeChartGeometry,
  nearestIndex,
  nearestTimeIndex,
  tooltipX,
  formatPnl,
  type Point as SparkPointType,
} from '@/components/chart-geometry'
import { formatLocalClock } from '@/live/lifecycle'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'

export type SparkPoint = SparkPointType

const HEIGHT = 88
const PAD_Y = 10
// Left gutter for the dollar-axis labels — only reserved in time-axis mode.
const AXIS_GUTTER = 30

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
  autoCloseAt,
}: {
  series: SparkPoint[]
  accent: string
  /** "Monitoring", "Profit Target / Stop Loss" — the trade's lifecycle label. */
  status: string
  current: number | null
  /** The session's scheduled close — present only for a trade still open. */
  autoCloseAt?: string | null
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const [width, setWidth] = useState(0)
  // The touched sample index. Set on press/drag; kept (not nulled) through the
  // release fade so the guide and box have something to draw while they fade out.
  const [touch, setTouch] = useState<number | null>(null)
  // Shared by the box (Animated.View) and the SVG guide/marker (Animated react-native-svg
  // components) — react-native-svg's animated components don't support the native driver,
  // so this stays JS-driven throughout rather than mixing drivers on one Animated.Value.
  const opacity = useRef(new Animated.Value(0)).current

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)

  const timeAxis = autoCloseAt !== undefined
  const gutter = timeAxis ? AXIS_GUTTER : 0
  const chartWidth = Math.max(0, width - gutter)

  // The maths lives in components/chart-geometry.ts so the one rule that matters — the
  // y-domain always contains zero — is covered by tests rather than by a comment.
  const indexGeom = useMemo(
    () => (timeAxis ? null : chartGeometry(series, width, HEIGHT, PAD_Y)),
    [series, width, timeAxis],
  )
  const timeGeom = useMemo(
    () => (timeAxis ? timeChartGeometry(series, autoCloseAt, chartWidth, HEIGHT, PAD_Y) : null),
    [series, chartWidth, timeAxis, autoCloseAt],
  )

  const active = touch != null ? series[touch] : null

  function showTouch(x: number) {
    const idx = timeGeom
      ? nearestTimeIndex(Math.max(0, Math.min(chartWidth, x - gutter)), timeGeom, series)
      : nearestIndex(x, width, series.length)
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

  // Pixel x/y for the active (touched) sample and "now" — whichever geometry is active.
  const px = (i: number) => (timeGeom ? timeGeom.x(new Date(series[i].timestamp).getTime()) + gutter : indexGeom!.x(i))
  const py = (i: number) => (timeGeom ? timeGeom.y(series[i].pnl) : indexGeom!.y(series[i].pnl))
  const zeroY = timeGeom ? timeGeom.y(0) : indexGeom!.zeroY
  const touchX = touch != null ? px(touch) : 0

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
        {timeGeom ? (
          <Svg width={width} height={HEIGHT}>
            {/* Rest of session — the untraded remainder up to the scheduled close
                (10.4 design `drawTradeChart`'s shaded rect). Never drawn when the
                close has already passed "now". */}
            {timeGeom.sessionEndX != null && timeGeom.sessionEndX > timeGeom.nowX ? (
              <Rect
                x={timeGeom.nowX + gutter}
                y={PAD_Y}
                width={Math.max(0, timeGeom.sessionEndX - timeGeom.nowX)}
                height={HEIGHT - PAD_Y * 2}
                fill={color.border}
                opacity={0.35}
                rx={4}
              />
            ) : null}
            {/* Dollar gridlines — zero solid, every other dashed (10.4 design). */}
            {timeGeom.yTicks.map((t) => (
              <Line
                key={`y-${t.pos}`}
                x1={gutter}
                x2={width}
                y1={t.pos}
                y2={t.pos}
                stroke={color.border}
                strokeWidth={1}
                strokeDasharray={Math.abs(t.pos - zeroY) < 0.5 ? undefined : '2 4'}
              />
            ))}
            {timeGeom.yTicks.map((t) => (
              <SvgText
                key={`yl-${t.pos}`}
                x={gutter - 6}
                y={t.pos + 3}
                fontSize={9.5}
                fill={color.muted}
                textAnchor="end"
              >
                {t.label}
              </SvgText>
            ))}
            {/* 30-minute time ticks across the session (10.4 design). */}
            {timeGeom.timeTicks.map((t) => (
              <SvgText
                key={`t-${t.pos}`}
                x={t.pos + gutter}
                y={HEIGHT - 3}
                fontSize={9}
                fill={color.muted}
                textAnchor="middle"
              >
                {t.label}
              </SvgText>
            ))}
            <Polyline
              points={series.map((p, i) => `${px(i).toFixed(2)},${py(i).toFixed(2)}`).join(' ')}
              fill="none"
              stroke={accent}
              strokeWidth={1.8}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <Circle cx={px(series.length - 1)} cy={py(series.length - 1)} r={3.5} fill={accent} />
            {active && touch != null ? (
              <>
                <AnimatedLine
                  x1={touchX}
                  y1={TIP_TOP + TIP_HEIGHT}
                  x2={touchX}
                  y2={zeroY}
                  stroke={accent}
                  strokeWidth={1}
                  opacity={opacity.interpolate({ inputRange: [0, 1], outputRange: [0, 0.6] })}
                />
                <AnimatedCircle
                  cx={touchX}
                  cy={py(touch)}
                  r={4}
                  fill={color.bg}
                  stroke={accent}
                  strokeWidth={2}
                  opacity={opacity}
                />
              </>
            ) : null}
          </Svg>
        ) : indexGeom ? (
          <Svg width={width} height={HEIGHT}>
            {/* Breakeven $0 */}
            <Line
              x1={0}
              y1={indexGeom.zeroY}
              x2={width}
              y2={indexGeom.zeroY}
              stroke={color.border}
              strokeWidth={1}
              strokeDasharray="4 4"
            />
            <Polyline
              points={indexGeom.points}
              fill="none"
              stroke={accent}
              strokeWidth={1.8}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {/* Now */}
            <Circle
              cx={indexGeom.x(series.length - 1)}
              cy={indexGeom.y(series[series.length - 1].pnl)}
              r={3.5}
              fill={accent}
            />
            {active && touch != null ? (
              <>
                {/* Guide drops from the pinned tooltip box down to the zero baseline —
                    never the full chart height, and never through the box above it. */}
                <AnimatedLine
                  x1={indexGeom.x(touch)}
                  y1={TIP_TOP + TIP_HEIGHT}
                  x2={indexGeom.x(touch)}
                  y2={indexGeom.zeroY}
                  stroke={accent}
                  strokeWidth={1}
                  opacity={opacity.interpolate({ inputRange: [0, 1], outputRange: [0, 0.6] })}
                />
                <AnimatedCircle
                  cx={indexGeom.x(touch)}
                  cy={indexGeom.y(active.pnl)}
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

        {/* Sits ON the dashed line, as in UX-003 — not floated in a corner. Only in the
            index-axis mode; the time axis already labels zero on its own $ gridline. */}
        {indexGeom && !timeGeom ? (
          <Text style={[s.beLabel, type.label, { top: Math.max(0, indexGeom.zeroY - 15) }]}>
            Breakeven $0
          </Text>
        ) : null}

        {active && touch != null ? (
          <Animated.View
            style={[
              s.tip,
              // Pinned to the top of the chart, slid inward near either edge so it
              // never clips — the point itself only ever moves the guide and marker.
              { left: tooltipX(touchX, TIP_WIDTH, width, TIP_INSET), opacity },
            ]}
          >
            <Text style={[type.label, { color: color.textDim }]}>
              {formatLocalClock(active.timestamp) ?? ''}
            </Text>
            <Text
              style={[
                type.body,
                { color: active.pnl >= 0 ? color.pos : color.neg, fontFamily: font.bodyBold },
              ]}
            >
              {formatPnl(active.pnl)}
            </Text>
          </Animated.View>
        ) : null}
      </View>

      {!timeGeom ? (
        <View style={s.axis}>
          <Text style={[type.label, { color: color.muted }]}>Open</Text>
          <Text style={[type.label, { color: color.muted }]}>Now</Text>
        </View>
      ) : null}
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
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const tone = current == null ? color.textDim : current >= 0 ? color.pos : color.neg
  return (
    <View style={s.head}>
      <Text style={[type.label, { color: accent, fontFamily: font.bodyMedium }]}>{status}</Text>
      <Text style={[type.body, { color: tone, fontFamily: font.bodyBold }]}>
        {current == null ? '—' : formatPnl(current)}
      </Text>
    </View>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
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
