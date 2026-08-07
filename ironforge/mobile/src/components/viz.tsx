import { View, Text, StyleSheet } from 'react-native'
import Svg, { Path, Circle, Line } from 'react-native-svg'
import { color, space, font, radius } from '@/theme/tokens'

/**
 * The two charts the approved layouts need (UX-002): the intraday P&L sparkline with a
 * breakeven baseline, and the four-step trade lifecycle stepper.
 *
 * Both are hand-drawn SVG rather than a charting library. react-native-svg is already
 * a dependency; a chart package would add weight for two fixed, opinionated shapes and
 * would fight the design rather than serve it.
 */

export interface SparkPoint {
  timestamp: string
  pnl: number
}

/**
 * Intraday P&L line with a dashed breakeven axis, an end dot, and Open/Now labels.
 *
 * The y-domain is FORCED to include zero. A series that never crosses breakeven would
 * otherwise auto-scale so the line sits mid-card with the dashed baseline off-screen —
 * which reads as "hovering around breakeven" when the position is in fact up or down
 * all day. Anchoring to zero makes the sign of the trade the first thing you see.
 */
export function Sparkline({
  data,
  width = 300,
  height = 76,
  stroke,
}: {
  data: SparkPoint[]
  width?: number
  height?: number
  stroke: string
}) {
  if (!data || data.length < 2) {
    return (
      <View style={[s.sparkEmpty, { height }]}>
        <Text style={s.sparkEmptyText}>No intraday data yet</Text>
      </View>
    )
  }

  const values = data.map((d) => d.pnl)
  const rawMin = Math.min(...values, 0)
  const rawMax = Math.max(...values, 0)
  // Guard the degenerate flat-at-zero case, which would divide by zero below.
  const span = rawMax - rawMin || 1
  const pad = span * 0.12
  const min = rawMin - pad
  const max = rawMax + pad

  const x = (i: number) => (i / (data.length - 1)) * width
  const y = (v: number) => height - ((v - min) / (max - min)) * height

  const d = data.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(2)},${y(p.pnl).toFixed(2)}`).join(' ')
  const zeroY = y(0)
  const last = data[data.length - 1]

  return (
    <View>
      <Svg width={width} height={height}>
        <Line
          x1={0}
          y1={zeroY}
          x2={width}
          y2={zeroY}
          stroke={color.border}
          strokeWidth={1}
          strokeDasharray="4 4"
        />
        <Path d={d} stroke={stroke} strokeWidth={2} fill="none" strokeLinejoin="round" />
        <Circle cx={x(data.length - 1)} cy={y(last.pnl)} r={4} fill={stroke} />
      </Svg>
      <View style={s.sparkAxis}>
        <Text style={s.axisLabel}>Open</Text>
        <Text style={s.axisLabel}>Now</Text>
      </View>
      <Text style={[s.breakeven, { top: zeroY - 16 }]}>Breakeven $0</Text>
    </View>
  )
}

const STEPS = ['Opened', 'Monitoring', 'Target / Stop', 'Auto Close'] as const

/**
 * The trade lifecycle stepper. `step` is CustomerState.timeline_step (0..4), which the
 * server documents as driving exactly this control — so the mapping is not ours to
 * invent. A null step renders nothing rather than guessing a position.
 */
export function TradeStepper({ step, accent }: { step: number | null; accent: string }) {
  if (step == null) return null
  return (
    <View style={s.stepper}>
      {STEPS.map((label, i) => {
        const done = i < step
        const current = i === step
        const active = done || current
        return (
          <View key={label} style={s.stepCol}>
            <View style={s.stepTrackRow}>
              {/* Connector to the previous node. Rendered first so the node sits on top. */}
              {i > 0 ? (
                <View
                  style={[
                    s.connector,
                    { backgroundColor: i <= step ? accent : color.border },
                  ]}
                />
              ) : (
                <View style={s.connectorSpacer} />
              )}
              <View
                style={[
                  s.node,
                  active
                    ? { borderColor: accent, backgroundColor: current ? 'transparent' : accent }
                    : { borderColor: color.border },
                ]}
              >
                {current ? <View style={[s.nodeInner, { backgroundColor: accent }]} /> : null}
                {done ? <Text style={s.check}>✓</Text> : null}
              </View>
              {i < STEPS.length - 1 ? (
                <View
                  style={[
                    s.connector,
                    { backgroundColor: i < step ? accent : color.border },
                  ]}
                />
              ) : (
                <View style={s.connectorSpacer} />
              )}
            </View>
            <Text
              style={[
                s.stepLabel,
                { color: current ? color.text : active ? color.textDim : color.muted },
              ]}
              numberOfLines={1}
            >
              {label}
            </Text>
            {current ? <Text style={[s.liveTag, { color: accent }]}>Live</Text> : null}
          </View>
        )
      })}
    </View>
  )
}

const s = StyleSheet.create({
  sparkEmpty: {
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: radius.md,
    backgroundColor: color.bg,
  },
  sparkEmptyText: { color: color.muted, fontFamily: font.body, fontSize: 12 },
  sparkAxis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 2 },
  axisLabel: { color: color.muted, fontFamily: font.body, fontSize: 11 },
  breakeven: { position: 'absolute', left: 0, color: color.muted, fontFamily: font.body, fontSize: 10 },

  stepper: { flexDirection: 'row', marginTop: space.md },
  stepCol: { flex: 1, alignItems: 'center' },
  stepTrackRow: { flexDirection: 'row', alignItems: 'center', width: '100%' },
  connector: { flex: 1, height: 2 },
  connectorSpacer: { flex: 1, height: 2, backgroundColor: 'transparent' },
  node: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  nodeInner: { width: 8, height: 8, borderRadius: 4 },
  check: { color: color.text, fontSize: 11, fontFamily: font.bodyBold, lineHeight: 13 },
  stepLabel: { fontFamily: font.body, fontSize: 11, marginTop: 6, textAlign: 'center' },
  liveTag: { fontFamily: font.bodyMedium, fontSize: 10, marginTop: 1 },
})
