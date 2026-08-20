import { useState } from 'react'
import {
  View,
  Text,
  ScrollView,
  TextInput,
  Pressable,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { api } from '@/api/client'
import { signOut } from '@/auth/session'
import { color, space, radius, type, font } from '@/theme/tokens'

/**
 * Change Password — APP-059.
 *
 * Posts to /api/auth/change-password, which is customer-session guarded with
 * verifyEpoch and enforces the same strength rules as signup. That route ALSO calls
 * revokeAllForUser, so a successful change kills every session including this device's
 * — by design, since a password change is how you evict someone who has your account.
 * The screen therefore signs out locally and returns to sign-in rather than pretending
 * the session survived and dying on the next request.
 *
 * Rules are shown BEFORE the attempt, live. Making someone submit to discover the policy
 * is the most common way this screen wastes people's time.
 */
const RULES = [
  { label: 'At least 12 characters', test: (v: string) => v.length >= 12 },
  { label: 'An uppercase letter', test: (v: string) => /[A-Z]/.test(v) },
  { label: 'A lowercase letter', test: (v: string) => /[a-z]/.test(v) },
  { label: 'A number', test: (v: string) => /[0-9]/.test(v) },
  { label: 'A special character', test: (v: string) => /[^A-Za-z0-9]/.test(v) },
]

export default function ChangePasswordScreen() {
  const router = useRouter()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const passes = RULES.every((r) => r.test(next))
  const matches = next.length > 0 && next === confirm
  const ready = current.length > 0 && passes && matches && !busy

  async function submit() {
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      await api('/api/auth/change-password', {
        method: 'POST',
        body: { currentPassword: current, newPassword: next },
      })
      setDone(true)
      // The server revoked every session, this device's included.
      await signOut()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <SafeAreaView style={s.screen} edges={['top']}>
        <View style={s.doneWrap}>
          <Ionicons name="checkmark-circle" size={48} color={color.pos} />
          <Text style={[type.title, { color: color.text, fontFamily: font.display, marginTop: space.lg }]}>
            Password changed
          </Text>
          <Text style={[type.body, { color: color.textDim, textAlign: 'center', marginTop: space.sm }]}>
            For your security you have been signed out everywhere. Sign in again with your new
            password.
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
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={26} color={color.text} />
        </Pressable>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
          Change Password
        </Text>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={{ padding: space.lg }} keyboardShouldPersistTaps="handled">
          <Field
            label="Current password"
            value={current}
            onChange={setCurrent}
            secure={!reveal}
            autoComplete="current-password"
          />
          <Field
            label="New password"
            value={next}
            onChange={setNext}
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
              const ok = r.test(next)
              return (
                <View key={r.label} style={s.ruleRow}>
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
                Both new entries match
              </Text>
            </View>
          </View>

          {error ? (
            <Text style={[type.body, { color: color.neg, marginTop: space.lg }]}>{error}</Text>
          ) : null}

          <Text style={[type.label, { color: color.muted, marginTop: space.lg }]}>
            Changing your password signs you out on every device.
          </Text>

          <Pressable onPress={submit} disabled={!ready} style={[s.primary, !ready && { opacity: 0.4 }]}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              {busy ? 'Changing…' : 'Change password'}
            </Text>
          </Pressable>
        </ScrollView>
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
  autoComplete: 'current-password' | 'new-password'
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
        textContentType={autoComplete === 'current-password' ? 'password' : 'newPassword'}
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
