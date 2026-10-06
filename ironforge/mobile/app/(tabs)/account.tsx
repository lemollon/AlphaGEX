import { useEffect, useMemo, useRef, useState } from 'react'
import { View, Text, ScrollView, Pressable, Switch, StyleSheet, Alert, Linking, Platform } from 'react-native'
import { usePreventScreenCapture } from 'expo-screen-capture'
import { useScrollToTop } from '@react-navigation/native'
import * as Clipboard from 'expo-clipboard'
import { SafeAreaView } from 'react-native-safe-area-context'
import * as WebBrowser from 'expo-web-browser'
import { useRouter } from 'expo-router'
import useSWR, { mutate as globalMutate } from 'swr'
import Constants from 'expo-constants'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { api, API_BASE, ApiError } from '@/api/client'
import type {
  MobileMe,
  MembershipResponse,
  PaymentMethodResponse,
  AutomationPauseResponse,
  AutomationActivation,
  EntitlementsResponse,
} from '@/api/types'
import { signOut, biometricsAvailable, isBiometricEnabled, setBiometricEnabled } from '@/auth/session'
import { unregisterPushDevice } from '@/notifications/push'
import { canManageBillingInApp, manageSubscriptionUrl } from '@/billing/store-policy'
import { space, radius, type, font, agentAccent } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Card, SectionLabel, Row, Loading, ErrorState } from '@/components/ui'
import { AppHeader, Mascot, SPARKY_AVATAR } from '@/components/Brand'
import { SUPPORT_EMAIL, supportMailto } from '@/support/contact'
import { BrokerageSection } from '@/components/BrokerageSection'
import { AGENT_LABEL } from '@/agents/copy'
import { agentDetailHref, type AgentBot } from '@/agents/routes'
import { getPlanCatalog } from '@/enroll/api'
import type { PlanCatalog } from '@/enroll/types'
import { showToast } from '@/notifications/toast'
import { trackEvent } from '@/analytics/trackEvent'

const ALL_BOTS: AgentBot[] = ['spark', 'flame', 'ember']

/**
 * Account — UX-006 (APP-037/038/039/040/043/044/058/059/060).
 *
 * "Manage Membership & Billing" opens a SERVER-CREATED Stripe portal session in the
 * system browser, never a WebView, so the customer can see the real URL and padlock —
 * which is the whole trust argument for handing over card details.
 *
 * The control is HIDDEN on iOS (APP-039 exception) per `canManageBillingInApp` in
 * src/billing/store-policy.ts — Apple rejected the app 2026-09-14 (Guideline 3.1.1)
 * for exposing this exact control, even restricted to a no-plan-change Stripe
 * configuration. See store-policy.ts for the full reasoning. Android and web keep it.
 *
 * iOS gets its OWN membership control instead (Apple IAP handoff, "Mobile contract"
 * §4), keyed off `billing.membership.provider`: an 'apple' membership shows "Manage
 * subscription" deep-linking to Apple's own App Store subscription settings
 * (`manageSubscriptionUrl` — that is Apple's IAP management UI, not a competing
 * purchase surface, so 3.1.1 does not apply to it); a 'stripe' (or unknown-provider)
 * membership on iOS shows a plain sentence with NO link or button at all — naming
 * ironforge.trade as the place to manage it would itself be the call-to-action
 * Guideline 3.1.1 exists to prevent.
 *
 * NOTE for whoever wires the membership card: the plan name comes from
 * LiveSummary.membership, which the server derives from real subscription rows and
 * fails SOFT to a neutral card. Do not hardcode a plan name here — a hardcoded
 * "Forge Automate" card that rendered identically for payers, trialers and
 * non-subscribers is exactly the bug that was deleted when Stripe landed.
 */
