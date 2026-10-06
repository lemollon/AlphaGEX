'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { useIsOperator } from '@/lib/useIsOperator'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Wordmark } from '@/components/Brand'
import { fetcher } from '@/lib/fetcher'
import SparkyWidget from '@/components/support/SparkyWidget'
import { clientSurface, filterNavBySurface, servesPath } from '@/lib/surface'
import { LIVE_BOT_ACCENT, LIVE_BOT_LABEL, isLiveBot, type LiveBot } from '@/lib/live/bots'
import { EMBER_AGENT } from '@/lib/agents/ember'
import DashboardHeaderBar from './DashboardHeaderBar'

/**
 * THE single customer app shell — used by every signed-in page (Live, Performance,
 * Community, Trade History, Open Account). One left rail + one mobile bar, so the
 * chrome is identical everywhere: the menu button never jumps sides, the plan card
 * is always pinned to the bottom, and the nav order is the same on every page.
 *
 * Pages that need an in-content header (e.g. /live's strategy pills) render it as
 * the first child — the shell owns the rail, not the page body.
 *
 * (Replaces the old split where /live, /performance and /account/trades used a
 * separate LiveSidebar with the card at the bottom + a right-side hamburger, while
 * /community and the Open Account pages used a different shell with a top nav bar,
 * the card at the top and a left-side hamburger.)
 */

const ICONS = {
  performance: 'M4 20V10m6 10V4m6 16v-7m-13 7h15',
  live: 'M3 12h4l3-8 4 16 3-8h4',
  community: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M15 3.13a4 4 0 0 1 0 7.75M11 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  history: 'M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  membership: 'M12 2l2.4 4.86 5.36.78-3.88 3.78.92 5.34L12 14.24l-4.8 2.52.92-5.34L4.24 7.64l5.36-.78z',
  brokerage: 'M3 21h18M3 10h18M5 6l7-3 7 3M5 10v11m4.5-11v11m5-11v11M19 10v11',
  password: 'M7 11V7a5 5 0 0 1 10 0v4M5 11h14a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2z',
  help: 'M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3m.08 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  support: 'M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'M18 6 6 18M6 6l12 12',
  ops: 'M13 2 4 14h6l-1 8 9-12h-6l1-8z',
}

// UAT-008 / IF-NAV-001: no "Live" item — the agents ARE the primary navigation.
// AgentNavItems renders Spark + Flame (with ACTIVE/ADD state) right after Performance.
const NAV_MAIN = [
  { label: 'Performance', href: '/performance', icon: ICONS.performance },
  { label: 'Community', href: '/community', icon: ICONS.community },
  { label: 'Trade History', href: '/account/trades', icon: ICONS.history },
]

const NAV_SECONDARY = [
  // UAT-013: ONE Settings entry replaces the three account-management rows
  // (Manage Membership / Brokerage Settings / Change Password). /settings is the
  // labeled directory; the destinations keep their own pages and deep links.
  { label: 'Settings', href: '/settings', icon: ICONS.membership },
  // Ask Sparky (the AI support assistant); Help stays the human-contact door.
  { label: 'Ask Sparky', href: '/support', icon: ICONS.support },
  { label: 'Help', href: '/contact', icon: ICONS.help },
]

// Settings stays highlighted while inside any of its destinations, so the rail
// doesn't lose its place when a deep link (/account/billing etc.) is open.
const SETTINGS_PREFIXES = ['/settings', '/account/billing', '/account/brokerage', '/change-password']

function Icon({ d, className = 'h-5 w-5 shrink-0' }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d={d} />
    </svg>
  )
}

function LogoLockup() {
  return (
    <Link href="/dashboard" aria-label="IronForge dashboard">
      <Wordmark markClass="h-8 w-auto" textClass="text-lg" />
    </Link>
  )
}

export interface PlanCardData {
  plan: string
  badge: string
  trial?: { label: string; day: number; total_days: number; ends_label: string } | null
  trialEndingSoon?: boolean
  paymentFailed?: boolean
}

