import { useState } from 'react'
import { View, Text, ScrollView, TextInput, Pressable, RefreshControl, Alert, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import useSWR from 'swr'
import { api } from '@/api/client'
import type { CommunityFeed, CommunityMessage } from '@/api/types'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Card, Loading, Empty, ErrorState } from '@/components/ui'
import { AppHeader, Mascot } from '@/components/Brand'

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

  /**
   * Toggle the flame (APP-055). Optimistic, then reconciled against the server.
   *
   * 🔥 not ❤️ on purpose: APP-055 says "one flame reaction per post", and the server's
   * ALLOWED_EMOJI is 👍🔥💯😂🎯🙌 — it has no heart to send. The mockup's red heart is
   * the outlier, and the client cannot invent an emoji the endpoint rejects.
   */
  async function toggleFlame(id: string) {
    await mutate((cur) => applyFlame(cur, id), { revalidate: false })
    try {
      await api('/api/community/reactions', {
        method: 'POST',
        body: { message_id: id, emoji: FLAME },
      })
    } catch (e) {
      Alert.alert('Could not react', (e as Error).message)
    } finally {
      // The server is the truth either way — a failed toggle rolls back on revalidate.
      mutate()
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

        <Pressable onPress={showGuidelines} style={s.welcome} accessibilityRole="button">
          <Mascot bot="flame" size={54} />
          <View style={{ flex: 1 }}>
            <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
              Welcome to Forge Community
            </Text>
            <Text style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
              Learn, share ideas, and grow together. Respect every member and protect the forge.
            </Text>
            <Text style={[type.label, { color: color.accent, marginTop: space.sm }]}>
              Community Guidelines
            </Text>
          </View>
        </Pressable>

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
              <FlameRow message={m} onPress={() => void toggleFlame(m.id)} />
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

const FLAME = '🔥'

/**
 * The flame count for one post. It renders at zero too — hiding the control until
 * somebody else reacted first means nobody can ever be the first to react.
 */
function FlameRow({ message, onPress }: { message: CommunityMessage; onPress: () => void }) {
  const flame = (message.reactions ?? []).find((r) => r.emoji === FLAME)
  const count = flame?.count ?? 0
  const mine = flame?.mine ?? false
  return (
    <View style={s.reactRow}>
      <Pressable
        onPress={onPress}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={mine ? 'Remove your flame' : 'Add a flame'}
        style={s.reactBtn}
      >
        <Text style={{ fontSize: 15, opacity: mine ? 1 : 0.45 }}>{FLAME}</Text>
        <Text
          style={[
            type.label,
            { color: mine ? color.accent : color.muted, fontFamily: font.bodyMedium },
          ]}
        >
          {count}
        </Text>
      </Pressable>
    </View>
  )
}

/** Optimistic local toggle, mirroring what the server's toggleReaction() does. */
function applyFlame(cur: CommunityFeed | undefined, id: string): CommunityFeed | undefined {
  if (!cur) return cur
  return {
    ...cur,
    messages: cur.messages.map((m) => {
      if (m.id !== id) return m
      const rest = (m.reactions ?? []).filter((r) => r.emoji !== FLAME)
      const flame = (m.reactions ?? []).find((r) => r.emoji === FLAME)
      const mine = !(flame?.mine ?? false)
      const count = Math.max(0, (flame?.count ?? 0) + (mine ? 1 : -1))
      return {
        ...m,
        reactions: count > 0 || mine ? [...rest, { emoji: FLAME, count, mine }] : rest,
      }
    }),
  }
}

function showGuidelines() {
  Alert.alert(
    'Community Guidelines',
    [
      'Respect every member. Disagree with the idea, never the person.',
      'No investment advice, tips or solicitation. Share what you did and why, not what somebody else should do.',
      'Never post account numbers, balances, or screenshots containing personal details — yours or anyone else’s.',
      'AI-authored posts and replies are always labelled AI.',
      'Posts are checked against these standards before they publish.',
    ].join('\n\n'),
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
  title: { ...type.title, color: color.text, fontFamily: font.display },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowCenter: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  welcome: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.md,
    marginTop: space.lg,
    borderWidth: 1,
    borderColor: color.accent,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  reactRow: { flexDirection: 'row', alignItems: 'center', marginTop: space.md },
  reactBtn: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
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
