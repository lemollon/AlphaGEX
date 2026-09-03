import { useEffect, useState } from 'react'
import {
  View,
  Text,
  Image,
  ScrollView,
  TextInput,
  Pressable,
  RefreshControl,
  Alert,
  Modal,
  StyleSheet,
  ActivityIndicator,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import useSWR from 'swr'
import { api, ApiError } from '@/api/client'
import type {
  AssistResponse,
  BlockedMember,
  CommunityFeedV2,
  CommunityMessageV2,
  ThreadReplies,
} from '@/api/types'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Card, Loading, Empty, ErrorState } from '@/components/ui'
import { AppHeader, Mascot, SPARKY_AVATAR } from '@/components/Brand'
import { applyFlame, FLAME } from '@/community/reactions'
import { initials, channelAccent, bubbleTint } from '@/community/identity'
import {
  appendOptimisticReply,
  applyFlameToReply,
  bumpReplyCount,
  reconcileReply,
  removeReply,
} from '@/community/threads'

/** A post reused inside the thread sheet. */
type CommunityMessage = CommunityMessageV2
/** The feed shape, threaded (APP-055). */
type CommunityFeed = CommunityFeedV2

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
 *
 * Every post by another member carries a ⋯ menu with Report and Block. Google Play's
 * User Generated Content policy requires both to exist IN THE APP; server-side
 * moderation is a pre-filter, not a substitute. Reporting is open to anyone signed in
 * (reading the feed does not need a membership, so neither does flagging it).
 */
