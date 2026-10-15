import { useCallback, useMemo, useRef, useState } from 'react'
import {
  View,
  Text,
  ScrollView,
  TextInput,
  Pressable,
  Image,
  KeyboardAvoidingView,
  Platform,
  Linking,
  StyleSheet,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { sendSparkyMessage, SparkyUnavailableError, type SparkyTurn } from '@/api/sparky'
import { SPARKY_AVATAR } from '@/components/Brand'
import { SUPPORT_EMAIL, supportMailto } from '@/support/contact'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { trackEvent } from '@/analytics/trackEvent'

/** 10.4 design `sugg` chips — exact copy, shown only on the empty state. */
const SUGGESTIONS = [
  'How am I doing this week?',
  'What happens if I pause?',
  'When do my agents trade?',
  'How do I cancel?',
] as const

/**
 * Ask Sparky — APP-032.
 *
 * The AI label is not decoration and is never conditional: APP-057 requires every
 * AI-authored message to be visibly labelled, and this whole screen is AI-authored.
 * The disclosure sits above the first message where it cannot be scrolled past unseen.
 *
 * History is server-side (#264, POST /api/sparky/chat {message, conversationId}), not
 * screen-local — but this screen still starts a new conversationId every time it mounts
 * (the ref resets with the component), so reopening still begins a visually fresh chat
 * even though the server could resume the prior one if asked to.
 *
 * REBUILT 2026-10-15: this used to be a `transparentModal` Sheet stacked on top of the
 * still-mounted tab underneath it (the 10.4 "sheet redesign"). That architecture caused
 * a customer-reproduced bug where the screen mounted and unmounted several times within
 * a few seconds of opening it, each a fresh conversation, so nothing ever visibly
 * persisted — confirmed via diagnostic logging across three repro sessions and NOT fixed
 * by four rounds of narrower patches (a double-send guard, a nav debounce, a focus gate
 * on one row, then on every tab's whole surface). Rather than add a fifth patch on top of
 * a custom modal implementation that nothing else in the app uses this way, Sparky is now
 * a plain pushed screen — exactly how it worked before the sheet redesign, and exactly
 * how every other non-sheet screen in this app behaves: React Navigation's native stack
 * mounts one screen at a time and gates touches to the background screen itself, so the
 * whole class of "background screen still interactive/still mounted" bug no longer has
 * anywhere to live. `/notifications`, `/agents/[bot]`, `/trade/[id]` and
 * `/notification-preferences` still use the Sheet — this change is scoped to Sparky only.
 */
export default function SparkyScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()
  const [turns, setTurns] = useState<SparkyTurn[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scroller = useRef<ScrollView>(null)
  // #264: the server keeps the conversation's history (sparky_conversations/
  // sparky_messages) — the client only ever sends ONE new message plus the id it got
  // back last time, never the whole transcript. A ref, not state: it must not trigger a
  // re-render, and `send` reads the latest value synchronously.
  const conversationIdRef = useRef<string | null>(null)
  // A ref, not the `sending` state: two touches landing before React re-renders between
  // them would otherwise both close over the same stale `sending === false`, and the
  // guard below would never see the first touch's in-flight request. Confirmed live via
  // a customer screen recording that produced two /api/sparky/chat calls 130ms apart from
  // one chip tap — a ref updates synchronously, before any re-render, so it closes that
  // gap. (Unrelated to the mount/unmount rebuild above — this guard stays either way.)
  const sendingRef = useRef(false)

  const send = useCallback(
    async (overrideText?: string) => {
      const text = (overrideText ?? draft).trim()
      if (!text || sendingRef.current) return
      sendingRef.current = true

      trackEvent('sparky_question', { mode: overrideText ? 'suggested' : 'typed' })
      // Captured by reference so the two updates below can find THIS call's own
      // placeholder by identity, not by array position.
      const placeholder: SparkyTurn = { role: 'assistant', content: '' }
      setTurns((prev) => [...prev, { role: 'user', content: text }, placeholder])
      setDraft('')
      setError(null)
      setSending(true)

      try {
        const res = await sendSparkyMessage(text, conversationIdRef.current)
        conversationIdRef.current = res.conversationId
        // Fill the trailing (placeholder) assistant turn with the full reply — one JSON
        // response, not streamed deltas. Matched by identity (the exact placeholder
        // object this call pushed), not array position.
        setTurns((prev) => {
          const idx = prev.findIndex((t) => t === placeholder)
          if (idx === -1) return prev
          const copy = [...prev]
          copy[idx] = { ...copy[idx], content: res.reply }
          return copy
        })
      } catch (e) {
        const msg =
          e instanceof SparkyUnavailableError ? e.message : (e as Error).message || 'Something went wrong.'
        setError(msg)
        // Drop this call's own empty assistant placeholder, by identity, rather than
        // assuming it's still the last entry in the array.
        setTurns((prev) => prev.filter((t) => t !== placeholder))
      } finally {
        sendingRef.current = false
        setSending(false)
      }
    },
    [draft],
  )

  return (
    <SafeAreaView edges={['top', 'bottom']} style={{ flex: 1, backgroundColor: color.bg }}>
      <View style={s.header}>
        <Pressable
          onPress={() => router.back()}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel="Back"
          style={s.backBtn}
        >
          <Ionicons name="chevron-back" size={26} color={color.text} />
        </Pressable>
        <Image source={SPARKY_AVATAR} style={s.avatar} resizeMode="contain" />
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18, flex: 1 }]} numberOfLines={1}>
          Ask Sparky
        </Text>
        <View style={s.aiTag}>
          <Text style={[type.label, { color: color.sparkText, fontFamily: font.bodyMedium }]}>AI</Text>
        </View>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          ref={scroller}
          contentContainerStyle={{ padding: space.lg, paddingBottom: space.xl }}
          onContentSizeChange={() => scroller.current?.scrollToEnd({ animated: true })}
        >
          <View style={s.disclosure}>
            <Ionicons name="information-circle-outline" size={16} color={color.textDim} />
            <Text style={[type.label, { color: color.textDim, flex: 1 }]}>
              Sparky is an AI assistant. It can help with your account, your agent and how
              IronForge works — it does not give trading advice and cannot place or change trades.
            </Text>
          </View>

          {turns.length === 0 ? (
            <View style={s.empty}>
              <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium }]}>
                What can I help with?
              </Text>
              <Text style={[type.body, { color: color.textDim, marginTop: space.sm, textAlign: 'center' }]}>
                Ask about your membership, your brokerage connection, or what your agent is doing
                right now.
              </Text>
              {/* Zero-effort canned prompts (10.4 design `.sugg`) — exact copy from
                  the prototype's suggestion chips. */}
              <View style={s.sugg}>
                {SUGGESTIONS.map((q) => (
                  <Pressable
                    key={q}
                    onPress={() => void send(q)}
                    disabled={sending}
                    accessibilityRole="button"
                    style={s.suggChip}
                  >
                    <Text style={[type.label, { color: color.text, fontFamily: font.bodyMedium }]}>{q}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : (
            turns.map((t, i) => <Bubble key={i} turn={t} pending={sending && i === turns.length - 1} />)
          )}

          {error ? (
            <View style={s.errorBox}>
              <Text style={[type.body, { color: color.neg }]}>{error}</Text>
              <Pressable onPress={() => void Linking.openURL(supportMailto('Sparky could not help'))}>
                <Text style={[type.label, { color: color.accentText, marginTop: space.sm }]}>
                  Email {SUPPORT_EMAIL} instead
                </Text>
              </Pressable>
            </View>
          ) : null}
        </ScrollView>

        <View style={s.composer}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Ask Sparky…"
            placeholderTextColor={color.muted}
            style={s.input}
            multiline
            editable={!sending}
          />
          <Pressable
            onPress={() => void send()}
            disabled={sending || !draft.trim()}
            accessibilityRole="button"
            accessibilityLabel="Send"
            style={[s.send, (sending || !draft.trim()) && { opacity: 0.5 }]}
          >
            <Ionicons name="send" size={18} color={color.text} />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

function Bubble({ turn, pending }: { turn: SparkyTurn; pending: boolean }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const mine = turn.role === 'user'
  return (
    <View style={[s.bubble, mine ? s.mine : s.theirs]}>
      {!mine ? (
        <View style={s.bubbleHead}>
          <Image source={SPARKY_AVATAR} style={s.bubbleAvatar} resizeMode="contain" />
          <Text style={[type.label, { color: color.sparkText, fontFamily: font.bodyMedium }]}>Sparky AI</Text>
        </View>
      ) : null}
      <Text style={[type.body, { color: mine ? color.text : color.textDim }]}>
        {turn.content}
        {pending && !turn.content ? 'Thinking…' : ''}
      </Text>
    </View>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomColor: color.border,
    borderBottomWidth: 1,
  },
  backBtn: { padding: space.xs },
  avatar: { width: 30, height: 30 },
  aiTag: {
    borderWidth: 1,
    borderColor: color.spark,
    borderRadius: radius.sm,
    paddingHorizontal: space.sm,
  },
  disclosure: {
    flexDirection: 'row',
    gap: space.sm,
    alignItems: 'flex-start',
    backgroundColor: color.card,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md,
    marginBottom: space.lg,
  },
  empty: { alignItems: 'center', paddingVertical: space.xxl, paddingHorizontal: space.lg },
  sugg: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.sm,
    justifyContent: 'center',
    marginTop: space.lg,
  },
  suggChip: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    backgroundColor: color.card,
  },
  bubble: {
    borderRadius: radius.lg,
    padding: space.md,
    marginBottom: space.md,
    maxWidth: '92%',
  },
  mine: { alignSelf: 'flex-end', backgroundColor: color.card, borderColor: color.border, borderWidth: 1 },
  theirs: { alignSelf: 'flex-start', backgroundColor: color.card, borderColor: color.spark, borderWidth: 1 },
  bubbleHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginBottom: space.sm },
  bubbleAvatar: { width: 20, height: 20 },
  errorBox: {
    borderColor: color.neg,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md,
    marginTop: space.sm,
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: space.sm,
    padding: space.lg,
    borderTopColor: color.border,
    borderTopWidth: 1,
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
    maxHeight: 110,
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
