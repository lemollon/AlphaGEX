import { View, Text, ScrollView, Pressable, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { api } from '@/api/client'
import type { LiveAgents, EntitlementsResponse, AutomationPauseResponse, BrokerageConnections } from '@/api/types'
import { color, space, radius, type, font, agentAccent } from '@/theme/tokens'
import { Card, Loading, ErrorState } from '@/components/ui'
import { Mascot } from '@/components/Brand'
import { agentAction, type AgentActionKind } from '@/agents/eligibility'
import { agentDetailHref, type AgentBot } from '@/agents/routes'
import { AGENT_LABEL, AGENT_BLURB } from '@/agents/copy'

const BOTS: AgentBot[] = ['spark', 'flame']

const DOT_COLOR: Record<string, string> = {
  green: color.pos,
  blue: color.spark,
  amber: color.warn,
  red: color.neg,
  gray: color.muted,
}

const ACTION_COPY: Record<AgentActionKind, string> = {
  active: 'View',
  paused: 'View',
  add: 'Add',
  setup_required: 'Setup Required',
  switch: 'Switch',
}

/**
 * Agents overview (APP-023) — Spark and Flame side by side, ONE action per card.
 *
 * The action shown is computed the same way the detail screen decides what to render
 * (src/agents/eligibility.ts), so tapping "Add" here and landing on the activation flow
 * on /agents/{bot} can never disagree about whether that flow should even be offered.
 */
export default function AgentsScreen() {
  const router = useRouter()
  const agents = useSWR<LiveAgents>('/api/live/agents', (p: string) => api<LiveAgents>(p))
  const entitlements = useSWR<EntitlementsResponse>('/api/billing/entitlements', (p: string) =>
    api<EntitlementsResponse>(p),
  )
  const pause = useSWR<AutomationPauseResponse>('/api/v1/automation/pause', (p: string) =>
    api<AutomationPauseResponse>(p),
  )
  const conns = useSWR<BrokerageConnections>('/api/brokerage/connections', (p: string) =>
    api<BrokerageConnections>(p),
  )

  const loading = agents.isLoading || entitlements.isLoading || pause.isLoading || conns.isLoading
  const failed = agents.error || pause.error

  const eligibleAccountCount = (conns.data?.connections ?? [])
    .flatMap((c) => c.accounts)
    .filter((a) => a.eligibility === 'eligible').length

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }} edges={['top']}>
      <View style={s.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={26} color={color.text} />
        </Pressable>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
          Agents
        </Text>
      </View>

      {loading ? (
        <Loading label="Loading your agents…" />
      ) : failed ? (
        <ErrorState
          message="Could not load your agents right now."
          onRetry={() => {
            agents.mutate()
            pause.mutate()
          }}
        />
      ) : (
        <ScrollView contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}>
          {BOTS.map((bot) => {
            const liveAgent = agents.data?.agents.find((a) => a.bot === bot) ?? null
            const action = agentAction({
              bot,
              entitlements: entitlements.data?.bots ?? [],
              activations: (pause.data?.activations ?? []).map((a) => ({
                agent: a.agent,
                paused: a.paused,
              })),
              eligibleAccountCount,
            })
            const accent = agentAccent(bot)
            const dotColor = liveAgent?.state
              ? DOT_COLOR[liveAgent.state.dot] ?? color.muted
              : action.kind === 'add'
                ? color.muted
                : action.kind === 'setup_required' || action.kind === 'switch'
                  ? color.warn
                  : color.muted

            return (
              <Pressable
                key={bot}
                onPress={() => router.push(agentDetailHref(bot))}
                accessibilityRole="button"
                accessibilityLabel={`${AGENT_LABEL[bot]}, ${action.label}`}
              >
                <Card style={{ borderColor: accent, marginBottom: space.lg }}>
                  <View style={s.rowBetween}>
                    <View style={s.rowCenter}>
                      <Mascot bot={bot} size={42} />
                      <View>
                        <Text
                          style={[
                            type.body,
                            { color: color.text, fontFamily: font.bodyBold, fontSize: 18 },
                          ]}
                        >
                          {AGENT_LABEL[bot]}
                        </Text>
                        <View style={s.rowCenter}>
                          <View style={[s.dot, { backgroundColor: dotColor }]} />
                          <Text style={[type.label, { color: color.textDim }]}>
                            {liveAgent?.state?.headline ?? action.label}
                          </Text>
                        </View>
                      </View>
                    </View>
                    <View style={[s.actionPill, { borderColor: accent }]}>
                      <Text style={[type.label, { color: accent, fontFamily: font.bodyMedium }]}>
                        {ACTION_COPY[action.kind]}
                      </Text>
                    </View>
                  </View>

                  <Text style={[type.body, { color: color.textDim, marginTop: space.md }]}>
                    {AGENT_BLURB[bot]}
                  </Text>
                </Card>
              </Pressable>
            )
          })}
        </ScrollView>
      )}
    </SafeAreaView>
  )
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
  dot: { width: 7, height: 7, borderRadius: 4 },
  actionPill: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
})
