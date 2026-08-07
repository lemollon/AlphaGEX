import { useEffect, useState } from 'react'
import { View, Text, ScrollView, Pressable, Switch, StyleSheet, Alert } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import * as WebBrowser from 'expo-web-browser'
import { useRouter } from 'expo-router'
import useSWR from 'swr'
import Constants from 'expo-constants'
import { api } from '@/api/client'
import type { MobileMe } from '@/api/types'
import { signOut, biometricsAvailable, isBiometricEnabled, setBiometricEnabled } from '@/auth/session'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Card, SectionLabel, Loading, ErrorState } from '@/components/ui'
import { AppHeader } from '@/components/brand'

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
  const [bioAvailable, setBioAvailable] = useState(false)
  const [bioOn, setBioOn] = useState(false)

  useEffect(() => {
    biometricsAvailable().then(setBioAvailable)
    isBiometricEnabled().then(setBioOn)
  }, [])

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
          <SectionLabel>Membership</SectionLabel>
        </View>
        <Card>
          {/*
            STATUS ONLY — deliberately no price and no billing button.
            Google Play's consumption-only allowance is what lets IronForge charge on
            the web without Play billing. A price or an upgrade CTA in the app turns
            this into a purchase surface, which would pull us into the external
            content links programme and its service fees. Membership is managed on
            ironforge.trade. Do not add a "Manage Billing" button back here.
          */}
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              {data?.hasMembership ? 'Active' : 'No active membership'}
            </Text>
            {data?.hasMembership ? (
              <View style={[s.statusPill, { borderColor: color.pos }]}>
                <Text style={[type.label, { color: color.pos }]}>Active</Text>
              </View>
            ) : null}
          </View>
          <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
            Manage your membership at ironforge.trade
          </Text>
        </Card>

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
  // Large bold sans page title per UX-006 — the display face is for the wordmark
  // and numerics, not headings.
  title: {
    color: color.text,
    fontFamily: font.bodyBold,
    fontSize: 34,
    letterSpacing: -0.5,
    marginBottom: space.lg,
  },
  statusPill: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 3,
  },
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
  signOut: { marginTop: space.xxl, alignItems: 'center', paddingVertical: space.md },
})
