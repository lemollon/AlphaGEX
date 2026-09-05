import { useEffect, useState } from 'react'
import { View, Text } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import * as Device from 'expo-device'
import Constants from 'expo-constants'
import Ionicons from '@expo/vector-icons/Ionicons'
import { apiPublic } from '@/api/client'
import { signIn } from '@/auth/session'
import { registerPushDevice } from '@/notifications/push'
import { color, space, type, font } from '@/theme/tokens'
import { Button, CodeInput, TextField } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { resumeEnrollment } from '@/enroll/api'
import { routeForNextStep } from '@/enroll/steps'
import { isValidVerifyCode } from '@/enroll/verify-code-validation'

const RESEND_COOLDOWN_SEC = 30

/**
 * Verify email (UAT #6, screen 2 of 9) — POST /api/auth/verify-code, then auto
 * sign-in via POST /api/auth/mobile/login and continue at the enrollment's
 * next_step. Replaces the "tap the link" screen from #2965 now that a 6-digit
 * code exists server-side (see verify-code/route.ts).
 *
 * The password typed on the previous screen is forwarded as a route param so this
 * screen can sign in without asking the customer to retype it — see the note on
 * create-account.tsx. If the param is missing (e.g. the app was killed and
 * relaunched mid-flow, which expo-router params do not survive), this screen falls
 * back to asking for the password once, same as the old link-based screen did.
 */
export default function VerifyScreen() {
  const router = useRouter()
  const params = useLocalSearchParams<{ email?: string; password?: string }>()
  const email = String(params.email ?? '')
  const [password, setPassword] = useState(String(params.password ?? ''))
  const needsPassword = !params.password
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resendCooldown, setResendCooldown] = useState(0)

  useEffect(() => {
    if (resendCooldown <= 0) return
    const t = setTimeout(() => setResendCooldown((s) => s - 1), 1000)
    return () => clearTimeout(t)
  }, [resendCooldown])

  async function continueToApp() {
    if (busy) return
    if (!isValidVerifyCode(code)) {
      setError('Enter the 6-digit code from your email.')
      return
    }
    if (!password) {
      setError('Enter your password to continue.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await apiPublic('/api/auth/verify-code', { email, code })
      await signIn(email, password, {
        deviceId: Device.osInternalBuildId ?? undefined,
        platform: 'mobile',
        appVersion: Constants.expoConfig?.version ?? undefined,
      })
      registerPushDevice().catch(() => {})
      const d = await resumeEnrollment()
      const canonical = routeForNextStep(d.next_step, d.enrollment.selected_plan)
      router.replace(canonical.route as never)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    if (resendCooldown > 0) return
    setError(null)
    try {
      await apiPublic('/api/auth/resend-verification', { email })
      setCode('')
      setResendCooldown(RESEND_COOLDOWN_SEC)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <EnrollShell title="Check your email" step={2} error={error}>
      <View style={{ alignItems: 'center', marginBottom: space.xl }}>
        <Ionicons name="mail-outline" size={44} color={color.accent} />
        <Text style={[type.body, { color: color.textDim, textAlign: 'center', marginTop: space.md }]}>
          We sent a 6-digit code to{'\n'}
          <Text style={{ color: color.text, fontFamily: font.bodyBold }}>{email}</Text>. Enter it below to
          verify your email.
        </Text>
      </View>

      <CodeInput value={code} onChangeText={setCode} onSubmitEditing={continueToApp} />

      {needsPassword ? (
        <TextField
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          textContentType="password"
          onSubmitEditing={continueToApp}
        />
      ) : null}

      <Button
        label="Continue"
        onPress={continueToApp}
        busy={busy}
        disabled={code.length !== 6 || !password}
      />

      <View style={{ marginTop: space.lg, alignItems: 'center' }}>
        <Button
          label={resendCooldown > 0 ? `Resend code (${resendCooldown}s)` : 'Resend code'}
          onPress={resend}
          variant="secondary"
          disabled={resendCooldown > 0}
        />
      </View>
    </EnrollShell>
  )
}
