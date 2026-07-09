'use client'

import { useEffect, useRef, useState } from 'react'
import useSWR, { mutate as globalMutate } from 'swr'
import useSWRImmutable from 'swr/immutable'
import { fetcher } from '@/lib/fetcher'
import type { LiveSummary } from '@/lib/live/types'
import type { CommunityFeed, CommunityMessage } from '@/lib/community/store'
import CustomerShell from '@/components/customer/CustomerShell'

/** Forge Community — chat-first center column + right info rail (per the
 *  approved design). Realtime via 4s SWR polling; no websockets in this stack. */

interface CustomerMe {
  ok: boolean
  customer?: { email?: string }
}

const AVATAR_STYLES = [
  'bg-amber-500/20 text-amber-500',
  'bg-emerald-500/20 text-emerald-500',
  'bg-spark/20 text-spark',
  'bg-stone-500/30 text-stone-300',
  'bg-red-500/20 text-red-400',
]

function avatarStyle(name: string): string {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return AVATAR_STYLES[h % AVATAR_STYLES.length]
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? parts[0]?.[1] ?? '')).toUpperCase()
}

function Avatar({ message, size = 'h-8 w-8' }: { message: Pick<CommunityMessage, 'sender_name' | 'sender_type'>; size?: string }) {
  if (message.sender_type !== 'USER') {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src="/forge-mascot-sm.png" alt="Forge" className={`${size} shrink-0 rounded-full bg-black ring-1 ring-amber-500/60`} />
  }
  return (
    <div className={`${size} flex shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${avatarStyle(message.sender_name)}`}>
      {initialsOf(message.sender_name)}
    </div>
  )
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit',
  })
}

function GreenCheck() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><path d="m9 11 3 3L22 4" />
    </svg>
  )
}

function RailHeader({ children }: { children: React.ReactNode }) {
  return <div className="text-xs font-semibold uppercase tracking-wider text-white">{children}</div>
}

