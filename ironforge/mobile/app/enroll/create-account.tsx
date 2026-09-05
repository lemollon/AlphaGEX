import { useState } from 'react'
import { View, Text, Pressable } from 'react-native'
import { useRouter } from 'expo-router'
import { apiPublic } from '@/api/client'
import { color, space, type, font } from '@/theme/tokens'
import { Button, TextField } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { validateSignup, type SignupFields, type SignupErrors } from '@/enroll/signup-validation'

/**
 * Create account (UAT #6, screen 1 of 9) — POST /api/auth/signup.
 *
 * All nine fields the server actually requires (webapp/src/lib/signup-validation.ts)
 * are collected here, not just the name/email/password the approved mock shows —
 * username, phone, state, and the three legal acknowledgements are mandatory server
 * side and there is no other screen in this funnel that collects them.
 */
export default function CreateAccountScreen() {
  const router = useRouter()
  const [fields, setFields] = useState<SignupFields>({
    firstName: '',
    lastName: '',
    username: '',
    email: '',
    phone: '',
    state: '',
    password: '',
    confirmPassword: '',
    ageConfirmed: false,
    noAdviceAcknowledged: false,
    electronicCommConsent: false,
  })
  const [errors, setErrors] = useState<SignupErrors>({})
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  function set<K extends keyof SignupFields>(key: K, value: SignupFields[K]) {
    setFields((f) => ({ ...f, [key]: value }))
  }

  async function submit() {
    const result = validateSignup(fields)
    setErrors(result.errors)
    if (!result.ok || busy) return
    setBusy(true)
    setServerError(null)
    try {
      await apiPublic('/api/auth/signup', { ...fields, referralCode: '' })
      router.push({ pathname: '/enroll/verify', params: { email: fields.email.trim().toLowerCase() } })
    } catch (e) {
      setServerError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnrollShell title="Create your account" step={1} error={serverError}>
      <TextField
        label="First name"
        value={fields.firstName}
        onChangeText={(v) => set('firstName', v)}
        error={errors.firstName}
        autoCapitalize="words"
      />
      <TextField
        label="Last name"
        value={fields.lastName}
        onChangeText={(v) => set('lastName', v)}
        error={errors.lastName}
        autoCapitalize="words"
      />
      <TextField
        label="Username"
        value={fields.username}
        onChangeText={(v) => set('username', v)}
        error={errors.username}
        autoCapitalize="none"
        autoCorrect={false}
      />
      <TextField
        label="Email"
        value={fields.email}
        onChangeText={(v) => set('email', v)}
        error={errors.email}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        textContentType="username"
      />
      <TextField
        label="Mobile phone"
        value={fields.phone}
        onChangeText={(v) => set('phone', v)}
        error={errors.phone}
        keyboardType="phone-pad"
        placeholder="(555) 123-4567"
      />
      <TextField
        label="State of residence"
        value={fields.state}
        onChangeText={(v) => set('state', v.toUpperCase().slice(0, 2))}
        error={errors.state}
        autoCapitalize="characters"
        maxLength={2}
        placeholder="WI"
      />
      <TextField
        label="Password"
        value={fields.password}
        onChangeText={(v) => set('password', v)}
        error={errors.password}
        secureTextEntry
        textContentType="newPassword"
      />
      <Text style={[type.label, { color: color.muted, marginTop: -space.md, marginBottom: space.lg }]}>
        12+ characters, upper, lower, number, and a special character.
      </Text>
      <TextField
        label="Confirm password"
        value={fields.confirmPassword}
        onChangeText={(v) => set('confirmPassword', v)}
        error={errors.confirmPassword}
        secureTextEntry
        textContentType="newPassword"
      />

      <Checkbox
        checked={fields.ageConfirmed}
        onToggle={() => set('ageConfirmed', !fields.ageConfirmed)}
        label="I confirm I am at least 18 years old."
        error={errors.ageConfirmed}
      />
      <Checkbox
        checked={fields.noAdviceAcknowledged}
        onToggle={() => set('noAdviceAcknowledged', !fields.noAdviceAcknowledged)}
        label="I understand IronForge does not provide individualized investment advice."
        error={errors.noAdviceAcknowledged}
      />
      <Checkbox
        checked={fields.electronicCommConsent}
        onToggle={() => set('electronicCommConsent', !fields.electronicCommConsent)}
        label="I consent to receive account communications electronically."
        error={errors.electronicCommConsent}
      />

      <View style={{ marginTop: space.lg }}>
        <Button label="Continue" onPress={submit} busy={busy} />
      </View>
    </EnrollShell>
  )
}

function Checkbox({
  checked,
  onToggle,
  label,
  error,
}: {
  checked: boolean
  onToggle: () => void
  label: string
  error?: string
}) {
  return (
    <Pressable
      onPress={onToggle}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      style={{ flexDirection: 'row', gap: space.md, marginBottom: space.md, alignItems: 'flex-start' }}
    >
      <View
        style={{
          width: 20,
          height: 20,
          borderRadius: 4,
          borderWidth: 1.5,
          borderColor: checked ? color.accent : color.border,
          backgroundColor: checked ? color.accent : 'transparent',
          alignItems: 'center',
          justifyContent: 'center',
          marginTop: 1,
        }}
      >
        {checked ? <Text style={{ color: color.text, fontSize: 13, fontWeight: '700' }}>✓</Text> : null}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[type.body, { color: color.text }]}>{label}</Text>
        {error ? <Text style={[type.label, { color: color.neg, marginTop: 2 }]}>{error}</Text> : null}
      </View>
    </Pressable>
  )
}
