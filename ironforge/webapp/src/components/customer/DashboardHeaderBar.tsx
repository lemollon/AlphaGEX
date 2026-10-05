'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import useSWR, { mutate } from 'swr'
import { useRouter } from 'next/navigation'
import { fetcher } from '@/lib/fetcher'

/**
 * The customer header controls the dev-handoff spec puts on every signed-in
 * page (dashboard §6): Pause all/Resume all, theme toggle, notification bell,
 * avatar menu. Gap audit had all four as MISSING/PARTIAL — this is the single
 * shared home for them so CustomerShell only wires them up once.
 */

const THEME_KEY = 'if-theme'

function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark' | null>(null)

  useEffect(() => {
    let stored: 'light' | 'dark' | null = null
    try {
      const raw = window.localStorage.getItem(THEME_KEY)
      if (raw) stored = JSON.parse(raw)
    } catch { /* falls back to OS preference */ }
    if (stored === 'light' || stored === 'dark') {
      setTheme(stored)
      document.documentElement.setAttribute('data-theme', stored)
    }
  }, [])

  function toggle() {
    const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
    const current = theme ?? (prefersDark ? 'dark' : 'light')
    const next = current === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
    try { window.localStorage.setItem(THEME_KEY, JSON.stringify(next)) } catch { /* theme still applies this view */ }
  }

  const isDark = theme === 'dark'
  return (
    <button type="button" onClick={toggle} aria-label="Switch light or dark mode"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--line)] text-[var(--muted)] transition-colors hover:text-[var(--fg)]">
      {isDark ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
          <circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4m11.4-11.4 1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  )
}

interface Activation { activation_id: string; agent: string; paused: boolean }

