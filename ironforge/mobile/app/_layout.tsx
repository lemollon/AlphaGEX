import { useEffect, useState } from 'react'
import { Stack, useRouter, useSegments } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { View } from 'react-native'
import { useFonts } from 'expo-font'
// DEEP imports, one weight per line. The package barrels
// (`@expo-google-fonts/inter`) re-export every weight AND italic, and Metro bundles
// every .ttf it can reach — measured at 18 Inter + 6 Oswald faces, ~8 MB of dead
// weight in the app. These five are the only faces theme/tokens.ts names.
import { Oswald_500Medium } from '@expo-google-fonts/oswald/500Medium'
import { Oswald_600SemiBold } from '@expo-google-fonts/oswald/600SemiBold'
import { Inter_400Regular } from '@expo-google-fonts/inter/400Regular'
import { Inter_500Medium } from '@expo-google-fonts/inter/500Medium'
import { Inter_700Bold } from '@expo-google-fonts/inter/700Bold'
import { hasSession } from '@/api/client'
import { color } from '@/theme/tokens'
import { Loading } from '@/components/ui'

/**
 * Root layout + auth gate.
 *
 * Presence of a REFRESH token is the signal, not an access token: the access token is
 * short-lived and routinely expired at cold start, so gating on it would bounce a
 * perfectly valid session to sign-in on every launch.
 */
export default function RootLayout() {
  const [sessionChecked, setSessionChecked] = useState(false)
  const [signedIn, setSignedIn] = useState(false)
  const segments = useSegments()
  const router = useRouter()

  /**
   * tokens.ts has always claimed these were "Loaded in app/_layout.tsx". They were not,
   * and expo-font was not even a dependency — so every `fontFamily: font.display` fell
   * through to the system face and the app never rendered the approved type. Loading
   * them here is what makes Oswald/Inter real.
   *
   * `fontError` is not fatal: shipping a readable app in the fallback face beats a
   * blank screen because a font CDN blipped at first launch.
   */
  const [fontsLoaded, fontError] = useFonts({
    Oswald_500Medium,
    Oswald_600SemiBold,
    Inter_400Regular,
    Inter_500Medium,
    Inter_700Bold,
  })

  const ready = sessionChecked && (fontsLoaded || !!fontError)

  useEffect(() => {
    hasSession()
      .then(setSignedIn)
      .finally(() => setSessionChecked(true))
  }, [])

  useEffect(() => {
    if (!ready) return
    const inAuthGroup = segments[0] === 'sign-in'
    if (!signedIn && !inAuthGroup) router.replace('/sign-in')
    else if (signedIn && inAuthGroup) router.replace('/')
  }, [ready, signedIn, segments, router])

  if (!ready) {
    return (
      <View style={{ flex: 1, backgroundColor: color.bg }}>
        <Loading label="Starting IronForge…" />
      </View>
    )
  }

  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: color.bg },
        }}
      />
    </>
  )
}