/**
 * db-states "Trial ending / payment failed" banner (gap audit #212). Shown on every
 * signed-in page because CustomerShell is the one place every one of them renders
 * through. Payment-failed takes priority — it is the state that is actually blocking
 * trading (the executor already refuses new orders on a past_due subscription; see
 * lib/customer-executor/contracts.ts OPENABLE_STATUSES) — trial-ending is informational.
 * Dismissible for the day only: the condition is re-read from the server on every page
 * load, so dismissing never hides a real block past today.
 */
function TrialAndBillingBanner({ membership }: { membership: PlanCardData | null }) {
  const paymentFailed = membership?.paymentFailed === true
  const trialEndingSoon = !paymentFailed && membership?.trialEndingSoon === true
  const active = paymentFailed || trialEndingSoon
  const todayKey = active ? `if-banner-dismissed-${paymentFailed ? 'payment' : 'trial'}-${new Date().toDateString()}` : null
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (!todayKey) {
      setDismissed(false)
      return
    }
    try {
      setDismissed(sessionStorage.getItem(todayKey) === '1')
    } catch {
      setDismissed(false)
    }
  }, [todayKey])

  if (!active || dismissed) return null

  function dismiss() {
    try { sessionStorage.setItem(todayKey!, '1') } catch { /* best-effort */ }
    setDismissed(true)
  }

  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 border-b px-4 py-2.5 text-sm"
      style={
        paymentFailed
          ? { borderColor: 'var(--bad)', background: 'color-mix(in srgb, var(--bad) 12%, var(--bg))', color: 'var(--bad)' }
          : { borderColor: 'var(--warn)', background: 'color-mix(in srgb, var(--warn) 12%, var(--bg))', color: 'var(--warn)' }
      }
    >
      <span className="font-medium">
        {paymentFailed
          ? 'Your last payment failed. New trades are paused until your card is updated.'
          : membership.trial?.label === 'Trial complete'
            ? 'Your free trial has ended.'
            : 'Your free trial ends after today’s session.'}
      </span>
      <span className="flex items-center gap-3 whitespace-nowrap">
        <Link href="/account/billing" className="font-semibold underline hover:opacity-80">
          {paymentFailed ? 'Update payment method' : 'Add a payment method'}
        </Link>
        <button onClick={dismiss} aria-label="Dismiss" className="text-current opacity-70 hover:opacity-100">
          <Icon className="h-4 w-4" d={ICONS.close} />
        </button>
      </span>
    </div>
  )
}

/** Optional strategy switcher shown under "Live" — /live passes bots + onSwitch. */
export interface StrategyNav {
  bots?: LiveBot[]
  activeBot?: LiveBot | null
  paperBots?: string[]
  onSwitch?: (bot: LiveBot) => void
}

