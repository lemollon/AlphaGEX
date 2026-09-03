import { useState } from 'react'
import { View, Text, ScrollView, Pressable, StyleSheet, Alert } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter, useLocalSearchParams } from 'expo-router'
import * as WebBrowser from 'expo-web-browser'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { mutate as globalMutate } from 'swr'
import { api, API_BASE, ApiError } from '@/api/client'
import type {
  LiveAgents,
  LiveAgent,
  EntitlementsResponse,
  AutomationPauseResponse,
  AutomationActivation,
  BrokerageConnections,
  BrokerageAccount,
  BrokerageConnection,
  AgentConfigResponse,
  ActivationPreviewResponse,
  ActivationResponse,
} from '@/api/types'
import { color, space, radius, type, font, agentAccent } from '@/theme/tokens'
import { Card, SectionLabel, Money, Loading, ErrorState } from '@/components/ui'
import { Mascot } from '@/components/Brand'
import { soleConnection, brokerLabel } from '@/api/brokerage'
import { track } from '@/analytics/track'
import { agentAction, type AgentActionKind } from '@/agents/eligibility'
import type { AgentBot } from '@/agents/routes'
import {
  AGENT_LABEL,
  AGENT_DESCRIPTION,
  ACCOUNT_REQUIREMENTS,
  TRADING_SCHEDULE,
  RISK_SUMMARY,
} from '@/agents/copy'
import { formatPausedAt } from '@/agents/time'

const DOT_COLOR: Record<string, string> = {
  green: color.pos,
  blue: color.spark,
  amber: color.warn,
  red: color.neg,
  gray: color.muted,
}

const PAUSE_COPY =
  "Stops new entries. Open positions continue to be managed by the agent's risk rules."

/**
 * Agent detail (APP-024) — one screen, five renderings, driven entirely by
 * agentAction(). Active/Paused get the live status + pause control (APP-028/029);
 * Add gets the activation flow (APP-025); Setup Required and Switch each get an
 * explanation and hand off to the web, because neither has an in-app endpoint.
 */