export default function CommunityScreen() {
  const [channel, setChannel] = useState('all-chat')
  const [draft, setDraft] = useState('')
  const [posting, setPosting] = useState(false)
  const [postError, setPostError] = useState<string | null>(null)
  // Two sheets, never both: the ⋯ menu, then the reason picker it opens.
  const [menuFor, setMenuFor] = useState<CommunityMessage | null>(null)
  const [reportFor, setReportFor] = useState<CommunityMessage | null>(null)
  const [blockedOpen, setBlockedOpen] = useState(false)
  // The open thread (APP-055) — a sheet inside this tab rather than a nested route,
  // per WP-F scope: expo-router nesting under app/(tabs)/community/ would touch the
  // tab layout, and a modal here does not.
  const [threadFor, setThreadFor] = useState<CommunityMessage | null>(null)
  // The "+" composer sheet (APP-031). No upload endpoint exists under
  // /api/community/* — see the sheet's own copy — so this never grows options
  // beyond the "coming soon" line until a real one ships.
  const [attachOpen, setAttachOpen] = useState(false)
  // AI assist (APP-031): the suggestion is held separately from the draft so the
  // member can compare "Use" vs "Keep mine" instead of the draft silently changing.
  const [assisting, setAssisting] = useState(false)
  const [assistSuggestion, setAssistSuggestion] = useState<string | null>(null)

  const { data, error, isLoading, mutate, isValidating } = useSWR<CommunityFeed>(
    `/api/community/messages?channel=${channel}`,
    (p: string) => api(p),
    { refreshInterval: 30_000 },
  )

  /**
   * The viewer's own block list. Not polled — it only changes when this screen
   * changes it, so it is fetched on mount and re-fetched after a block/unblock.
   */
  const { data: blocks, mutate: mutateBlocks } = useSWR<{ blocked: BlockedMember[] }>(
    '/api/community/blocks',
    (p: string) => api(p),
    { refreshInterval: 0, revalidateOnFocus: false },
  )
  const blockedCount = blocks?.blocked?.length ?? 0

  async function submitReport(message: CommunityMessage, reason: string) {
    setReportFor(null)
    try {
      await api('/api/community/reports', {
        method: 'POST',
        body: { message_id: message.id, reason },
      })
      Alert.alert(
        'Report sent',
        'Thanks — the IronForge team will review this post. You can also block this member so you stop seeing their posts.',
      )
    } catch (e) {
      Alert.alert('Could not report', (e as Error).message)
    }
  }

  /**
   * Block, then drop the author's posts from view immediately. The feed is
   * re-fetched rather than filtered locally because the server owns the rule —
   * a local filter would disagree with the next poll.
   */
  async function blockAuthor(message: CommunityMessage) {
    setMenuFor(null)
    try {
      const res = await api<{ blocked_name?: string }>('/api/community/blocks', {
        method: 'POST',
        body: { message_id: message.id },
      })
      await Promise.all([mutate(), mutateBlocks()])
      Alert.alert(
        'Member blocked',
        `You will no longer see posts from ${res?.blocked_name ?? message.sender_name}. They are not told, and you can unblock them any time from Blocked members.`,
      )
    } catch (e) {
      Alert.alert('Could not block', (e as Error).message)
    }
  }

  async function unblock(member: BlockedMember) {
    try {
      await api('/api/community/blocks', {
        method: 'DELETE',
        body: { user_id: member.user_id },
      })
      await Promise.all([mutate(), mutateBlocks()])
    } catch (e) {
      Alert.alert('Could not unblock', (e as Error).message)
    }
  }

  async function send() {
    const message = draft.trim()
    if (!message || posting) return
    setPosting(true)
    setPostError(null)
    try {
      await api('/api/community/messages', { method: 'POST', body: { channel, message } })
      setDraft('')
      setAssistSuggestion(null)
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
   * AI assist (APP-031). Sends the current draft to be tightened/clarified — never
   * to add a trade idea or a number that isn't already there (server-enforced, see
   * webapp's /api/community/assist). The result sits beside the draft until the
   * member chooses "Use" or "Keep mine"; it never overwrites what they typed.
   */
  async function askAssist() {
    const text = draft.trim()
    if (!text || assisting) return
    setAssisting(true)
    setAssistSuggestion(null)
    try {
      const res = await api<AssistResponse>('/api/community/assist', {
        method: 'POST',
        body: { draft: text, channel },
      })
      setAssistSuggestion(res.suggestion)
    } catch (e) {
      Alert.alert(
        'AI assist unavailable',
        e instanceof ApiError && e.status === 402
          ? 'An active membership is required for AI assist.'
          : (e as Error).message,
      )
    } finally {
      setAssisting(false)
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

        {/*
          Always visible, not only when the list is non-empty: a block the viewer
          cannot find is a block they cannot undo.
        */}
        <Pressable
          onPress={() => {
            void mutateBlocks()
            setBlockedOpen(true)
          }}
          style={s.blockedLink}
          accessibilityRole="button"
        >
          <Text style={[type.label, { color: color.textDim }]}>
            Blocked members{blockedCount > 0 ? ` · ${blockedCount}` : ''}
          </Text>
        </Pressable>

        {/*
          APP-054: horizontally scrollable so a 5th (or 6th, later) category never
          wraps onto a second line and pushes the feed down. Switching channels
          swaps the SWR key, which both refetches AND resets paging — there is no
          separate page cursor to forget to clear.
        */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={s.chipScroll}
          contentContainerStyle={s.chipRow}
        >
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
        </ScrollView>

        {messages.length === 0 ? (
          <Empty title="Nothing here yet" detail="Be the first to post in this channel." />
        ) : (
          messages.map((m) => (
            <Card key={m.id} style={{ marginBottom: space.md }}>
              {/* UX-005: avatar rail on the left, everything else indented beside it. */}
              <View style={s.postRow}>
                <Avatar message={m} />
                <View style={{ flex: 1 }}>
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
                      <Text style={[type.label, { color: color.muted }]}>{time(m.created_at)}</Text>
                    </View>
                    <View style={s.rowCenter}>
                      <CategoryChip message={m} />
                      {/* Your own posts, and Forge's, have nothing to report or block. */}
                      {m.mine !== true && m.sender_type === 'USER' ? (
                        <Pressable
                          onPress={() => setMenuFor(m)}
                          hitSlop={10}
                          accessibilityRole="button"
                          accessibilityLabel={`Options for the post by ${m.sender_name}`}
                          style={s.moreBtn}
                        >
                          <Text style={{ color: color.muted, fontSize: 18, lineHeight: 18 }}>⋯</Text>
                        </Pressable>
                      ) : null}
                    </View>
                  </View>
                  <Text style={[type.body, { color: color.textDim, marginTop: space.sm }]}>
                    {m.message}
                  </Text>
                  <View style={s.rowCenter}>
                    <FlameRow message={m} onPress={() => void toggleFlame(m.id)} />
                    <Pressable
                      onPress={() => setThreadFor(m)}
                      hitSlop={8}
                      accessibilityRole="button"
                      accessibilityLabel={
                        (m.reply_count ?? 0) > 0 ? `${m.reply_count} replies` : 'Reply'
                      }
                      style={s.replyBtn}
                    >
                      <Text style={[type.label, { color: color.textDim, fontFamily: font.bodyMedium }]}>
                        {(m.reply_count ?? 0) > 0 ? `💬 ${m.reply_count}` : 'Reply'}
                      </Text>
                    </Pressable>
                  </View>
                </View>
              </View>
            </Card>
          ))
        )}
      </ScrollView>

      <View style={s.composer}>
        {postError ? (
          <Text style={[type.label, { color: color.neg, marginBottom: space.sm }]}>{postError}</Text>
        ) : null}
        {assistSuggestion ? (
          <View style={s.assistBox}>
            <Text style={[type.label, { color: color.spark, fontFamily: font.bodyBold, marginBottom: space.xs }]}>
              AI assist
            </Text>
            <Text style={[type.body, { color: color.text }]}>{assistSuggestion}</Text>
            <View style={[s.rowCenter, { marginTop: space.sm }]}>
              <Pressable
                onPress={() => {
                  setDraft(assistSuggestion)
                  setAssistSuggestion(null)
                }}
                style={s.assistUseBtn}
              >
                <Text style={[type.label, { color: color.bg, fontFamily: font.bodyBold }]}>Use</Text>
              </Pressable>
              <Pressable onPress={() => setAssistSuggestion(null)} hitSlop={8}>
                <Text style={[type.label, { color: color.textDim }]}>Keep mine</Text>
              </Pressable>
            </View>
          </View>
        ) : null}
        <View style={s.rowCenter}>
          <Pressable
            onPress={() => setAttachOpen(true)}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Add to your post"
            style={s.plusBtn}
          >
            <Text style={{ color: color.textDim, fontSize: 20, lineHeight: 20 }}>+</Text>
          </Pressable>
          <TextInput
            value={draft}
            onChangeText={(t) => {
              setDraft(t)
              setAssistSuggestion(null)
            }}
            placeholder="Share with the community..."
            placeholderTextColor={color.muted}
            style={s.input}
            multiline
          />
          <Pressable
            onPress={askAssist}
            disabled={assisting || !draft.trim()}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="AI assist — tighten my message"
            style={[s.plusBtn, { opacity: assisting || !draft.trim() ? 0.4 : 1 }]}
          >
            {assisting ? (
              <ActivityIndicator size="small" color={color.spark} />
            ) : (
              <Text style={{ fontSize: 16 }}>✨</Text>
            )}
          </Pressable>
          <Pressable onPress={send} disabled={posting || !draft.trim()} style={s.send}>
            <Text style={{ color: color.text, fontSize: 16 }}>{posting ? '…' : '➤'}</Text>
          </Pressable>
        </View>
        <Text style={[type.label, { color: color.muted, marginTop: space.sm }]}>
          AI monitored · Community standards active
        </Text>
      </View>

      <Sheet
        visible={menuFor != null}
        title={menuFor ? `Post by ${menuFor.sender_name}` : ''}
        options={[
          { label: 'Report this post', value: 'report' },
          {
            label: `Block ${menuFor?.sender_name ?? 'this member'}`,
            value: 'block',
            destructive: true,
          },
        ]}
        onSelect={(v) => {
          const target = menuFor
          if (!target) return
          if (v === 'report') {
            setMenuFor(null)
            setReportFor(target)
          } else {
            void blockAuthor(target)
          }
        }}
        onClose={() => setMenuFor(null)}
      />

      <Sheet
        visible={reportFor != null}
        title="Why are you reporting this?"
        options={REPORT_REASONS}
        onSelect={(v) => {
          if (reportFor) void submitReport(reportFor, v)
        }}
        onClose={() => setReportFor(null)}
      />

      <BlockedSheet
        visible={blockedOpen}
        members={blocks?.blocked ?? []}
        onUnblock={(m) => void unblock(m)}
        onClose={() => setBlockedOpen(false)}
      />

      <AttachSheet visible={attachOpen} onClose={() => setAttachOpen(false)} />

      <ThreadSheet
        parent={threadFor}
        channel={channel}
        onClose={() => setThreadFor(null)}
        onReplyPosted={() => void mutate((cur) => bumpReplyCount(cur, threadFor!.id, 1), { revalidate: false })}
      />
    </Shell>
  )
}

/**
 * Report reasons. These mirror the server's REPORT_REASONS allowlist — a value it
 * does not recognise is a 400, so the two lists have to move together.
 */
const REPORT_REASONS = [
  { label: 'Spam or scam', value: 'SPAM' },
  { label: 'Harassment or bullying', value: 'HARASSMENT' },
  { label: 'Hate speech or violence', value: 'HATE', destructive: true },
  { label: 'Investment advice or solicitation', value: 'ADVICE' },
  { label: 'Something else', value: 'OTHER' },
]

/**
 * A bottom sheet of choices.
 *
 * Deliberately not Alert.alert: Android renders at most THREE buttons, and the reason
 * picker has five. An Alert would silently drop the rest on exactly the platform this
 * control exists for.
 */
function Sheet({
  visible,
  title,
  options,
  onSelect,
  onClose,
}: {
  visible: boolean
  title: string
  options: Array<{ label: string; value: string; destructive?: boolean }>
  onSelect: (value: string) => void
  onClose: () => void
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel="Dismiss" />
      <View style={s.sheet}>
        <Text style={[type.label, { color: color.muted, marginBottom: space.md }]}>{title}</Text>
        {options.map((o) => (
          <Pressable key={o.value} onPress={() => onSelect(o.value)} style={s.sheetRow}>
            <Text style={[type.body, { color: o.destructive ? color.neg : color.text }]}>
              {o.label}
            </Text>
          </Pressable>
        ))}
        <Pressable onPress={onClose} style={s.sheetRow}>
          <Text style={[type.body, { color: color.textDim }]}>Cancel</Text>
        </Pressable>
      </View>
    </Modal>
  )
}

/** The block list, with an Unblock beside each member. */
function BlockedSheet({
  visible,
  members,
  onUnblock,
  onClose,
}: {
  visible: boolean
  members: BlockedMember[]
  onUnblock: (m: BlockedMember) => void
  onClose: () => void
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel="Dismiss" />
      <View style={s.sheet}>
        <Text style={[type.label, { color: color.muted, marginBottom: space.md }]}>
          Blocked members
        </Text>
        {members.length === 0 ? (
          <Text style={[type.body, { color: color.textDim, paddingVertical: space.md }]}>
            You have not blocked anyone. Blocking hides that member's posts from your feed
            only — they are never told.
          </Text>
        ) : (
          members.map((m) => (
            <View key={m.user_id} style={[s.sheetRow, s.rowBetween]}>
              <Text style={[type.body, { color: color.text }]}>{m.display_name}</Text>
              <Pressable onPress={() => onUnblock(m)} hitSlop={8} accessibilityRole="button">
                <Text style={[type.label, { color: color.accent }]}>Unblock</Text>
              </Pressable>
            </View>
          ))
        )}
        <Pressable onPress={onClose} style={s.sheetRow}>
          <Text style={[type.body, { color: color.textDim }]}>Close</Text>
        </Pressable>
      </View>
    </Modal>
  )
}

/**
 * The "+" composer sheet (APP-031). There is no upload/attachment endpoint under
 * /api/community/* — grepped the webapp's api/community routes (messages,
 * reactions, reports, blocks only) — so this shows exactly one honest line
 * instead of options that would fail the moment someone tapped them.
 */
function AttachSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel="Dismiss" />
      <View style={s.sheet}>
        <Text style={[type.label, { color: color.muted, marginBottom: space.md }]}>Add to your post</Text>
        <Text style={[type.body, { color: color.textDim, paddingVertical: space.md }]}>
          Attachments are coming soon.
        </Text>
        <Pressable onPress={onClose} style={s.sheetRow}>
          <Text style={[type.body, { color: color.textDim }]}>Close</Text>
        </Pressable>
      </View>
    </Modal>
  )
}

/**
 * A thread (APP-055) — one post's replies, opened as a modal sheet inside this
 * tab rather than an expo-router nested screen (see the note above
 * CommunityScreen's `threadFor` state: a sheet here doesn't touch the tab layout).
 *
 * Optimistic reply + reconciliation mirrors toggleFlame() on the main screen:
 * append locally, POST, then either replace the temp row with the server's copy
 * or drop it and roll the parent's reply_count back on failure. The pure logic
 * lives in src/community/threads.ts so it can be unit-tested without a renderer.
 */
function ThreadSheet({
  parent,
  channel,
  onClose,
  onReplyPosted,
}: {
  parent: CommunityMessage | null
  channel: string
  onClose: () => void
  onReplyPosted: () => void
}) {
  const [draft, setDraft] = useState('')
  const [posting, setPosting] = useState(false)
  const [postError, setPostError] = useState<string | null>(null)

  const { data, mutate, isLoading, error } = useSWR<ThreadReplies>(
    parent ? `/api/community/messages/${parent.id}/replies` : null,
    (p: string) => api<ThreadReplies>(p),
    {},
  )

  // A fresh thread each time a different post is opened — otherwise a half-typed
  // reply to one post would reappear under the next one opened.
  useEffect(() => {
    setDraft('')
    setPostError(null)
  }, [parent?.id])

  const replies = data?.replies ?? []
  const hasAi = parent?.sender_type !== 'USER' || replies.some((r) => r.sender_type !== 'USER')

  async function send() {
    if (!parent) return
    const message = draft.trim()
    if (!message || posting) return
    setPosting(true)
    setPostError(null)
    const tempId = `temp-${Date.now()}`
    const optimistic: CommunityMessage = {
      id: tempId,
      sender_name: 'You',
      sender_type: 'USER',
      message,
      created_at: new Date().toISOString(),
      reactions: [],
      mine: true,
      blockable: false,
      channel_slug: parent.channel_slug,
      channel_name: parent.channel_name,
      reply_count: 0,
      parent_id: parent.id,
    }
    await mutate((cur) => appendOptimisticReply(cur, optimistic), { revalidate: false })
    try {
      const res = await api<{ messageId: string | null }>('/api/community/messages', {
        method: 'POST',
        body: { channel, message, parent_id: parent.id },
      })
      setDraft('')
      onReplyPosted()
      await mutate(
        (cur) => reconcileReply(cur, tempId, { ...optimistic, id: res.messageId ?? tempId }),
        { revalidate: false },
      )
    } catch (e) {
      await mutate((cur) => removeReply(cur, tempId), { revalidate: false })
      const msg = (e as Error).message
      setPostError(msg.includes('MEMBERSHIP') ? 'An active membership is required to reply.' : msg)
    } finally {
      setPosting(false)
    }
  }

  async function toggleReplyFlame(id: string) {
    await mutate((cur) => applyFlameToReply(cur, id), { revalidate: false })
    try {
      await api('/api/community/reactions', { method: 'POST', body: { message_id: id, emoji: FLAME } })
    } catch (e) {
      Alert.alert('Could not react', (e as Error).message)
    } finally {
      mutate()
    }
  }

  return (
    <Modal visible={parent != null} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: color.bg }}>
        <View style={s.threadHeader}>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
            Thread
          </Text>
          <Pressable onPress={onClose} hitSlop={8} accessibilityRole="button" accessibilityLabel="Close thread">
            <Text style={{ color: color.textDim, fontSize: 18 }}>✕</Text>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={{ padding: space.lg, flexGrow: 1 }}>
          {parent ? (
            <Card style={{ marginBottom: space.lg }}>
              <View style={s.postRow}>
                <Avatar message={parent} />
                <View style={{ flex: 1 }}>
                  <View style={s.rowCenter}>
                    <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>
                      {parent.sender_name}
                    </Text>
                    {parent.sender_type !== 'USER' ? (
                      <View style={s.aiTag}>
                        <Text style={[type.label, { color: color.spark }]}>AI</Text>
                      </View>
                    ) : null}
                    <Text style={[type.label, { color: color.muted }]}>{time(parent.created_at)}</Text>
                  </View>
                  <Text style={[type.body, { color: color.textDim, marginTop: space.sm }]}>
                    {parent.message}
                  </Text>
                </View>
              </View>
            </Card>
          ) : null}

          {isLoading ? (
            <Loading label="Loading replies…" />
          ) : error ? (
            <ErrorState message={String((error as Error).message)} onRetry={() => mutate()} />
          ) : replies.length === 0 ? (
            <Empty title="No replies yet" detail="Be the first to reply." />
          ) : (
            replies.map((r) => (
              <View key={r.id} style={s.replyRow}>
                <Avatar message={r} />
                <View style={{ flex: 1 }}>
                  <View style={s.rowCenter}>
                    <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 13 }]}>
                      {r.sender_name}
                    </Text>
                    {r.sender_type !== 'USER' ? (
                      <View style={s.aiTag}>
                        <Text style={[type.label, { color: color.spark }]}>AI</Text>
                      </View>
                    ) : null}
                    <Text style={[type.label, { color: color.muted }]}>{time(r.created_at)}</Text>
                  </View>
                  <Text style={[type.body, { color: color.textDim, marginTop: space.xs, fontSize: 14 }]}>
                    {r.message}
                  </Text>
                  <FlameRow message={r} onPress={() => void toggleReplyFlame(r.id)} />
                </View>
              </View>
            ))
          )}

          {hasAi ? (
            <Text style={[type.label, { color: color.muted, marginTop: space.md }]}>
              AI updates are general market context, not personalized advice.
            </Text>
          ) : null}
        </ScrollView>

        <View style={s.composer}>
          {postError ? (
            <Text style={[type.label, { color: color.neg, marginBottom: space.sm }]}>{postError}</Text>
          ) : null}
          <View style={s.rowCenter}>
            <TextInput
              value={draft}
              onChangeText={setDraft}
              placeholder="Reply…"
              placeholderTextColor={color.muted}
              style={s.input}
              multiline
            />
            <Pressable onPress={() => void send()} disabled={posting || !draft.trim()} style={s.send}>
              <Text style={{ color: color.text, fontSize: 16 }}>{posting ? '…' : '➤'}</Text>
            </Pressable>
          </View>
        </View>
      </SafeAreaView>
    </Modal>
  )
}

