/**
 * Brokerage Connections — UX-006 / APP-040, APP-041.
 *
 * This section did not exist. PR #2740 shipped the entire mobile brokerage OAuth flow in
 * August — `/api/brokerage/connections` and `/api/onboarding/brokerage/connect` both
 * accept a mobile bearer — and no screen ever called either one. This is the UI for
 * backend that has been sitting in production, finished, for eighteen days.
 *
 * Credentials are NEVER collected here. Connect and reconnect open the server-generated
 * SnapTrade portal in a system auth session, and the customer returns through the
 * verified `ironforge://` deep link. That is APP-041's hard requirement and it is also
 * the only version Apple and Google will accept.
 *
 * Disconnect is now offered because the connections payload returns `authorization_id` —
 * the handle DELETE requires. It previously did not, so the screen could list a
 * connection and then had nothing to act on.
 */
import { useState } from 'react'
import { View, Text, Pressable, Alert, ActivityIndicator, StyleSheet } from 'react-native'
import * as WebBrowser from 'expo-web-browser'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts (~3 MB,
// MaterialCommunityIcons alone is 1.3 MB). Ionicons is the only set used.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { api } from '@/api/client'
import type { BrokerageConnection, BrokerageConnections } from '@/api/types'
import { brokerLabel, health, type HealthKey } from '@/api/brokerage'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Card, SectionLabel } from '@/components/ui'

const RETURN_URL = 'ironforge://app/return'

const HEALTH_COLOR: Record<HealthKey, string> = {
  connected: color.pos,
  attention: color.warn,
  disconnected: color.neg,
  restricted: color.neg,
}

export function BrokerageSection() {
  // Generic named on api() deliberately — see the note in app/(tabs)/index.tsx.
  const { data, error, isLoading, mutate } = useSWR<BrokerageConnections>(
    '/api/brokerage/connections',
    (p: string) => api<BrokerageConnections>(p),
  )
  const [busy, setBusy] = useState(false)

  /** Opens the server-created portal. `broker` prefills it for a reconnect. */
  async function openPortal(broker?: string) {
    if (busy) return
    setBusy(true)
    try {
      const res = await api<{ ok: boolean; redirectURI?: string; error?: string }>(
        '/api/onboarding/brokerage/connect',
        { method: 'POST', body: broker ? { broker } : {} },
      )
      if (!res.redirectURI) throw new Error(res.error ?? 'Could not start the connection.')
      await WebBrowser.openAuthSessionAsync(res.redirectURI, RETURN_URL)
      // The callback writes the row server-side; re-read rather than guessing the result.
      mutate()
    } catch (e) {
      Alert.alert('Could not open your brokerage', (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  /**
   * Disconnect, behind a second confirmation.
   *
   * This stops an agent trading that account, which is not something to do on one tap.
   * The wording says what actually happens rather than a generic "are you sure": it
   * removes the authorization at the broker, and it does NOT close anything already open.
   */
  function confirmDisconnect(c: BrokerageConnection) {
    const name = brokerLabel(c.broker ?? c.provider)
    if (!c.authorization_id) {
      Alert.alert(
        'Cannot disconnect yet',
        `This ${name} connection has not finished linking. Reconnect it first, or contact support.`,
      )
      return
    }
    Alert.alert(
      `Disconnect ${name}?`,
      'Your agent will stop placing new trades on this account. Any position that is already open stays open and is not closed by disconnecting.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: () => void disconnect(c),
        },
      ],
    )
  }

  async function disconnect(c: BrokerageConnection) {
    if (busy) return
    setBusy(true)
    try {
      await api('/api/brokerage/connection', {
        method: 'DELETE',
        body: { authorizationId: c.authorization_id },
      })
    } catch (e) {
      Alert.alert('Could not disconnect', (e as Error).message)
    } finally {
      setBusy(false)
      // Re-read either way — the server is the truth about what is still linked.
      mutate()
    }
  }

  function manage(c: BrokerageConnection) {
    const name = brokerLabel(c.broker ?? c.provider)
    Alert.alert(
      name,
      `Connected on ${c.connected_on}. Reconnecting opens ${name} in a secure browser — IronForge never sees your brokerage password.`,
      [
        { text: 'Close', style: 'cancel' },
        { text: 'Disconnect', style: 'destructive', onPress: () => confirmDisconnect(c) },
        { text: 'Reconnect', onPress: () => void openPortal(c.broker ?? undefined) },
      ],
    )
  }

  const connections = data?.connections ?? []

  return (
    <>
      <View style={{ marginTop: space.xl }}>
        <SectionLabel>Brokerage Connections</SectionLabel>
      </View>
      <Card>
        {isLoading ? (
          <ActivityIndicator color={color.accent} />
        ) : error ? (
          <Text style={[type.body, { color: color.textDim }]}>
            Could not load your connections right now.
          </Text>
        ) : data?.configured === false ? (
          <Text style={[type.body, { color: color.textDim }]}>
            Brokerage connections are not available on this environment.
          </Text>
        ) : connections.length === 0 ? (
          <Text style={[type.body, { color: color.textDim }]}>
            No brokerage connected yet. Connect one so your agent can trade.
          </Text>
        ) : (
          connections.map((c, i) => (
            <ConnectionRow key={c.id} conn={c} first={i === 0} onManage={() => manage(c)} />
          ))
        )}

        <Pressable
          onPress={() => void openPortal()}
          disabled={busy}
          accessibilityRole="button"
          style={[s.outlineBtn, busy && { opacity: 0.5 }]}
        >
          <Text style={[type.body, { color: color.accent, fontFamily: font.bodyMedium }]}>
            {busy ? 'Opening…' : 'Connect Another Brokerage'}
          </Text>
        </Pressable>
      </Card>
    </>
  )
}

function ConnectionRow({
  conn,
  first,
  onManage,
}: {
  conn: BrokerageConnection
  first: boolean
  onManage: () => void
}) {
  const h = health(conn.status)
  const name = brokerLabel(conn.broker ?? conn.provider)
  const masks = conn.accounts.map((a) => a.mask).filter((m): m is string => !!m)

  return (
    <Pressable
      onPress={onManage}
      accessibilityRole="button"
      accessibilityLabel={`Manage ${name}, ${h.label}`}
      style={[s.row, !first && s.rowDivider]}
    >
      <View style={s.avatar}>
        <Ionicons name="business-outline" size={20} color={color.textDim} />
      </View>

      <View style={{ flex: 1 }}>
        <View style={s.rowCenter}>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>{name}</Text>
          <View style={[s.dot, { backgroundColor: HEALTH_COLOR[h.key] }]} />
          <Text style={[type.label, { color: HEALTH_COLOR[h.key] }]}>{h.label}</Text>
        </View>
        {masks.length ? (
          <Text style={[type.label, { color: color.textDim, marginTop: 2 }]}>
            {masks.map((m) => `•••• ${m}`).join('   ')}
          </Text>
        ) : null}
      </View>

      <View style={s.rowCenter}>
        <Text style={[type.label, { color: color.textDim }]}>Manage</Text>
        <Ionicons name="chevron-forward" size={16} color={color.muted} />
      </View>
    </Pressable>
  )
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.md },
  rowDivider: { borderTopWidth: 1, borderTopColor: color.border },
  rowCenter: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dot: { width: 7, height: 7, borderRadius: 4 },
  outlineBtn: {
    marginTop: space.lg,
    borderWidth: 1,
    borderColor: color.accent,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
})