export default function AgentDetailScreen() {
  const router = useRouter()
  const params = useLocalSearchParams<{ bot: string }>()
  const bot = (params.bot === 'flame' ? 'flame' : 'spark') as AgentBot
  const label = AGENT_LABEL[bot]

  const agentsSWR = useSWR<LiveAgents>('/api/live/agents', (p: string) => api<LiveAgents>(p))
  const entitlementsSWR = useSWR<EntitlementsResponse>('/api/billing/entitlements', (p: string) =>
    api<EntitlementsResponse>(p),
  )
  const pauseSWR = useSWR<AutomationPauseResponse>('/api/v1/automation/pause', (p: string) =>
    api<AutomationPauseResponse>(p),
  )
  const connsSWR = useSWR<BrokerageConnections>('/api/brokerage/connections', (p: string) =>
    api<BrokerageConnections>(p),
  )

  const loading =
    agentsSWR.isLoading || entitlementsSWR.isLoading || pauseSWR.isLoading || connsSWR.isLoading
  const failed = agentsSWR.error || pauseSWR.error

  if (loading) {
    return (
      <Shell bot={bot} router={router}>
        <Loading label={`Loading ${label}…`} />
      </Shell>
    )
  }
  if (failed) {
    return (
      <Shell bot={bot} router={router}>
        <ErrorState
          message={`Could not load ${label} right now.`}
          onRetry={() => {
            agentsSWR.mutate()
            pauseSWR.mutate()
            connsSWR.mutate()
          }}
        />
      </Shell>
    )
  }

  const liveAgent = agentsSWR.data?.agents.find((a) => a.bot === bot) ?? null
  const eligibleAccounts = (connsSWR.data?.connections ?? []).flatMap((c) =>
    c.accounts
      .filter((a) => a.eligibility === 'eligible')
      .map((a) => ({ account: a, connection: c })),
  )
  const activations: AutomationActivation[] = pauseSWR.data?.activations ?? []
  const action = agentAction({
    bot,
    entitlements: entitlementsSWR.data?.bots ?? [],
    activations: activations.map((a) => ({ agent: a.agent, paused: a.paused })),
    eligibleAccountCount: eligibleAccounts.length,
  })

  return (
    <Shell bot={bot} router={router}>
      <ScrollView contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}>
        <View style={s.rowCenter}>
          <Mascot bot={bot} size={44} />
          <View style={{ flex: 1 }}>
            <Text style={[type.title, { color: color.text, fontFamily: font.display }]}>
              {label}
            </Text>
            <View style={s.rowCenter}>
              <View
                style={[
                  s.dot,
                  {
                    backgroundColor: liveAgent?.state
                      ? (DOT_COLOR[liveAgent.state.dot] ?? color.muted)
                      : color.muted,
                  },
                ]}
              />
              <Text style={[type.label, { color: color.textDim }]}>
                {liveAgent?.state?.headline ?? action.label}
              </Text>
            </View>
          </View>
        </View>

        <Card style={{ marginTop: space.lg }}>
          <SectionLabel>How it works</SectionLabel>
          <Text style={[type.body, { color: color.textDim }]}>{AGENT_DESCRIPTION[bot]}</Text>
          <Text style={[type.body, { color: color.textDim, marginTop: space.md }]}>
            {TRADING_SCHEDULE[bot]}
          </Text>
          <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
            Account requirements
          </Text>
          <Text style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
            {ACCOUNT_REQUIREMENTS}
          </Text>
          <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
            Risk summary
          </Text>
          <Text style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
            {RISK_SUMMARY}
          </Text>
        </Card>

        {action.kind === 'active' || action.kind === 'paused' ? (
          <CurrentAgentSection
            bot={bot}
            label={label}
            liveAgent={liveAgent}
            activation={activations.find((a) => a.agent === bot) ?? null}
            connections={connsSWR.data}
            agentsSWR={agentsSWR}
            connsSWR={connsSWR}
            pauseSWR={pauseSWR}
          />
        ) : action.kind === 'setup_required' ? (
          <SetupRequiredSection bot={bot} label={label} />
        ) : action.kind === 'switch' ? (
          <SwitchSection bot={bot} label={label} otherAgent={agentsSWR.data?.agents.find((a) => a.bot !== bot) ?? null} />
        ) : (
          <ActivationFlow bot={bot} label={label} eligibleAccounts={eligibleAccounts} />
        )}
      </ScrollView>
    </Shell>
  )
}

function Shell({
  bot,
  router,
  children,
}: {
  bot: AgentBot
  router: ReturnType<typeof useRouter>
  children: React.ReactNode
}) {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }} edges={['top']}>
      <View style={s.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={26} color={color.text} />
        </Pressable>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
          {AGENT_LABEL[bot]}
        </Text>
      </View>
      {children}
    </SafeAreaView>
  )
}