function PlanCard({ membership, variant }: { membership: PlanCardData | null; variant: 'trial' | 'active' }) {
  const trial = membership?.trial ?? null
  const pct = trial ? Math.min(100, Math.max(0, Math.round((trial.day / trial.total_days) * 100))) : 0

  // NO membership is a real, common state (signed up, nothing subscribed yet) and it
  // must not be dressed as a paid one. This used to default to
  // `plan ?? 'IronForge Membership'` and `badge ?? 'Active'`, so a customer with no
  // subscription at all saw "IronForge Membership ✓ Active" in green — the card
  // asserting a plan they had never bought, on the same screen that was asking them to
  // sign up for one. Falsely claiming an active paid membership is the worst direction
  // for this error to point.
  const none = !membership
  const plan = membership?.plan ?? 'No membership'

  return (
    <div className={`rounded-xl border bg-[var(--bg)] p-3.5 ${none ? 'border-[var(--line)]' : 'border-[var(--accent-soft)]'}`}>
      <div className="flex items-start gap-2.5">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${none ? 'text-[var(--muted)]' : 'text-[var(--accent)]'}`}
          d="M12 2l8 3v6c0 5.25-3.4 9.74-8 11-4.6-1.26-8-5.75-8-11V5z" />
        <div>
          <div className={`font-display text-base leading-tight ${none ? 'text-[var(--muted)]' : 'text-[var(--accent-text)]'}`}>{plan}</div>
          {none ? (
            <a href="/account/billing" className="text-xs text-[var(--accent-text)] hover:opacity-80">
              Choose a plan
            </a>
          ) : variant === 'trial' && trial ? (
            <div className="text-xs text-[var(--muted)]">{trial.label}</div>
          ) : membership.badge === 'Payment due' ? (
            /* Audit M11: this used to render as a GREEN CHECK — "✓ Payment due" in
               emerald — the exact state that needs attention dressed as success.
               Amber warning + a direct path to fix the card. */
            <a href="/account/billing" className="flex items-center gap-1 text-xs font-semibold text-[var(--accent-text)] hover:opacity-80">
              <Icon className="h-3.5 w-3.5" d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
              Payment due — update card
            </a>
          ) : (
            <div className="flex items-center gap-1 text-xs text-[var(--up)]">
              <Icon className="h-3.5 w-3.5" d="M20 6 9 17l-5-5" />
              {membership.badge ?? 'Active'}
            </div>
          )}
        </div>
      </div>
      {variant === 'trial' && trial && (
        <div className="mt-3">
          <div className="text-xs text-[var(--fg)]">Trial Day {trial.day} of {trial.total_days}</div>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-forge-border">
            <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-1.5 text-[11px] text-[var(--muted)]">{trial.ends_label}</div>
        </div>
      )}
    </div>
  )
}

/** The two customer-purchasable strategies — the ONLY bots ever shown on the customer
 *  surface. */
const PURCHASABLE_BOTS: LiveBot[] = ['spark', 'flame']

const strategyGlyph = (accent: string) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={`h-4 w-4 shrink-0 ${accent}`}>
    <path d="M12 2c1.5 3.5-.5 5.5-2 7.5S8 14 9.5 15.5c.5-1.5 1.5-2.5 2.5-3 .5 2 2 3 2 5a4 4 0 1 1-8 0c0-4.5 4-6 4-10 0-2 1-4 2-5.5z" />
  </svg>
)

/**
 * Agent navigation (UAT-008 / IF-NAV-001): Spark and Flame are TOP-LEVEL items with a
 * state badge, replacing the removed "Live" tab.
 *
 *   - OWNED  → ACTIVE badge, opens that agent's workspace at /agents/{bot}.
 *   - NOT owned → ADD badge, opens the setup flow at /live/{bot}/open (a bundle
 *     upgrade if the other agent is already active).
 *
 * Ownership reads /api/billing/entitlements; badges render only once ownership is
 * KNOWN — never invite a paying customer to re-buy a strategy while loading.
 */
function AgentNavItems({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  const { data: ent } = useSWR<{ bots?: string[] }>('/api/billing/entitlements', fetcher, { shouldRetryOnError: false })

  const owned = new Set<LiveBot>(
    (ent?.bots ?? []).filter((b): b is LiveBot => isLiveBot(b) && PURCHASABLE_BOTS.includes(b)),
  )
  const known = ent !== undefined

  return (
    <>
      <EmberNavItem onNavigate={onNavigate} />
      {PURCHASABLE_BOTS.map((b) => {
        const flame = LIVE_BOT_ACCENT[b] === 'flame'
        const accent = flame ? 'text-flame' : 'text-spark'
        const badgeClass = flame ? 'bg-flame/15 text-flame' : 'bg-spark/15 text-spark'
        const isOwned = owned.has(b)
        const href = isOwned || !known ? `/agents/${b}` : `/live/${b}/open`
        const active = pathname.startsWith(`/agents/${b}`)
        return (
          <Link key={b} href={href} onClick={onNavigate}
            aria-current={active ? 'page' : undefined}
            className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
              active
                ? `border-l-2 border-[var(--accent)] bg-[var(--accent)]/10 font-medium ${accent}`
                : 'border-l-2 border-transparent text-[var(--muted)] hover:text-[var(--fg)]'
            }`}>
            {strategyGlyph(accent)}
            <span>{LIVE_BOT_LABEL[b]}</span>
            {known && (
              <span className={`ml-auto rounded px-1.5 py-px text-[9px] font-bold uppercase tracking-wider ${badgeClass}`}>
                {isOwned ? 'Active' : 'Add'}
              </span>
            )}
          </Link>
        )
      })}
    </>
  )
}

