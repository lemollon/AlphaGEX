/**
 * Bottom sheet chrome (10.4 redesign, mobile addendum §2 "Sheets & components table"):
 * max 88% height, 26px top radius, grab handle; drag-down >90px or scrim tap dismisses;
 * scrolls inside (caller supplies its own ScrollView); traps focus for VoiceOver via
 * `accessibilityViewIsModal`.
 *
 * REBUILT 2026-10 (see 2026-10-14-sparky-blank-transcript-sheet-remount incident):
 * this used to be presented via each route's own `presentation: 'transparentModal'`
 * Stack.Screen option (app/sparky.tsx, app/agents/[bot].tsx, app/trade/[id].tsx,
 * app/notifications.tsx, app/notification-preferences.tsx all did this), which kept
 * the previous tab mounted underneath a transparent screen. That caused a customer-
 * reproduced remount-loop bug in Sparky; all five were converted back to plain pushed
 * screens with a manual back-chevron header. This component's only remaining caller is
 * `EmberTradeSheet` in app/(tabs)/ledger.tsx, which renders it as an in-place overlay
 * from local state (no route/transparentModal involved) — a plain conditionally-rendered
 * child never has the background-screen-stays-mounted failure mode this traded away.
 */
import { useEffect, useRef, useState } from 'react'
import {
  View,
  Text,
  Pressable,
  Animated,
  PanResponder,
  StyleSheet,
  Dimensions,
  AccessibilityInfo,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { space, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'

const DISMISS_THRESHOLD = 90
const SHEET_RADIUS = 26
const SCRIM_OPACITY = 0.6

/**
 * `children` is a render prop rather than a plain node so anything inside — a close "X",
 * a cancel button deep in a multi-step flow — can trigger the same slide-down-then-navigate
 * sequence as the scrim tap and the drag gesture, instead of calling `onClose` directly and
 * skipping the exit animation.
 */
export function Sheet({
  onClose,
  accent,
  maxHeightPct = 0.88,
  children,
}: {
  onClose: () => void
  accent?: string
  maxHeightPct?: number
  children: (close: () => void) => React.ReactNode
}) {
  const { colors: color } = useTheme()
  const windowHeight = Dimensions.get('window').height
  const sheetMaxHeight = Math.round(windowHeight * maxHeightPct)
  const [reduceMotion, setReduceMotion] = useState(false)
  const translateY = useRef(new Animated.Value(windowHeight)).current
  const scrim = useRef(new Animated.Value(0)).current
  const dragY = useRef(new Animated.Value(0)).current
  const closingRef = useRef(false)

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled?.()
      .then(setReduceMotion)
      .catch(() => {})
  }, [])

  useEffect(() => {
    const duration = reduceMotion ? 0 : 260
    Animated.parallel([
      Animated.timing(translateY, { toValue: 0, duration, useNativeDriver: true }),
      Animated.timing(scrim, { toValue: SCRIM_OPACITY, duration, useNativeDriver: true }),
    ]).start()
    // Entrance animation is a one-shot on mount — a reduceMotion flip mid-sheet should
    // not replay it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function close() {
    if (closingRef.current) return
    closingRef.current = true
    const duration = reduceMotion ? 0 : 220
    Animated.parallel([
      Animated.timing(translateY, { toValue: windowHeight, duration, useNativeDriver: true }),
      Animated.timing(scrim, { toValue: 0, duration, useNativeDriver: true }),
    ]).start(() => onClose())
  }

  const panResponder = useRef(
    PanResponder.create({
      // Only claims the gesture once it is clearly a vertical drag — a tap on the handle
      // itself must still register as a tap, and a mostly-horizontal swipe must not be
      // mistaken for a dismiss drag.
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dy) > 4 && Math.abs(g.dy) > Math.abs(g.dx) * 1.5,
      onPanResponderMove: (_, g) => {
        if (g.dy > 0) dragY.setValue(g.dy)
      },
      onPanResponderRelease: (_, g) => {
        if (g.dy > DISMISS_THRESHOLD) {
          close()
        } else {
          Animated.spring(dragY, { toValue: 0, useNativeDriver: true, bounciness: 4 }).start()
        }
      },
      onPanResponderTerminate: () => {
        Animated.spring(dragY, { toValue: 0, useNativeDriver: true, bounciness: 4 }).start()
      },
    }),
  ).current

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      <Animated.View style={[styles.scrim, { opacity: scrim }]} pointerEvents="box-none">
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={close}
          accessibilityRole="button"
          accessibilityLabel="Dismiss"
        />
      </Animated.View>
      <Animated.View
        accessibilityViewIsModal
        style={[
          styles.card,
          {
            backgroundColor: color.card,
            maxHeight: sheetMaxHeight,
            borderColor: color.border,
            transform: [{ translateY: Animated.add(translateY, dragY) }],
          },
          accent ? { borderTopColor: accent, borderTopWidth: 3 } : null,
        ]}
      >
        <View {...panResponder.panHandlers} style={styles.grip}>
          <View style={[styles.handle, { backgroundColor: color.border }]} />
        </View>
        <SafeAreaView edges={['bottom']} style={{ flex: 1 }}>
          {children(close)}
        </SafeAreaView>
      </Animated.View>
    </View>
  )
}

/**
 * The header row every sheet uses below the grab handle: optional leading visual
 * (mascot, outcome badge…), title + subtitle, optional trailing content, then the
 * close "X" — replacing the old full-screen chevron-back header these screens used
 * when they were stack pushes.
 */
export function SheetHeader({
  title,
  subtitle,
  left,
  right,
  onClose,
}: {
  title: string
  subtitle?: string
  left?: React.ReactNode
  right?: React.ReactNode
  onClose: () => void
}) {
  const { colors: color } = useTheme()
  return (
    <View style={headerStyles.row}>
      {left}
      <View style={{ flex: 1 }}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={[type.label, { color: color.textDim, marginTop: 2 }]} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right}
      <Pressable
        onPress={onClose}
        hitSlop={12}
        accessibilityRole="button"
        accessibilityLabel="Close"
        style={headerStyles.closeBtn}
      >
        <Ionicons name="close" size={24} color={color.textDim} />
      </Pressable>
    </View>
  )
}

const styles = StyleSheet.create({
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#000' },
  card: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: SHEET_RADIUS,
    borderTopRightRadius: SHEET_RADIUS,
    borderWidth: 1,
    borderBottomWidth: 0,
    overflow: 'hidden',
  },
  grip: { alignItems: 'center', paddingVertical: 10 },
  handle: { width: 40, height: 5, borderRadius: 3 },
})

const headerStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
  },
  closeBtn: { padding: space.xs },
})
