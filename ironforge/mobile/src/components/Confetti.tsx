/**
 * A one-shot confetti burst (mobile addendum §2 "Add-agent sheet": "confetti
 * in agent color on success" — flagged MISSING in the 10.4 gap audit). Pure
 * `Animated` from react-native core, not a new native dependency — the audit
 * item that blocks haptics here (expo-haptics not installed) does not apply:
 * confetti is visual-only.
 *
 * Respects `prefers-reduced-motion` the same way Sheet.tsx already does —
 * AccessibilityInfo.isReduceMotionEnabled, skipping straight to onDone.
 */
import { useEffect, useMemo, useRef } from 'react'
import { Animated, Easing, StyleSheet, View, AccessibilityInfo } from 'react-native'

const PARTICLE_COUNT = 28
const DURATION_MS = 1100

interface Particle {
  dx: number
  dy: number
  rotate: number
  delay: number
  color: string
  size: number
}

export function Confetti({ colors, onDone }: { colors: string[]; onDone?: () => void }) {
  const particles = useMemo<Particle[]>(
    () =>
      Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
        dx: (Math.random() - 0.5) * 260,
        dy: 180 + Math.random() * 120,
        rotate: (Math.random() - 0.5) * 540,
        delay: Math.random() * 100,
        color: colors[i % colors.length] ?? colors[0],
        size: 5 + Math.random() * 6,
      })),
    [colors],
  )
  const progress = useRef(new Animated.Value(0)).current
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    let cancelled = false
    void AccessibilityInfo.isReduceMotionEnabled?.().then((reduced) => {
      if (cancelled) return
      if (reduced) {
        onDoneRef.current?.()
        return
      }
      Animated.timing(progress, {
        toValue: 1,
        duration: DURATION_MS,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start(() => onDoneRef.current?.())
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires exactly once per mount
  }, [])

  return (
    <View style={StyleSheet.absoluteFillObject} pointerEvents="none">
      {particles.map((p, i) => {
        const translateY = progress.interpolate({ inputRange: [0, 1], outputRange: [0, p.dy] })
        const translateX = progress.interpolate({ inputRange: [0, 1], outputRange: [0, p.dx] })
        const opacity = progress.interpolate({ inputRange: [0, 0.75, 1], outputRange: [1, 1, 0] })
        const rotate = progress.interpolate({ inputRange: [0, 1], outputRange: ['0deg', `${p.rotate}deg`] })
        return (
          <Animated.View
            key={i}
            style={[
              styles.particle,
              {
                width: p.size,
                height: p.size,
                backgroundColor: p.color,
                opacity,
                transform: [{ translateX }, { translateY }, { rotate }],
              },
            ]}
          />
        )
      })}
    </View>
  )
}

const styles = StyleSheet.create({
  particle: {
    position: 'absolute',
    top: '18%',
    left: '50%',
    borderRadius: 2,
  },
})
