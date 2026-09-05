import { useEffect, useState } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { ApiError } from '@/api/client'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Loading } from '@/components/ui'
import { Mascot } from '@/components/Brand'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { getBrokerConnections, createAgentConfig } from '@/enroll/api'
import { AGENT_LABEL, AGENT_BLURB } from '@/agents/copy'
import type { AgentBot } from '@/agents/routes'

const BOTS: AgentBot[] = ['spark', 'flame']

/**
 * Pick your agent (UAT #6, screen 7 of 9) — POST /api/v1/agent-configs.
 *
 * JUDGMENT CALL: "Both" at the plan screen still only configures ONE agent here —
 * v1's agent-configs/activations endpoints activate a single agent_code per pass.
 * A "both" enrollee starts with whichever they pick below; the second bot is added
 * afterward through the existing /live bundle-upgrade path, not through this funnel.
 * The note under the tiles says so.
 */
export default function AgentsScreen() {
  const { enrollment, busy, setBusy, error, setError, router } = useEnrollment('agents')
  const params = useLocalSearchParams<{ accountId?: string }>()
  const [accountId, setAccountId] = useState<string | null>(params.accountId ?? null)
  const [resolving, setResolving] = useState(!params.accountId)

  // Fallback: re-derive the eligible account if this screen was reached without the
  // route param (deep link resume, or back-then-forward navigation) — same fallback
  // AgentClient.tsx uses on the web.
  useEffect(() => {
    if (accountId || !enrollment) return
    getBrokerConnections()
      .then((d) => {
        const eligible = (d.connections ?? []).flatMap((c) => c.accounts).filter((a) => a.eligibility === 'eligible')
        if (eligible.length === 1) setAccountId(eligible[0].id)
        else router.replace('/enroll/broker')
      })
      .catch((e) => setError(e instanceof ApiError ? e.humanMessage : (e as Error).message))
      .finally(() => setResolving(false))
  }, [accountId, enrollment, router, setError])

  async function select(bot: AgentBot) {
    if (!accountId || busy) return
    setBusy(true)
    setError(null)
    try {
      const d = await createAgentConfig(bot, accountId)
      if (d.status !== 'valid') {
        const detail = d.violations.length ? ` ${d.violations.join(' ')}` : ''
        setError(`Your setup needs attention before review.${detail}`)
        setBusy(false)
        return
      }
      router.push({ pathname: '/enroll/review', params: { configId: d.id } })
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
      setBusy(false)
    }
  }

  return (
    <EnrollShell title="Pick your agent" step={7} error={error}>
      <Text style={[type.body, { color: color.textDim, marginBottom: space.lg }]}>
        Both agents use the same rules-based strategy at different times of day. Selecting one creates a draft
        setup — it does not start trading yet.
      </Text>

      {resolving || !enrollment ? (
        <Loading label="Loading your account…" />
      ) : (
        <View style={{ gap: space.md }}>
          {BOTS.map((bot) => (
            <Pressable
              key={bot}
              onPress={() => select(bot)}
              disabled={busy}
              style={[s.tile, { borderColor: bot === 'spark' ? color.spark : color.flame, opacity: busy ? 0.6 : 1 }]}
            >
              <Mascot bot={bot} size={40} />
              <View style={{ flex: 1 }}>
                <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
                  {AGENT_LABEL[bot]}
                </Text>
                <Text style={[type.label, { color: color.textDim, marginTop: 2 }]}>{AGENT_BLURB[bot]}</Text>
              </View>
            </Pressable>
          ))}
        </View>
      )}

      {enrollment?.selected_plan === 'both' ? (
        <Text style={[type.label, { color: color.muted, marginTop: space.lg }]}>
          You chose the two-agent bundle — start with one here, then add the second from the Agents tab any time.
        </Text>
      ) : null}
    </EnrollShell>
  )
}

const s = StyleSheet.create({
  tile: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderWidth: 1.5,
    borderRadius: radius.lg,
    padding: space.lg,
    backgroundColor: color.card,
  },
})
