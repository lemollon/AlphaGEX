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
import { Stack, useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { streamSparky, SparkyUnavailableError, type SparkyTurn } from '@/api/sparky'
import { SPARKY_AVATAR } from '@/components/Brand'
import { Sheet, SheetHeader } from '@/components/Sheet'
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
 * History is screen-local. `/api/support/chat` is stateless and persists no transcript,
 * so there is nothing to load and nothing left behind on sign-out — which is also the
 * simplest possible answer to "conversation history scoped to the signed-in member".
 */
export default function SparkyScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()
  const [turns, setTurns] = useState<SparkyTurn[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scroller = useRef<ScrollView>(null)

  const send = useCallback(
    async (overrideText?: string) => {
      const text = (overrideText ?? draft).trim()
      if (!text || streaming) return

      trackEvent('sparky_question', { mode: overrideText ? 'suggested' : 'typed' })
      const next: SparkyTurn[] = [...turns, { role: 'user', content: text }]
      setTurns([...next, { role: 'assistant', content: '' }])
      setDraft('')
      setError(null)
      setStreaming(true)

      try {
        await streamSparky(next, (delta) => {
          // Append to the trailing assistant turn as chunks land.
          setTurns((prev) => {
            const copy = [...prev]
            const last = copy[copy.length - 1]
            if (last?.role === 'assistant') copy[copy.length - 1] = { ...last, content: last.content + delta }
            return copy
          })
        })
      } catch (e) {
        const msg =
          e instanceof SparkyUnavailableError ? e.message : (e as Error).message || 'Something went wrong.'
        setError(msg)
        // Drop the empty assistant bubble rather than leaving a blank message behind.
        setTurns((prev) => {
          const last = prev[prev.length - 1]
          return last?.role === 'assistant' && !last.content ? prev.slice(0, -1) : prev
        })
      } finally {
        setStreaming(false)
      }
    },
    [draft, streaming, turns],
  )

  return (
    <>
      <Stack.Screen
        options={{ presentation: 'transparentModal', animation: 'fade', contentStyle: { backgroundColor: 'transparent' } }}
      />
      <Sheet accent={color.spark} onClose={() => router.back()}>
        {(close) => (
          <>
            <SheetHeader
              title="Ask Sparky"
              left={<Image source={SPARKY_AVATAR} style={s.avatar} resizeMode="contain" />}
              right={
                <View style={s.aiTag}>
                  <Text style={[type.label, { color: color.spark, fontFamily: font.bodyMedium }]}>AI</Text>
                </View>
              }
              onClose={close}
            />
            <KeyboardAvoidingView
              style={{ flex: 1 }}
              behavior={Platform.OS === 'ios' ? 'padding' : undefined}
              keyboardVerticalOffset={8}
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
                          disabled={streaming}
                          accessibilityRole="button"
                          style={s.suggChip}
                        >
                          <Text style={[type.label, { color: color.text, fontFamily: font.bodyMedium }]}>{q}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                ) : (
                  turns.map((t, i) => <Bubble key={i} turn={t} streaming={streaming && i === turns.length - 1} />)
                )}

                {error ? (
                  <View style={s.errorBox}>
                    <Text style={[type.body, { color: color.neg }]}>{error}</Text>
                    <Pressable onPress={() => void Linking.openURL(supportMailto('Sparky could not help'))}>
                      <Text style={[type.label, { color: color.accent, marginTop: space.sm }]}>
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
                  editable={!streaming}
                />
                <Pressable
                  onPress={() => void send()}
                  disabled={streaming || !draft.trim()}
                  accessibilityRole="button"
                  accessibilityLabel="Send"
                  style={[s.send, (streaming || !draft.trim()) && { opacity: 0.5 }]}
                >
                  <Ionicons name="send" size={18} color={color.text} />
                </Pressable>
              </View>
            </KeyboardAvoidingView>
          </>
        )}
      </Sheet>
    </>
  )
}

function Bubble({ turn, streaming }: { turn: SparkyTurn; streaming: boolean }) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const mine = turn.role === 'user'
  return (
    <View style={[s.bubble, mine ? s.mine : s.theirs]}>
      {!mine ? (
        <View style={s.bubbleHead}>
          <Image source={SPARKY_AVATAR} style={s.bubbleAvatar} resizeMode="contain" />
          <Text style={[type.label, { color: color.spark, fontFamily: font.bodyMedium }]}>Sparky AI</Text>
        </View>
      ) : null}
      <Text style={[type.body, { color: mine ? color.text : color.textDim }]}>
        {turn.content}
        {streaming && !turn.content ? 'Thinking…' : ''}
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
