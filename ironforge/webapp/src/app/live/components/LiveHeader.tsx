'use client'

import { useEffect, useRef, useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { LiveViewerInfo } from '@/lib/live/types'
import { LIVE_BOT_ACCENT, LIVE_BOT_PILL, isLiveBot, type LiveBot } from '@/lib/live/bots'

interface CustomerMe {
  ok: boolean
  customer?: { email?: string }
}

interface LiveHeaderProps {
  viewer?: LiveViewerInfo | null
  onSwitch?: (bot: LiveBot) => void
}

export default function LiveHeader({ viewer, onSwitch }: LiveHeaderProps = {}) {
  // Public route: 401s cleanly when signed out — chip just falls back.
  const { data } = useSWR<CustomerMe>('/api/auth/customer-me', fetcher, {
    shouldRetryOnError: false,
  })
  const email = data?.customer?.email ?? null
  const name = email ? email.split('@')[0] : 'Trader'
  const initials = name.slice(0, 2).toUpperCase()

  // Account menu. The avatar chevron previously implied a dropdown that did not
  // exist, so a customer on /live (especially on mobile, where the sidebar with
  // its wordmark/Log Out collapses) had no way back to the site — the "stuck
  // inside a live account" trap. This gives every screen size an escape route.
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!menuOpen) return
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onEsc)
    }
  }, [menuOpen])

  async function handleLogout() {
    try { await fetch('/api/auth/customer-logout', { method: 'POST' }) } catch { /* navigate anyway */ }
    window.location.href = '/'
  }

  return (
    <div className="flex items-center justify-between">
      <h1 className="font-display text-2xl tracking-wide text-white">Live</h1>
      <div className="flex items-center gap-4">
        {viewer && viewer.allowedBots.length > 1 && onSwitch ? (
          <div className="flex items-center overflow-hidden rounded-lg border border-forge-border text-xs font-semibold">
            {viewer.allowedBots.filter(isLiveBot).map((b) => {
              const active = b === viewer.bot
              const isPaper = (viewer.paperBots ?? []).includes(b)
              // Strategy accent is identity, not mode: Flame is orange whether
              // it is on paper or live money; Spark accounts are blue.
              const activeClass = LIVE_BOT_ACCENT[b] === 'flame'
                ? 'bg-flame/20 px-3 py-1.5 text-flame'
                : 'bg-spark/20 px-3 py-1.5 text-spark'
              return (
                <button
                  key={b}
                  type="button"
                  onClick={() => onSwitch(b)}
                  title={isPaper ? 'Paper trading — simulated, no real orders' : undefined}
                  className={
                    active ? activeClass : 'px-3 py-1.5 text-gray-400 transition-colors hover:text-white'
                  }
                >
                  {LIVE_BOT_PILL[b]}
                  {isPaper ? (
                    <span className="ml-1.5 rounded bg-gray-700 px-1 py-px text-[9px] font-bold uppercase tracking-wider text-gray-300">
                      Paper
                    </span>
                  ) : null}
                </button>
              )
            })}
          </div>
        ) : null}
        {/* The notification bell lived here with a permanently-lit unread dot and no
            handler — it advertised alerts that were never delivered and could not be
            read. Removed rather than faked; if it comes back it wires to the existing
            /api/vol-alerts feed. */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            className="flex items-center gap-2 rounded-lg px-1 py-1 transition-colors hover:bg-white/5"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-spark/20 text-xs font-semibold text-spark">
              {initials}
            </div>
            <span className="hidden text-sm text-gray-300 sm:block">{name}</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round"
              className={`h-4 w-4 text-gray-500 transition-transform ${menuOpen ? 'rotate-180' : ''}`}>
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
          {menuOpen ? (
            <div
              role="menu"
              className="absolute right-0 z-50 mt-2 w-52 overflow-hidden rounded-xl border border-forge-border bg-forge-card shadow-xl"
            >
              {email ? (
                <div className="border-b border-forge-border px-4 py-3">
                  <div className="truncate text-xs text-gray-400">Signed in as</div>
                  <div className="truncate text-sm font-medium text-white">{email}</div>
                </div>
              ) : null}
              <a href="/" role="menuitem"
                className="block px-4 py-2.5 text-sm text-gray-300 transition-colors hover:bg-white/5 hover:text-white">
                Back to site
              </a>
              <a href="/home" role="menuitem"
                className="block px-4 py-2.5 text-sm text-gray-300 transition-colors hover:bg-white/5 hover:text-white">
                Dashboard
              </a>
              <a href="/account/trades" role="menuitem"
                className="block px-4 py-2.5 text-sm text-gray-300 transition-colors hover:bg-white/5 hover:text-white">
                Trade History
              </a>
              <a href="/change-password" role="menuitem"
                className="block px-4 py-2.5 text-sm text-gray-300 transition-colors hover:bg-white/5 hover:text-white">
                Change password
              </a>
              <button type="button" role="menuitem" onClick={handleLogout}
                className="block w-full border-t border-forge-border px-4 py-2.5 text-left text-sm text-gray-300 transition-colors hover:bg-white/5 hover:text-white">
                Log Out
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
