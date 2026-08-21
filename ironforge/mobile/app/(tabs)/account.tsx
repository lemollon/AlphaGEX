import { useEffect, useState } from 'react'
import { View, Text, ScrollView, Pressable, Switch, StyleSheet, Alert, Linking } from 'react-native'
import * as Clipboard from 'expo-clipboard'
import { SafeAreaView } from 'react-native-safe-area-context'
import * as WebBrowser from 'expo-web-browser'
import { useRouter } from 'expo-router'
import useSWR from 'swr'
import Constants from 'expo-constants'
import { api, API_BASE, ApiError } from '@/api/client'
import type { MobileMe, MembershipResponse } from '@/api/types'
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
 * system browser, never a WebView, so the customer can see the real URL and padlock —
 * which is the whole trust argument for handing over card details.
 *
 * 🚨 The control is HIDDEN ENTIRELY ON iOS (canManageBillingInApp). Keeping it out of
 * a WebView is not sufficient there: the portal session uses Stripe's default
 * configuration, which allows changing plan, so any route to it from inside the iOS
 * app is a purchasing mechanism under App Review Guideline 3.1.1. See
 * src/billing/store-policy.ts for the full reasoning before re-enabling it.
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
  // Real billing state (APP-038): plan, status, price and next renewal, all derived
  // server-side from the Stripe-written customer_bot_subscriptions rows. This used to
  // read LiveSummary.membership, which was a hardcoded "IronForge Membership /
  // Early Access" placeholder with no price and no date.
  const { data: billing } = useSWR<MembershipResponse>('/api/billing/membership', (p: string) =>
    api<MembershipResponse>(p),
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
      // `portal_unconfigured` is the server refusing to open the plan-changing default
      // portal for a mobile client. Deliberately does NOT point anyone at the web to go
      // and pay — that would be the call to action the refusal exists to avoid.
      Alert.alert('Billing unavailable', e instanceof ApiError ? e.humanMessage : (e as Error).message)
    }
  }

  /**
   * APP-043: open a native draft; if no mail client can handle it, fall back to a
   * copyable address rather than a silent no-op.
   */
  /**
   * Legal pages live on the marketing site, not in the app, so there is ONE copy of the
   * terms rather than a bundled snapshot that silently goes stale the moment they are
   * revised — which for an agreement someone is being held to is the difference between
   * a document and a screenshot.
   */
  async function openLegal(path: string) {
    await WebBrowser.openBrowserAsync(`${API_BASE}${path}`)
  }

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

          <View style={{ marginTop: space.md }}>
            <Row
              icon="person-outline"
              label="Edit Profile"
              detail="Your name as it appears in IronForge"
              onPress={() => router.push('/edit-profile')}
              first
            />
            <Row
              icon="lock-closed-outline"
              label="Change Password"
              detail="Signs you out on every device"
              onPress={() => router.push('/change-password')}
            />
          </View>
        </Card>

        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Membership and Billing</SectionLabel>
        </View>
        <Card>
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
              {billing?.membership?.plan ?? (data?.hasMembership ? 'Membership' : 'No membership')}
            </Text>
            {billing?.membership ? (
              <View style={[s.pill, { borderColor: statusColor(billing.membership.status) }]}>
                <Text style={[type.label, { color: statusColor(billing.membership.status) }]}>
                  {billing.membership.badge}
                </Text>
              </View>
            ) : null}
          </View>

          {billing?.membership ? (
            <>
              <Text
                style={[type.title, { color: color.text, fontFamily: font.display, marginTop: space.sm }]}
              >
                ${billing.membership.price_monthly}
                <Text style={[type.body, { color: color.textDim, fontFamily: font.body }]}>
                  {' '}/ month
                </Text>
              </Text>
              {billing.membership.next_billing_date ? (
                <Text style={[type.label, { color: color.textDim, marginTop: space.xs }]}>
                  {billing.membership.status === 'canceled' ? 'Access ends' : 'Next billing date'}:{' '}
                  {formatBillingDate(billing.membership.next_billing_date)}
                </Text>
              ) : null}
            </>
          ) : (
            <Text style={[type.body, { color: color.textDim, marginTop: space.sm }]}>
              You do not have an active membership.
            </Text>
          )}
          {/*
            APP-039, Must Have, MVP. Present on every platform — the 3.1.1 problem was
            never this button, it was WHICH portal the server opened: Stripe's default
            configuration permits changing plan. The route now serves mobile a
            configuration with subscription updates disabled, and refuses rather than
            falling back to the default one. See api/billing/portal/route.ts.
          */}
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

        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Legal</SectionLabel>
        </View>
        <Card>
          {/*
            The app had no route to the Terms or the Privacy Policy anywhere. For an app
            carrying a member feed that is a Guideline 1.2 gap as much as a courtesy one:
            the terms are where the no-tolerance-for-objectionable-content agreement
            lives, and a reviewer looks for it.

            System browser, not a WebView — same reason as everywhere else in this file,
            the customer gets to see the real URL.
          */}
          <Row
            icon="document-text-outline"
            label="Terms of Service"
            onPress={() => openLegal('/terms')}
            first
          />
          <Row
            icon="lock-closed-outline"
            label="Privacy Policy"
            onPress={() => openLegal('/privacy')}
          />
        </Card>

        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Danger Zone</SectionLabel>
        </View>
        <Card>
          {/*
            App Store Review Guideline 5.1.1(v) requires account deletion to be initiable
            from INSIDE the app. Google Play accepts the public /delete-account URL and
            that is what shipped, so until now the app had no deletion path at all — one
            of the most common first-submission rejections on iOS.

            It lives under its own heading rather than in Security so it is findable, and
            it routes to a screen that explains the consequences rather than firing an
            Alert straight from a tap.
          */}
          <Row
            icon="trash-outline"
            label="Delete Account"
            detail="Cancel your membership and permanently erase your data"
            onPress={() => router.push('/delete-account')}
            first
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

/** past_due is the one status that needs the customer to act, so it reads as a warning. */
function statusColor(status: string): string {
  if (status === 'past_due') return color.warn
  if (status === 'canceled') return color.neg
  return color.pos
}

/**
 * next_billing_date is a plain YYYY-MM-DD from the server, deliberately unformatted.
 * Parsed as LOCAL, not UTC — `new Date('2026-08-31')` is midnight UTC, which renders as
 * the 30th anywhere west of Greenwich and would show the wrong billing day.
 */
function formatBillingDate(d: string): string {
  const [y, m, day] = d.split('-').map(Number)
  if (!y || !m || !day) return d
  return new Date(y, m - 1, day).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
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