/**
 * Ember nav item — shown ONLY when owned (no "Add" CTA here: Ember has no in-app
 * purchase path, it is free/1-per-person/enrollment-only, see /enroll). Separate from
 * AgentNavItems because Ember is not a LiveBot (no `/api/{bot}/...` Postgres tables) and
 * PURCHASABLE_BOTS' "Add" href assumes a /live/{bot}/open checkout flow that doesn't
 * exist for a free agent.
 */
function EmberNavItem({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  const { data: ent } = useSWR<{ bots?: string[] }>('/api/billing/entitlements', fetcher, { shouldRetryOnError: false })
  if (!(ent?.bots ?? []).includes('ember')) return null
  const active = pathname.startsWith('/agents/ember')
  return (
    <Link href="/agents/ember" onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
        active
          ? 'border-l-2 bg-[var(--bg-2)] font-medium'
          : 'border-l-2 border-transparent text-[var(--muted)] hover:text-[var(--fg)]'
      }`}
      style={active ? { borderColor: EMBER_AGENT.accent, color: EMBER_AGENT.accent } : undefined}>
      {strategyGlyph('text-[var(--muted)]')}
      <span>{EMBER_AGENT.name}</span>
      <span className="ml-auto rounded px-1.5 py-px text-[9px] font-bold uppercase tracking-wider"
        style={{ backgroundColor: `${EMBER_AGENT.accent}26`, color: EMBER_AGENT.accent }}>Active</span>
    </Link>
  )
}

/** Main + secondary nav + logout — shared by the desktop rail and the mobile drawer. */
function NavItems({ onNavigate, strategy }: { onNavigate?: () => void; strategy?: StrategyNav }) {
  const pathname = usePathname()
  const router = useRouter()
  const isOperator = useIsOperator()
  const surface = clientSurface()

  async function handleLogout() {
    try { await fetch('/api/auth/customer-logout', { method: 'POST' }) } finally { router.push('/login') }
  }

  const renderItem = (item: { label: string; href: string; icon: string }) => {
    const active =
      item.href === '/settings'
        ? SETTINGS_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
        : pathname === item.href
    return (
      <Link key={item.label} href={item.href} onClick={onNavigate}
        className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
          active
            ? 'border-l-2 border-[var(--accent)] bg-[var(--accent)]/10 font-medium text-[var(--accent-text)]'
            : 'border-l-2 border-transparent text-[var(--muted)] hover:text-[var(--fg)]'
        }`}>
        <Icon d={item.icon} />
        <span>{item.label}</span>
      </Link>
    )
  }

  return (
    <>
      {/* Operator-only shortcut into the bot console. Never ships on the customer
          surface — /spark 404s there and operator chrome shouldn't reach customers. */}
      {isOperator && servesPath(surface, '/spark') ? (
        <Link href="/spark" onClick={onNavigate}
          className="flex items-center gap-3 border-l-2 border-transparent px-4 py-2.5 text-sm font-semibold text-[var(--accent-text)] transition-colors hover:opacity-80">
          <Icon d={ICONS.ops} />
          <span>Ops</span>
        </Link>
      ) : null}
      {filterNavBySurface(NAV_MAIN, surface).map((item) =>
        item.label === 'Performance' ? (
          <div key="perf-and-agents">
            {renderItem(item)}
            <AgentNavItems onNavigate={onNavigate} />
          </div>
        ) : (
          renderItem(item)
        ),
      )}
      <div className="mx-4 my-3 border-t border-[var(--line)]" />
      {filterNavBySurface(NAV_SECONDARY, surface).map(renderItem)}
      <div className="mx-4 my-3 border-t border-[var(--line)]" />
      <button onClick={handleLogout}
        className="flex w-full items-center gap-3 border-l-2 border-transparent px-4 py-2.5 text-sm text-[var(--muted)] transition-colors hover:text-[var(--fg)]">
        <Icon d={ICONS.logout} />
        <span>Log Out</span>
      </button>
    </>
  )
}

