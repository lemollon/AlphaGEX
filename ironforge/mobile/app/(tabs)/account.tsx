import { useEffect, useState } from 'react'
import { View, Text, ScrollView, Pressable, Switch, StyleSheet, Alert } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import * as WebBrowser from 'expo-web-browser'
import { useRouter } from 'expo-router'
import useSWR from 'swr'
import Constants from 'expo-constants'
import { api } from '@/api/client'
import type { MobileMe, LiveSummary } from '@/api/types'
import { signOut, biometricsAvailable, isBiometricEnabled, setBiometricEnabled } from '@/auth/session'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Card, SectionLabel, Loading, ErrorState } from '@/components/ui'
import { AppHeader } from '@/components/Brand'
import { BrokerageSection } from '@/components/BrokerageSection'

/**
 * Account — UX-006 (APP-037/038/039/040/043/044/058/059/060).
 *
 * "Manage Membership & Billing" opens a SERVER-CREATED Stripe portal session in the
 * system browser, never a WebView. Two reasons: Apple treats an in-app WebView payment
 * surface as IAP circumvention, and the customer can see the real URL and padlock —
 * which is the whole trust argument for handing over card details.
 *
 * NOTE for whoever wires the membership card: the plan name comes from
 * LiveSummary.membership, which the server derives from real subscription rows and
 * fails SOFT to a neutral card. Do not hardcode a plan name here — a hardcoded
 * "Forge Automate" card that rendered identically for payers, trialers and
 * non-subscribers is exactly the bug that was deleted when Stripe landed.
 */
export default function AccountScreen() {
  const router = useRouter()
  // The fetcher's return type must be explicit. With no third (config) argument, SWR's
  // overloads let TypeScript read `(p: string) => api(p)` — which resolves to
  // Promise<unknown> — as a config object instead of a fetcher, and the call fails to
  // typecheck. Naming the generic on `api` resolves it.
  const { data, error, isLoading, mutate } = useSWR<MobileMe>(
    '/api/auth/mobile/me',
    (p: string) => api<MobileMe>(p),
  )
  // The plan NAME is server-derived (LiveSummary.membership.plan) — see the note above
  // about never hardcoding one here. Fails soft: no summary just means no plan line.
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', (p: string) =>
    api<LiveSummary>(p),
  )
  const [bioAvailable, setBioAvailable] = useState(false)
  const [bioOn, setBioOn] = useState(false)

  useEffect(() => {
    biometricsAvailable().then(setBioAvailable)
    isBiometricEnabled().then(setBioOn)
  }, [])

  async function openBilling() {
    try {
      const res = await api<{ ok: boolean; url: string }>('/api/billing/portal', { method: 'POST' })
      if (res.url) await WebBrowser.openBrowserAsync(res.url)
      mutate()
    } catch (e) {
      Alert.alert('Billing unavailable', (e as Error).message)
    }
  }

  async function doSignOut() {
    await signOut()
    router.replace('/sign-in')
  }

  if (isLoading) return <Shell><Loading /></Shell>
  if (error) {
    return (
      <Shell>
        <ErrorState message={String((error as Error).message)} onRetry={() => mutate()} />
      </Shell>
    )
  }

  const c = data?.customer

  return (
    <Shell>
      <ScrollView contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}>
        <Text style={s.title}>Account</Text>

        <Card>
          <View style={s.rowCenter}>
            <View style={s.avatar}>
              <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>
                {c?.initials ?? '—'}
              </Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
                {c?.displayName ?? '—'}
              </Text>
              <Text style={[type.label, { color: color.textDim, marginTop: 2 }]}>{c?.email}</Text>
              {c?.memberSince ? (
                <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>
                  Member since {memberSince(c.memberSince)}
                </Text>
              ) : null}
            </View>
          </View>
        </Card>

        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Membership and Billing</SectionLabel>
        </View>
        <Card>
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
              {summary?.membership?.plan ?? (data?.hasMembership ? 'Membership' : 'No membership')}
            </Text>
            {data?.hasMembership ? (
              <View style={[s.pill, { borderColor: color.pos }]}>
                <Text style={[type.label, { color: color.pos }]}>
                  {summary?.membership?.badge ?? 'Active'}
                </Text>
              </View>
            ) : null}
          </View>
          {/* Price and next billing date are NOT in any payload yet (APP-038). Stripe
              subscription fields have to be added server-side before this card can show
              "$50 / month · Next billing August 31" as UX-006 does. Inventing them here
              would put a wrong number next to a real charge. */}
          <Pressable onPress={openBilling} style={s.outlineBtn}>
            <Text style={[type.body, { color: color.accent, fontFamily: font.bodyMedium }]}>
              Manage Membership and Billing
            </Text>
          </Pressable>
          <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
            Securely managed through Stripe
          </Text>
        </Card>

        <BrokerageSection />

        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Security</SectionLabel>
        </View>
        <Card>
          <View style={s.rowBetween}>
            <View style={{ flex: 1, paddingRight: space.md }}>
              <Text style={[type.body, { color: color.text }]}>Unlock with biometrics</Text>
              <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>
                {bioAvailable
                  ? 'Use Face ID or your fingerprint instead of your password.'
                  : 'Not available on this device.'}
              </Text>
            </View>
            <Switch
              value={bioOn}
              disabled={!bioAvailable}
              onValueChange={(v) => {
                setBioOn(v)
                setBiometricEnabled(v)
              }}
              trackColor={{ true: color.accent, false: color.border }}
            />
          </View>
        </Card>

        <Pressable onPress={doSignOut} style={s.signOut}>
          <Text style={[type.body, { color: color.neg, fontFamily: font.bodyMedium }]}>Log Out</Text>
        </Pressable>

        <Text style={[type.label, { color: color.muted, textAlign: 'center', marginTop: space.md }]}>
          IronForge v{Constants.expoConfig?.version ?? '1.0.0'}
        </Text>
      </ScrollView>
    </Shell>
  )
}

function memberSince(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }} edges={['top']}>
      <AppHeader />
      {children}
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  title: { ...type.title, color: color.text, fontFamily: font.display, marginBottom: space.lg },
  rowCenter: { flexDirection: 'row', alignItems: 'center', gap: space.lg },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: color.bg,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  outlineBtn: {
    marginTop: space.lg,
    borderWidth: 1,
    borderColor: color.accent,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  pill: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  signOut: { marginTop: space.xxl, alignItems: 'center', paddingVertical: space.md },
})
