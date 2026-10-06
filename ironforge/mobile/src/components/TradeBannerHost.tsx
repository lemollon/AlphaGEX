/**
 * The floating "trade opened/closed" banner (10.4 design `.banner` — avatar, title,
 * subtitle, slides in from the top, auto-dismisses, tap to navigate). Mounted once in
 * app/_layout.tsx, signed-in and unlocked only.
 *
 * Fed by expo-notifications' foreground listener (the SAME push channel push.ts
 * already registers this device for) rather than a second poll loop — a trade_opened/
 * trade_closed push is a real server-side trade event, exactly the "real data" this
 * banner is required to use. `tradeBannerFromNotification` (alerts/trade-banner.ts)
 * decides whether a given payload is one of those two kinds and, if so, what to show;
 * this component is presentation + the listener wiring only.
 */
import { useEffect, useRef, useState } from 'react'
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'
import * as Notifications from 'expo-notifications'
import { tradeBannerFromNotification, type TradeBanner } from '@/alerts/trade-banner'
import { Mascot } from '@/components/Brand'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'

/** Design's prototype banner lingers roughly this long before sliding back out. */
const BANNER_DURATION_MS = 4800

export function TradeBannerHost() {
  const { colors: color } = useTheme()
  const router = useRouter()
  const [banner, setBanner] = useState<TradeBanner | null>(null)
  const translateY = useRef(new Animated.Value(-140)).current
  const opacity = useRef(new Animated.Value(0)).current
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    const sub = Notifications.addNotificationReceivedListener((event) => {
      const content = event.request.content
      const data = (content.data ?? null) as Record<string, unknown> | null
      const next = tradeBannerFromNotification({ title: content.title, body: content.body, data })
      if (!next) return
      show(next)
    })
    return () => sub.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- show() closes over stable Animated refs
  }, [])

  function show(next: TradeBanner) {
    if (hideTimer.current) clearTimeout(hideTimer.current)
    setBanner(next)
    translateY.stopAnimation()
    opacity.stopAnimation()
    Animated.parallel([
      Animated.spring(translateY, { toValue: 0, useNativeDriver: true, bounciness: 6 }),
      Animated.timing(opacity, { toValue: 1, duration: 220, useNativeDriver: true }),
    ]).start()
    hideTimer.current = setTimeout(hide, BANNER_DURATION_MS)
  }

  function hide() {
    Animated.parallel([
      Animated.timing(translateY, { toValue: -140, duration: 240, useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: true }),
    ]).start(({ finished }) => {
      if (finished) setBanner(null)
    })
  }

  function onPress() {
    if (!banner) return
    const href = banner.href
    hide()
    if (href) router.push(href)
  }

  if (!banner) return null

  return (
    <Animated.View
      pointerEvents="box-none"
      style={[styles.wrap, { opacity, transform: [{ translateY }] }]}
    >
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={`${banner.title}. ${banner.subtitle}`}
        style={[styles.card, { backgroundColor: color.card, borderColor: color.border }]}
      >
        {banner.bot ? (
          <View style={[styles.avatar, { backgroundColor: color.bg }]}>
            <Mascot bot={banner.bot} size={28} />
          </View>
        ) : null}
        <View style={{ flex: 1 }}>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]} numberOfLines={1}>
            {banner.title}
          </Text>
          {banner.subtitle ? (
            <Text style={[type.label, { color: color.textDim, marginTop: 2 }]} numberOfLines={1}>
              {banner.subtitle}
            </Text>
          ) : null}
        </View>
      </Pressable>
    </Animated.View>
  )
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    top: 54,
    left: 10,
    right: 10,
    zIndex: 70,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.md,
    borderRadius: radius.lg + 2,
    borderWidth: 1,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 6,
  },
  avatar: { width: 38, height: 38, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
})