export default function AccountScreen() {
  // Dev handoff mobile Security checklist: block screenshots/screen recording
  // on the billing screen. This whole tab is the only screen that renders the
  // membership/billing card (plan, price, payment method last 4) — there is
  // no separate /account/billing route to scope this to more narrowly.
  usePreventScreenCapture()
  const { colors: color, scheme, setPreference } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()
  // Re-tap-tab-to-scroll-to-top (#231).
  const scrollRef = useRef<ScrollView>(null)
  useScrollToTop(scrollRef)
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
  // Payment method row (fidelity audit) — only meaningful for a Stripe-billed
  // membership; Apple IAP has no Stripe card to show, so this is never fetched there.
  const stripeBilled = billing?.membership != null && billing.membership.provider !== 'apple'
  const { data: paymentMethod } = useSWR<PaymentMethodResponse>(
    stripeBilled ? '/api/billing/payment-method' : null,
    (p: string) => api<PaymentMethodResponse>(p),
  )
  // "Pause all agents" (10.4 app.html Account tab, flagged MISSING in the gap
  // audit — only a per-agent pause existed). The server already supports a
  // bulk pause/resume: POST /api/v1/automation/pause with no `agent` field
  // updates every one of this customer's activations at once (see the route's
  // `agent ?? 'all'` audit-log fallback) — no backend change needed, just a
  // control that calls it that way.
  const pauseSWR = useSWR<AutomationPauseResponse>('/api/v1/automation/pause', (p: string) =>
    api<AutomationPauseResponse>(p),
  )
  // Ember ownership (#3177) — /api/v1/automation/pause never includes Ember (it has no
  // spark/flame-style activation row; see automation/pause/route.ts's agent allowlist),
  // so the inline agent list below needs this separately to know whether to render
  // Ember as an owned row or an "Add Ember" row. Same cache key the Forge tab and the
  // agent sheet already fetch — SWR shares it.
  const entitlementsSWR = useSWR<EntitlementsResponse>('/api/billing/entitlements', (p: string) =>
    api<EntitlementsResponse>(p),
  )
  // Per-agent price/trial rows (#253) — the real catalogue, same unauthenticated
  // route /enroll/plan.tsx reads, cached indefinitely by SWR's default dedupe since
  // prices change by redeploy, not by anything this screen does.
  const { data: catalog } = useSWR<PlanCatalog>('/api/public/plans', () => getPlanCatalog())
  const [pausingAll, setPausingAll] = useState(false)
  // In-flight guard per agent (10.4 design `.lrow` inline switch) — a Set rather than
  // one shared boolean so flipping Spark's switch does not disable Flame's.
  const [togglingAgents, setTogglingAgents] = useState<Set<string>>(new Set())
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
      // The route's body carries a machine code (`no_subscription`, `portal_unconfigured`)
      // rather than a customer sentence for these two, so the status decides the copy here
      // instead of trusting ApiError.humanMessage to fall back to the raw code.
      if (e instanceof ApiError && e.status === 409) {
        Alert.alert('Billing unavailable', 'No active subscription to manage.')
        return
      }
      if (e instanceof ApiError && e.status === 503) {
        Alert.alert('Billing unavailable', 'Billing portal is temporarily unavailable.')
        return
      }
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

  /**
   * "Agreements and Disclosures" (10.4 design Help card) — one row reaching both
   * documents, the same Alert.alert pattern already used for the Appearance picker,
   * rather than two separate rows under a standalone "Legal" heading.
   */
  function openAgreements() {
    Alert.alert('Agreements and Disclosures', undefined, [
      { text: 'Terms of Service', onPress: () => void openLegal('/terms') },
      { text: 'Privacy Policy', onPress: () => void openLegal('/privacy') },
      { text: 'Cancel', style: 'cancel' },
    ])
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

  async function togglePauseAll(nextPaused: boolean) {
    setPausingAll(true)
    try {
      const res = await api<AutomationPauseResponse>('/api/v1/automation/pause', {
        method: 'POST',
        body: { paused: nextPaused },
      })
      pauseSWR.mutate(res, { revalidate: false })
      // Same shared SWR cache key the Forge tab and each agent sheet poll — this is
      // what makes both reflect the bulk change without either screen doing anything.
      void globalMutate('/api/live/agents')
      if (nextPaused) trackEvent('pause_all')
      Alert.alert(
        nextPaused ? 'All agents paused' : 'All agents resumed',
        nextPaused
          ? "No agent will open a new trade. Any open trade stays protected and closes by the end of its session."
          : 'Your agents can open new trades again.',
      )
    } catch (e) {
      Alert.alert('Could not update', e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setPausingAll(false)
    }
  }

  /**
   * One agent's inline switch (10.4 design Account tab `.lrow` + Switch) — the SAME
   * pause endpoint the agent sheet's PauseResumeControl calls, just reached with one
   * tap instead of opening the sheet. Design's switch toggles instantly (no confirm
   * step), so this mirrors that directly — the sheet's own control keeps its
   * confirmation dialog for the drill-down path, this does not duplicate it.
   */
  async function toggleAgent(bot: string, nextPaused: boolean) {
    setTogglingAgents((prev) => new Set(prev).add(bot))
    try {
      const res = await api<AutomationPauseResponse>('/api/v1/automation/pause', {
        method: 'POST',
        body: { paused: nextPaused, agent: bot },
      })
      pauseSWR.mutate(res, { revalidate: false })
      void globalMutate('/api/live/agents')
      showToast(`${AGENT_LABEL[bot as keyof typeof AGENT_LABEL] ?? bot} ${nextPaused ? 'paused' : 'resumed'}`)
    } catch (e) {
      showToast(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setTogglingAgents((prev) => {
        const next = new Set(prev)
        next.delete(bot)
        return next
      })
    }
  }

  function confirmPauseAll(nextPaused: boolean) {
    Alert.alert(
      nextPaused ? 'Pause all agents?' : 'Resume all agents?',
      nextPaused
        ? "Pausing stops new trades. An open trade stays protected and closes by the end of its session."
        : 'Your agents will be able to open new trades again.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: nextPaused ? 'Pause all' : 'Resume all',
          style: nextPaused ? 'destructive' : 'default',
          onPress: () => void togglePauseAll(nextPaused),
        },
      ],
    )
  }

  async function doSignOut() {
    // Unregister the push token BEFORE the tokens that authorize doing so are cleared
    // (cross-package contract, SPEC.md) — signOut() afterward would leave this device's
    // token live server-side with no session left to revoke it with.
    await unregisterPushDevice().catch(() => {})
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
  const platform = Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : 'web'

  return (
    <Shell>
      <ScrollView ref={scrollRef} contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}>
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
            {/* 10.4 design `.lrow` "Password & Face ID" is one row — the change-
                password screen and the biometric switch fold under it here instead
                of a standalone "Security" section the design never has. */}
            <Row
              icon="lock-closed-outline"
              label="Password & Face ID"
              detail="Signs you out on every device"
              onPress={() => router.push('/change-password')}
            />
            <View style={[s.rowBetween, s.row, s.rowDivider]}>
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
          </View>
        </Card>

        {/* 10.4 design "Agents & billing" — one heading over the agent list, the
            membership/billing card and the payment method, not the separate
            "Trading" + "Membership and Billing" headings this used to split them
            into. */}
        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Agents and Billing</SectionLabel>
        </View>
        <Card>
          <Row
            icon="flash-outline"
            label="Agents"
            detail="View and manage Spark and Flame"
            onPress={() => router.push('/agents')}
            first
          />
        </Card>
        <Card style={{ marginTop: space.md }}>
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
              {billing?.membership?.plan ?? (data?.hasMembership ? 'Membership' : 'No membership')}
            </Text>
            {billing?.membership ? (
              <View style={[s.pill, { borderColor: statusColor(billing.membership.status, color) }]}>
                <Text style={[type.label, { color: statusColor(billing.membership.status, color) }]}>
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
            APP-039, Must Have, MVP — present on Android/web. Hidden on iOS: Apple
            rejected 2026-09-14 (Guideline 3.1.1) for exposing this control at all,
            even pointed at a Stripe portal with plan changes disabled server-side.
            See canManageBillingInApp in src/billing/store-policy.ts.

            iOS gets its own branch below instead of nothing: an 'apple' membership
            (Apple IAP handoff §4) still needs SOME way to manage it, just not this
            one — Apple's own subscription settings, never Stripe's.
          */}
          {canManageBillingInApp(platform) ? (
            <Pressable onPress={openBilling} style={s.outlineBtn}>
              <Text style={[type.body, { color: color.accentText, fontFamily: font.bodyMedium }]}>
                Manage Membership and Billing (opens secure Stripe portal)
              </Text>
            </Pressable>
          ) : platform === 'ios' && billing?.membership ? (
            billing.membership.provider === 'apple' ? (
              <Pressable
                onPress={() => {
                  const url = manageSubscriptionUrl(billing.membership!.provider, platform)
                  if (url) Linking.openURL(url).catch(() => {})
                }}
                style={s.outlineBtn}
              >
                <Text style={[type.body, { color: color.accentText, fontFamily: font.bodyMedium }]}>
                  Manage subscription
                </Text>
              </Pressable>
            ) : (
              <Text style={[type.body, { color: color.textDim, marginTop: space.lg }]}>
                Billing for this membership is managed on the web.
              </Text>
            )
          ) : null}
          {stripeBilled && paymentMethod?.paymentMethod ? (
            <View style={[s.rowBetween, { marginTop: space.lg }]}>
              <View style={s.rowCenter}>
                <Ionicons name="card-outline" size={18} color={color.textDim} />
                <Text style={[type.body, { color: color.text, marginLeft: space.sm }]}>
                  {capitalize(paymentMethod.paymentMethod.brand)} •••• {paymentMethod.paymentMethod.last4}
                </Text>
              </View>
            </View>
          ) : null}
          {billing?.membership?.provider !== 'apple' ? (
            <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
              Securely managed through Stripe
            </Text>
          ) : null}
        </Card>

        {/* Inline per-agent rows (10.4 design Account tab `.lrow` + Switch,
            ironforge-app.html line ~663-664) — one row per OWNED agent with its
            pause/resume switch, PLUS an inline "Add {Agent}" row for anything this
            viewer does not yet own, all in the same card. Previously only the
            owned-agent switches existed; there was no way to add Spark/Flame/Ember
            without leaving Account for the Forge tab or /agents.
            Price/trial (#253) come from real sources only: the public plan
            catalogue (GET /api/public/plans, the same unauthenticated route
            /enroll/plan.tsx reads) for price_monthly and trial_days, and the
            membership row already fetched above for trial state — never a
            hardcoded or guessed number. */}
        {(() => {
          const ownedAgentBots = new Set(
            (pauseSWR.data?.activations ?? []).map((a) => a.agent as AgentBot),
          )
          const ownsEmber = (entitlementsSWR.data?.bots ?? []).includes('ember')
          if (ownsEmber) ownedAgentBots.add('ember')
          const addableBots = ALL_BOTS.filter((b) => !ownedAgentBots.has(b))
          if (ownedAgentBots.size === 0 && addableBots.length === 0) return null
          return (
            <Card style={{ marginTop: space.md }}>
              {(pauseSWR.data?.activations ?? []).map((a, i) => {
                const priceLabel = agentPriceLabel(a.agent, catalog)
                const inTrial =
                  billing?.membership?.status === 'trialing' && (billing.membership.bots ?? []).includes(a.agent)
                const subtitle = [
                  priceLabel,
                  inTrial ? (billing?.membership?.trial_ending_soon ? 'Trial ending soon' : 'Trial') : null,
                  a.paused ? 'Paused' : 'Trading',
                  'Community included',
                ]
                  .filter(Boolean)
                  .join(' · ')
                return (
                  <View key={a.agent} style={[s.agentRow, i > 0 && s.agentRowDivider]}>
                    <Mascot bot={a.agent} size={30} />
                    <View style={{ flex: 1, marginLeft: space.md }}>
                      <Text
                        style={[
                          type.body,
                          { color: agentAccent(a.agent as AgentBot), fontFamily: font.bodyBold },
                        ]}
                      >
                        {AGENT_LABEL[a.agent as keyof typeof AGENT_LABEL] ?? a.agent}
                      </Text>
                      <Text style={[type.label, { color: color.muted, marginTop: 1 }]} numberOfLines={1}>
                        {subtitle}
                      </Text>
                    </View>
                    <Switch
                      value={!a.paused}
                      disabled={togglingAgents.has(a.agent)}
                      onValueChange={(on) => void toggleAgent(a.agent, !on)}
                      trackColor={{ true: color.accent, false: color.border }}
                    />
                  </View>
                )
              })}
              {addableBots.map((bot, i) => {
                const priceLabel = agentPriceLabel(bot, catalog)
                const subtitle =
                  bot === 'ember'
                    ? 'Free · one account per person'
                    : [priceLabel, catalog ? `${catalog.trial_days}-day free trial` : null, 'Community included']
                        .filter(Boolean)
                        .join(' · ')
                return (
                  <Pressable
                    key={bot}
                    onPress={() => router.push(agentDetailHref(bot))}
                    accessibilityRole="button"
                    style={[s.agentRow, (i > 0 || ownedAgentBots.size > 0) && s.agentRowDivider]}
                  >
                    <Mascot bot={bot} size={30} />
                    <View style={{ flex: 1, marginLeft: space.md }}>
                      <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>
                        {`Add ${AGENT_LABEL[bot]}`}
                      </Text>
                      <Text style={[type.label, { color: color.muted, marginTop: 1 }]} numberOfLines={1}>
                        {subtitle}
                      </Text>
                    </View>
                    <View style={[s.addTag, { borderColor: color.border }]}>
                      <Text style={[type.label, { color: color.textDim, fontFamily: font.bodyMedium }]}>
                        Add
                      </Text>
                    </View>
                  </Pressable>
                )
              })}
            </Card>
          )
        })()}

        <BrokerageSection />

        {/* 10.4 design "Alerts & display" — Notifications and Appearance together,
            not two separate headings. */}
        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Alerts and Display</SectionLabel>
        </View>
        <Card>
          <Row
            icon="notifications-outline"
            label="Notifications"
            detail="Alerts and push preferences"
            onPress={() => router.push('/notifications')}
            first
          />
          {/* 10.4 design (ironforge-app.html `#dmSw`): an inline Switch, not the
              Alert.alert System/Light/Dark picker this used to be. The design's own
              row is a plain binary "Dark mode" toggle with no inline System option,
              so flipping it always sets an explicit preference — same as the design's
              setTheme(checked?'dark':'light'). 'system' as a stored preference is
              still supported (ThemeContext/preference.ts); this row just never writes
              it, matching the one control the design actually shows here. */}
          <View style={[s.rowBetween, s.row, s.rowDivider]}>
            <View style={s.rowCenter}>
              <Ionicons name="moon-outline" size={18} color={color.textDim} />
              <Text style={[type.body, { color: color.text }]}>Dark mode</Text>
            </View>
            <Switch
              value={scheme === 'dark'}
              onValueChange={(on) => {
                const pref = on ? 'dark' : 'light'
                setPreference(pref)
                trackEvent('theme_toggle', { theme: pref })
              }}
              trackColor={{ true: color.accent, false: color.border }}
            />
          </View>
        </Card>

        {/* 10.4 design "Help" — Ask Sparky, Email support and (folded in here, under
            one design-consistent row rather than the standalone "Legal" and "Danger
            Zone" headings the design never has) the agreements/legal documents and
            account deletion every store review still requires reachable. */}
        <View style={{ marginTop: space.xl }}>
          <SectionLabel>Help</SectionLabel>
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
          {/*
            Terms and Privacy still open in the system browser, not a WebView, for the
            same reason as everywhere else in this file — the customer sees the real
            URL. One row reaches both, rather than a standalone "Legal" section.
          */}
          <Row
            icon="document-text-outline"
            label="Agreements and Disclosures"
            detail="Terms of Service and Privacy Policy"
            onPress={openAgreements}
          />
          {/*
            App Store Review Guideline 5.1.1(v) requires account deletion to be
            initiable from INSIDE the app — kept reachable here instead of under its
            own "Danger Zone" heading the design never has. Routes to a screen that
            explains the consequences rather than firing an Alert straight from a tap.
          */}
          <Row
            icon="trash-outline"
            label="Delete Account"
            detail="Cancel your membership and permanently erase your data"
            onPress={() => router.push('/delete-account')}
            tint={color.neg}
          />
        </Card>

        {(pauseSWR.data?.activations.length ?? 0) > 0 ? (
          <Pressable
            onPress={() => confirmPauseAll(!allAgentsPaused(pauseSWR.data?.activations))}
            disabled={pausingAll}
            style={[s.pauseAllBtn, { opacity: pausingAll ? 0.5 : 1 }]}
          >
            <Ionicons name="pause-circle-outline" size={18} color={color.neg} />
            <Text style={[type.body, { color: color.neg, fontFamily: font.bodyMedium, marginLeft: space.sm }]}>
              {pausingAll
                ? 'Working…'
                : allAgentsPaused(pauseSWR.data?.activations)
                  ? 'Resume all agents'
                  : 'Pause all agents'}
            </Text>
          </Pressable>
        ) : null}

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

/** True only when there is at least one activation AND every one of them is
 *  paused — an empty list is "nothing to resume", not "everything paused". */
function allAgentsPaused(activations: AutomationActivation[] | undefined): boolean {
  if (!activations || activations.length === 0) return false
  return activations.every((a) => a.paused)
}

/**
 * The real monthly price for one agent (#253) — Ember is genuinely free (no Apple
 * product, no Stripe price, see src/billing/apple-products.ts), Spark/Flame come
 * from the public plan catalogue. Returns null while the catalogue is still
 * loading rather than a placeholder number.
 */
function agentPriceLabel(bot: string, catalog: PlanCatalog | undefined): string | null {
  if (bot === 'ember') return 'Free'
  const entry = catalog?.bots.find((b) => b.slug === bot)
  return entry ? `$${entry.price_monthly}/month` : null
}

/** past_due is the one status that needs the customer to act, so it reads as a warning. */
function statusColor(status: string, color: ColorTokens): string {
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

/** Stripe's card.brand is lowercase ("visa", "mastercard") — title-case it for display. */
function capitalize(s: string): string {
  return s.length > 0 ? s[0].toUpperCase() + s.slice(1) : s
}

function memberSince(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

function Shell({ children }: { children: React.ReactNode }) {
  const { colors: color } = useTheme()
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }} edges={['top']}>
      <AppHeader />
      {children}
    </SafeAreaView>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
  title: { ...type.title, color: color.text, fontFamily: font.display, marginBottom: space.lg },
  rowCenter: { flexDirection: 'row', alignItems: 'center', gap: space.lg },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  // Mirrors components/ui.tsx's Row — so a plain (non-navigating, switch-ended)
  // row sits flush with the Row-based rows above and below it in the same Card.
  row: { paddingVertical: space.md },
  rowDivider: { borderTopWidth: 1, borderTopColor: color.border },
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
  pauseAllBtn: {
    marginTop: space.xl,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: color.neg,
    borderRadius: radius.md,
    paddingVertical: space.md,
  },
  signOut: { marginTop: space.xxl, alignItems: 'center', paddingVertical: space.md },
  agentRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.md },
  agentRowDivider: { borderTopWidth: 1, borderTopColor: color.border },
  addTag: {
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: space.sm,
    paddingVertical: 4,
  },
  })