/** Active or Paused: live status, assigned account, latest trade, pause/resume. */
function CurrentAgentSection({
  bot,
  label,
  liveAgent,
  activation,
  connections,
  agentsSWR,
  connsSWR,
  pauseSWR,
}: {
  bot: AgentBot
  label: string
  liveAgent: LiveAgent | null
  activation: AutomationActivation | null
  connections: BrokerageConnections | undefined
  agentsSWR: ReturnType<typeof useSWR<LiveAgents>>
  connsSWR: ReturnType<typeof useSWR<BrokerageConnections>>
  pauseSWR: ReturnType<typeof useSWR<AutomationPauseResponse>>
}) {
  const state = liveAgent?.state ?? null
  const trade = liveAgent?.trade ?? null
  const sole = soleConnection(connections)
  const accent = agentAccent(bot)

  return (
    <>
      <Card style={{ marginTop: space.lg, borderColor: accent }}>
        <SectionLabel>Current status</SectionLabel>
        {liveAgent?.error === 'state' || !state ? (
          <Text style={[type.body, { color: color.warn }]}>
            Status is unavailable for {label} right now.
          </Text>
        ) : (
          <>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              {state.headline}
            </Text>
            <Text style={[type.label, { color: color.textDim, marginTop: space.xs }]}>
              {state.subtitle}
            </Text>
            {state.check_line ? (
              <Text style={[type.label, { color: color.muted, marginTop: space.xs }]}>
                {state.check_line}
              </Text>
            ) : null}
          </>
        )}

        <View style={s.divider} />
        <Text style={[type.label, { color: color.muted }]}>Brokerage account</Text>
        <Text style={[type.body, { color: color.text, marginTop: space.xs }]}>
          {sole
            ? `${brokerLabel(sole.broker ?? sole.provider)}${sole.mask ? `  •••• ${sole.mask}` : ''}`
            : 'Not available'}
        </Text>

        <View style={s.divider} />
        <Text style={[type.label, { color: color.muted, marginBottom: space.xs }]}>
          Latest trade
        </Text>
        {liveAgent?.error === 'trade' ? (
          <Text style={[type.body, { color: color.warn }]}>
            Position details are unavailable right now.
          </Text>
        ) : trade?.active ? (
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text }]}>Open position</Text>
            <Money value={trade.unrealized_pnl} />
          </View>
        ) : trade?.today_result ? (
          <View style={s.rowBetween}>
            <Text style={[type.body, { color: color.text }]}>Today&apos;s result</Text>
            <Money value={trade.today_result.pnl} />
          </View>
        ) : (
          <Text style={[type.body, { color: color.textDim }]}>No recent trade.</Text>
        )}
      </Card>

      <PauseResumeControl
        bot={bot}
        label={label}
        activation={activation}
        agentsSWR={agentsSWR}
        connsSWR={connsSWR}
        pauseSWR={pauseSWR}
      />
    </>
  )
}

/** Pause / Resume — APP-028/029. */
function PauseResumeControl({
  bot,
  label,
  activation,
  agentsSWR,
  connsSWR,
  pauseSWR,
}: {
  bot: AgentBot
  label: string
  activation: AutomationActivation | null
  agentsSWR: ReturnType<typeof useSWR<LiveAgents>>
  connsSWR: ReturnType<typeof useSWR<BrokerageConnections>>
  pauseSWR: ReturnType<typeof useSWR<AutomationPauseResponse>>
}) {
  const [pending, setPending] = useState(false)
  const paused = activation?.paused ?? false
  const accent = agentAccent(bot)

  async function doToggle(nextPaused: boolean) {
    setPending(true)
    try {
      const res = await api<AutomationPauseResponse>('/api/v1/automation/pause', {
        method: 'POST',
        body: { paused: nextPaused, agent: bot },
      })
      pauseSWR.mutate(res, { revalidate: false })
      // Shared SWR cache key with the Forge tab — this is what makes AgentTile there
      // reflect the new paused state without that screen doing anything itself.
      void globalMutate('/api/live/agents')
      track(nextPaused ? 'agent_pause_confirmed' : 'agent_resume_confirmed', { agent: bot })

      const row = res.activations.find((a) => a.agent === bot)
      const when = formatPausedAt(row?.paused_at ?? null)
      Alert.alert(
        nextPaused ? 'Trading paused' : 'Trading resumed',
        nextPaused
          ? `${label} will not open new trades.${when ? ` Effective ${when}.` : ''} Open positions continue to be managed by the agent's risk rules.`
          : `${label} can open new trades again.${when ? ` Effective ${when}.` : ''}`,
      )
    } catch (e) {
      Alert.alert('Could not update', e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setPending(false)
    }
  }

  function confirmToggle(nextPaused: boolean) {
    Alert.alert(nextPaused ? `Pause ${label}?` : `Resume ${label}?`, PAUSE_COPY, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: nextPaused ? 'Pause' : 'Resume',
        style: nextPaused ? 'destructive' : 'default',
        onPress: () => void doToggle(nextPaused),
      },
    ])
  }

  /**
   * Resume preflight: re-fetch before offering the confirm, and refuse with the
   * reason rather than let a resume race an account that just went bad (SPEC.md).
   */
  async function handleResumeTap() {
    setPending(true)
    try {
      const [freshAgents, freshConns] = await Promise.all([agentsSWR.mutate(), connsSWR.mutate()])
      const fresh = freshAgents?.agents.find((a) => a.bot === bot) ?? null
      const key = fresh?.state?.key
      if (key === 'BLOCKED' || key === 'ACTION_REQUIRED') {
        Alert.alert(
          'Cannot resume yet',
          fresh?.state?.check_line ?? `${label} cannot resume trading right now.`,
        )
        return
      }
      const disconnected = (freshConns?.connections ?? []).some(
        (c) => c.status === 'disconnected' || c.status === 'revoked' || c.status === 'expired',
      )
      if (disconnected) {
        Alert.alert(
          'Cannot resume yet',
          'A connected brokerage needs attention before trading can resume. Fix it from Account first.',
        )
        return
      }
      confirmToggle(false)
    } finally {
      setPending(false)
    }
  }

  return (
    <Pressable
      onPress={() => (paused ? void handleResumeTap() : confirmToggle(true))}
      disabled={pending || !activation}
      style={[
        s.actionBtn,
        { borderColor: paused ? color.pos : accent, opacity: pending || !activation ? 0.5 : 1 },
      ]}
    >
      <Text
        style={[
          type.body,
          { color: paused ? color.pos : accent, fontFamily: font.bodyMedium },
        ]}
      >
        {pending ? 'Working…' : paused ? 'Resume trading' : 'Pause new trading'}
      </Text>
    </Pressable>
  )
}

