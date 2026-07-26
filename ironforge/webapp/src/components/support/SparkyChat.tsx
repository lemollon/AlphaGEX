'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { SUGGESTED_PROMPTS } from '@/lib/support/knowledge'
import { SPARKY_DISCLAIMER, SPARKY_GREETING } from '@/lib/support/persona'

/**
 * Shared Sparky chat surface — used by BOTH the floating widget panel and the /support page.
 * Conversation is persisted to localStorage under one key, so the widget and the page show the
 * SAME conversation on the same device (the MVP form of "shared history"; cross-device sync is a
 * later, DB-backed phase). Streaming is read from the SSE the /api/support/chat route sends.
 */

const STORAGE_KEY = 'sparky-conversation-v1'
const AVATAR = '/support/sparky-avatar.png'

interface Msg { id: string; role: 'user' | 'assistant'; content: string }

let idSeq = 0
const newId = () => `${Date.now()}-${idSeq++}`

/** Escape then apply a tiny, XSS-safe markdown subset (bold, links, bullets, breaks). */
function renderContent(text: string): string {
  let s = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Links: internal (/...) stay in-app; external (https://) open in a new tab.
  s = s.replace(/\[([^\]]+)\]\((\/[^)\s]*|https?:\/\/[^)\s]+)\)/g, (_m, label, href) => {
    const external = /^https?:/i.test(href)
    const attrs = external ? ' target="_blank" rel="noopener noreferrer"' : ''
    return `<a href="${href}"${attrs} class="underline decoration-spark/50 hover:decoration-spark">${label}</a>`
  })
  // Bullet lines beginning with "- ".
  const lines = s.split('\n')
  const out: string[] = []
  let inList = false
  for (const line of lines) {
    if (/^\s*-\s+/.test(line)) {
      if (!inList) { out.push('<ul class="my-1 ml-4 list-disc space-y-0.5">'); inList = true }
      out.push(`<li>${line.replace(/^\s*-\s+/, '')}</li>`)
    } else {
      if (inList) { out.push('</ul>'); inList = false }
      out.push(line)
    }
  }
  if (inList) out.push('</ul>')
  return out.join('\n').replace(/\n/g, '<br/>')
}

export default function SparkyChat({ variant = 'panel' }: { variant?: 'panel' | 'page' }) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Load persisted conversation on mount.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) setMessages(JSON.parse(raw))
    } catch { /* ignore */ }
  }, [])

  // Persist on change.
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-40))) } catch { /* ignore */ }
  }, [messages])

  // Auto-scroll to newest.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    setError(null)
    const userMsg: Msg = { id: newId(), role: 'user', content: trimmed }
    const assistantMsg: Msg = { id: newId(), role: 'assistant', content: '' }
    const history = [...messages, userMsg]
    setMessages([...history, assistantMsg])
    setDraft('')
    setSending(true)

    const controller = new AbortController()
    abortRef.current = controller
    try {
      const res = await fetch('/api/support/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history.map((m) => ({ role: m.role, content: m.content })) }),
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.error || 'Sparky is unavailable right now.')
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let acc = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let sep: number
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const line = buffer.slice(0, sep).trim()
          buffer = buffer.slice(sep + 2)
          if (!line.startsWith('data:')) continue
          const evt = JSON.parse(line.slice(5).trim())
          if (evt.t) {
            acc += evt.t
            setMessages((prev) => prev.map((m) => (m.id === assistantMsg.id ? { ...m, content: acc } : m)))
          } else if (evt.error) {
            throw new Error(evt.error)
          }
        }
      }
      if (!acc.trim()) {
        setMessages((prev) => prev.map((m) => (m.id === assistantMsg.id ? { ...m, content: "Sorry, I didn't catch that — try rephrasing?" } : m)))
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      const msg = e instanceof Error ? e.message : 'Something went wrong.'
      setError(msg)
      // Drop the empty assistant placeholder on failure.
      setMessages((prev) => prev.filter((m) => m.id !== assistantMsg.id || m.content))
    } finally {
      setSending(false)
      abortRef.current = null
    }
  }, [messages, sending])

  function clearChat() {
    abortRef.current?.abort()
    setMessages([])
    setError(null)
    try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
  }

  const empty = messages.length === 0

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 min-h-0 space-y-3 overflow-y-auto px-3 py-3">
        {empty ? (
          <div className="flex flex-col items-center gap-3 py-5 text-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/support/sparky-avatar-anim.webp" alt="Sparky" width={72} height={72}
              className="h-[72px] w-[72px] rounded-full ring-1 ring-spark/40" />
            <p className="max-w-[34ch] text-sm text-gray-300">{SPARKY_GREETING}</p>
            <div className="mt-1 flex w-full flex-col gap-2">
              {SUGGESTED_PROMPTS.map((p) => (
                <button key={p} onClick={() => void send(p)} disabled={sending}
                  className="rounded-lg border border-forge-border bg-forge-card/60 px-3 py-2 text-left text-[13px] text-gray-200 transition-colors hover:border-spark/50 hover:text-white disabled:opacity-50">
                  {p}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={`flex items-start gap-2 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
              {m.role === 'assistant' && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={AVATAR} alt="Sparky" width={26} height={26} className="mt-0.5 h-[26px] w-[26px] shrink-0 rounded-full ring-1 ring-spark/30" />
              )}
              <div className={`max-w-[82%] rounded-2xl px-3 py-2 text-[13.5px] leading-relaxed ${
                m.role === 'user'
                  ? 'rounded-br-sm bg-spark/15 text-white'
                  : 'rounded-bl-sm bg-forge-card text-gray-100 border border-forge-border'
              }`}>
                {m.content
                  ? <span dangerouslySetInnerHTML={{ __html: renderContent(m.content) }} />
                  : <span className="inline-flex gap-1 py-1" aria-label="Sparky is typing">
                      <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-spark [animation-delay:-0.2s]" />
                      <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-spark [animation-delay:-0.1s]" />
                      <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-spark" />
                    </span>}
              </div>
            </div>
          ))
        )}
        {error && (
          <div className="rounded-lg border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-forge-border px-3 py-2.5">
        <form
          onSubmit={(e) => { e.preventDefault(); void send(draft) }}
          className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(draft) } }}
            rows={1}
            placeholder="Ask Sparky…"
            maxLength={2000}
            className="max-h-28 min-h-[38px] flex-1 resize-none rounded-lg border border-forge-border bg-forge-bg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none transition-colors focus:border-spark/50"
          />
          <button type="submit" disabled={sending || !draft.trim()}
            className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-lg bg-spark text-white transition-colors hover:bg-spark/85 disabled:opacity-40"
            aria-label="Send">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
              <path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" />
            </svg>
          </button>
        </form>
        <div className="mt-1.5 flex items-center justify-between gap-2 text-[10.5px] text-gray-500">
          <span className="truncate">{SPARKY_DISCLAIMER}</span>
          <span className="flex shrink-0 items-center gap-2">
            {!empty && <button onClick={clearChat} className="hover:text-gray-300">Clear</button>}
            <a href="/contact" className="text-spark/80 hover:text-spark">Talk to a person</a>
          </span>
        </div>
      </div>
    </div>
  )
}
