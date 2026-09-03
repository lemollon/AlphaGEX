import { useState } from 'react'
import { View, Text, TextInput, Pressable, KeyboardAvoidingView, Platform, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { apiPublic } from '@/api/client'
import { track } from '@/analytics/track'
import { color, space, radius, type, font } from '@/theme/tokens'

/**
 * Forgot password (APP-009).
 *
 * The server always answers 200 {ok:true}, even for an email with no account — this
 * screen must never distinguish those two cases, or it hands back the account-
 * enumeration oracle the enrolled/unenrolled split exists to prevent. The confirmation
 * copy is written to be true in both cases at once.
 */
export default function ForgotPasswordScreen() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const ready = email.trim().length > 0 && !busy

  async function submit() {
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      await apiPublic('/api/auth/forgot-password', { email: email.trim() })
      track('forgot_password_requested')
      setDone(true)
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
          <Ionicons name="mail-outline" size={48} color={color.pos} />
          <Text style={[type.title, { color: color.text, fontFamily: font.display, marginTop: space.lg, textAlign: 'center' }]}>
            Check your email
          </Text>
          <Text style={[type.body, { color: color.textDim, textAlign: 'center', marginTop: space.sm }]}>
            If an account exists for that email, a reset link is on its way. The link expires in 1
            hour.
          </Text>
          <Pressable onPress={() => router.replace('/sign-in')} style={s.primary}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              Back to sign in
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
          Forgot Password
        </Text>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={{ padding: space.lg }}>
          <Text style={[type.body, { color: color.textDim, marginBottom: space.lg }]}>
            Enter the email on your IronForge account and we will send you a link to reset your
            password.
          </Text>

          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="Email"
            placeholderTextColor={color.muted}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            textContentType="username"
            onSubmitEditing={submit}
            style={s.input}
          />

          {error ? (
            <Text style={[type.body, { color: color.neg, marginTop: space.lg }]}>{error}</Text>
          ) : null}

          <Pressable onPress={submit} disabled={!ready} style={[s.primary, !ready && { opacity: 0.4 }]}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              {busy ? 'Sending…' : 'Send reset link'}
            </Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
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
  primary: {
    marginTop: space.xl,
    backgroundColor: color.accent,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  doneWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl },
})
