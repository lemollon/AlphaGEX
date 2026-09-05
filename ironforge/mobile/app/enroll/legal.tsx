import { useEffect, useState } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import * as WebBrowser from 'expo-web-browser'
import { ApiError, API_BASE } from '@/api/client'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Button, TextField, Loading } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { getLegal, acceptLegal } from '@/enroll/api'
import type { LegalRequirement } from '@/enroll/types'

/** Row subtitles from the approved screen — mirrors webapp/src/app/enroll/legal/LegalClient.tsx. */
const DOC_SUBTITLES: Record<string, string> = {
  TERMS: 'Platform terms and member responsibilities',
  RISK: 'Risks associated with options and automated trading',
  PRIVACY: 'How IronForge collects and protects information',
  ADVICE_DISCLAIMER: 'IronForge does not provide individualized advice',
  ELECTRONIC_CONSENT: 'Consent to receive and sign records electronically',
  TRADING_AUTH: 'Authorization to submit orders through your brokerage',
  REFUND: 'Billing, cancellation and refund terms',
}

/**
 * Legal review (UAT #6, screen 4 of 9) — GET/POST /api/v1/enrollments/{id}/legal|acceptances.
 *
 * Documents, order, and signature requirement all come from the API — never a fixed
 * 3-checkbox list. Community has no standalone legal screen (its core docs are a
 * clickwrap at billing submit); a community enrollment that lands here bounces to
 * billing immediately, mirroring the web LegalClient.tsx guard.
 */
export default function LegalScreen() {
  const { enrollment, busy, setBusy, error, setError, router } = useEnrollment('legal')
  const [docs, setDocs] = useState<LegalRequirement[]>([])
  const [opened, setOpened] = useState<Record<string, boolean>>({})
  const [agreed, setAgreed] = useState(false)
  const [signature, setSignature] = useState('')

  useEffect(() => {
    if (!enrollment) return
    if (enrollment.selected_plan === 'community') {
      router.replace('/enroll/billing')
      return
    }
    getLegal(enrollment.id)
      .then((d) => {
        setDocs(d.documents)
        const seen: Record<string, boolean> = {}
        for (const doc of d.documents) if (doc.accepted) seen[doc.code] = true
        setOpened((o) => ({ ...seen, ...o }))
      })
      .catch((e) => setError(e instanceof ApiError ? e.humanMessage : (e as Error).message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enrollment])

  const allOpened = docs.length > 0 && docs.every((d) => opened[d.code])
  const canSubmit = allOpened && agreed && signature.trim().length >= 2 && !busy

  async function accept() {
    if (!enrollment || !canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const d = await acceptLegal(
        enrollment.id,
        docs.map((doc) => doc.code),
        signature.trim(),
      )
      if (!d.ok) {
        setError('Please open and accept every required agreement to continue.')
        setBusy(false)
        return
      }
      router.push('/enroll/billing')
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
      setBusy(false)
    }
  }

  return (
    <EnrollShell title="Review and accept" step={4} error={error}>
      <Text style={[type.body, { color: color.textDim, marginBottom: space.lg }]}>
        These agreements are required for automated trading.
      </Text>

      {!enrollment || (docs.length === 0 && !error) ? <Loading label="Loading agreements…" /> : null}

      {docs.length > 0 ? (
        <>
          <View style={s.list}>
            {docs.map((d, i) => (
              <View key={d.code} style={[s.row, i > 0 && s.rowDivider]}>
                <View style={{ flex: 1 }}>
                  <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>{d.title}</Text>
                  <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>
                    {DOC_SUBTITLES[d.code] ?? `Version ${d.version}`}
                  </Text>
                </View>
                {opened[d.code] ? <Text style={{ color: color.pos, fontWeight: '700' }}>✓</Text> : null}
                <Pressable
                  onPress={async () => {
                    await WebBrowser.openBrowserAsync(`${API_BASE}${d.contentUri}`)
                    setOpened((o) => ({ ...o, [d.code]: true }))
                  }}
                  hitSlop={8}
                >
                  <Text style={[type.body, { color: color.accent, fontFamily: font.bodyBold }]}>Review</Text>
                </Pressable>
              </View>
            ))}
          </View>

          <Pressable
            onPress={() => allOpened && setAgreed((v) => !v)}
            style={{ flexDirection: 'row', gap: space.md, marginTop: space.lg, alignItems: 'flex-start' }}
          >
            <View
              style={{
                width: 20,
                height: 20,
                borderRadius: 4,
                borderWidth: 1.5,
                borderColor: agreed ? color.accent : color.border,
                backgroundColor: agreed ? color.accent : 'transparent',
                opacity: allOpened ? 1 : 0.4,
              }}
            >
              {agreed ? <Text style={{ color: color.text, textAlign: 'center', fontSize: 13 }}>✓</Text> : null}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[type.body, { color: color.text }]}>
                I have opened, reviewed, and agree to all required agreements.
              </Text>
              {!allOpened ? (
                <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>
                  Review each document above to enable this.
                </Text>
              ) : null}
            </View>
          </Pressable>

          <View style={{ marginTop: space.lg }}>
            <TextField
              label="Electronic signature — type your full legal name"
              value={signature}
              onChangeText={setSignature}
              autoCapitalize="words"
              textContentType="name"
            />
          </View>

          <Button label="Accept & Continue" onPress={accept} busy={busy} disabled={!canSubmit} />
        </>
      ) : null}
    </EnrollShell>
  )
}

const s = StyleSheet.create({
  list: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.lg,
    backgroundColor: color.card,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  rowDivider: { borderTopWidth: 1, borderTopColor: color.border },
})
