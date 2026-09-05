import { useCallback, useEffect, useState } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import * as WebBrowser from 'expo-web-browser'
import * as Linking from 'expo-linking'
import { ApiError } from '@/api/client'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Button, Loading } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { getBrokerConnections, startTradierConnect, selectBrokerAccount } from '@/enroll/api'
import type { BrokerAccountPick } from '@/enroll/types'

/**
 * Connect brokerage (UAT #6, screen 6 of 9) — Tradier only, per the approved mock.
 *
 * KNOWN MISMATCH (see PR description): the Tradier OAuth callback
 * (webapp/src/app/api/onboarding/brokerage/tradier/callback/route.ts) always
 * deep-links a MOBILE client to /account/brokerage regardless of the `return_to:
 * 'enroll'` this screen sends — only the WEB branch honors return_to. This screen's
 * auth session listens for the ACTUAL return route (/account/brokerage), not
 * /enroll/broker, so the round trip still completes; it then reloads the connection
 * list via the same GET /api/brokerage/connections the web /enroll/broker page uses.
 *
 * NOTE: there is no "skip — trade in paper mode" path in the v1 enrollment API today.
 * Activation (POST /api/v1/activations) hard-blocks on BROKERAGE_NOT_CONNECTED without
 * an eligible account, so a "skip for now" button here would be a dead end wearing a
 * label — omitted rather than faked. (Existing SPARK/FLAME paper access lives outside
 * this funnel entirely.)
 */
export default function BrokerScreen() {
  const { enrollment, busy, setBusy, error, setError, router } = useEnrollment('broker')
  const [accounts, setAccounts] = useState<BrokerAccountPick[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [connecting, setConnecting] = useState(false)

  const load = useCallback(async () => {
    try {
      const d = await getBrokerConnections()
      const all = (d.connections ?? []).flatMap((c) => c.accounts)
      setAccounts(all)
      const eligible = all.filter((a) => a.eligibility === 'eligible')
      if (eligible.length === 1) setSelected(eligible[0].id)
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    }
  }, [setError])

  useEffect(() => {
    if (enrollment) load()
  }, [enrollment, load])

  async function connect() {
    setConnecting(true)
    setError(null)
    try {
      const d = await startTradierConnect()
      // The callback deep-links to /account/brokerage (not /enroll/broker) for a mobile
      // client regardless of return_to — see the module note above.
      await WebBrowser.openAuthSessionAsync(d.redirectURI, Linking.createURL('/account/brokerage'))
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setConnecting(false)
    }
  }

  async function continueWithAccount() {
    if (!enrollment || !selected || busy) return
    setBusy(true)
    setError(null)
    try {
      const d = await selectBrokerAccount(enrollment.id, selected)
      router.push({ pathname: '/enroll/agents', params: { accountId: d.broker_account.id } })
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
      setBusy(false)
    }
  }

  const eligibleCount = (accounts ?? []).filter((a) => a.eligibility === 'eligible').length

  return (
    <EnrollShell title="Connect your brokerage" step={6} error={error}>
      <Text style={[type.body, { color: color.textDim, marginBottom: space.lg }]}>
        IronForge places orders through Tradier. You authorize the connection on Tradier&apos;s site and can
        revoke it there any time. IronForge never sees or stores your brokerage password.
      </Text>

      <Button label={connecting ? 'Connecting…' : 'Connect Tradier'} onPress={connect} busy={connecting} />

      {accounts === null ? (
        <View style={{ marginTop: space.xl }}>
          <Loading label="Loading your accounts…" />
        </View>
      ) : accounts.length > 0 ? (
        <View style={{ marginTop: space.xl }}>
          <Text style={[type.label, { color: color.muted, marginBottom: space.sm }]}>YOUR ACCOUNTS</Text>
          <View style={s.list}>
            {accounts.map((a, i) => {
              const ok = a.eligibility === 'eligible'
              const isSelected = selected === a.id
              return (
                <Pressable
                  key={a.id}
                  disabled={!ok}
                  onPress={() => setSelected(a.id)}
                  style={[s.row, i > 0 && s.rowDivider, isSelected && { backgroundColor: `${color.accent}15` }]}
                >
                  <View
                    style={[
                      s.radio,
                      { borderColor: isSelected ? color.accent : color.border },
                      isSelected && { backgroundColor: color.accent },
                    ]}
                  />
                  <View style={{ flex: 1 }}>
                    <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
                      {a.mask ?? '••••'}
                    </Text>
                    {!ok && a.ineligible_reason ? (
                      <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>{a.ineligible_reason}</Text>
                    ) : null}
                  </View>
                  <Text style={[type.label, { color: ok ? color.pos : color.muted, fontFamily: font.bodyMedium }]}>
                    {ok ? 'Eligible' : 'Not eligible'}
                  </Text>
                </Pressable>
              )
            })}
          </View>

          {eligibleCount === 0 ? (
            <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
              None of these accounts can be used yet. Reconnect above after updating with your broker.
            </Text>
          ) : null}

          <View style={{ marginTop: space.lg }}>
            <Button label="Continue with this account" onPress={continueWithAccount} busy={busy} disabled={!selected} />
          </View>
        </View>
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
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md },
  rowDivider: { borderTopWidth: 1, borderTopColor: color.border },
  radio: { width: 18, height: 18, borderRadius: 9, borderWidth: 1.5 },
})
