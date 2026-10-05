/**
 * Forge hero chart — the account-value line under the big balance (mobile
 * addendum §2 Forge tab step 3: "scrubbable chart (press-drag crosshair...
 * release restores)"). Tap a period tile to pick the series (Today / Past
 * week / Past month / Lifetime — done by the caller, which swaps `series`);
 * drag across this chart to scrub it.
 *
 * No haptic tick on scrub: the design calls for one, but expo-haptics is not
 * an installed dependency and adding one is out of scope for this pass (no
 * native dependency changes). The visual guide + marker still track the
 * finger; only the buzz is missing.
 */
import { useMemo, useState } from 'react'
import { View, StyleSheet, type LayoutChangeEvent } from 'react-native'
import Svg, { Polyline, Line, Circle } from 'react-native-svg'
import { accountChartGeometry, nearestAccountIndex } from '@/components/account-chart-geometry'
import type { AccountPoint } from '@/live/account-series'
import { useTheme } from '@/theme/ThemeContext'

const HEIGHT = 150
const PAD_Y = 10

export function AccountChart({
  series,
  color: lineColor,
  onScrub,
}: {
  series: AccountPoint[]
  color: string
  /** Called with the touched point while dragging, and `null` on release. */
  onScrub: (point: AccountPoint | null) => void
}) {
  const { colors: color } = useTheme()
  const [width, setWidth] = useState(0)
  const [touch, setTouch] = useState<number | null>(null)

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)
  const geom = useMemo(() => accountChartGeometry(series, width, HEIGHT, PAD_Y), [series, width])

  if (series.length < 2) {
    // One sample (or none) is not a chart to drag across — an empty plot area
    // reads honestly as "nothing to show yet" rather than a broken line.
    return <View style={[s.plot, { height: HEIGHT }]} />
  }

  function move(x: number) {
    const idx = nearestAccountIndex(x, width, series.length)
    setTouch(idx)
    onScrub(series[idx])
  }

  function release() {
    setTouch(null)
    onScrub(null)
  }

  return (
    <View
      style={[s.plot, { height: HEIGHT }]}
      onLayout={onLayout}
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
