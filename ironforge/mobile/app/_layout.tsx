import { useEffect, useRef, useState } from 'react'
import { Stack, useRouter, useSegments } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { View, Text, Pressable, AppState, StyleSheet, type AppStateStatus } from 'react-native'
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
import { hasSession, onSessionChange } from '@/api/client'
import {
  fetchSessionPolicy,
  getStoredSessionPolicy,
  isBiometricEnabled,
  biometricsAvailable,
  unlockWithBiometrics,
  signOut,
} from '@/auth/session'
import { nextLockState, INITIAL_LOCK_STATE, type LockPolicy, type LockState } from '@/auth/lock'
import { color, space, font, type } from '@/theme/tokens'
import { Loading } from '@/components/ui'
import { Wordmark } from '@/components/Brand'

/**
 * Root layout + auth gate + foreground lock (APP-007 / APP-008 / APP-010).
 *
 * Presence of a REFRESH token is the signal, not an access token: the access token is
 * short-lived and routinely expired at cold start, so gating on it would bounce a
 * perfectly valid session to sign-in on every launch.
 *
 * The lock is a THIRD state inside this same gate, not a route. A route would fight the
 * router.replace() below every time the app foregrounds — one gate wins over two
 * competing navigators. All the actual decision logic lives in the pure
 * src/auth/lock.ts state machine; this component is just an AppState listener and a
 * renderer for the overlay.
 */
/** Can the lock overlay actually be answered? Face ID on in Account AND enrolled on the device. */
async function biometricsUsable(): Promise<boolean> {
  try {
    const [enabled, available] = await Promise.all([isBiometricEnabled(), biometricsAvailable()])
    return enabled && available
  } catch {
    return false
  }
}

