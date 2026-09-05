import { useState } from 'react'
import { View, Text } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import * as Device from 'expo-device'
import Constants from 'expo-constants'
import Ionicons from '@expo/vector-icons/Ionicons'
import { apiPublic } from '@/api/client'
import { signIn } from '@/auth/session'
import { registerPushDevice } from '@/notifications/push'
import { color, space, type, font } from '@/theme/tokens'
import { Button, TextField } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { resumeEnrollment } from '@/enroll/api'
import { routeForNextStep } from '@/enroll/steps'

/**
 * Verify email (UAT #6, screen 2 of 9) — POST /api/auth/resend-verification +
 * POST /api/auth/mobile/login.
 *
 * SPEC/API MISMATCH (see PR description): the approved mock shows a 6-digit code
 * entry ("Check your email — 4 8 2 _ _ _"). No such endpoint exists anywhere in the
 * webapp — email verification is link-based only (GET /api/auth/verify?token=...,
 * which mints a WEB cookie session and is not reachable from a mobile bearer client
 * at all). Building an OTP system server-side is a new auth mechanism, out of scope
 * for this PR. Instead: the customer taps the emailed link (opens in their default
 * browser, verifies email_verified server-side), returns to the app, and enters their
 * password here — POST /api/auth/mobile/login already answers `email_unverified` if
 * the link has not been tapped yet, which this screen surfaces inline. No new API.
 */
export default function VerifyScreen() {
  const router = useRouter()
  const params = useLocalSearchParams<{ email?: string }>()
  const email = String(params.email ?? '')
  const [password, setPassword] = useState('')
  const [resent, setResent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function resend() {
    setError(null)
    try {
      await apiPublic('/api/auth/resend-verification', { email })
      setResent(true)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function continueToApp() {
    if (!password || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await signIn(email, password, {
        deviceId: Device.osInternalBuildId ?? undefined,
        platform: 'mobile',
        appVersion: Constants.expoConfig?.version ?? undefined,
      })
      if (!res.customer.emailVerified) {
        setError('Still not verified — open the link in the email we sent, then try again.')
        return
      }
      registerPushDevice().catch(() => {})
      const d = await resumeEnrollment()
      const canonical = routeForNextStep(d.next_step, d.enrollment.selected_plan)
      router.replace(canonical.route as never)
    } catch (e) {
      const msg = (e as Error).message
      setError(
        msg.toLowerCase().includes('verify')
          ? 'Still not verified — open the link in the email we sent, then try again.'
          : msg,
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnrollShell title="Check your email" step={2} error={error}>
      <View style={{ alignItems: 'center', marginBottom: space.xl }}>
        <Ionicons name="mail-outline" size={44} color={color.accent} />
        <Text style={[type.body, { color: color.textDim, textAlign: 'center', marginTop: space.md }]}>
          We sent a verification link to{'\n'}
          <Text style={{ color: color.text, fontFamily: font.bodyBold }}>{email}</Text>. Open it, then come back
          and enter your password to continue.
        </Text>
      </View>

      <TextField
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        textContentType="password"
        onSubmitEditing={continueToApp}
      />

      <Button label="Continue" onPress={continueToApp} busy={busy} disabled={!password} />

      <View style={{ marginTop: space.lg, alignItems: 'center' }}>
        <Button label={resent ? 'Link sent again' : 'Resend link'} onPress={resend} variant="secondary" />
      </View>
    </EnrollShell>
  )
}