function SetupRequiredSection({ bot, label }: { bot: AgentBot; label: string }) {
  return (
    <Card style={{ marginTop: space.lg }}>
      <SectionLabel>Setup required</SectionLabel>
      <Text style={[type.body, { color: color.textDim }]}>
        No eligible brokerage account is connected yet. Connect one that is funded and
        approved for automated options trading so {label} can be activated.
      </Text>
      <Pressable
        onPress={() => void WebBrowser.openBrowserAsync(`${API_BASE}/account/brokerage`)}
        style={[s.actionBtn, { borderColor: color.accent, marginTop: space.lg }]}
      >
        <Text style={[type.body, { color: color.accent, fontFamily: font.bodyMedium }]}>
          Connect a brokerage on the web
        </Text>
      </Pressable>
    </Card>
  )
}

function SwitchSection({
  bot,
  label,
  otherAgent,
}: {
  bot: AgentBot
  label: string
  otherAgent: LiveAgent | null
}) {
  const otherLabel = otherAgent?.label ?? (bot === 'spark' ? 'Flame' : 'Spark')
  const hasOpenTrade = otherAgent?.trade?.active === true

  return (
    <Card style={{ marginTop: space.lg }}>
      <SectionLabel>Switch required</SectionLabel>
      <Text style={[type.body, { color: color.textDim }]}>
        {otherLabel} is already active on your only eligible brokerage account. Activating{' '}
        {label} would mean switching that account from {otherLabel} to {label} — it is not
        something both agents can do on the same account at once.
      </Text>
      {hasOpenTrade ? (
        <Text style={[type.body, { color: color.warn, marginTop: space.md }]}>
          {otherLabel} currently has an open position, so switching is not available until it
          closes.
        </Text>
      ) : null}
      <Pressable
        onPress={() => void WebBrowser.openBrowserAsync(`${API_BASE}/agents/${bot}`)}
        style={[s.actionBtn, { borderColor: color.accent, marginTop: space.lg }]}
      >
        <Text style={[type.body, { color: color.accent, fontFamily: font.bodyMedium }]}>
          Manage on the web
        </Text>
      </Pressable>
    </Card>
  )
}

type EligibleAccount = { account: BrokerageAccount; connection: BrokerageConnection }
type ActivationStep = 'select' | 'ack' | 'review' | 'done'

