import { useEffect, useState } from 'react'
import { Stack, useRouter, useSegments } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { View } from 'react-native'
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
  const [ready, setReady] = useState(false)
  const [signedIn, setSignedIn] = useState(false)
  const segments = useSegments()
  const router = useRouter()

  useEffect(() => {
    hasSession()
      .then(setSignedIn)
      .finally(() => setReady(true))
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
