/**
 * Renders whatever notifications/toast.ts's bus emits — the 10.4 design's floating
 * bottom snackbar (`.toast`), mounted once in app/_layout.tsx so every screen can
 * call `showToast()` without its own host. Pill shape, inverted surface (dark-on-
 * light / light-on-dark, matching the design's `background:var(--fg);color:var(--bg)`
 * regardless of which theme is active), auto-dismiss at TOAST_DURATION_MS, RN
 * Animated only (no native deps beyond what already ships).
 */
import { useEffect, useRef, useState } from 'react'
import { Animated, StyleSheet, Text } from 'react-native'
import { subscribeToast, TOAST_DURATION_MS, type ToastEvent } from '@/notifications/toast'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'

export function ToastHost() {
  const { colors: color } = useTheme()
  const [event, setEvent] = useState<ToastEvent | null>(null)
  const opacity = useRef(new Animated.Value(0)).current
  const translateY = useRef(new Animated.Value(12)).current
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    return subscribeToast((next) => {
      if (hideTimer.current) clearTimeout(hideTimer.current)
      if (!next) {
        hide()
        return
      }
      setEvent(next)
      opacity.stopAnimation()
      translateY.stopAnimation()
      Animated.parallel([
        Animated.timing(opacity, { toValue: 1, duration: 180, useNativeDriver: true }),
        Animated.timing(translateY, { toValue: 0, duration: 180, useNativeDriver: true }),
      ]).start()
      hideTimer.current = setTimeout(hide, TOAST_DURATION_MS)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- opacity/translateY are stable refs
  }, [])

  function hide() {
    Animated.timing(opacity, { toValue: 0, duration: 180, useNativeDriver: true }).start(
      ({ finished }) => {
        if (finished) setEvent(null)
      },
    )
  }

  if (!event) return null

  return (
    <Animated.View
      pointerEvents="none"
      accessibilityLiveRegion="polite"
      style={[
        styles.toast,
        { backgroundColor: color.text, opacity, transform: [{ translateY }] },
      ]}
    >
      <Text style={[type.label, { color: color.bg, fontFamily: font.bodyMedium }]} numberOfLines={2}>
        {event.message}
      </Text>
    </Animated.View>
  )
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute',
    left: space.xl,
    right: space.xl,
    bottom: 96,
    alignSelf: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.pill,
    alignItems: 'center',
    zIndex: 60,
  },
})
