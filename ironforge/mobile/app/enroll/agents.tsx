import { useEffect, useMemo, useState } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { ApiError } from '@/api/client'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Loading } from '@/components/ui'
import { Mascot } from '@/components/Brand'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { getBrokerConnections, createAgentConfig } from '@/enroll/api'
import { AGENT_LABEL, AGENT_BLURB } from '@/agents/copy'

/**
 * This deferred-choice screen is reached only from the retired "both" family value
 * and the "automate" family value (pick Spark or Flame after setup) — Ember is
 * never deferred, it's chosen directly at /enroll/plan and skips straight past
 * billing, so it never reaches here. Kept as its own narrower type (not the
 * app-wide AgentBot, which now also has 'ember') because createAgentConfig's
 * /api/v1/agent-configs only ever accepts 'spark' | 'flame'.
 */
type DeferredBot = 'spark' | 'flame'

const BOTS: DeferredBot[] = ['spark', 'flame']

/**
 * Pick your agent (step 7 of 8) — POST /api/v1/agent-configs.
 *
 * JUDGMENT CALL: a legacy "both" enrollee still only configures ONE agent here —
 * v1's agent-configs/activations endpoints activate a single agent_code per pass.
 * Such an enrollee starts with whichever they pick below; the second bot is added
 * afterward through the existing /live bundle-upgrade path, not through this funnel.
 * The note under the tiles says so. "Both" is no longer offered at /enroll/plan for
 * new enrollments (Leron, 2026-10-04) — this path only serves pre-existing ones.
 */
export default function AgentsScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
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

  async function select(bot: DeferredBot) {
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

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
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
