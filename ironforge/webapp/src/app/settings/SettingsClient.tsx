'use client'

import Link from 'next/link'
import useSWR, { mutate } from 'swr'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import CustomerShell from '@/components/customer/CustomerShell'
import type { LiveSummary } from '@/lib/live/types'
import { LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'

/**
 * Settings hub (UAT-013): ONE rail entry replaces the three account-management links
 * (Manage Membership / Brokerage Settings / Change Password). Each destination keeps
 * its own page, permissions, and deep-linkable URL — this page is the clearly-labeled
 * directory the doc asks for.
 *
 * Automation + Alerts (dev-handoff §6 — gap-audit MISSING) were added here on top of
 * UAT-016's "no agent controls" scope cut: that cut removed a TradingView config
 * section, not the pause/alert controls the dashboard spec actually calls for, and the
 * spec is explicit that Settings owns "per-agent automation toggle switches" and an
 * "Alerts section". Both wire to real, already-shipped backend routes —
 * `/api/v1/automation/pause` (per-agent pause/resume) and `/api/notifications/preferences`
 * (the real alert columns) — nothing here is a new trading/scanner code path.
 */
const SECTIONS = [
  {
    href: '/account/billing',
    title: 'Membership & Billing',
    blurb: 'Your plan, payment method, invoices, and strategy upgrades.',
    icon: 'M4 7h16v10H4zM4 10h16',
  },
  {
    href: '/account/brokerage',
    title: 'Brokerage Connections',
    blurb: 'Connected brokers, account eligibility, and reconnect actions.',
    icon: 'M4 20h16M6 20V9m4 11V9m4 11V9m4 11V9M3 9l9-5 9 5',
  },
  {
    href: '/change-password',
    title: 'Security',
    blurb: 'Change your password.',
    icon: 'M8 11V7a4 4 0 1 1 8 0v4M5 11h14v9H5z',
  },
  // db-controls #203: "brokerage, plan and agreements links" — the first two
  // already have sections above; this was the missing third.
  {
    href: '/legal',
    title: 'Agreements & Disclosures',
    blurb: 'Terms, risk disclosure, and the other documents you signed.',
    icon: 'M9 12h6m-6 4h6M7 4h10a2 2 0 0 1 2 2v14l-3-2-3 2-3-2-3 2V6a2 2 0 0 1 2-2Z',
  },
] as const

function ToggleSwitch({ on, onChange, disabled }: { on: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      disabled={disabled}
      onClick={onChange}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50 ${on ? 'bg-[var(--accent)]' : 'bg-[var(--line-2)]'}`}
    >
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-[22px]' : 'translate-x-0.5'}`} />
    </button>
  )
}

interface Activation { activation_id: string; agent: string; paused: boolean }

/** Per-agent automation toggles — dev-handoff: "Settings page: per-agent
 *  automation toggle switches." Wired to the real pause/resume activation
 *  route; flipping it off pauses that agent the same way the header's
 *  Pause-all button does for every agent at once. */
function AutomationSection() {
  const { data } = useSWR<{ ok: boolean; activations: Activation[] }>('/api/v1/automation/pause', fetcher, { shouldRetryOnError: false })
  const [pending, setPending] = useState<string | null>(null)

  async function toggle(agent: string, currentlyPaused: boolean) {
    setPending(agent)
    try {
      await fetch('/api/v1/automation/pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paused: !currentlyPaused, agent }),
      })
      await mutate('/api/v1/automation/pause')
    } finally {
      setPending(null)
    }
  }

  if (data && data.activations.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--bg)] p-5">
      <h2 className="text-sm font-semibold text-[var(--fg)]">Automation</h2>
      <p className="mt-0.5 text-xs text-[var(--muted)]">Turn an agent's trading on or off. Any open trade stays protected and closes by the end of its session.</p>
      <div className="mt-4 space-y-3">
        {!data ? (
          <div className="h-10 animate-pulse rounded-lg bg-[var(--bg-2)]" />
        ) : (
          data.activations.map((a) => (
            <div key={a.activation_id} className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-[var(--fg)]">
                  {LIVE_BOT_LABEL[a.agent as LiveBot] ?? a.agent}
                </div>
                <div className="text-xs text-[var(--muted)]">{a.paused ? 'Paused — not taking new trades' : 'Active — trading normally'}</div>
              </div>
              <ToggleSwitch on={!a.paused} onChange={() => toggle(a.agent, a.paused)} disabled={pending === a.agent} />
            </div>
          ))
        )}
      </div>
    </div>
  )
}

