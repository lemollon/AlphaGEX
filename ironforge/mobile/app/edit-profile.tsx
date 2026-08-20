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
import useSWR, { mutate as globalMutate } from 'swr'
import { api } from '@/api/client'
import type { MobileMe, ProfileResponse } from '@/api/types'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Loading, ErrorState } from '@/components/ui'

/**
 * Edit Profile — APP-058.
 *
 * Name only. The email field is shown but NOT editable, and says why: changing the login
 * address needs a verification round-trip before it takes effect, and the endpoint
 * rejects an email in the body rather than silently ignoring it. A disabled field with a
 * reason is honest; an editable one that quietly does nothing is not.
 */
export default function EditProfileScreen() {
  const router = useRouter()
  const { data, error, isLoading, mutate } = useSWR<MobileMe>('/api/auth/mobile/me', (p: string) =>
    api<MobileMe>(p),
  )

  const [first, setFirst] = useState<string | null>(null)
  const [last, setLast] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const c = data?.customer
  // null means "not edited yet" — fall back to the server value without clobbering an
  // intentional empty string while typing.
  const firstValue = first ?? c?.firstName ?? ''
  const lastValue = last ?? c?.lastName ?? ''
  const dirty =
    firstValue.trim() !== (c?.firstName ?? '') || lastValue.trim() !== (c?.lastName ?? '')
  const ready = !!firstValue.trim() && !!lastValue.trim() && dirty && !busy

  async function save() {
    if (!ready) return
    setBusy(true)
    setSaveError(null)
    try {
      await api<ProfileResponse>('/api/account/profile', {
        method: 'PUT',
        body: { firstName: firstValue.trim(), lastName: lastValue.trim() },
      })
      // Re-read rather than patching the cache by hand: the server normalises the name
      // (whitespace, control characters) and its version is the one that is stored.
      await mutate()
      await globalMutate('/api/auth/mobile/me')
      router.back()
    } catch (e) {
      setSaveError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <View style={s.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={26} color={color.text} />
        </Pressable>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
          Edit Profile
        </Text>
      </View>

      {isLoading ? (
        <Loading />
      ) : error ? (
        <ErrorState message={String((error as Error).message)} onRetry={() => mutate()} />
      ) : (
        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <ScrollView contentContainerStyle={{ padding: space.lg }} keyboardShouldPersistTaps="handled">
            <Field label="First name" value={firstValue} onChange={setFirst} />
            <Field label="Last name" value={lastValue} onChange={setLast} />

            <View style={{ marginBottom: space.lg }}>
              <Text style={[type.label, { color: color.textDim, marginBottom: space.sm }]}>
                Email address
              </Text>
              <View style={[s.input, s.disabled]}>
                <Text style={[type.body, { color: color.muted }]}>{c?.email ?? '—'}</Text>
              </View>
              <Text style={[type.label, { color: color.muted, marginTop: space.sm }]}>
                This is your sign-in address. Changing it has to be verified first — contact
                support and we will move it for you.
              </Text>
            </View>

            {saveError ? (
              <Text style={[type.body, { color: color.neg, marginTop: space.sm }]}>{saveError}</Text>
            ) : null}

            <Pressable onPress={save} disabled={!ready} style={[s.primary, !ready && { opacity: 0.4 }]}>
              <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
                {busy ? 'Saving…' : 'Save changes'}
              </Text>
            </Pressable>
          </ScrollView>
        </KeyboardAvoidingView>
      )}
    </SafeAreaView>
  )
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <View style={{ marginBottom: space.lg }}>
      <Text style={[type.label, { color: color.textDim, marginBottom: space.sm }]}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        autoCapitalize="words"
        autoCorrect={false}
        maxLength={60}
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
  disabled: { backgroundColor: color.bg },
  primary: {
    marginTop: space.md,
    backgroundColor: color.accent,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
})
