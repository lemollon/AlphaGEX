'use client'

import { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import SparkyChat from './SparkyChat'

/**
 * Floating Sparky support widget — bottom-right on signed-in pages.
 *
 * Three states, persisted in localStorage so navigation/reload never re-pops it:
 *   - 'closed'     → collapsed bubble (default)
 *   - 'open'       → expanded chat panel
 *   - 'dismissed'  → fully hidden ("deleted"); comes back only via the Support nav link.
 *
 * Hidden on /support itself (that page IS the full chat, so the floating copy would be redundant).
 */

type WState = 'closed' | 'open' | 'dismissed'
const KEY = 'sparky-widget-state'

export default function SparkyWidget() {
  const pathname = usePathname()
  const [state, setState] = useState<WState>('closed')
  const [ready, setReady] = useState(false)

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY) as WState | null
      if (saved === 'open' || saved === 'closed' || saved === 'dismissed') setState(saved)
    } catch { /* ignore */ }
    setReady(true)
  }, [])

  const persist = (s: WState) => {
    setState(s)
    try { localStorage.setItem(KEY, s) } catch { /* ignore */ }
  }

  // Esc minimizes the open panel.
  useEffect(() => {
    if (state !== 'open') return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') persist('closed') }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state])

  // Don't render until we've read persisted state (avoids a flash of the bubble
  // for someone who dismissed it), and never on the dedicated support page.
  if (!ready || pathname === '/support' || state === 'dismissed') return null

  if (state === 'closed') {
    return (
      <button
        onClick={() => persist('open')}
        aria-label="Chat with Sparky support"
        className="group fixed bottom-4 right-4 z-40 flex h-14 w-14 items-center justify-center rounded-full border border-spark/40 bg-forge-card shadow-[0_8px_30px_-6px_rgba(47,128,237,0.6)] transition-transform hover:scale-105 motion-safe:animate-[sparkpulse_3s_ease-in-out_infinite]"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/support/sparky-avatar.png" alt="" width={56} height={56} className="h-14 w-14 rounded-full" />
        <span className="pointer-events-none absolute inset-0 rounded-full ring-2 ring-spark/0 transition group-hover:ring-spark/40" />
        <style>{`@keyframes sparkpulse{0%,100%{box-shadow:0 8px 30px -6px rgba(47,128,237,.45)}50%{box-shadow:0 8px 34px -4px rgba(47,128,237,.85)}}`}</style>
      </button>
    )
  }

  // Open panel
  return (
    <div className="fixed inset-0 z-40 sm:inset-auto sm:bottom-4 sm:right-4" role="dialog" aria-label="Sparky support chat">
      <div className="flex h-full w-full flex-col overflow-hidden border border-forge-border bg-forge-bg shadow-2xl sm:h-[560px] sm:max-h-[80vh] sm:w-[384px] sm:rounded-2xl">
        {/* Header */}
        <div className="flex items-center gap-2.5 border-b border-forge-border bg-forge-card/70 px-3 py-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/support/sparky-avatar-anim.webp" alt="Sparky" width={34} height={34} className="h-[34px] w-[34px] rounded-full ring-1 ring-spark/40" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-white">Sparky</div>
            <div className="flex items-center gap-1 text-[11px] text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> IronForge Support
            </div>
          </div>
          <button onClick={() => persist('closed')} aria-label="Minimize"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-white/5 hover:text-white">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-4 w-4"><path d="M5 12h14" /></svg>
          </button>
          <button onClick={() => persist('dismissed')} aria-label="Close and hide Sparky"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-white/5 hover:text-white">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-4 w-4"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </div>
        {/* Chat */}
        <div className="min-h-0 flex-1">
          <SparkyChat variant="panel" />
        </div>
      </div>
    </div>
  )
}