export default function RootLayout() {
  const [sessionChecked, setSessionChecked] = useState(false)
  const [signedIn, setSignedIn] = useState(false)
  const [lockState, setLockState] = useState<LockState>(INITIAL_LOCK_STATE)
  const [unlocking, setUnlocking] = useState(false)
  const [unlockError, setUnlockError] = useState<string | null>(null)
  const [canUseBiometrics, setCanUseBiometrics] = useState(false)
  /**
   * Did a session already exist when this process launched? Only THAT session needs
   * a cold-start re-prove. A session that appears later in the same process came from
   * the person typing their password on /sign-in seconds ago — locking that one was
   * the 9/4 loop: sign in → "Locked" → "Use password" (= signOut) → sign in → "Locked".
   */
  const bootHadSessionRef = useRef<boolean>(false)
  const segments = useSegments()
  const router = useRouter()

  // AppState's listener callback is registered once and must never read stale state, so
  // signedIn/policy are mirrored into refs alongside the state used for rendering.
  const signedInRef = useRef(false)
  const policyRef = useRef<LockPolicy | null>(null)

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

  /**
   * Read the stored session once at cold start, then STAY SUBSCRIBED. The subscription
   * is the fix for the sign-in loop: without it this state is frozen at its cold-start
   * value, and a successful login was bounced straight back to /sign-in by the gate
   * below (and a sign-out bounced back into the app). See onSessionChange in api/client.
   */
  useEffect(() => {
    hasSession()
      .then((had) => {
        bootHadSessionRef.current = had
        setSignedIn(had)
      })
      .finally(() => setSessionChecked(true))
    return onSessionChange(setSignedIn)
  }, [])

  useEffect(() => {
    signedInRef.current = signedIn
  }, [signedIn])

  /**
   * Cold-start lock decision + policy load. Runs once we know whether there is a
   * session — a signed-out cold start never locks, a signed-in one always does (see
   * nextLockState's 'cold_start' case) until the person proves it's them again.
   */
  useEffect(() => {
    if (!sessionChecked) return
    if (!signedIn) {
      policyRef.current = null
      setLockState(INITIAL_LOCK_STATE)
      return
    }
    let cancelled = false
    ;(async () => {
      const stored = await getStoredSessionPolicy()
      if (cancelled) return
      policyRef.current = stored
      if (bootHadSessionRef.current) {
        // Restored from disk: re-prove identity before showing anything — but ONLY if
        // biometrics can actually answer the lock. With Face ID off, the overlay's sole
        // button is "Use password", which signs out; locking there is not security, it
        // is a forced re-login on every launch (Leron, 9/4). The stored session is the
        // proof in that case; turning Face ID on in Account opts into the lock.
        const usable = await biometricsUsable()
        if (cancelled) return
        setLockState((prev) =>
          usable ? nextLockState(prev, { type: 'cold_start' }, true, stored) : INITIAL_LOCK_STATE,
        )
      } else {
        // Fresh password sign-in in this process: identity was just proven. The
        // background/foreground timer takes over from here.
        setLockState(INITIAL_LOCK_STATE)
      }
      // Consumed: any later sign-in in this process is a fresh one, never a cold start.
      bootHadSessionRef.current = false

      // Refresh from the server in the background; a stale local policy is fine to
      // start on, it just should not stay stale for the rest of the session.
      const fresh = await fetchSessionPolicy()
      if (!cancelled && fresh) policyRef.current = fresh
    })()
    return () => {
      cancelled = true
    }
  }, [sessionChecked, signedIn])

  /** The background/foreground clock that drives everything after cold start. */
  useEffect(() => {
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      const nowMs = Date.now()
      if (next !== 'active') {
        setLockState((prev) =>
          nextLockState(prev, { type: 'app_backgrounded', nowMs }, signedInRef.current, policyRef.current),
        )
        return
      }
      // Same rule as cold start: a foreground re-lock is only meaningful when biometrics
      // can answer it. Re-read the preference each time so a Face ID toggle in Account
      // takes effect without a relaunch.
      biometricsUsable().then((usable) => {
        setLockState((prev) =>
          usable
            ? nextLockState(prev, { type: 'app_foregrounded', nowMs }, signedInRef.current, policyRef.current)
            : { locked: prev.locked, backgroundedAtMs: null },
        )
      })
    })
    return () => sub.remove()
  }, [])

  /** Only worth checking once the lock is actually showing. */
  useEffect(() => {
    if (!lockState.locked) return
    let cancelled = false
    Promise.all([isBiometricEnabled(), biometricsAvailable()])
      .then(([enabled, available]) => {
        if (!cancelled) setCanUseBiometrics(enabled && available)
      })
      .catch(() => {
        if (!cancelled) setCanUseBiometrics(false)
      })
    return () => {
      cancelled = true
    }
  }, [lockState.locked])

  useEffect(() => {
    if (!ready) return
    const inAuthGroup = segments[0] === 'sign-in'
    // 'enroll' is reachable BOTH signed out (create-account, verify — there is no
    // session yet) and signed in (legal onward, once the verify screen auto-signs the
    // customer in). It must never trigger either bounce below: redirecting a signed-out
    // visitor away from /enroll/create-account would make account creation unreachable,
    // and redirecting a signed-in one to '/' the instant they finish verifying would
    // eject them from their own enrollment funnel mid-flow.
    const inEnrollGroup = segments[0] === 'enroll'
    if (!signedIn && !inAuthGroup && !inEnrollGroup) router.replace('/sign-in')
    else if (signedIn && inAuthGroup) router.replace('/')
  }, [ready, signedIn, segments, router])

  async function tryBiometricUnlock() {
    if (unlocking) return
    setUnlocking(true)
    setUnlockError(null)
    try {
      const ok = await unlockWithBiometrics()
      if (ok) {
        setLockState((prev) => nextLockState(prev, { type: 'unlocked' }, true, policyRef.current))
      } else {
        // Cancel, mismatch, or the OS refusing — never distinguish which, and never
        // touch the password or tokens. The lock simply stays up.
        setUnlockError('Try again or use your password.')
      }
    } finally {
      setUnlocking(false)
    }
  }

  async function usePasswordInstead() {
    setUnlockError(null)
    // signOut clears tokens and fires onSessionChange, which flips signedIn false and
    // lets the gate effect above route to /sign-in — no explicit navigation needed here.
    await signOut()
  }

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
      {signedIn && lockState.locked ? (
        <View style={s.overlay}>
          <Wordmark height={32} />
          <Text style={s.locked}>Locked</Text>
          {canUseBiometrics ? (
            <Pressable
              onPress={tryBiometricUnlock}
              disabled={unlocking}
              style={[s.primary, unlocking && { opacity: 0.6 }]}
            >
              <Text style={s.primaryLabel}>
                {unlocking ? 'Checking…' : 'Unlock with Face ID / biometrics'}
              </Text>
            </Pressable>
          ) : null}
          {unlockError ? <Text style={s.error}>{unlockError}</Text> : null}
          <Pressable onPress={usePasswordInstead} style={s.secondary}>
            <Text style={s.secondaryLabel}>Use password</Text>
          </Pressable>
        </View>
      ) : null}
    </>
  )
}

const s = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: color.bg,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.md,
  },
  locked: {
    ...type.title,
    fontFamily: font.display,
    color: color.text,
    marginBottom: space.lg,
  },
  primary: {
    backgroundColor: color.accent,
    borderRadius: 10,
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  primaryLabel: { ...type.body, color: color.text, fontFamily: font.bodyBold },
  secondary: { marginTop: space.sm, padding: space.sm },
  secondaryLabel: { ...type.body, color: color.textDim, fontFamily: font.bodyMedium },
  error: { ...type.label, color: color.neg, textAlign: 'center' },
})
