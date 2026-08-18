import { useState } from 'react'
import { View, Text, ScrollView, TextInput, Pressable, RefreshControl, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import useSWR from 'swr'
import { api } from '@/api/client'
import type { CommunityFeed } from '@/api/types'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Card, Loading, Empty, ErrorState } from '@/components/ui'
import { AppHeader } from '@/components/brand'

/**
 * Community — UX-005 (APP-030/031/054/055).
 *
 * Polls every 30s, NOT the web's 4s. On a phone a 4-second poll is a battery and
 * cellular-data problem, and the feed is conversational rather than real-time critical.
 * SWR pauses when the screen loses focus, so a backgrounded app costs nothing.
 *
 * AI authorship is always visible (APP-057): sender_type FORGE/SYSTEM renders a label.
 * Posting requires a membership — the server answers 402 MEMBERSHIP_REQUIRED, which is
 * surfaced as its own message rather than a generic failure.
 */
export default function CommunityScreen() {
  const [channel, setChannel] = useState('all-chat')
  const [draft, setDraft] = useState('')
  const [posting, setPosting] = useState(false)
  const [postError, setPostError] = useState<string | null>(null)

  const { data, error, isLoading, mutate, isValidating } = useSWR<CommunityFeed>(
    `/api/community/messages?channel=${channel}`,
    (p: string) => api(p),
    { refreshInterval: 30_000 },
  )

  async function send() {
    const message = draft.trim()
    if (!message || posting) return
    setPosting(true)
    setPostError(null)
    try {
      await api('/api/community/messages', { method: 'POST', body: { channel, message } })
      setDraft('')
      mutate()
    } catch (e) {
      const msg = (e as Error).message
      setPostError(
        msg.includes('MEMBERSHIP')
          ? 'An active membership is required to post.'
          : msg,
      )
    } finally {
      setPosting(false)
    }
  }

  if (isLoading) return <Shell><Loading label="Loading the community…" /></Shell>
  if (error) {
    return (
      <Shell>
        <ErrorState message={String((error as Error).message)} onRetry={() => mutate()} />
      </Shell>
    )
  }

  const channels = data?.channels ?? []
  const messages = data?.messages ?? []

  return (
    <Shell>
      <ScrollView
        contentContainerStyle={{ padding: space.lg }}
        refreshControl={
          <RefreshControl refreshing={isValidating} onRefresh={() => mutate()} tintColor={color.accent} />
        }
      >
        <View style={s.rowBetween}>
          <Text style={s.title}>Community</Text>
          <Text style={[type.label, { color: color.pos }]}>{data?.online_count ?? 0} online</Text>
        </View>

        <View style={s.chipRow}>
          {channels.map((c) => (
            <Pressable
              key={c.slug}
              onPress={() => setChannel(c.slug)}
              style={[s.chip, channel === c.slug && { backgroundColor: color.accent, borderColor: color.accent }]}
            >
              <Text style={[type.label, { color: channel === c.slug ? color.text : color.textDim }]}>
                {c.name}
              </Text>
            </Pressable>
          ))}
        </View>

        {messages.length === 0 ? (
          <Empty title="Nothing here yet" detail="Be the first to post in this channel." />
        ) : (
          messages.map((m) => (
            <Card key={m.id} style={{ marginBottom: space.md }}>
              <View style={s.rowBetween}>
                <View style={s.rowCenter}>
                  <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>
                    {m.sender_name}
                  </Text>
                  {m.sender_type !== 'USER' ? (
                    <View style={s.aiTag}>
                      <Text style={[type.label, { color: color.spark }]}>AI</Text>
                    </View>
                  ) : null}
                </View>
                <Text style={[type.label, { color: color.muted }]}>{time(m.created_at)}</Text>
              </View>
              <Text style={[type.body, { color: color.textDim, marginTop: space.sm }]}>{m.message}</Text>
            </Card>
          ))
        )}
      </ScrollView>

      <View style={s.composer}>
        {postError ? (
          <Text style={[type.label, { color: color.neg, marginBottom: space.sm }]}>{postError}</Text>
        ) : null}
        <View style={s.rowCenter}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Share with the community..."
            placeholderTextColor={color.muted}
            style={s.input}
            multiline
          />
          <Pressable onPress={send} disabled={posting || !draft.trim()} style={s.send}>
            <Text style={{ color: color.text, fontSize: 16 }}>{posting ? '…' : '➤'}</Text>
          </Pressable>
        </View>
        <Text style={[type.label, { color: color.muted, marginTop: space.sm }]}>
          AI monitored · Community standards active
        </Text>
      </View>
    </Shell>
  )
}

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
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
  // Large bold sans page title per UX-005 — the display face is for the wordmark
  // and numerics, not headings.
  title: { color: color.text, fontFamily: font.bodyBold, fontSize: 34, letterSpacing: -0.5 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowCenter: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginVertical: space.lg },
  chip: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  aiTag: {
    borderWidth: 1,
    borderColor: color.spark,
    borderRadius: radius.sm,
    paddingHorizontal: space.sm,
  },
  composer: {
    borderTopColor: color.border,
    borderTopWidth: 1,
    padding: space.lg,
    backgroundColor: color.card,
  },
  input: {
    flex: 1,
    backgroundColor: color.bg,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    color: color.text,
    maxHeight: 100,
  },
  send: {
    backgroundColor: color.accent,
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
})
