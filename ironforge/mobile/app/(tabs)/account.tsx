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
  const { data, error, isLoading, mutate } = useSWR<MobileMe>('/api/auth/mobile/me', (p: string) => api(p))
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
          <Text style={[type.body, { color: color.textDim }]}>
            {data?.hasMembership ? 'Active membership' : 'No active membership'}
          </Text>
          <Pressable onPress={openBilling} style={s.outlineBtn}>
            <Text style={[type.body, { color: color.accent, fontFamily: font.bodyMedium }]}>
              Manage Membership and Billing
            </Text>
          </Pressable>
          <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
            Securely managed through Stripe
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
  return <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }} edges={['top']}>{children}</SafeAreaView>
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
  signOut: { marginTop: space.xxl, alignItems: 'center', paddingVertical: space.md },
})
