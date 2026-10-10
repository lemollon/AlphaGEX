/**
 * Forge hero chart — the account-value line under the big balance (mobile
 * addendum §2 Forge tab step 3: "scrubbable chart (press-drag crosshair...
 * release restores)"). Tap a period tile to pick the series (Today / Past
 * week / Past month / Lifetime — done by the caller, which swaps `series`);
 * drag across this chart to scrub it.
 *
 * A light haptic tick fires each time the scrub crosses into a new point
 * (#235) — not on every pixel of finger movement, which would buzz
 * continuously and feel like noise rather than a tick per data point.
 */
import { useMemo, useRef, useState } from 'react'
import { View, StyleSheet, type LayoutChangeEvent } from 'react-native'
import Svg, { Polyline, Line, Circle } from 'react-native-svg'
import * as Haptics from 'expo-haptics'
import { accountChartGeometry, nearestAccountIndex } from '@/components/account-chart-geometry'
import type { AccountPoint } from '@/live/account-series'
import { useTheme } from '@/theme/ThemeContext'

const HEIGHT = 150
const PAD_Y = 10

export function AccountChart({
  series,
  color: lineColor,
  onScrub,
  periodLabel,
}: {
  series: AccountPoint[]
  color: string
  /** Called with the touched point while dragging, and `null` on release. */
  onScrub: (point: AccountPoint | null) => void
  /**
   * The period this chart covers, e.g. "today" — folded into the accessibility
   * label (mobile fidelity #282, "states the period total"). A VoiceOver/
   * TalkBack user cannot drag a finger across an SVG to scrub it the way a
   * sighted customer can, so the chart needs to simply SAY the number instead:
   * start/end value and the net change over the period, in one sentence.
   */
  periodLabel: string
}) {
  const { colors: color } = useTheme()
  const [width, setWidth] = useState(0)
  const [touch, setTouch] = useState<number | null>(null)
  // A ref, not state: responder-move events fire faster than React re-renders,
  // so reading `touch` (state) here could still see the PREVIOUS point and
  // double-tick. The ref is updated synchronously on every move.
  const lastTickIndex = useRef<number | null>(null)

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)
  const geom = useMemo(() => accountChartGeometry(series, width, HEIGHT, PAD_Y), [series, width])

  if (series.length < 2) {
    // One sample (or none) is not a chart to drag across — an empty plot area
    // reads honestly as "nothing to show yet" rather than a broken line.
    return <View style={[s.plot, { height: HEIGHT }]} />
  }

  const first = series[0].v
  const last = series[series.length - 1].v
  const change = last - first
  const changeLabel =
    change > 0 ? `up $${change.toFixed(2)}` : change < 0 ? `down $${Math.abs(change).toFixed(2)}` : 'unchanged'
  const accessibilityLabel = `Account value chart, ${periodLabel}. Started at $${first.toFixed(2)}, now $${last.toFixed(2)}, ${changeLabel}.`

  function move(x: number) {
    const idx = nearestAccountIndex(x, width, series.length)
    if (idx !== lastTickIndex.current) {
      lastTickIndex.current = idx
      void Haptics.selectionAsync()
    }
    setTouch(idx)
    onScrub(series[idx])
  }

  function release() {
    lastTickIndex.current = null
    setTouch(null)
    onScrub(null)
  }

  return (
    <View
      style={[s.plot, { height: HEIGHT }]}
      onLayout={onLayout}
      accessible
      accessibilityRole="image"
      accessibilityLabel={accessibilityLabel}
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderGrant={(e) => move(e.nativeEvent.locationX)}
      onResponderMove={(e) => move(e.nativeEvent.locationX)}
      onResponderRelease={release}
      onResponderTerminate={release}
    >
      {geom ? (
        <Svg width={width} height={HEIGHT}>
          <Polyline
            points={geom.points}
            fill="none"
            stroke={lineColor}
            strokeWidth={2.2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {touch != null ? (
            <>
              <Line
                x1={geom.x(touch)}
                y1={PAD_Y}
                x2={geom.x(touch)}
                y2={HEIGHT - PAD_Y}
                stroke={color.muted}
                strokeWidth={1}
                strokeOpacity={0.5}
              />
              <Circle
                cx={geom.x(touch)}
                cy={geom.y(series[touch].v)}
                r={5}
                fill={lineColor}
                stroke={color.card}
                strokeWidth={2}
              />
            </>
          ) : null}
        </Svg>
      ) : null}
    </View>
  )
}

const s = StyleSheet.create({
  plot: { width: '100%' },
})
