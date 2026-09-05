import { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { ApiError } from '@/api/client'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Button, Loading } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { previewActivation, activate } from '@/enroll/api'
import type { ActivationPreview, ActivationBlocker } from '@/enroll/types'

/** Not security-sensitive — only needs to be unique per screen visit so a double-tap
 * or a retry-after-timeout reuses the SAME Idempotency-Key rather than minting a new
 * one (which would defeat the server's double-activation guard). */
function randomKey(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

function usd(cents: number): string {
  return (cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

const BLOCKER_ROUTE: Record<string, string> = {
  MEMBERSHIP_NOT_ACTIVE: '/enroll/billing',
  PAYMENT_METHOD_INVALID: '/enroll/billing',
  LEGAL_ACCEPTANCE_STALE: '/enroll/legal',
  BROKERAGE_NOT_CONNECTED: '/enroll/broker',
  BROKER_ACCOUNT_INELIGIBLE: '/enroll/broker',
  AGENT_CONFIG_NOT_VALID: '/enroll/agents',
}

/**
 * Review and activate (UAT #6, screen 8 of 9) — POST /api/v1/activations/preview
 * then POST /api/v1/activations. Everything shown is a LIVE server-computed snapshot,
 * never a hardcoded number. On success, hands off to /enroll/done (screen 9), which
 * calls confirmation-seen and enters the app.
 */
export default function ReviewScreen() {
  const { enrollment, busy, setBusy, error, setError, router } = useEnrollment('review')
  const params = useLocalSearchParams<{ configId?: string }>()
  const configId = params.configId ?? null
  const [preview, setPreview] = useState<ActivationPreview | null>(null)
  const [riskAck, setRiskAck] = useState(false)
  const [authAck, setAuthAck] = useState(false)
  const [blockers, setBlockers] = useState<ActivationBlocker[]>([])
  const idemKey = useRef(randomKey())

  const load = useCallback(async () => {
    if (!configId) return
    try {
      const p = await previewActivation(configId)
      setPreview(p)
      setBlockers(p.blockers)
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    }
  }, [configId, setError])

  useEffect(() => {
    if (!configId) {
      router.replace('/enroll/agents')
      return
    }
    if (enrollment) load()
  }, [configId, enrollment, load, router])

  async function submit() {
    if (!configId || !preview || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await activate({
        configId,
        previewHash: preview.preview_hash,
        riskAcknowledged: riskAck,
        authorizationAcknowledged: authAck,
        idempotencyKey: idemKey.current,
      })
      if (res.ok) {
        router.replace({ pathname: '/enroll/done', params: { activationId: res.activation_id, agent: res.agent } })
        return
      }
      setBlockers(res.blockers ?? [])
      if (res.blockers?.some((b) => b.code === 'PREVIEW_STALE')) {
        setError('Something changed while you were reviewing — refreshed below. Please review again.')
        await load()
      } else if (!res.blockers?.length) {
        setError(res.message ?? 'Activation could not be completed. Please try again.')
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const visibleBlockers = blockers.filter((b) => b.code !== 'PREVIEW_STALE')
  const canActivate = riskAck && authAck && !busy && preview != null && visibleBlockers.length === 0 && preview.can_activate

  return (
    <EnrollShell title="Review and activate" step={8} error={error}>
      {!preview ? (
        <Loading label="Building your review…" />
      ) : (
        <>
          {visibleBlockers.length > 0 ? (
            <View style={s.blockBox}>
              <Text style={[type.body, { color: color.neg, fontFamily: font.bodyBold }]}>Before you can activate:</Text>
              {visibleBlockers.map((b) => (
                <Pressable
                  key={b.code}
                  disabled={!b.remediable || !BLOCKER_ROUTE[b.code]}
                  onPress={() => router.push(BLOCKER_ROUTE[b.code] as never)}
                  style={{ marginTop: space.sm }}
                >
                  <Text style={[type.body, { color: color.text }]}>{b.message}</Text>
                  {b.remediable && BLOCKER_ROUTE[b.code] ? (
                    <Text style={[type.label, { color: color.accent, fontFamily: font.bodyBold, marginTop: 2 }]}>
                      Fix this →
                    </Text>
                  ) : null}
                </Pressable>
              ))}
            </View>
          ) : (
            <View style={[s.blockBox, { borderColor: color.pos }]}>
              <Text style={[type.body, { color: color.text }]}>All required checks passed</Text>
            </View>
          )}

          <View style={s.card}>
            <Text style={[type.label, { color: color.muted, marginBottom: space.sm }]}>TRADING SETUP</Text>
            <Kv label="Agent" value={preview.snapshot.agent === 'spark' ? 'Spark' : 'Flame'} />
            <Kv label="Brokerage account" value={preview.snapshot.account_mask || '—'} />
            <Kv
              label="Maximum capital deployment"
              value={usd(preview.snapshot.max_deployment_cents)}
            />
          </View>

          <View style={s.card}>
            <Text style={[type.label, { color: color.muted, marginBottom: space.sm }]}>TRIAL &amp; BILLING</Text>
            <Kv label="Due today" value="$0.00" />
            <Kv label="Free trial" value={`${preview.snapshot.trial.eligible_days_total} eligible trading days`} />
            <Kv label="After trial" value={preview.snapshot.plan ? `$${preview.snapshot.plan.price_monthly}/month` : '—'} />
          </View>

          <Ack
            checked={riskAck}
            onToggle={() => setRiskAck((v) => !v)}
            label="I understand automated options trading involves substantial risk."
          />
          <Ack
            checked={authAck}
            onToggle={() => setAuthAck((v) => !v)}
            label="I authorize IronForge to submit and manage orders using this configuration."
          />

          <Button label="Enter the Forge" onPress={submit} busy={busy} disabled={!canActivate} />
        </>
      )}
    </EnrollShell>
  )
}

function Kv({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: space.sm }}>
      <Text style={[type.label, { color: color.muted }]}>{label}</Text>
      <Text style={[type.body, { color: color.text }]}>{value}</Text>
    </View>
  )
}

function Ack({ checked, onToggle, label }: { checked: boolean; onToggle: () => void; label: string }) {
  return (
    <Pressable onPress={onToggle} style={{ flexDirection: 'row', gap: space.md, marginBottom: space.md }}>
      <View
        style={{
          width: 20,
          height: 20,
          borderRadius: 4,
          borderWidth: 1.5,
          borderColor: checked ? color.accent : color.border,
          backgroundColor: checked ? color.accent : 'transparent',
        }}
      >
        {checked ? <Text style={{ color: color.text, textAlign: 'center', fontSize: 13 }}>✓</Text> : null}
      </View>
      <Text style={[type.body, { color: color.text, flex: 1 }]}>{label}</Text>
    </Pressable>
  )
}

const s = StyleSheet.create({
  blockBox: {
    borderWidth: 1,
    borderColor: color.neg,
    borderRadius: radius.lg,
    padding: space.md,
    marginBottom: space.lg,
  },
  card: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.lg,
    padding: space.lg,
    backgroundColor: color.card,
    marginBottom: space.md,
  },
})