/**
 * The flame count for one post. It renders at zero too — hiding the control until
 * somebody else reacted first means nobody can ever be the first to react.
 */
/**
 * UX-005 avatar. Forge and Sparky wear their mascots; members get initials on a tint
 * derived from the NAME, so the same person keeps the same colour as the feed reorders.
 */
function Avatar({ message }: { message: CommunityMessage }) {
  if (message.sender_type !== 'USER') {
    // Sparky answers in threads, Forge posts market updates — different faces.
    const isSparky = message.sender_name.toLowerCase().includes('sparky')
    return isSparky ? (
      <Image source={SPARKY_AVATAR} style={s.avatarImg} resizeMode="contain" />
    ) : (
      <Mascot bot="flame" size={40} />
    )
  }
  return (
    <View style={[s.avatarBubble, { backgroundColor: bubbleTint(message.sender_name) }]}>
      <Text style={[type.label, { color: color.text, fontFamily: font.bodyBold }]}>
        {initials(message.sender_name)}
      </Text>
    </View>
  )
}

/**
 * The category chip. Renders only when the server actually told us which channel the
 * post came from — an older API predates that field, and a chip reading "undefined" is
 * worse than no chip.
 */
function CategoryChip({ message }: { message: CommunityMessage }) {
  if (!message.channel_name) return null
  const accent = channelAccent(message.channel_slug)
  return (
    <View style={[s.categoryChip, { borderColor: accent }]}>
      <Text style={[type.label, { color: accent }]}>{message.channel_name}</Text>
    </View>
  )
}

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
  postRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  avatarImg: { width: 40, height: 40, borderRadius: 20 },
  avatarBubble: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  categoryChip: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.sm,
    paddingVertical: 2,
  },
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
  moreBtn: { paddingHorizontal: space.xs },
  blockedLink: { alignSelf: 'flex-start', marginTop: space.md },
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#000', opacity: 0.6 },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: color.card,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    borderTopWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    paddingBottom: space.xl,
  },
  sheetRow: { paddingVertical: space.md },
  reactRow: { flexDirection: 'row', alignItems: 'center', marginTop: space.md },
  reactBtn: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  replyBtn: { marginTop: space.md, marginLeft: space.md, paddingVertical: space.xs },
  chipScroll: { marginVertical: space.lg },
  chipRow: { flexDirection: 'row', gap: space.sm, paddingRight: space.lg },
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
  plusBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: space.sm,
  },
  assistBox: {
    borderWidth: 1,
    borderColor: color.spark,
    borderRadius: radius.md,
    padding: space.md,
    marginBottom: space.md,
    backgroundColor: color.bg,
  },
  assistUseBtn: {
    backgroundColor: color.spark,
    borderRadius: radius.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    marginRight: space.md,
  },
  threadHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomColor: color.border,
    borderBottomWidth: 1,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  replyRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.sm, marginBottom: space.lg },
})