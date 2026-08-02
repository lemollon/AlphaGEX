import { useState } from 'react'
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
import * as Device from 'expo-device'
import Constants from 'expo-constants'
import { signIn } from '@/auth/session'
import { color, space, radius, type, font } from '@/theme/tokens'

/**
 * Sign-in (APP-007). Enrollment stays on the web for MVP, so there is deliberately no
 * sign-up path here — only credentials for an existing member.
 *
 * The failure copy is identical for "no such account" and "wrong password". The server
 * already refuses to distinguish them (classifyLoginAttempt + a dummy bcrypt compare to
 * flatten timing); echoing anything more specific here would hand back the
 * account-enumeration oracle that design exists to prevent.
 */
export default function SignInScreen() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (busy || !email.trim() || !password) return
    setBusy(true)
    setError(null)
    try {
      await signIn(email.trim(), password, {
        deviceId: Device.osInternalBuildId ?? undefined,
        platform: Platform.OS,
        appVersion: Constants.expoConfig?.version ?? undefined,
      })
      router.replace('/')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.wrap}>
        <Text style={s.wordmark}>
          IRON<Text style={{ color: color.wordmark }}>FORGE</Text>
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
          style={s.input}
        />

        <View style={s.passwordRow}>
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="Password"
            placeholderTextColor={color.muted}
            secureTextEntry={!show}
            autoCapitalize="none"
            textContentType="password"
            style={[s.input, { flex: 1, marginBottom: 0 }]}
            onSubmitEditing={submit}
          />
          <Pressable onPress={() => setShow((v) => !v)} style={s.reveal}>
            <Text style={[type.label, { color: color.textDim }]}>{show ? 'Hide' : 'Show'}</Text>
          </Pressable>
        </View>

        {error ? <Text style={s.error}>{error}</Text> : null}

        <Pressable onPress={submit} disabled={busy} style={[s.button, busy && { opacity: 0.6 }]}>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>
            {busy ? 'Signing in…' : 'Sign In'}
          </Text>
        </Pressable>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  wrap: { flex: 1, justifyContent: 'center', padding: space.xl },
  wordmark: {
    ...type.title,
    fontFamily: font.display,
    color: color.text,
    textAlign: 'center',
    marginBottom: space.xxl,
    letterSpacing: 2,
  },
  input: {
    backgroundColor: color.card,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.lg,
    color: color.text,
    fontSize: 16,
    marginBottom: space.md,
  },
  passwordRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  reveal: { paddingHorizontal: space.md, paddingVertical: space.lg },
  error: { ...type.body, color: color.neg, marginTop: space.md },
  button: {
    backgroundColor: color.accent,
    borderRadius: radius.md,
    paddingVertical: space.lg,
    alignItems: 'center',
    marginTop: space.xl,
  },
})
