import { useEffect, useState } from 'react'
import { View, Text, ScrollView, Pressable, Switch, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { api } from '@/api/client'
import { color, space, type, font } from '@/theme/tokens'
import { Card, SectionLabel, Loading, ErrorState } from '@/components/ui'

/**
 * Notification preferences — APP-036.
 *
 * Every toggle PUTs immediately (optimistic, rolled back on failure) rather than
 * batching behind a Save button — this is a settings screen someone visits once and
 * leaves; a forgotten unsaved toggle would mean the preference silently never took
 * effect. Security notices (session revoked, password changed, new device) are not
 * a toggle here at all — they are the one category a customer cannot turn off, so
 * showing it as a switch that does nothing would be a lie.
 */
type Preferences = {
  trade_opened: boolean
  trade_closed: boolean
  trade_approval: boolean
  brokerage_health: boolean
  billing: boolean
  community: boolean
  show_amounts_on_lockscreen: boolean
}

type PrefKey = keyof Preferences

interface PreferencesResponse {
  ok: boolean
  preferences: Preferences
}

const GROUPS: Array<{ label: string; rows: Array<{ key: PrefKey; label: string; detail: string }> }> = [
  {
    label: 'Trades',
    rows: [
      { key: 'trade_opened', label: 'Trade opened', detail: 'When an agent opens a new position.' },
      { key: 'trade_closed', label: 'Trade closed', detail: 'When a position hits its target, stop, or expires.' },
      {
        key: 'trade_approval',
        label: 'Trade needs your approval',
        detail: 'Time-sensitive — expires in 5 minutes.',
      },
    ],
  },
  {
    label: 'Brokerage',
    rows: [
      {
        key: 'brokerage_health',
        label: 'Connection needs attention',
        detail: 'Your brokerage link is degraded or disconnected.',
      },
    ],
  },
  {
    label: 'Billing',
    rows: [{ key: 'billing', label: 'Billing', detail: 'Payment issues and membership changes.' }],
  },
  {
    label: 'Community',
    rows: [{ key: 'community', label: 'Community', detail: 'Replies and activity in the community feed.' }],
  },
  {
    label: 'Privacy',
    rows: [
      {
        key: 'show_amounts_on_lockscreen',
        label: 'Show dollar amounts on lock screen',
        detail: 'Off by default — P&L stays hidden until you unlock your phone.',
      },
    ],
  },
]

export default function NotificationsScreen() {
  const router = useRouter()
  const [prefs, setPrefs] = useState<Preferences | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<Set<PrefKey>>(new Set())

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const res = await api<PreferencesResponse>('/api/notifications/preferences')
      setPrefs(res.preferences)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function toggle(key: PrefKey, value: boolean) {
    if (!prefs) return
    const previous = prefs
    setPrefs({ ...prefs, [key]: value })
    setPending((p) => new Set(p).add(key))
    try {
      const res = await api<PreferencesResponse>('/api/notifications/preferences', {
        method: 'PUT',
        body: { [key]: value },
      })
      setPrefs(res.preferences)
    } catch {
      // Roll back — the server never saw the change, so the switch must not claim it did.
      setPrefs(previous)
    } finally {
      setPending((p) => {
        const next = new Set(p)
        next.delete(key)
        return next
      })
    }
  }

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <View style={s.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={26} color={color.text} />
        </Pressable>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
          Notifications
        </Text>
      </View>

      {loading ? (
        <Loading label="Loading preferences…" />
      ) : error || !prefs ? (
        <ErrorState message={error ?? 'Preferences unavailable.'} onRetry={load} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: space.lg }}>
          {GROUPS.map((group) => (
            <View key={group.label} style={{ marginBottom: space.xl }}>
              <SectionLabel>{group.label}</SectionLabel>
              <Card>
                {group.rows.map((row, i) => (
                  <View key={row.key} style={[s.row, i > 0 && s.rowDivider]}>
                    <View style={{ flex: 1, paddingRight: space.md }}>
                      <Text style={[type.body, { color: color.text }]}>{row.label}</Text>
                      <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>{row.detail}</Text>
                    </View>
                    <Switch
                      value={prefs[row.key]}
                      disabled={pending.has(row.key)}
                      onValueChange={(v) => toggle(row.key, v)}
                      trackColor={{ true: color.accent, false: color.border }}
                    />
                  </View>
                ))}
              </Card>
            </View>
          ))}

          <View style={s.securityRow}>
            <Ionicons name="shield-checkmark-outline" size={18} color={color.muted} />
            <Text style={[type.label, { color: color.muted }]}>Security notices are always on.</Text>
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
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
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.md },
  rowDivider: { borderTopWidth: 1, borderTopColor: color.border },
  securityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    justifyContent: 'center',
    marginTop: space.sm,
    marginBottom: space.xl,
  },
})
