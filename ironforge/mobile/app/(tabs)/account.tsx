import { useEffect, useState } from 'react'
import { View, Text, ScrollView, Pressable, Switch, StyleSheet, Alert, Linking } from 'react-native'
import * as Clipboard from 'expo-clipboard'
import { SafeAreaView } from 'react-native-safe-area-context'
import * as WebBrowser from 'expo-web-browser'
import { useRouter } from 'expo-router'
import useSWR from 'swr'
import Constants from 'expo-constants'
import { api } from '@/api/client'
import type { MobileMe, LiveSummary } from '@/api/types'
import { signOut, biometricsAvailable, isBiometricEnabled, setBiometricEnabled } from '@/auth/session'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Card, SectionLabel, Row, Loading, ErrorState } from '@/components/ui'
import { AppHeader, SPARKY_AVATAR } from '@/components/Brand'
import { SUPPORT_EMAIL, supportMailto } from '@/support/contact'
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

  /**
   * APP-043: open a native draft; if no mail client can handle it, fall back to a
   * copyable address rather than a silent no-op.
   */
  async function emailSupport() {
    const url = supportMailto()
    const canOpen = await Linking.canOpenURL(url).catch(() => false)
    if (canOpen) {
      await Linking.openURL(url).catch(() => void copyAddress())
      return
    }
    await copyAddress()
  }

  async function copyAddress() {
    await Clipboard.setStringAsync(SUPPORT_EMAIL).catch(() => {})
    Alert.alert(
      'No email app found',
      `${SUPPORT_EMAIL} has been copied to your clipboard.`,
    )
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

          {/* APP-058 "Edit Profile" is deliberately absent: there is no endpoint that
              updates a customer's name or email, so the row would be a dead chevron.
              It needs a server route before it can exist. */}
          <View style={{ marginTop: space.md }}>
            <Row
              icon="lock-closed-outline"
              label="Change Password"
              detail="Signs you out on every device"
              onPress={() => router.push('/change-password')}
              first
            />
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

        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Help and Support</SectionLabel>
        </View>
        <Card>
          <Row
            image={SPARKY_AVATAR}
            label="Ask Sparky"
            detail="Get instant help from the IronForge AI agent"
            onPress={() => router.push('/sparky')}
            first
            badge={
              <View style={s.aiTag}>
                <Text style={[type.label, { color: color.spark, fontFamily: font.bodyMedium }]}>
                  AI
                </Text>
              </View>
            }
          />
          <Row
            icon="mail-outline"
            label="Email Support"
            detail={SUPPORT_EMAIL}
            onPress={emailSupport}
          />
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
  aiTag: {
    borderWidth: 1,
    borderColor: color.spark,
    borderRadius: radius.sm,
    paddingHorizontal: space.sm,
  },
  pill: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  signOut: { marginTop: space.xxl, alignItems: 'center', paddingVertical: space.md },
})
