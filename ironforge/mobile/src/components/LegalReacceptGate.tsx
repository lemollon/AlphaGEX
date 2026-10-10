/**
 * Blocking re-acceptance screen — the mobile half of the same mechanism
 * CustomerShell.tsx (webapp) adds for the web dashboard. Reads/writes the
 * SAME two endpoints the web gate uses (GET /api/v1/legal/outstanding, POST
 * /api/v1/legal/reaccept), via the existing bearer-aware `api()` client
 * rather than anything web-specific — one acceptance record either client
 * writes lands in the same `legal_acceptances` table.
 *
 * Mounted once in app/_layout.tsx, in the same spot the Face ID lock overlay
 * sits: both are "something must be resolved before the signed-in app is
 * usable" screens over the same Stack.
 */
import { useEffect, useMemo, useState } from 'react'
import { View, Text, Pressable, Linking, StyleSheet } from 'react-native'
import useSWR from 'swr'
import { api } from '@/api/client'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Button, TextField } from '@/components/ui'
import { Wordmark } from '@/components/Brand'
import { API_BASE } from '@/api/client'

interface OutstandingDoc {
  code: string
  title: string
  version: string
  contentUri: string
}

interface OutstandingResponse {
  documents: OutstandingDoc[]
  outstanding: string[]
}

export function LegalReacceptGate() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const { data, mutate } = useSWR<OutstandingResponse>('/api/v1/legal/outstanding', (p: string) => api<OutstandingResponse>(p))

  const outstandingCodes = data?.outstanding ?? []
  const changed = (data?.documents ?? []).filter((d) => outstandingCodes.includes(d.code))

  const [opened, setOpened] = useState<Record<string, boolean>>({})
  const [signature, setSignature] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setOpened({})
    setSignature('')
    setError(null)
  }, [outstandingCodes.join(',')])

  if (changed.length === 0) return null

  const allOpened = changed.every((d) => opened[d.code])
  const canSubmit = allOpened && signature.trim().length >= 2 && /\s/.test(signature.trim()) && !busy

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await api('/api/v1/legal/reaccept', {
        method: 'POST',
        body: { codes: changed.map((d) => d.code), signature_name: signature.trim() },
      })
      await mutate()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record your acceptance. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <View style={s.overlay}>
      <Wordmark height={28} />
      <Text style={s.title}>We&rsquo;ve updated our agreements</Text>
      <Text style={s.body}>
        Review and re-accept the documents below to keep using the app. Nothing else about your account or
        trading changes.
      </Text>

      <View style={s.docList}>
        {changed.map((d) => (
          <Pressable
            key={d.code}
            onPress={() => {
              setOpened((o) => ({ ...o, [d.code]: true }))
              void Linking.openURL(`${API_BASE}${d.contentUri}`)
            }}
            style={s.docRow}
            accessibilityRole="button"
          >
            <View style={{ flex: 1 }}>
              <Text style={s.docTitle}>{d.title}</Text>
              <Text style={s.docVersion}>Version {d.version}</Text>
            </View>
            <Text style={s.docAction}>{opened[d.code] ? 'Reviewed ✓' : 'Review →'}</Text>
          </Pressable>
        ))}
      </View>

      {error ? <Text style={s.error}>{error}</Text> : null}

      <View style={{ width: '100%', marginTop: space.md }}>
        <TextField
          label="Type your full legal name to sign"
          value={signature}
          onChangeText={setSignature}
          editable={allOpened}
          placeholder="First and last name"
          autoCapitalize="words"
        />
      </View>

      <View style={{ width: '100%' }}>
        <Button label="Accept and continue" onPress={submit} busy={busy} disabled={!canSubmit} />
      </View>
    </View>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
    overlay: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: color.bg,
      alignItems: 'center',
      justifyContent: 'center',
      padding: space.xl,
      gap: space.md,
    },
    title: {
      ...type.title,
      fontFamily: font.display,
      color: color.text,
      textAlign: 'center',
      marginTop: space.md,
    },
    body: { ...type.body, color: color.textDim, textAlign: 'center', marginTop: space.sm },
    docList: { width: '100%', marginTop: space.lg, gap: space.sm },
    docRow: {
      flexDirection: 'row',
      alignItems: 'center',
      borderWidth: 1,
      borderColor: color.border,
      borderRadius: radius.md,
      padding: space.md,
    },
    docTitle: { ...type.body, color: color.text, fontFamily: font.bodyMedium },
    docVersion: { ...type.label, color: color.muted, marginTop: 2 },
    docAction: { ...type.label, color: color.accent, fontFamily: font.bodyMedium },
    error: { ...type.label, color: color.neg, textAlign: 'center', marginTop: space.sm },
  })