function MessageRow({ msg, canReact, onReact }: {
  msg: CommunityMessage
  canReact: boolean
  onReact: (id: string, emoji: string) => void
}) {
  return (
    <div className="group flex gap-2.5">
      <Avatar message={msg} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold text-white">{msg.sender_name}</span>
          {msg.sender_type === 'FORGE' && (
            <span className="rounded bg-amber-500 px-1 py-px text-[9px] font-bold leading-none text-white">AI</span>
          )}
          <span className="text-[10px] text-gray-500">{timeLabel(msg.created_at)}</span>
        </div>
        <div className="mt-0.5 whitespace-pre-wrap break-words text-sm leading-relaxed text-gray-200">{msg.message}</div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {msg.reactions.map((r) => (
            <button key={r.emoji} disabled={!canReact}
              onClick={() => onReact(msg.id, r.emoji)}
              className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
                r.mine ? 'border-amber-500/50 bg-amber-500/10 text-amber-500' : 'border-forge-border bg-forge-bg text-gray-300'
              } ${canReact ? 'hover:border-amber-500/50' : 'cursor-default'}`}>
              <span>{r.emoji}</span>
              <span>{r.count}</span>
            </button>
          ))}
          {canReact && (
            <div className="hidden gap-1 group-hover:flex">
              {['👍', '🔥'].filter((e) => !msg.reactions.some((r) => r.emoji === e)).map((e) => (
                <button key={e} onClick={() => onReact(msg.id, e)}
                  className="rounded-full border border-forge-border px-2 py-0.5 text-[11px] opacity-60 transition-opacity hover:opacity-100">
                  {e}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function CommunityClient() {
  const [channel, setChannel] = useState('all-chat')
  const [draft, setDraft] = useState('')
  const [sendError, setSendError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [welcomeDismissed, setWelcomeDismissed] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const lastMsgIdRef = useRef<string | null>(null)

  const feedKey = `/api/community/messages?channel=${channel}`
  const { data: feed, error: feedError, mutate } = useSWR<CommunityFeed>(feedKey, fetcher, { refreshInterval: 4_000 })
  const { data: me } = useSWRImmutable<CustomerMe>('/api/auth/customer-me', fetcher, { shouldRetryOnError: false })
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher, { refreshInterval: 120_000 })
  const loggedIn = Boolean(me?.ok)

  useEffect(() => {
    setWelcomeDismissed(typeof window !== 'undefined' && localStorage.getItem('forge-welcome-dismissed') === '1')
  }, [])

  // Auto-scroll when new messages arrive.
  useEffect(() => {
    const last = feed?.messages[feed.messages.length - 1]?.id ?? null
    if (last && last !== lastMsgIdRef.current) {
      lastMsgIdRef.current = last
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
    }
  }, [feed])

  function dismissWelcome() {
    setWelcomeDismissed(true)
    try { localStorage.setItem('forge-welcome-dismissed', '1') } catch { /* ignore */ }
  }

  async function handleSend() {
    const message = draft.trim()
    if (!message || sending) return
    if (!loggedIn) { window.location.href = '/login'; return }
    setSending(true)
    setSendError(null)
    try {
      const res = await fetch('/api/community/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel, message }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.error || 'Failed to send message.')
      }
      setDraft('')
      await mutate()
    } catch (e) {
      setSendError(e instanceof Error ? e.message : 'Failed to send message.')
    } finally {
      setSending(false)
    }
  }

  async function handleReact(messageId: string, emoji: string) {
    if (!loggedIn) return
    // Optimistic toggle for snappy UI; poll reconciles.
    void globalMutate(
      feedKey,
      (current: CommunityFeed | undefined) => {
        if (!current) return current
        return {
          ...current,
          messages: current.messages.map((m) => {
            if (m.id !== messageId) return m
            const existing = m.reactions.find((r) => r.emoji === emoji)
            let reactions
            if (!existing) reactions = [...m.reactions, { emoji, count: 1, mine: true }]
            else if (existing.mine) {
              reactions = m.reactions
                .map((r) => (r.emoji === emoji ? { ...r, count: r.count - 1, mine: false } : r))
                .filter((r) => r.count > 0)
            } else {
              reactions = m.reactions.map((r) => (r.emoji === emoji ? { ...r, count: r.count + 1, mine: true } : r))
            }
            return { ...m, reactions }
          }),
        }
      },
      { revalidate: false },
    )
    await fetch('/api/community/reactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_id: messageId, emoji }),
    }).catch(() => undefined)
    void mutate()
  }

  const channels = feed?.channels ?? [
    { slug: 'all-chat', name: 'All Chat' },
    { slug: 'market-talk', name: 'Market Talk' },
    { slug: 'trade-ideas', name: 'Trade Ideas' },
    { slug: 'news-events', name: 'News & Events' },
    { slug: 'general', name: 'General' },
  ]

  return (
    <CustomerShell membership={summary?.membership ?? null} planVariant="active" maxWidthClass="max-w-[1280px]">
      <div className="grid items-start gap-4 lg:grid-cols-[1fr_300px]">
        {/* ── Chat column ── */}
        <div className="flex h-[calc(100vh-6.5rem)] min-h-[480px] flex-col rounded-xl border border-forge-border bg-forge-card">
          {/* Header */}
          <div className="flex items-center gap-2 border-b border-forge-border px-4 py-3">
            <span className="font-display text-lg tracking-wide text-white">Forge Community</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 text-gray-500">
              <path d="m6 9 6 6 6-6" />
            </svg>
            <span className="ml-2 flex items-center gap-1.5 text-xs text-gray-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              {feed ? `${feed.online_count.toLocaleString()} member${feed.online_count === 1 ? '' : 's'} online` : '…'}
            </span>
            <div className="ml-auto flex items-center gap-3 text-gray-500">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 cursor-default">
                <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
              </svg>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 cursor-default">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M15 3.13a4 4 0 0 1 0 7.75M11 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0" />
              </svg>
              <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4 cursor-default">
                <circle cx="12" cy="5" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="12" cy="19" r="1.6" />
              </svg>
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col px-4">
            {/* Welcome banner */}
            {!welcomeDismissed && (
              <div className="mt-3 flex items-start gap-3 rounded-lg border border-amber-500/25 bg-gradient-to-r from-amber-500/10 to-transparent p-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/forge-mascot.png" alt="Forge" className="h-12 w-12 shrink-0 rounded-lg bg-black object-cover" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-white">
                    Welcome to <span className="text-amber-500">Forge Community</span>
                  </div>
                  <div className="mt-0.5 text-xs leading-relaxed text-gray-300">
                    A place for disciplined traders to learn, share ideas, and grow together.
                    Respect every member and protect the forge.
                  </div>
                </div>
                <button onClick={dismissWelcome} className="text-gray-500 transition-colors hover:text-white" aria-label="Dismiss">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                    <path d="M18 6 6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            {/* Channel tabs */}
            <div className="mt-3 flex flex-wrap gap-2">
              {channels.map((c) => (
                <button key={c.slug} onClick={() => setChannel(c.slug)}
                  className={`rounded-full px-3 py-1 text-xs transition-colors ${
                    channel === c.slug
                      ? 'bg-amber-500 font-medium text-white'
                      : 'border border-forge-border text-gray-300 hover:text-white'
                  }`}>
                  {c.name}
                </button>
              ))}
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto py-4">
              {feedError && !feed ? (
                <div className="py-8 text-center text-xs text-gray-500">
                  The community is temporarily unavailable. Try refreshing in a moment.
                </div>
              ) : !feed ? (
                <div className="py-8 text-center text-xs text-gray-500">Loading the conversation…</div>
              ) : feed.messages.length === 0 ? (
                <div className="py-8 text-center text-xs text-gray-500">
                  No messages in this channel yet — start the conversation.
                </div>
              ) : (
                feed.messages.map((m) => (
                  <MessageRow key={m.id} msg={m} canReact={loggedIn} onReact={handleReact} />
                ))
              )}
            </div>

            {/* Composer */}
            <div className="border-t border-forge-border py-3">
              {sendError && <div className="mb-2 text-xs text-red-400">{sendError}</div>}
              <div className="flex items-center gap-2">
                <button className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-forge-border text-gray-400 transition-colors hover:text-white" aria-label="Add attachment">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                </button>
                <input
                  value={draft}
                  onChange={(e) => { setDraft(e.target.value); setSendError(null) }}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSend() } }}
                  placeholder={loggedIn ? 'Message Forge Community...' : 'Log in to join the conversation'}
                  disabled={!loggedIn && me !== undefined}
                  maxLength={2000}
                  className="h-9 min-w-0 flex-1 rounded-lg border border-forge-border bg-forge-bg px-3 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-amber-500/50 disabled:opacity-60"
                />
                <button className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-forge-border text-gray-400 transition-colors hover:text-white sm:flex" aria-label="Emoji"
                  onClick={() => setDraft((d) => `${d}🔥`)}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                    strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                    <circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01" />
                  </svg>
                </button>
                <button onClick={() => void handleSend()} disabled={sending || (!draft.trim() && loggedIn)}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-white transition-colors hover:bg-amber-400 disabled:opacity-50"
                  aria-label="Send">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                    <path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Right rail ── */}
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-forge-border bg-forge-card p-4">
            <RailHeader>About Forge AI</RailHeader>
            <div className="mt-3 flex items-start gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/forge-mascot-sm.png" alt="Forge" className="h-10 w-10 shrink-0 rounded-lg bg-black" />
              <p className="text-xs leading-relaxed text-gray-300">
                Forge is your AI-powered guide. Sharing trade ideas, market news, and insights throughout the day.
              </p>
            </div>
            <a href="mailto:support@ironforge.trade?subject=About%20Forge%20AI" className="mt-3 inline-block text-xs font-medium text-amber-500 hover:text-amber-400">
              Learn More →
            </a>
          </div>

          <div className="rounded-xl border border-forge-border bg-forge-card p-4">
            <RailHeader>Community Standards</RailHeader>
            <p className="mt-1.5 text-xs text-gray-500">Keep our community strong.</p>
            <div className="mt-3 space-y-2.5">
              {[
                'Be respectful and professional',
                'Share ideas, not personal attacks',
                'No harassment or hate speech',
                'Profanity or aggression = removal',
              ].map((rule) => (
                <div key={rule} className="flex items-start gap-2">
                  <GreenCheck />
                  <span className="text-xs text-gray-200">{rule}</span>
                </div>
              ))}
            </div>
            <a href="/terms" className="mt-3 inline-block text-xs font-medium text-amber-500 hover:text-amber-400">
              View Full Guidelines
            </a>
          </div>

          <div className="rounded-xl border border-forge-border bg-forge-card p-4">
            <RailHeader>Online Members {feed ? `(${feed.online_count.toLocaleString()})` : ''}</RailHeader>
            <div className="mt-3 space-y-2.5">
              {feed && feed.members.length > 0 ? (
                feed.members.slice(0, 6).map((m, i) => (
                  <div key={i} className="flex items-center gap-2.5">
                    <div className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-semibold ${avatarStyle(m.name)}`}>
                      {initialsOf(m.name)}
                    </div>
                    <span className="text-xs text-gray-200">
                      {m.name}{m.you ? ' (You)' : ''}
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-xs text-gray-500">No members online right now.</div>
              )}
            </div>
            {feed && feed.members.length > 6 && (
              <div className="mt-3 text-xs font-medium text-amber-500">View All Members</div>
            )}
          </div>

          <div className="rounded-xl border border-forge-border bg-forge-card p-4">
            <div className="flex items-center gap-2">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 text-amber-500">
                <path d="M3 11h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5zm18 0h-3a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-5z" />
                <path d="M3 11v-1a9 9 0 0 1 18 0v1" />
              </svg>
              <RailHeader>Need Support?</RailHeader>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-gray-400">
              Forge can help with most questions. For anything else, our team is here.
            </p>
            <a href="mailto:support@ironforge.trade"
              className="mt-3 flex items-center justify-center gap-2 rounded-lg border border-amber-500 px-3 py-2 text-xs font-medium text-amber-500 transition-colors hover:bg-amber-500/10">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                <rect x="2" y="4" width="20" height="16" rx="2" /><path d="m22 7-10 6L2 7" />
              </svg>
              support@ironforge.trade
            </a>
          </div>
        </div>
      </div>
    </CustomerShell>
  )
}
