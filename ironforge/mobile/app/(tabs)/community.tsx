import { useEffect, useMemo, useState } from 'react'
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
import Svg, { Path } from 'react-native-svg'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { api, ApiError } from '@/api/client'
import { getItem, setItem } from '@/api/storage'
import type {
  AssistResponse,
  BlockedMember,
  CommunityFeedV2,
  CommunityMessageV2,
  ThreadReplies,
} from '@/api/types'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Card, Loading, Empty, ErrorState } from '@/components/ui'
import { AppHeader, Mascot, SPARKY_AVATAR } from '@/components/Brand'
import { applyHeart, FLAME, HEART } from '@/community/reactions'
import { initials, channelAccent, bubbleTint } from '@/community/identity'
import {
  appendOptimisticReply,
  applyHeartToReply,
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
/** The welcome card's dismissal (10.4 design `st.cWelcomeGone`) — permanent, not
 *  per-session: once a member taps the X it never comes back on this device. */
const WELCOME_DISMISSED_KEY = 'ironforge.community.welcomeDismissed'

export default function CommunityScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const [channel, setChannel] = useState('all-chat')
  const [draft, setDraft] = useState('')
  const [posting, setPosting] = useState(false)
  const [postError, setPostError] = useState<string | null>(null)
  // Two sheets, never both: the report/block menu, then the reason picker it opens.
  const [menuFor, setMenuFor] = useState<CommunityMessage | null>(null)
  const [reportFor, setReportFor] = useState<CommunityMessage | null>(null)
  const [blockedOpen, setBlockedOpen] = useState(false)
  // The open thread (APP-055) — a sheet inside this tab rather than a nested route,
  // per WP-F scope: expo-router nesting under app/(tabs)/community/ would touch the
  // tab layout, and a modal here does not.
  const [threadFor, setThreadFor] = useState<CommunityMessage | null>(null)
  // AI assist (APP-031): the suggestion is held separately from the draft so the
  // member can compare "Use" vs "Keep mine" instead of the draft silently changing.
  const [assisting, setAssisting] = useState(false)
  const [assistSuggestion, setAssistSuggestion] = useState<string | null>(null)
  // 10.4 design: a dismiss "X", not a navigation — starts hidden (not shown) until
  // the stored flag resolves, so a returning member never sees a one-frame flash of
  // a card they already dismissed.
  const [welcomeDismissed, setWelcomeDismissed] = useState<boolean | null>(null)
  useEffect(() => {
    getItem(WELCOME_DISMISSED_KEY).then((v) => setWelcomeDismissed(v === '1'))
  }, [])
  function dismissWelcome() {
    setWelcomeDismissed(true)
    void setItem(WELCOME_DISMISSED_KEY, '1')
  }

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
   * Toggle the heart (APP-055, 10.4 redesign — every design screenshot's reaction
   * icon is a heart). Optimistic, then reconciled against the server. The server's
   * ALLOWED_EMOJI now includes ❤️ specifically for this; a post's pre-existing 🔥
   * rows (from before this change) still render via ReactionRow below, just as a
   * read-only legacy count — this is the only reaction any UI here still SENDS.
   */
  async function toggleHeart(id: string) {
    await mutate((cur) => applyHeart(cur, id), { revalidate: false })
    try {
      await api('/api/community/reactions', {
        method: 'POST',
        body: { message_id: id, emoji: HEART },
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

        {/* 10.4 design `.welcome`: a static card with a dismiss "X" that hides it for
            good (`st.cWelcomeGone`) — not a link to anywhere. Blocked-members access
            (Google Play UGC policy) and Community Guidelines both moved to design-
            consistent rows on the Account tab's Help card instead of living here. */}
        {welcomeDismissed === false ? (
          <View style={s.welcome}>
            <Mascot bot="flame" size={54} />
            <View style={{ flex: 1 }}>
              <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
                Welcome to Forge Community
              </Text>
              <Text style={[type.body, { color: color.textDim, marginTop: space.xs }]}>
                Learn, share ideas, and grow together. Respect every member and protect the forge.
              </Text>
            </View>
            <Pressable
              onPress={dismissWelcome}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityLabel="Dismiss"
              style={s.welcomeDismiss}
            >
              <Ionicons name="close" size={14} color={color.textDim} />
            </Pressable>
          </View>
        ) : null}

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
          messages.map((m) => {
            // Your own posts, and Forge's, have nothing to report or block.
            const reportable = m.mine !== true && m.sender_type === 'USER'
            return (
            <Pressable
              key={m.id}
              onLongPress={reportable ? () => setMenuFor(m) : undefined}
              disabled={!reportable}
              accessibilityRole={reportable ? 'button' : undefined}
              accessibilityLabel={reportable ? `Long-press for options on the post by ${m.sender_name}` : undefined}
            >
            <Card style={{ marginBottom: space.md }}>
              {/* UX-005: avatar rail on the left, everything else indented beside it.
                  10.4 design has no visible report affordance on a post — moderation
                  stays reachable via a long-press (mobile handoff "long-press a post
                  to report"), not a persistent "⋯" icon. */}
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
                    </View>
                  </View>
                  <Text style={[type.body, { color: color.textDim, marginTop: space.sm }]}>
                    {m.message}
                  </Text>
                  <View style={s.rowCenter}>
                    <ReactionRow message={m} onPress={() => void toggleHeart(m.id)} />
                    <Pressable
                      onPress={() => setThreadFor(m)}
                      hitSlop={8}
                      accessibilityRole="button"
                      accessibilityLabel={
                        (m.reply_count ?? 0) > 0 ? `${m.reply_count} replies` : 'Reply'
                      }
                      style={[s.replyBtn, s.reactBtn]}
                    >
                      <Ionicons name="chatbubble-outline" size={16} color={color.textDim} />
                      <Text style={[type.label, { color: color.textDim, fontFamily: font.bodyMedium }]}>
                        {(m.reply_count ?? 0) > 0 ? m.reply_count : 'Reply'}
                      </Text>
                    </Pressable>
                  </View>
                </View>
              </View>
            </Card>
            </Pressable>
            )
          })
        )}

        {/* Community Guidelines and Blocked members (Google Play UGC policy) are
            real, required entry points with no equivalent in the 10.4 design — kept
            as one quiet footer row rather than styled as a feature of the feed. */}
        <View style={s.metaFooter}>
          <Pressable onPress={showGuidelines} hitSlop={8} accessibilityRole="button">
            <Text style={[type.label, { color: color.muted }]}>Community Guidelines</Text>
          </Pressable>
          <Text style={[type.label, { color: color.muted }]}> · </Text>
          <Pressable
            onPress={() => {
              void mutateBlocks()
              setBlockedOpen(true)
            }}
            hitSlop={8}
            accessibilityRole="button"
          >
            <Text style={[type.label, { color: color.muted }]}>
              Blocked members{blockedCount > 0 ? ` · ${blockedCount}` : ''}
            </Text>
          </Pressable>
        </View>
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
          {/* 10.4 design composer is one row: input + send (its topic `<select>` is
              already covered above by the channel chips, which also target the post).
              The "+" attach control is dropped entirely — there has never been an
              upload endpoint under /api/community/*, so it opened a "coming soon"
              sheet with no function to preserve. */}
          <TextInput
            value={draft}
            onChangeText={(t) => {
              setDraft(t)
              setAssistSuggestion(null)
            }}
            placeholder="Share with the community..."
            placeholderTextColor={color.muted}
            style={s.input}
            maxLength={500}
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
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
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
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
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
                <Text style={[type.label, { color: color.accentText }]}>Unblock</Text>
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
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
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

  async function toggleReplyHeart(id: string) {
    await mutate((cur) => applyHeartToReply(cur, id), { revalidate: false })
    try {
      await api('/api/community/reactions', { method: 'POST', body: { message_id: id, emoji: HEART } })
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
                  <ReactionRow message={r} onPress={() => void toggleReplyHeart(r.id)} />
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
  const { colors: color, scheme } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  if (message.sender_type !== 'USER') {
    // Sparky answers in threads, Forge posts market updates — different faces. Forge
    // posts previously fell back to Flame's mascot, which wrongly implied Flame
    // specifically authored a generic platform update (fidelity audit "AI-generated
    // post avatar" — design shows a neutral black square + forge glyph, `cav('forge')`,
    // never an agent's own face).
    const isSparky = message.sender_name.toLowerCase().includes('sparky')
    return isSparky ? (
      <Image source={SPARKY_AVATAR} style={s.avatarImg} resizeMode="contain" />
    ) : (
      <ForgeAvatar />
    )
  }
  return (
    <View style={[s.avatarBubble, { backgroundColor: bubbleTint(message.sender_name, scheme) }]}>
      <Text style={[type.label, { color: color.text, fontFamily: font.bodyBold }]}>
        {initials(message.sender_name)}
      </Text>
    </View>
  )
}

/**
 * The generic "Forge" (platform/AI) post avatar — a near-black square with the forge
 * shield glyph in the brand accent (design `.cav.forge`, `--av` background), always
 * this fixed look regardless of light/dark theme, same as the design's own `--av` token.
 */
function ForgeAvatar() {
  const { colors: color } = useTheme()
  return (
    <View style={{ width: 40, height: 40, borderRadius: 11, backgroundColor: '#0B0B0F', alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={22} height={22} viewBox="0 0 24 24">
        <Path
          d="M12 3l7.5 3v5.5c0 4.6-3.1 8.3-7.5 9.5-4.4-1.2-7.5-4.9-7.5-9.5V6L12 3z"
          stroke={color.accent}
          strokeWidth={1.8}
          strokeLinejoin="round"
          fill="none"
        />
        <Path
          d="M8 14l2.5-2.5 2 2L16 10"
          stroke={color.accent}
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </Svg>
    </View>
  )
}

/**
 * The category chip. Renders only when the server actually told us which channel the
 * post came from — an older API predates that field, and a chip reading "undefined" is
 * worse than no chip.
 */
function CategoryChip({ message }: { message: CommunityMessage }) {
  const { colors: color, resolveTone } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  if (!message.channel_name) return null
  // channelAccent() returns a DARK-canonical hex (tested in identity.test.ts) — resolve
  // it to the active scheme here, at the render site.
  const accent = resolveTone(channelAccent(message.channel_slug))
  return (
    <View style={[s.categoryChip, { borderColor: accent }]}>
      <Text style={[type.label, { color: accent }]}>{message.channel_name}</Text>
    </View>
  )
}

/**
 * The reaction row (10.4 design: a heart icon + count). Also renders any legacy 🔥
 * count this message already carries from before the redesign — read-only, never a
 * second tappable control — so a reaction placed under the old UI keeps displaying
 * rather than silently vanishing once nobody can add to it anymore.
 */
function ReactionRow({ message, onPress }: { message: CommunityMessage; onPress: () => void }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const heart = (message.reactions ?? []).find((r) => r.emoji === HEART)
  const count = heart?.count ?? 0
  const mine = heart?.mine ?? false
  const legacyFlame = (message.reactions ?? []).find((r) => r.emoji === FLAME)
  return (
    <View style={s.reactRow}>
      <Pressable
        onPress={onPress}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={mine ? 'Remove your heart' : 'Add a heart'}
        style={s.reactBtn}
      >
        <Text style={{ fontSize: 15, opacity: mine ? 1 : 0.45 }}>{HEART}</Text>
        <Text
          style={[
            type.label,
            { color: mine ? color.accentText : color.muted, fontFamily: font.bodyMedium },
          ]}
        >
          {count}
        </Text>
      </Pressable>
      {legacyFlame && legacyFlame.count > 0 ? (
        <View style={[s.reactBtn, { opacity: 0.6 }]} accessibilityLabel={`${legacyFlame.count} legacy flame reactions`}>
          <Text style={{ fontSize: 13 }}>{FLAME}</Text>
          <Text style={[type.label, { color: color.muted }]}>{legacyFlame.count}</Text>
        </View>
      ) : null}
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
  welcomeDismiss: {
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metaFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.lg,
  },
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
  reactRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, marginTop: space.md },
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