/** Slide-out mobile navigation (opens from the mobile bar's hamburger). */
export function MobileNavDrawer({
  open,
  onClose,
  membership,
  planVariant = 'trial',
  strategy,
}: {
  open: boolean
  onClose: () => void
  membership: PlanCardData | null
  planVariant?: 'trial' | 'active'
  strategy?: StrategyNav
}) {
  // Dialog semantics + Escape (audit: the primary mobile navigation had neither —
  // the pattern already existed in SparkyWidget and just wasn't reused here).
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} aria-hidden />
      <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col overflow-y-auto border-r border-[var(--line)] bg-[var(--bg)]">
        <div className="flex items-center justify-between px-4 py-4">
          <LogoLockup />
          <button onClick={onClose} className="p-1 text-[var(--muted)] transition-colors hover:text-[var(--fg)]" aria-label="Close menu">
            <Icon className="h-5 w-5" d={ICONS.close} />
          </button>
        </div>
        <nav className="flex-1 space-y-0.5 pb-6">
          <NavItems onNavigate={onClose} strategy={strategy} />
        </nav>
        <div className="mt-auto p-4">
          <PlanCard membership={membership} variant={planVariant} />
        </div>
      </div>
    </div>
  )
}

export default function CustomerShell({
  membership,
  planVariant = 'trial',
  maxWidthClass = 'max-w-[1200px]',
  bots,
  activeBot,
  paperBots,
  onSwitch,
  children,
}: {
  membership: PlanCardData | null
  planVariant?: 'trial' | 'active'
  maxWidthClass?: string
  children: React.ReactNode
} & StrategyNav) {
  const [menuOpen, setMenuOpen] = useState(false)
  const strategy: StrategyNav = { bots, activeBot, paperBots, onSwitch }

  return (
    <div className="if-dash min-h-screen bg-[var(--bg)]">
      {/* Mobile top bar — hamburger on the LEFT, then wordmark, then the same
          header controls (pause-all, theme, bell, avatar) the desktop rail gets
          via DashboardHeaderBar below — the dev-handoff header is global, not
          overview-only, so it must render on every signed-in page/breakpoint. */}
      <div className="flex items-center gap-3 border-b border-[var(--line)] bg-[var(--bg)] px-4 py-3 lg:hidden">
        <button onClick={() => setMenuOpen(true)} className="-ml-1 p-1 text-[var(--muted)] transition-colors hover:text-[var(--fg)]" aria-label="Open menu">
          <Icon className="h-6 w-6" d={ICONS.menu} />
        </button>
        <Link href="/" className="min-w-0 flex-1"><Wordmark markClass="h-6 w-auto" textClass="text-lg" /></Link>
        <DashboardHeaderBar compact />
      </div>
      <MobileNavDrawer open={menuOpen} onClose={() => setMenuOpen(false)}
        membership={membership} planVariant={planVariant} strategy={strategy} />

      {/* Desktop rail — the whole column scrolls; the plan card sits at the bottom
          (mt-auto) but is never clipped on short viewports. */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col overflow-y-auto border-r border-[var(--line)] bg-[var(--bg)] lg:flex">
        <div className="shrink-0 px-4 py-5"><LogoLockup /></div>
        <nav className="shrink-0 space-y-0.5 pb-4">
          <NavItems strategy={strategy} />
        </nav>
        <div className="mt-auto shrink-0 p-4">
          <PlanCard membership={membership} variant={planVariant} />
        </div>
      </aside>

      <div className="lg:pl-60">
        {/* Desktop header row — Pause all/Resume all, theme toggle, notification
            bell, avatar menu (dev-handoff §6 header spec; gap-audit MISSING rows).
            Hidden on mobile, where the same controls live in the top bar above. */}
        <div className="hidden items-center justify-end gap-2 border-b border-[var(--line)] bg-[var(--bg)] px-4 py-2.5 lg:flex">
          <DashboardHeaderBar />
        </div>
        <TrialAndBillingBanner membership={membership} />
        <div className={`mx-auto ${maxWidthClass} px-4 py-5`}>{children}</div>
      </div>

      {/* Sparky support — floating, dismissible, on every signed-in page (hides itself on /support). */}
      <SparkyWidget />
    </div>
  )
}
