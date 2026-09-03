import { useEffect } from 'react'
import { View, Text, ScrollView, Pressable, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useLocalSearchParams, useRouter } from 'expo-router'
import useSWR from 'swr'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { api, ApiError } from '@/api/client'
import type { TradeDetailResponse } from '@/api/types'
import { color, space, radius, type, font, agentAccent } from '@/theme/tokens'
import { Card, SectionLabel, Money, OutcomeBadge, AgentBadge, Loading, ErrorState } from '@/components/ui'
import { track } from '@/analytics/track'

/**
 * Trade detail — APP-019/022.
 *
 * Every field below can legitimately be null: the server only ever fills a field
 * from a column that actually exists for this trade, never fabricates one, so
 * "Not available" is a normal, expected state here, not an error.
 */
export default function TradeDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>()
  const router = useRouter()

  const { data, error, isLoading, mutate } = useSWR<TradeDetailResponse>(
    id ? `/api/live/trades/${id}` : null,
    (p: string) => api<TradeDetailResponse>(p),
  )

  useEffect(() => {
    if (data?.trade) track('trade_detail_opened', { outcome_kind: data.trade.outcome_kind })
  }, [data?.trade])

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <View style={s.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={26} color={color.text} />
        </Pressable>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>Trade Detail</Text>
      </View>

      {isLoading ? (
        <Loading label="Loading trade…" />
      ) : error || !data ? (
        <ErrorState
          message={error instanceof ApiError ? error.humanMessage : 'Could not load this trade.'}
          onRetry={() => mutate()}
        />
      ) : (
        <Content data={data} />
      )}
    </SafeAreaView>
  )
}

function Content({ data }: { data: TradeDetailResponse }) {
  const { trade, detail } = data

  return (
    <ScrollView contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}>
      <View style={s.rowBetween}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
          <AgentBadge name={trade.strategy} accent={agentAccent(trade.bot)} />
          <OutcomeBadge kind={trade.outcome_kind} label={trade.outcome} />
        </View>
      </View>
      <Text style={[type.title, { color: color.text, fontFamily: font.display, marginTop: space.md }]}>
        {formatDate(trade.close_date)}
      </Text>

      <Card style={{ marginTop: space.lg }}>
        <SectionLabel>Result</SectionLabel>
        <View style={s.rowBetween}>
          <Money value={trade.pnl} size="hero" />
          <Text style={[type.body, { color: color.textDim }]}>
            {trade.pnl_pct != null ? `${trade.pnl_pct >= 0 ? '+' : ''}${trade.pnl_pct}%` : '—'}
          </Text>
        </View>
        <View style={[s.rowBetween, { marginTop: space.lg }]}>
          <Field label="Contracts" value={String(trade.contracts)} />
          <Field label="Credit" value={trade.credit != null ? `$${trade.credit.toFixed(2)}` : '—'} />
          <Field
            label="Buying power used"
            value={detail.buying_power_used != null ? `$${detail.buying_power_used.toFixed(2)}` : '—'}
          />
        </View>
      </Card>

      <Card style={{ marginTop: space.lg }}>
        <SectionLabel>Position</SectionLabel>
        {detail.legs ? (
          <View style={{ gap: space.sm }}>
            {detail.legs.map((leg, i) => (
              <View key={i} style={s.legRow}>
                <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
                  {leg.side === 'buy' ? 'Buy' : 'Sell'} {leg.right === 'put' ? 'Put' : 'Call'}
                </Text>
                <Text style={[type.body, { color: color.textDim }]}>${leg.strike}</Text>
                <Text style={[type.label, { color: color.muted }]}>x{leg.qty}</Text>
              </View>
            ))}
            {detail.entry_at_ct ? (
              <Text style={[type.label, { color: color.muted, marginTop: space.xs }]}>
                Opened {detail.entry_at_ct}
              </Text>
            ) : null}
          </View>
        ) : (
          <NotAvailable />
        )}
      </Card>

      <Card style={{ marginTop: space.lg }}>
        <SectionLabel>Timeline</SectionLabel>
        {detail.lifecycle ? (
          <View style={{ gap: space.md }}>
            {detail.lifecycle.map((entry, i) => (
              <View key={i} style={s.timelineRow}>
                <View style={s.timelineDot} />
                <View style={{ flex: 1 }}>
                  <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>{entry.event}</Text>
                  <Text style={[type.label, { color: color.muted, marginTop: 2 }]}>{entry.at_ct}</Text>
                  {entry.note ? (
                    <Text style={[type.label, { color: color.textDim, marginTop: 2 }]}>{entry.note}</Text>
                  ) : null}
                </View>
              </View>
            ))}
          </View>
        ) : (
          <NotAvailable />
        )}
      </Card>

      <Card style={{ marginTop: space.lg }}>
        <SectionLabel>Why It Closed</SectionLabel>
        {detail.exit_reason_text ? (
          <View>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
              {detail.exit_reason_text}
            </Text>
            {trade.closed_ct ? (
              <Text style={[type.label, { color: color.muted, marginTop: space.xs }]}>
                {trade.closed_ct} CT
              </Text>
            ) : null}
          </View>
        ) : (
          <NotAvailable />
        )}
      </Card>

      <Card style={{ marginTop: space.lg }}>
        <SectionLabel>Latest Monitoring Message</SectionLabel>
        {detail.monitoring_message ? (
          <Text style={[type.body, { color: color.text }]}>{detail.monitoring_message}</Text>
        ) : (
          <NotAvailable />
        )}
      </Card>
    </ScrollView>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View>
      <Text style={[type.label, { color: color.muted, marginBottom: space.xs }]}>{label}</Text>
      <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>{value}</Text>
    </View>
  )
}

function NotAvailable() {
  return <Text style={[type.body, { color: color.muted }]}>Not available</Text>
}

/** close_date is a plain CT date string from the server — parse as local, not UTC. */
function formatDate(d: string): string {
  const [y, m, day] = d.split('-').map(Number)
  if (!y || !m || !day) return d
  return new Date(y, m - 1, day).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.bg },
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
  legRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: color.border,
  },
  timelineRow: { flexDirection: 'row', gap: space.md },
  timelineDot: {
    width: 8,
    height: 8,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
    marginTop: 6,
  },
})
