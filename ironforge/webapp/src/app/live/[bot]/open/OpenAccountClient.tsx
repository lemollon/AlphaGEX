'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CustomerShell, { type PlanCardData } from '@/components/customer/CustomerShell'
import CheckoutNotice from '@/components/customer/CheckoutNotice'
import { BOT_PLANS, otherBotSlug, type BotSlug } from '@/lib/billing/plans'

interface BrokerageAccount {
  id: string
  name?: string | null
  institution?: string | null
}
interface AccountsResp {
  ok: boolean
  connected?: boolean
  accounts?: BrokerageAccount[]
}
interface SummaryResp {
  membership?: PlanCardData | null
}
interface EntitlementsResp {
  bots?: string[]
}

function Chevron() {
  return (
    <svg aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted)]"
      viewBox="0 0 20 20" fill="none">
      <path d="M6 8l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function InfoDot({ accent, label, value, icon }: { accent: string; label: string; value: string; icon: JSX.Element }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <span className="shrink-0" style={{ color: accent }}>{icon}</span>
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
        <div className="truncate text-sm font-medium text-[var(--fg)]">{value}</div>
      </div>
    </div>
  )
}

export default function OpenAccountClient({ bot }: { bot: BotSlug }) {
  const plan = BOT_PLANS[bot]
  const accent = plan.accent

  const { data: summary } = useSWR<SummaryResp>('/api/live/summary', fetcher, { refreshInterval: 60_000 })
  const { data: accountsData } = useSWR<AccountsResp>('/api/brokerage/accounts', fetcher, { shouldRetryOnError: false })
  const { data: entitlements } = useSWR<EntitlementsResp>('/api/billing/entitlements', fetcher, { shouldRetryOnError: false })
  const accounts = accountsData?.accounts ?? []

  // No bundle for new purchases (Leron, binding, 2026-10-04): a second bot is its own
  // full-price subscription — ownsOther is informational copy only now, never a price
  // adjustment. Legacy both_monthly bundle subscribers are unaffected (see
  // lib/billing/membership.ts resolvePlan).
  const ownsOther = (entitlements?.bots ?? []).includes(otherBotSlug(bot))
  const displayPrice = plan.priceMonthly

  const [connection, setConnection] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const accountLabel = (a: BrokerageAccount) => a.name || a.institution || 'Connected account'

  // Brokerage connection is INFORMATIONAL here, never a gate (UX audit B3): the
  // selected value was never sent to checkout, yet an empty SnapTrade list (every
  // Tradier-only and community-upgrade customer) left this button permanently
  // disabled — an unopenable door at the end of the documented upgrade path.
  // Brokerage linking is verified where it matters: at activation.
  const canOpen = useMemo(() => !busy, [busy])

  async function openAccount() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/billing/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.url) {
        window.location.href = data.url
        return
      }
      setError(
        res.status === 503
          ? 'Checkout isn’t available just yet — please try again shortly.'
          : data.error || 'Could not start checkout. Please try again.',
      )
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <CustomerShell membership={summary?.membership ?? null} planVariant="trial">
      {/* Stripe sends `?canceled=1` here on abandon; nothing used to read it. */}
      <CheckoutNotice />
      {/* Breadcrumb */}
      <nav className="mb-4 flex items-center gap-2 text-sm">
        <Link href={`/agents/${bot}`} className="capitalize transition-colors hover:text-[var(--fg)]" style={{ color: accent }}>{plan.name}</Link>
        <span className="text-[var(--muted)]">›</span>
        <span className="text-[var(--muted)]">Open Account</span>
      </nav>

      <div className="rounded-2xl border border-[var(--line)] bg-[var(--bg-2)] p-6 sm:p-8">
        {/* Header */}
        <div className="flex items-start gap-5">
          <img src={plan.mascot} alt="" className="h-20 w-20 shrink-0 object-contain sm:h-24 sm:w-24"
            style={{ filter: `drop-shadow(0 0 22px ${accent}66)` }} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-bold text-[var(--fg)] sm:text-3xl">Open {plan.name} Account</h1>
              <span className="rounded-full border px-3 py-1 text-xs font-medium"
                style={{ borderColor: `${accent}66`, color: accent }}>Simple Setup</span>
              <span className="rounded-full border px-3 py-1 text-xs font-medium"
                style={{ borderColor: `${accent}66`, color: accent }}>
                ${displayPrice} <span className="text-[var(--muted)]">/ month</span>
              </span>
            </div>
            <p className="mt-2 text-sm text-[var(--muted)]">{plan.blurb}</p>
            {ownsOther && (
              <p className="mt-2 text-sm text-[var(--muted)]">
                You already run {BOT_PLANS[otherBotSlug(bot)].name}. {plan.name} is billed separately —
                ${displayPrice} / month, its own 5 trading days free.
              </p>
            )}
            {/* db-dash #185: "Forge Community already included" — shown on the design's
                add-agent sheet bullet list (dev-handoff: "pitch, bullets, 'Forge Community
                already included'") and missing here entirely. Community ships with every
                agent, Spark/Flame/Ember alike — never a separate purchase. */}
            <p className="mt-2 text-sm font-medium" style={{ color: accent }}>
              Forge Community already included.
            </p>
          </div>
        </div>

        {/* Form */}
        <div className="mt-8 space-y-6">
          {/* Fixed defaults, not choices (UAT-010): these rendered as disabled dropdowns
              with chevrons, signalling configurability that doesn't exist. They are
              read-only configuration rows; the values are never sent anywhere. */}
          <Field label="Account Type">
            <div className="rounded-lg border border-[var(--line)] bg-[var(--bg)]/60 px-4 py-3 text-sm text-[var(--fg)]">
              Dedicated {plan.name} Account
            </div>
          </Field>

          <Field label="Separate Brokerage Account"
            help={`${plan.name} should use its own brokerage account so strategy activity stays separate from your other active strategies.`}>
            <div className="rounded-lg border border-[var(--line)] bg-[var(--bg)]/60 px-4 py-3 text-sm text-[var(--fg)]">
              Yes, use a separate brokerage account
            </div>
          </Field>

          <Field label="Brokerage Connection" help="Choose an existing connected brokerage or connect a new one.">
            {accounts.length > 0 ? (
              <div className="relative">
                <select
                  className="w-full appearance-none rounded-lg border border-[var(--line)] bg-[var(--bg)]/60 px-4 py-3 pr-10 text-sm text-[var(--fg)] outline-none transition focus:border-[var(--fg)] disabled:cursor-not-allowed disabled:opacity-70"
                  value={connection}
                  onChange={(e) => setConnection(e.target.value)}
                  style={connection ? { borderColor: `${accent}99` } : undefined}
                >
                  <option value="">Select brokerage connection</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>{accountLabel(a)}</option>
                  ))}
                </select>
                <Chevron />
              </div>
            ) : (
              <div className="rounded-lg border border-[var(--line)] bg-[var(--bg)]/60 px-4 py-3 text-sm text-[var(--muted)]">
                No brokerage connected yet — you can connect yours after checkout from Brokerage
                Settings. Automated trading only begins once a brokerage is linked and activated.
              </div>
            )}
          </Field>
        </div>

        {/* Info strip */}
        <div className="mt-6 grid grid-cols-1 divide-y divide-[var(--line)] rounded-xl border border-[var(--line)] sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4">
          <InfoDot accent={accent} label="Strategy" value={plan.name}
            icon={<svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="3" /><circle cx="12" cy="12" r="8" /></svg>} />
          <InfoDot accent={accent} label="Account Setup" value="Separate Brokerage"
            icon={<svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3l8 3v6c0 4.4-3 8-8 9-5-1-8-4.6-8-9V6z" /><path d="M12 8v4" strokeLinecap="round" /><circle cx="12" cy="15.5" r="0.6" fill="currentColor" /></svg>} />
          <InfoDot accent={accent} label="Automation" value="Trades Managed Automatically"
            icon={<svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="4" y="8" width="16" height="11" rx="2" /><path d="M12 8V5M9 13h.01M15 13h.01" strokeLinecap="round" /></svg>} />
          <InfoDot accent={accent} label="Connection" value="Select Before Opening"
            icon={<svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 12a3 3 0 013-3h3a3 3 0 010 6h-1M15 12a3 3 0 01-3 3H9a3 3 0 010-6h1" strokeLinecap="round" /></svg>} />
        </div>

        {/* What this means */}
        <div className="mt-6 rounded-xl border border-[var(--line)] bg-[var(--bg)]/40 p-5">
          <div className="text-sm font-semibold text-[var(--fg)]">What this means</div>
          <ul className="mt-3 space-y-2 text-sm text-[var(--muted)]">
            {[
              `${plan.name} will trade through a dedicated brokerage account.`,
              `Using a separate account keeps ${plan.name} activity independent from your other bots.`,
              'You can choose an existing connected brokerage or add a new one.',
              'Forge Community already included.',
            ].map((t) => (
              <li key={t} className="flex items-start gap-2">
                <svg className="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" opacity="0.5" /><path d="M8 12.5l2.5 2.5L16 9.5" /></svg>
                <span>{t}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm text-[var(--muted)]">
            5 trading days free, $0 due today. {plan.name} is billed{' '}
            <span className="font-medium" style={{ color: accent }}>${displayPrice} / month</span> after that —
            a separate subscription from any other strategy you run.
          </p>
        </div>

        {error && (
          <p className="mt-5 rounded-md border border-[var(--bad)]/40 bg-[var(--bad-soft)]/30 px-3 py-2 text-sm text-[var(--bad)]">{error}</p>
        )}

        {/* Actions */}
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <Link
            href="/onboarding/brokerage"
            className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-[var(--line)] px-4 py-3.5 text-sm font-semibold text-[var(--fg)] transition hover:bg-[var(--bg-2)]"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><path d="M12 8v8M8 12h8" strokeLinecap="round" /></svg>
            Connect New Brokerage
          </Link>
          <button
            onClick={openAccount}
            disabled={!canOpen}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-3.5 text-sm font-semibold text-[var(--fg)] transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{ backgroundColor: accent }}
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M13 3L4 14h6l-1 7 9-11h-6l1-7z" strokeLinejoin="round" /></svg>
            {busy
              ? 'Starting…'
              : ownsOther
                ? `Add ${plan.name} — $${displayPrice} / month`
                : `Open ${plan.name} Account — $${displayPrice} / month`}
          </button>
        </div>
        <p className="mt-3 flex items-center justify-center gap-1.5 text-center text-xs text-[var(--muted)]">
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 018 0v3" /></svg>
          Your brokerage connection is secure and can be updated anytime.
        </p>
      </div>
    </CustomerShell>
  )
}

function Field({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-[220px_1fr] sm:items-start sm:gap-6">
      <label className="pt-3 text-sm font-medium text-[var(--muted)]">{label}</label>
      <div>
        {children}
        {help && <p className="mt-2 text-xs leading-relaxed text-[var(--muted)]">{help}</p>}
      </div>
    </div>
  )
}
