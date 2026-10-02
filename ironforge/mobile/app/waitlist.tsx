import { useMemo, useState } from 'react'
import {
  View,
  Text,
  TextInput,
  Pressable,
  ScrollView,
  Modal,
  StyleSheet,
} from 'react-native'
import type { TextInputProps } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { ApiError } from '@/api/client'
import { submitWaitlist } from '@/waitlist/api'
import {
  validateWaitlist,
  normalizePhone,
  CAPITAL_RANGES,
  CONSENT_COPY,
  US_STATES,
  type WaitlistFields,
  type WaitlistErrors,
  type CapitalRange,
} from '@/waitlist/validation'

const INITIAL: WaitlistFields = {
  firstName: '',
  lastName: '',
  email: '',
  phone: '',
  city: '',
  state: '',
  tradingCapitalRange: '',
  communicationConsent: false,
}

/**
 * Join the Waitlist (screen 2 of 3) — POST /api/waitlist, the same public,
 * unauthenticated endpoint the web /waitlist form already calls live. Field rules
 * mirror webapp/src/lib/waitlist.ts via src/waitlist/validation.ts; the server is
 * still the authority and is what actually decides acceptance.
 */
export default function WaitlistScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()
  const [fields, setFields] = useState<WaitlistFields>(INITIAL)
  const [errors, setErrors] = useState<WaitlistErrors>({})
  const [statePickerOpen, setStatePickerOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  function set<K extends keyof WaitlistFields>(key: K, value: WaitlistFields[K]) {
    setFields((f) => ({ ...f, [key]: value }))
  }

  // Live validity drives the submit button's disabled state; the error TEXT under each
  // field only appears after a submit attempt (same split as enroll/create-account.tsx)
  // so a first-time visitor doesn't see a wall of red before typing anything.
  const liveErrors = useMemo(() => validateWaitlist(fields), [fields])
  const valid = Object.keys(liveErrors).length === 0

  async function submit() {
    const fieldErrors = validateWaitlist(fields)
    setErrors(fieldErrors)
    if (Object.keys(fieldErrors).length > 0 || busy) return
    setBusy(true)
    setServerError(null)
    try {
      await submitWaitlist({
        firstName: fields.firstName.trim(),
        lastName: fields.lastName.trim(),
        email: fields.email.trim(),
        phone: normalizePhone(fields.phone),
        city: fields.city.trim(),
        state: fields.state.trim().toUpperCase(),
        tradingCapitalRange: fields.tradingCapitalRange as CapitalRange,
        communicationConsent: true,
      })
      router.replace('/waitlist-success')
    } catch (e) {
      setServerError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <View style={s.header}>
        {router.canGoBack() ? (
          <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
            <Ionicons name="chevron-back" size={26} color={color.text} />
          </Pressable>
        ) : (
          <View style={{ width: 26 }} />
        )}
        <Text style={s.wordmark}>
          IRON<Text style={{ color: color.wordmark }}>FORGE</Text>
        </Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={s.title}>Join the Waitlist</Text>
        <Text style={s.subtitle}>Secure your early access. Spots are limited.</Text>

        {serverError ? (
          <View style={s.errorBanner}>
            <Text style={[type.body, { color: color.neg }]}>{serverError}</Text>
          </View>
        ) : null}

        <SectionLabel color={color}>Contact Information</SectionLabel>
        <View style={s.row}>
          <View style={{ flex: 1 }}>
            <Field
              color={color}
              label="First Name *"
              value={fields.firstName}
              onChangeText={(v) => set('firstName', v)}
              error={errors.firstName}
              autoCapitalize="words"
            />
          </View>
          <View style={{ flex: 1 }}>
            <Field
              color={color}
              label="Last Name *"
              value={fields.lastName}
              onChangeText={(v) => set('lastName', v)}
              error={errors.lastName}
              autoCapitalize="words"
            />
          </View>
        </View>
        <Field
          color={color}
          label="Email Address"
          value={fields.email}
          onChangeText={(v) => set('email', v)}
          error={errors.email}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          textContentType="username"
        />
        <Field
          color={color}
          label="Phone Number"
          value={fields.phone}
          onChangeText={(v) => set('phone', v)}
          error={errors.phone}
          keyboardType="phone-pad"
          placeholder="(555) 123-4567"
        />

        <SectionLabel color={color}>Location</SectionLabel>
        <View style={s.row}>
          <View style={{ flex: 1 }}>
            <Field
              color={color}
              label="City"
              value={fields.city}
              onChangeText={(v) => set('city', v)}
              error={errors.city}
              autoCapitalize="words"
            />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.fieldLabel}>State</Text>
            <Pressable
              onPress={() => setStatePickerOpen(true)}
              style={[s.input, errors.state && { borderColor: color.neg }]}
            >
              <Text style={fields.state ? s.inputText : s.inputPlaceholder}>
                {fields.state || 'Select'}
              </Text>
            </Pressable>
            {errors.state ? <Text style={s.fieldError}>{errors.state}</Text> : null}
          </View>
        </View>

        <SectionLabel color={color}>Trading Profile</SectionLabel>
        <Text style={s.radioQuestion}>How much capital do you expect to actively trade? *</Text>
        <View style={{ marginBottom: space.lg }}>
          {CAPITAL_RANGES.map((r) => (
            <RadioRow
              key={r.value}
              color={color}
              label={r.label}
              selected={fields.tradingCapitalRange === r.value}
              onPress={() => set('tradingCapitalRange', r.value)}
            />
          ))}
        </View>
        {errors.tradingCapitalRange ? <Text style={s.fieldError}>{errors.tradingCapitalRange}</Text> : null}

        <Pressable
          onPress={() => set('communicationConsent', !fields.communicationConsent)}
          accessibilityRole="checkbox"
          accessibilityState={{ checked: fields.communicationConsent }}
          style={s.consentRow}
        >
          <View
            style={[
              s.checkbox,
              fields.communicationConsent && { backgroundColor: color.accent, borderColor: color.accent },
            ]}
          >
            {fields.communicationConsent ? (
              <Text style={{ color: color.text, fontSize: 13, fontWeight: '700' }}>{'✓'}</Text>
            ) : null}
          </View>
          <Text style={s.consentText}>{CONSENT_COPY}</Text>
        </Pressable>
        {errors.communicationConsent ? (
          <Text style={s.fieldError}>{errors.communicationConsent}</Text>
        ) : null}

        <Pressable
          onPress={submit}
          disabled={!valid || busy}
          style={[s.submit, (!valid || busy) && { opacity: 0.5 }]}
        >
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>
            {busy ? 'Submitting…' : 'Join the Waitlist'}
          </Text>
        </Pressable>

        <Text style={s.footer}>
          We respect your privacy. Your information will never be shared.
        </Text>
      </ScrollView>

      <StatePickerModal
        visible={statePickerOpen}
        selected={fields.state}
        onSelect={(v) => {
          set('state', v)
          setStatePickerOpen(false)
        }}
        onClose={() => setStatePickerOpen(false)}
      />
    </SafeAreaView>
  )
}

