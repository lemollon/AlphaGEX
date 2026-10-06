/**
 * The "Live now" card (10.4 design `.live`/`liveCard()`) — avatar + name + "Live" pill,
 * big P&L, an "Open {elapsed} · {left} left" row with a 6px elapsed-time progress bar,
 * an ALWAYS-VISIBLE mini intraday chart (no toggle — see fidelity audit row "Live now
 * section"), and a 3-stage footer (Opened / Monitoring / Auto close).
 *
 * Shared by the Forge tab (one of these per agent with an open trade) and the agent
 * sheet (one embedded instance for that agent's own open trade) — same component, same
 * real data, so the sheet is never a second, drifted copy of the tile.
 */
import { useEffect, useMemo, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import type { LiveTrade } from '@/api/types'
import { Mascot } from '@/components/Brand'
import { Money } from '@/components/ui'
import { PnlChart } from '@/components/PnlChart'
import {
  formatLocalClock,
  formatElapsedMinutes,
  minutesSince,
  liveProgressFraction,
  liveCardStage,
} from '@/live/lifecycle'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'

const STAGE_LABELS = ['Opened', 'Monitoring', 'Auto close'] as const

export function LiveTradeCard({
  bot,
  label,
  accent,
  trade,
  onPress,
}: {
  bot: string
  label: string
  accent: string
  trade: LiveTrade
  onPress?: () => void
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  // Re-renders once a minute so "Open 37 min" and the progress bar creep forward on
  // their own, same pattern as the Forge tab's LifecycleLine.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  const openedAt = trade.opened_at
  const autoCloseAt = trade.auto_close_at ?? null
  const elapsed = openedAt ? formatElapsedMinutes(minutesSince(openedAt)) : '—'
  const closeClock = formatLocalClock(autoCloseAt)
  const openClock = formatLocalClock(openedAt)
  const fraction = liveProgressFraction(openedAt, autoCloseAt)
  const stage = liveCardStage(openedAt, autoCloseAt)
  const pnlTone = (trade.unrealized_pnl ?? 0) >= 0 ? color.pos : color.neg

  const Wrapper = onPress ? Pressable : View

  return (
    <Wrapper
      onPress={onPress}
      accessibilityRole={onPress ? 'button' : undefined}
      style={[s.card, { borderColor: `${accent}66`, backgroundColor: color.card }]}
    >
      <View style={s.header}>
        <Mascot bot={bot} size={42} />
        <View style={{ flex: 1 }}>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>{label}</Text>
          <Text style={[type.label, { color: color.muted, marginTop: 2 }]} numberOfLines={1}>
            {openClock ? `Opened ${openClock}` : 'Open position'}
            {closeClock ? ` · closes by ${closeClock}` : ''}
          </Text>
        </View>
        <View style={[s.livePill, { backgroundColor: `${color.pos}22` }]}>
          <View style={[s.liveDot, { backgroundColor: color.pos }]} />
          <Text style={[type.label, { color: color.pos, fontFamily: font.bodyMedium }]}>Live</Text>
        </View>
      </View>

      <View style={s.pnlRow}>
        <Text style={[type.label, { color: color.muted }]}>Profit &amp; loss so far</Text>
        <Money value={trade.unrealized_pnl} size="hero" />
      </View>

      {fraction != null ? (
        <View style={s.lifeBlock}>
          <View style={s.lifeRow}>
            <Text style={[type.label, { color: color.muted }]}>
              Open <Text style={{ color: color.text, fontFamily: font.bodyBold }}>{elapsed}</Text>
            </Text>
            <Text style={[type.label, { color: color.muted }]}>
              {closeClock ? `by ${closeClock}` : ''}
            </Text>
          </View>
          <View style={[s.bar, { backgroundColor: color.border }]}>
            <View style={[s.barFill, { width: `${Math.round(fraction * 100)}%`, backgroundColor: accent }]} />
          </View>
        </View>
      ) : (
        <Text style={[type.label, { color: color.muted, marginTop: space.sm }]}>Open {elapsed}</Text>
      )}

      <PnlChart
        series={trade.spark_series}
        accent={accent}
        status={STAGE_LABELS[stage]}
        current={trade.unrealized_pnl}
      />

      <View style={s.stages}>
        {STAGE_LABELS.map((lbl, i) => {
          const done = i < stage
          const now = i === stage
          return (
            <View key={lbl} style={s.stageCol}>
              <View
                style={[
                  s.stageBar,
                  { backgroundColor: done || now ? accent : color.border },
                ]}
              />
              <Text
                style={[
                  type.label,
                  { color: now ? color.text : color.muted, fontFamily: now ? font.bodyMedium : font.body, marginTop: 4, textAlign: 'center' },
                ]}
              >
                {lbl}
              </Text>
            </View>
          )
        })}
      </View>
    </Wrapper>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
    card: {
      borderWidth: 1,
      borderRadius: radius.lg + 6,
      padding: space.lg,
      marginBottom: space.lg,
    },
    header: { flexDirection: 'row', alignItems: 'center', gap: space.md },
    livePill: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: space.xs,
      borderRadius: radius.pill,
      paddingHorizontal: space.sm,
      paddingVertical: 4,
    },
    liveDot: { width: 6, height: 6, borderRadius: 3 },
    pnlRow: { marginTop: space.md },
    lifeBlock: { marginTop: space.md, gap: 6 },
    lifeRow: { flexDirection: 'row', justifyContent: 'space-between' },
    bar: { height: 6, borderRadius: radius.pill, overflow: 'hidden' },
    barFill: { height: '100%', borderRadius: radius.pill },
    stages: { flexDirection: 'row', marginTop: space.md, gap: space.sm },
    stageCol: { flex: 1 },
    stageBar: { height: 4, borderRadius: radius.pill },
  })
