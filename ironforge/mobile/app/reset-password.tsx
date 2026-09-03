import { useState } from 'react'
import { View, Text, TextInput, Pressable, KeyboardAvoidingView, Platform, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter, useLocalSearchParams } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { apiPublic, clearTokens } from '@/api/client'
import { checkPassword } from '@/auth/password-rules'
import { color, space, radius, type, font } from '@/theme/tokens'

/**
 * Reset password (APP-009) — the far end of the emailed link from forgot-password.tsx.
 *
 * A successful reset revokes every mobile session server-side (see
 * webapp/reset-password/route.ts's revokeAllForUser call), so this device's own tokens
 * are already dead the moment the request succeeds. clearTokens() just makes the local
 * Keychain state match that reality instead of holding refresh tokens the server will
 * reject on the next use.
 */
const RULES = [
  { label: 'At least 12 characters', key: 'minLength' as const },
  { label: 'An uppercase letter', key: 'upper' as const },
  { label: 'A lowercase letter', key: 'lower' as const },
  { label: 'A number', key: 'number' as const },
  { label: 'A special character', key: 'special' as const },
]

export default function ResetPasswordScreen() {
  const router = useRouter()
  const { token } = useLocalSearchParams<{ token?: string }>()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const { valid: passes, rules } = checkPassword(password)
  const matches = confirm.length > 0 && confirm === password
  const ready = !!token && passes && matches && !busy

  async function submit() {
    if (!ready || !token) return
    setBusy(true)
    setError(null)
    try {
      await apiPublic('/api/auth/reset-password', {
        token,
        password,
        confirmPassword: confirm,
      })
      // The server already revoked every session; make the local Keychain agree.
      await clearTokens()
      setDone(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <SafeAreaView style={s.screen} edges={['top']}>
        <View style={s.doneWrap}>
          <Ionicons name="alert-circle-outline" size={48} color={color.neg} />
          <Text style={[type.title, { color: color.text, fontFamily: font.display, marginTop: space.lg, textAlign: 'center' }]}>
            Invalid link
          </Text>
          <Text style={[type.body, { color: color.textDim, textAlign: 'center', marginTop: space.sm }]}>
            This reset link is invalid or has expired.
          </Text>
          <Pressable onPress={() => router.replace('/forgot-password')} style={s.primary}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              Request a new link
            </Text>
          </Pressable>
        </View>
      </SafeAreaView>
    )
  }

  if (done) {
    return (
      <SafeAreaView style={s.screen} edges={['top']}>
        <View style={s.doneWrap}>
          <Ionicons name="checkmark-circle" size={48} color={color.pos} />
          <Text style={[type.title, { color: color.text, fontFamily: font.display, marginTop: space.lg, textAlign: 'center' }]}>
            Password updated
          </Text>
          <Text style={[type.body, { color: color.textDim, textAlign: 'center', marginTop: space.sm }]}>
            Sign in with your new password.
          </Text>
          <Pressable onPress={() => router.replace('/sign-in')} style={s.primary}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              Go to sign in
            </Text>
          </Pressable>
        </View>
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <View style={s.header}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
          Reset Password
        </Text>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={{ padding: space.lg }}>
          <Field
            label="New password"
            value={password}
            onChange={setPassword}
            secure={!reveal}
            autoComplete="new-password"
          />
          <Field
            label="Confirm new password"
            value={confirm}
            onChange={setConfirm}
            secure={!reveal}
            autoComplete="new-password"
          />

          <Pressable onPress={() => setReveal((v) => !v)} style={s.revealRow} hitSlop={8}>
            <Ionicons
              name={reveal ? 'eye-off-outline' : 'eye-outline'}
              size={18}
              color={color.textDim}
            />
            <Text style={[type.label, { color: color.textDim }]}>
              {reveal ? 'Hide passwords' : 'Show passwords'}
            </Text>
          </Pressable>

          <View style={s.rules}>
            {RULES.map((r) => {
              const ok = rules[r.key]
              return (
                <View key={r.key} style={s.ruleRow}>
                  <Ionicons
                    name={ok ? 'checkmark-circle' : 'ellipse-outline'}
                    size={15}
                    color={ok ? color.pos : color.muted}
                  />
                  <Text style={[type.label, { color: ok ? color.textDim : color.muted }]}>
                    {r.label}
                  </Text>
                </View>
              )
            })}
            <View style={s.ruleRow}>
              <Ionicons
                name={matches ? 'checkmark-circle' : 'ellipse-outline'}
                size={15}
                color={matches ? color.pos : color.muted}
              />
              <Text style={[type.label, { color: matches ? color.textDim : color.muted }]}>
                Both entries match
              </Text>
            </View>
          </View>

          {error ? (
            <Text style={[type.body, { color: color.neg, marginTop: space.lg }]}>{error}</Text>
          ) : null}

          <Pressable onPress={submit} disabled={!ready} style={[s.primary, !ready && { opacity: 0.4 }]}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              {busy ? 'Updating…' : 'Update password'}
            </Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

function Field({
  label,
  value,
  onChange,
  secure,
  autoComplete,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  secure: boolean
  autoComplete: 'new-password'
}) {
  return (
    <View style={{ marginBottom: space.lg }}>
      <Text style={[type.label, { color: color.textDim, marginBottom: space.sm }]}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        secureTextEntry={secure}
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete={autoComplete}
        textContentType="newPassword"
        style={s.input}
      />
    </View>
  )
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomColor: color.border,
    borderBottomWidth: 1,
  },
  input: {
    backgroundColor: color.card,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    color: color.text,
    fontSize: 16,
  },
  revealRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rules: { marginTop: space.lg, gap: space.sm },
  ruleRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  primary: {
    marginTop: space.xl,
    backgroundColor: color.accent,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  doneWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl },
})