function PauseAllButton() {
  const { data } = useSWR<{ ok: boolean; activations: Activation[] }>(
    '/api/v1/automation/pause', fetcher, { shouldRetryOnError: false, refreshInterval: 60_000 },
  )
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const activations = data?.activations ?? []

  // Nothing owned yet (fresh signup) — nothing to pause, so no button at all.
  if (data && activations.length === 0) return null

  const allPaused = activations.length > 0 && activations.every((a) => a.paused)
  const nextPaused = !allPaused

  async function apply() {
    setPending(true)
    try {
      await fetch('/api/v1/automation/pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paused: nextPaused, agent: null }),
      })
      await mutate('/api/v1/automation/pause')
    } finally {
      setPending(false)
      setConfirmOpen(false)
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setConfirmOpen(true)}
        disabled={!data || pending}
        className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${
          allPaused
            ? 'border-[var(--up)]/40 bg-[var(--up)]/10 text-[var(--up)] hover:bg-[var(--up)]/15'
            : 'border-[var(--line)] text-[var(--fg)] hover:bg-[var(--bg-2)]'
        }`}
      >
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-3.5 w-3.5">
          {allPaused ? <path d="M8 5v14l11-7z" /> : <path d="M6 5h4v14H6zm8 0h4v14h-4z" />}
        </svg>
        {allPaused ? 'Resume all' : 'Pause all'}
      </button>

      {confirmOpen && (
        <div className="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-[var(--line)] bg-[var(--bg)] p-4 shadow-xl">
          <p className="text-sm text-[var(--fg)]">
            {allPaused
              ? 'Resume automated trading on every agent you own?'
              : 'No new trades will open until you resume. Any open trade stays protected by its protection line and closes by the end of its session.'}
          </p>
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" onClick={() => setConfirmOpen(false)}
              className="rounded-md px-3 py-1.5 text-xs font-semibold text-[var(--muted)] hover:text-[var(--fg)]">
              Cancel
            </button>
            <button type="button" onClick={apply} disabled={pending}
              className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-xs font-semibold text-[var(--accent-ink)] hover:brightness-105 disabled:opacity-60">
              {pending ? 'Working…' : allPaused ? 'Resume all' : 'Pause all'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

interface NotificationRow {
  id: string
  kind: string
  title: string
  body: string
  created_at: string
  read_at: string | null
}
interface NotificationsResp {
  ok?: boolean
  notifications?: NotificationRow[]
  unread_count?: number
}

/**
 * Notification bell — wired to the real history feed that landed on `main`
 * while this branch was in flight (`GET /api/v1/notifications`, PR #3182:
 * "Add real notification history feed"). Still probes defensively: if this
 * branch is ever built against an older `main` without that route, the 401/404
 * degrades the bell to a plain link into Settings rather than rendering a
 * feed that can't load. No fake notification content ships either way.
 */
function NotificationBell() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { data, error, mutate: mutateFeed } = useSWR<NotificationsResp>('/api/v1/notifications', fetcher, {
    shouldRetryOnError: false,
    refreshInterval: 60_000,
  })

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const feedExists = !error && data?.ok !== false
  const items = data?.notifications ?? []
  const unread = data?.unread_count ?? 0

  async function openFeed() {
    const next = !open
    setOpen(next)
    if (next && unread > 0) {
      // Mark-all-read on open, same action the mobile notifications sheet
      // uses (POST /api/v1/notifications/read {all: true}).
      await fetch('/api/v1/notifications/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ all: true }),
      }).catch(() => {})
      mutateFeed()
    }
  }

  const bellIcon = (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  )

  if (!feedExists) {
    return (
      <Link href="/settings" aria-label="Notification settings"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--line)] text-[var(--muted)] transition-colors hover:text-[var(--fg)]">
        {bellIcon}
      </Link>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={openFeed} aria-label="Notifications"
        className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--line)] text-[var(--muted)] transition-colors hover:text-[var(--fg)]">
        {bellIcon}
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--accent)] px-1 text-[9px] font-bold text-[var(--accent-ink)]">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl border border-[var(--line)] bg-[var(--bg)] shadow-xl">
          <div className="border-b border-[var(--line)] px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Notifications
          </div>
          {items.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-[var(--muted)]">Nothing yet — trade and account alerts will show up here.</p>
          ) : (
            items.map((n) => (
              <div key={n.id} className={`border-b border-[var(--line)]/60 px-4 py-3 last:border-0 ${n.read_at ? '' : 'bg-[var(--accent)]/5'}`}>
                <div className="text-sm font-semibold text-[var(--fg)]">{n.title}</div>
                {n.body && <p className="mt-0.5 text-xs text-[var(--muted)]">{n.body}</p>}
                <div className="mt-1 text-[11px] text-[var(--muted)]">
                  {new Date(n.created_at).toLocaleString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function AvatarMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const router = useRouter()
  const { data } = useSWR<{ ok: boolean; customer?: { email?: string } }>('/api/auth/customer-me', fetcher, { shouldRetryOnError: false })

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  if (!data?.ok || !data.customer?.email) return null
  const email = data.customer.email
  const initials = email.slice(0, 2).toUpperCase()

  async function handleLogout() {
    try { await fetch('/api/auth/customer-logout', { method: 'POST' }) } finally { router.push('/login') }
  }

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-label="Account menu"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/15 text-xs font-bold text-[var(--accent)]">
        {initials}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-[var(--line)] bg-[var(--bg)] p-1.5 shadow-xl">
          <div className="truncate px-2.5 py-2 text-xs text-[var(--muted)]">{email}</div>
          <Link href="/settings" onClick={() => setOpen(false)}
            className="block rounded-lg px-2.5 py-2 text-sm text-[var(--fg)] hover:bg-[var(--bg-2)]">
            Settings
          </Link>
          <button type="button" onClick={handleLogout}
            className="block w-full rounded-lg px-2.5 py-2 text-left text-sm text-[var(--fg)] hover:bg-[var(--bg-2)]">
            Log out
          </button>
        </div>
      )}
    </div>
  )
}

export default function DashboardHeaderBar({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`flex items-center ${compact ? 'gap-2' : 'gap-3'}`}>
      <PauseAllButton />
      <ThemeToggle />
      <NotificationBell />
      <AvatarMenu />
    </div>
  )
}