/** Add — APP-025/026/027: account selection -> acknowledgements -> review -> confirm. */
function ActivationFlow({
  bot,
  label,
  eligibleAccounts,
}: {
  bot: AgentBot
  label: string
  eligibleAccounts: EligibleAccount[]
}) {
  const router = useRouter()
  const [step, setStep] = useState<ActivationStep>('select')
  const [accountId, setAccountId] = useState<string | null>(
    eligibleAccounts.length === 1 ? eligibleAccounts[0].account.id : null,
  )
  const [riskAck, setRiskAck] = useState(false)
  const [authAck, setAuthAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [configId, setConfigId] = useState<string | null>(null)
  const [preview, setPreview] = useState<ActivationPreviewResponse | null>(null)
  const [activated, setActivated] = useState<ActivationResponse | null>(null)
  const [idemKey] = useState(() => generateIdempotencyKey())

  if (eligibleAccounts.length === 0) {
    return <SetupRequiredSection bot={bot} label={label} />
  }

  function openWebHandoff() {
    void WebBrowser.openBrowserAsync(`${API_BASE}/agents/${bot}`)
  }

  async function proceedToReview() {
    if (!accountId) return
    setBusy(true)
    setFailure(null)
    try {
      const cfg = await api<AgentConfigResponse>('/api/v1/agent-configs', {
        method: 'POST',
        body: { agent_code: bot, broker_account_id: accountId, config: {} },
      })
      setConfigId(cfg.id)
      const prev = await api<ActivationPreviewResponse>('/api/v1/activations/preview', {
        method: 'POST',
        body: { config_id: cfg.id },
      })
      setPreview(prev)
      setStep('review')
    } catch (e) {
      setFailure(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function confirmActivate() {
    if (!configId || !preview) return
    setBusy(true)
    setFailure(null)
    try {
      // A 2xx from this call is the only thing allowed to say "activated" — api()
      // throws on anything else, so reaching the next line already proves it.
      const res = await api<ActivationResponse>('/api/v1/activations', {
        method: 'POST',
        headers: { 'Idempotency-Key': idemKey },
        body: {
          config_id: configId,
          risk_acknowledged: true,
          authorization_acknowledged: true,
          preview_hash: preview.preview_hash,
        },
      })
      setActivated(res)
      void globalMutate('/api/live/agents')
      void globalMutate('/api/v1/automation/pause')
      setStep('done')
    } catch (e) {
      setFailure(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (step === 'select') {
    return (
      <Card style={{ marginTop: space.lg }}>
        <SectionLabel>Choose an account</SectionLabel>
        {eligibleAccounts.map(({ account, connection }) => {
          const selected = account.id === accountId
          return (
            <Pressable
              key={account.id}
              onPress={() => setAccountId(account.id)}
              style={[s.selectRow, selected && { borderColor: color.accent }]}
            >
              <Ionicons
                name={selected ? 'radio-button-on' : 'radio-button-off'}
                size={20}
                color={selected ? color.accent : color.muted}
              />
              <Text style={[type.body, { color: color.text, marginLeft: space.sm }]}>
                {brokerLabel(connection.broker ?? connection.provider)}
                {account.mask ? `  •••• ${account.mask}` : ''}
              </Text>
            </Pressable>
          )
        })}
        <Pressable
          onPress={() => setStep('ack')}
          disabled={!accountId}
          style={[s.primaryBtn, { opacity: accountId ? 1 : 0.5 }]}
        >
          <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>Continue</Text>
        </Pressable>
      </Card>
    )
  }

  if (step === 'ack') {
    return (
      <Card style={{ marginTop: space.lg }}>
        <SectionLabel>Before you continue</SectionLabel>
        <CheckRow
          checked={riskAck}
          onToggle={() => setRiskAck((v) => !v)}
          label="I understand automated options trading involves risk, including the risk of loss."
        />
        <CheckRow
          checked={authAck}
          onToggle={() => setAuthAck((v) => !v)}
          label={`I authorize ${label} to place trades in my selected brokerage account.`}
        />
        {failure ? (
          <Text style={[type.body, { color: color.neg, marginTop: space.md }]}>{failure}</Text>
        ) : null}
        <Pressable
          onPress={() => void proceedToReview()}
          disabled={!riskAck || !authAck || busy}
          style={[s.primaryBtn, { opacity: riskAck && authAck && !busy ? 1 : 0.5 }]}
        >
          <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>
            {busy ? 'Loading review…' : 'Continue to review'}
          </Text>
        </Pressable>
      </Card>
    )
  }

  if (step === 'review' && preview) {
    const s1 = preview.snapshot
    return (
      <Card style={{ marginTop: space.lg }}>
        <SectionLabel>Review</SectionLabel>
        <ReviewRow label="Account" value={s1.account_mask ? `•••• ${s1.account_mask}` : 'Not available'} />
        {s1.plan ? (
          <ReviewRow label="Plan" value={`${s1.plan.name} — $${s1.plan.price_monthly}/mo`} />
        ) : null}
        {s1.buying_power_cents != null ? (
          <ReviewRow label="Buying power" value={`$${(s1.buying_power_cents / 100).toLocaleString()}`} />
        ) : null}
        {s1.max_deployment_cents != null ? (
          <ReviewRow
            label="Max deployment"
            value={`$${(s1.max_deployment_cents / 100).toLocaleString()}`}
          />
        ) : null}

        {preview.blockers.length > 0 ? (
          <>
            <Text style={[type.label, { color: color.warn, marginTop: space.lg }]}>
              A few things need to be finished before {label} can be activated:
            </Text>
            {preview.blockers.map((b, i) => (
              <Text key={b.code + i} style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
                • {b.message}
              </Text>
            ))}
            <Pressable
              onPress={openWebHandoff}
              style={[s.primaryBtn, { backgroundColor: color.accent, marginTop: space.lg }]}
            >
              <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>
                Finish setup on the web
              </Text>
            </Pressable>
          </>
        ) : (
          <>
            {failure ? (
              <Text style={[type.body, { color: color.neg, marginTop: space.md }]}>{failure}</Text>
            ) : null}
            <Pressable
              onPress={() => void confirmActivate()}
              disabled={busy}
              style={[s.primaryBtn, { marginTop: space.lg, opacity: busy ? 0.5 : 1 }]}
            >
              <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>
                {busy ? 'Activating…' : `Activate ${label}`}
              </Text>
            </Pressable>
          </>
        )}
      </Card>
    )
  }

  if (step === 'done' && activated) {
    return (
      <Card style={{ marginTop: space.lg }}>
        <View style={s.rowCenter}>
          <Ionicons name="checkmark-circle" size={22} color={color.pos} />
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, marginLeft: space.sm }]}>
            {label} activated
          </Text>
        </View>
        <Text style={[type.body, { color: color.textDim, marginTop: space.md }]}>
          {activated.account_mask
            ? `Trading on •••• ${activated.account_mask}. `
            : ''}
          Your trial is now active.
        </Text>
        <Pressable
          onPress={() => router.replace('/agents')}
          style={[s.primaryBtn, { marginTop: space.lg }]}
        >
          <Text style={[type.body, { color: color.bg, fontFamily: font.bodyBold }]}>Done</Text>
        </Pressable>
      </Card>
    )
  }

  return null
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={[s.rowBetween, { marginTop: space.sm }]}>
      <Text style={[type.body, { color: color.textDim }]}>{label}</Text>
      <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>{value}</Text>
    </View>
  )
}

function CheckRow({
  checked,
  onToggle,
  label,
}: {
  checked: boolean
  onToggle: () => void
  label: string
}) {
  return (
    <Pressable onPress={onToggle} style={s.checkRow} accessibilityRole="checkbox" accessibilityState={{ checked }}>
      <Ionicons
        name={checked ? 'checkbox' : 'square-outline'}
        size={20}
        color={checked ? color.accent : color.muted}
      />
      <Text style={[type.body, { color: color.text, flex: 1, marginLeft: space.sm }]}>{label}</Text>
    </Pressable>
  )
}

/** Non-cryptographic v4-shaped id — good enough for a per-attempt dedupe key. */
function generateIdempotencyKey(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

const s = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomColor: color.border,
    borderBottomWidth: 1,
  },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowCenter: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.md },
  actionBtn: {
    marginTop: space.lg,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  primaryBtn: {
    marginTop: space.lg,
    backgroundColor: color.accent,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  selectRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    padding: space.md,
    marginTop: space.sm,
  },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', marginTop: space.md },
})
