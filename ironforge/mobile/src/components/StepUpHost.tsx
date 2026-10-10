/**
 * Renders whatever auth/stepUp.ts's bus emits — the Face ID + password gate in front
 * of billing and brokerage changes (mobile fidelity #273). Mounted once in
 * app/_layout.tsx, same shape as ToastHost, so any screen can `await requestStepUp()`
 * without its own modal.
 *
 * Face ID runs FIRST, automatically, the moment a request comes in — not behind a
 * button, since its whole purpose is a fast presence check before the password even
 * appears. A cancel or mismatch there aborts the request outright; it never silently
 * falls through to the password step on a FAILED biometric, only on biometrics being
 * unavailable/off in the first place (see auth/stepUp.ts's biometricPresenceCheck).
 */
import { useEffect, useState } from 'react'
import { Modal, View, Text, TextInput, Pressable, ActivityIndicator, StyleSheet } from 'react-native'
import { api, ApiError } from '@/api/client'
import { subscribeStepUp, biometricPresenceCheck, type StepUpRequest } from '@/auth/stepUp'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'

interface ReauthResponse {
  ok: boolean
  stepUpToken: string
  expiresInSec: number
}

export function StepUpHost() {
  const { colors: color } = useTheme()
  const s = makeStyles(color)
  const [req, setReq] = useState<StepUpRequest | null>(null)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    return subscribeStepUp((next) => {
      setPassword('')
      setError(null)
      setBusy(false)
      // Face ID happens before the password modal even appears. A failed/cancelled
      // check resolves the whole request as null; only biometrics being off/unavailable
      // lets it through to the password step below.
      void biometricPresenceCheck().then((passed) => {
        if (!passed) {
          next.resolve(null)
          return
        }
        setReq(next)
      })
    })
  }, [])

  function cancel() {
    req?.resolve(null)
    setReq(null)
  }

  async function confirm() {
    if (!req || !password || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await api<ReauthResponse>('/api/auth/mobile/reauth', {
        method: 'POST',
        body: { password, action: req.action },
      })
      req.resolve(res.stepUpToken)
      setReq(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!req) return null

  return (
    <Modal visible transparent animationType="fade" onRequestClose={cancel}>
      <Pressable style={s.scrim} onPress={cancel} accessibilityLabel="Dismiss" />
      <View style={s.sheet}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
          Confirm it&apos;s you
        </Text>
        <Text style={[type.body, { color: color.textDim, marginTop: space.sm }]}>
          Enter your password to continue. This protects changes to your billing and
          brokerage connections.
        </Text>
        <TextInput
          value={password}
          onChangeText={setPassword}
          placeholder="Password"
          placeholderTextColor={color.muted}
          secureTextEntry
          autoFocus
          autoCapitalize="none"
          autoCorrect={false}
          onSubmitEditing={() => void confirm()}
          style={[s.input, { color: color.text, borderColor: color.border }]}
        />
        {error ? <Text style={[type.label, { color: color.neg, marginTop: space.sm }]}>{error}</Text> : null}
        <View style={s.row}>
          <Pressable onPress={cancel} style={s.secondaryBtn} disabled={busy}>
            <Text style={[type.body, { color: color.textDim, fontFamily: font.bodyMedium }]}>Cancel</Text>
          </Pressable>
          <Pressable
            onPress={() => void confirm()}
            disabled={!password || busy}
            style={[s.primaryBtn, { backgroundColor: color.accent, opacity: !password || busy ? 0.5 : 1 }]}
          >
            {busy ? (
              <ActivityIndicator color={color.text} />
            ) : (
              <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>Confirm</Text>
            )}
          </Pressable>
        </View>
      </View>
    </Modal>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
    scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#000', opacity: 0.6 },
    sheet: {
      position: 'absolute',
      left: space.lg,
      right: space.lg,
      top: '30%',
      backgroundColor: color.card,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: color.border,
      padding: space.lg,
    },
    input: {
      marginTop: space.lg,
      borderWidth: 1,
      borderRadius: radius.md,
      paddingHorizontal: space.md,
      paddingVertical: space.sm,
      fontSize: 16,
    },
    row: { flexDirection: 'row', justifyContent: 'flex-end', gap: space.md, marginTop: space.lg },
    secondaryBtn: { paddingVertical: space.sm, paddingHorizontal: space.md, justifyContent: 'center' },
    primaryBtn: {
      paddingVertical: space.sm,
      paddingHorizontal: space.lg,
      borderRadius: radius.md,
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: 90,
    },
  })