function SectionLabel({ color, children }: { color: ColorTokens; children: string }) {
  const s = useMemo(() => makeStyles(color), [color])
  return <Text style={s.sectionLabel}>{children.toUpperCase()}</Text>
}

function Field({
  color,
  label,
  error,
  ...inputProps
}: {
  color: ColorTokens
  label: string
  error?: string
} & TextInputProps) {
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <View style={{ marginBottom: space.lg }}>
      <Text style={s.fieldLabel}>{label}</Text>
      <TextInput
        placeholderTextColor={color.muted}
        style={[s.input, error && { borderColor: color.neg }]}
        {...inputProps}
      />
      {error ? <Text style={s.fieldError}>{error}</Text> : null}
    </View>
  )
}

function RadioRow({
  color,
  label,
  selected,
  onPress,
}: {
  color: ColorTokens
  label: string
  selected: boolean
  onPress: () => void
}) {
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      style={s.radioRow}
    >
      <View style={[s.radioCircle, selected && { borderColor: color.accent }]}>
        {selected ? <View style={[s.radioDot, { backgroundColor: color.accent }]} /> : null}
      </View>
      <Text style={[type.body, { color: color.text }]}>{label}</Text>
    </Pressable>
  )
}

function StatePickerModal({
  visible,
  selected,
  onSelect,
  onClose,
}: {
  visible: boolean
  selected: string
  onSelect: (v: string) => void
  onClose: () => void
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel="Dismiss" />
      <View style={s.sheet}>
        <Text style={[type.label, { color: color.muted, marginBottom: space.md }]}>Select state</Text>
        <ScrollView style={{ maxHeight: 360 }}>
          {US_STATES.map((st) => (
            <Pressable key={st} onPress={() => onSelect(st)} style={s.sheetRow}>
              <Text style={[type.body, { color: st === selected ? color.accent : color.text }]}>{st}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <Pressable onPress={onClose} style={s.sheetRow}>
          <Text style={[type.body, { color: color.textDim }]}>Cancel</Text>
        </Pressable>
      </View>
    </Modal>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: color.bg },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: space.lg,
      paddingVertical: space.md,
      borderBottomColor: color.border,
      borderBottomWidth: 1,
    },
    wordmark: {
      fontFamily: font.display,
      fontSize: 18,
      letterSpacing: 1,
      color: color.text,
    },
    title: {
      ...type.title,
      fontFamily: font.display,
      color: color.text,
      marginTop: space.lg,
    },
    subtitle: {
      ...type.body,
      color: color.textDim,
      marginTop: space.xs,
      marginBottom: space.xl,
    },
    errorBanner: {
      borderWidth: 1,
      borderColor: color.neg,
      borderRadius: radius.md,
      padding: space.md,
      marginBottom: space.lg,
    },
    sectionLabel: {
      ...type.section,
      color: color.accent,
      fontFamily: font.bodyBold,
      marginTop: space.lg,
      marginBottom: space.md,
    },
    row: { flexDirection: 'row', gap: space.md },
    fieldLabel: {
      ...type.label,
      color: color.textDim,
      marginBottom: space.xs,
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
      justifyContent: 'center',
      minHeight: 50,
    },
    inputText: { color: color.text, fontSize: 16 },
    inputPlaceholder: { color: color.muted, fontSize: 16 },
    fieldError: { ...type.label, color: color.neg, marginTop: space.xs },
    radioQuestion: {
      ...type.body,
      color: color.text,
      fontFamily: font.bodyMedium,
      marginBottom: space.md,
    },
    radioRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: space.md,
      paddingVertical: space.md,
      borderBottomColor: color.border,
      borderBottomWidth: 1,
    },
    radioCircle: {
      width: 20,
      height: 20,
      borderRadius: 10,
      borderWidth: 1.5,
      borderColor: color.border,
      alignItems: 'center',
      justifyContent: 'center',
    },
    radioDot: { width: 10, height: 10, borderRadius: 5 },
    consentRow: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: space.md,
      marginTop: space.lg,
    },
    checkbox: {
      width: 20,
      height: 20,
      borderRadius: 4,
      borderWidth: 1.5,
      borderColor: color.border,
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: 1,
    },
    consentText: { ...type.body, color: color.text, flex: 1 },
    submit: {
      backgroundColor: color.accent,
      borderRadius: radius.md,
      paddingVertical: space.lg,
      alignItems: 'center',
      marginTop: space.xl,
    },
    footer: {
      ...type.label,
      color: color.textDim,
      textAlign: 'center',
      marginTop: space.lg,
    },
    scrim: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)' },
    sheet: {
      position: 'absolute',
      left: space.lg,
      right: space.lg,
      top: '20%',
      backgroundColor: color.card,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: color.border,
      padding: space.lg,
    },
    sheetRow: {
      paddingVertical: space.md,
      borderTopColor: color.border,
      borderTopWidth: StyleSheet.hairlineWidth,
    },
  })