/** Column → label/description for the Alerts UI. Keys match
 *  `notification_prefs` exactly (BOOL_COLUMNS in the preferences route) — no
 *  column here is invented; this is the real, already-shipped contract. */
const ALERT_ROWS: Array<{ key: string; label: string; blurb: string }> = [
  { key: 'trade_opened', label: 'Trade opened', blurb: 'Notify me when an agent opens a new trade.' },
  { key: 'trade_closed', label: 'Trade closed', blurb: 'Notify me when a trade closes, win or loss.' },
  { key: 'trade_approval', label: 'Trade needs approval', blurb: 'Notify me when a trade is waiting on my OK.' },
  { key: 'brokerage_health', label: 'Brokerage health', blurb: 'Notify me if a connected broker disconnects or needs attention.' },
  { key: 'billing', label: 'Billing', blurb: 'Notify me about payment issues or upcoming charges.' },
  { key: 'weekly_summary', label: 'Weekly summary', blurb: 'A recap of the week’s results, once a week.' },
  { key: 'community', label: 'Community activity', blurb: 'Notify me about replies and mentions in Forge Community.' },
]

/** Alerts section — dev-handoff: "Alerts section" with push/email toggles.
 *  Wired to `/api/notifications/preferences`, the real backend route; no new
 *  alert category is introduced beyond what that route already persists. */
function AlertsSection() {
  const { data } = useSWR<{ ok: boolean; preferences: Record<string, boolean> }>('/api/notifications/preferences', fetcher, { shouldRetryOnError: false })
  const [pending, setPending] = useState<string | null>(null)
  const prefs = data?.preferences ?? {}

  async function toggle(key: string) {
    setPending(key)
    try {
      await fetch('/api/notifications/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: !prefs[key] }),
      })
      await mutate('/api/notifications/preferences')
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--bg)] p-5">
      <h2 className="text-sm font-semibold text-[var(--fg)]">Alerts</h2>
      <p className="mt-0.5 text-xs text-[var(--muted)]">Choose what IronForge notifies you about.</p>
      <div className="mt-4 space-y-3">
        {!data ? (
          <div className="h-32 animate-pulse rounded-lg bg-[var(--bg-2)]" />
        ) : (
          ALERT_ROWS.map((r) => (
            <div key={r.key} className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[var(--fg)]">{r.label}</div>
                <div className="text-xs text-[var(--muted)]">{r.blurb}</div>
              </div>
              <ToggleSwitch on={prefs[r.key] ?? false} onChange={() => toggle(r.key)} disabled={pending === r.key} />
            </div>
          ))
        )}
      </div>
    </div>
  )
}

/** Settings body, extracted so it can render inline as the /dashboard
 *  "Settings" tab (dev-handoff §6) as well as standalone at /settings
 *  (which now redirects to /dashboard?tab=settings). */
export function SettingsBody() {
  return (
    <>
      <h1 className="text-2xl font-bold text-[var(--fg)]">Settings</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">Account management, automation, and alerts.</p>

      <div className="mt-5 space-y-3">
        <AutomationSection />
        <AlertsSection />
        {SECTIONS.map((s) => (
          <Link key={s.href} href={s.href}
            className="flex items-center gap-4 rounded-xl border border-[var(--line)] bg-[var(--bg)] p-5 transition hover:border-[var(--line-2)]">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
              className="h-6 w-6 shrink-0 text-[var(--accent)]" aria-hidden="true">
              <path d={s.icon} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-[var(--fg)]">{s.title}</span>
              <span className="mt-0.5 block text-xs text-[var(--muted)]">{s.blurb}</span>
            </span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
              className="ml-auto h-4 w-4 shrink-0 text-[var(--muted)]" aria-hidden="true">
              <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        ))}
      </div>
    </>
  )
}

/** Standalone /settings route — now just CustomerShell + the extracted body. */
export default function SettingsClient() {
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher)

  return (
    <CustomerShell membership={summary?.membership ?? null} maxWidthClass="max-w-[860px]">
      <SettingsBody />
    </CustomerShell>
  )
}
