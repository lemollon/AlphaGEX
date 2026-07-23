'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CustomerShell, { type PlanCardData } from '@/components/customer/CustomerShell'
import { BOT_PLANS, type BotSlug } from '@/lib/billing/plans'

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

function Chevron() {
  return (
    <svg aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500"
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
        <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
        <div className="truncate text-sm font-medium text-white">{value}</div>
      </div>
    </div>
  )
}

export default function OpenAccountClient({ bot }: { bot: BotSlug }) {
  const plan = BOT_PLANS[bot]
  const accent = plan.accent

  const { data: summary } = useSWR<SummaryResp>('/api/live/summary', fetcher, { refreshInterval: 60_000 })
  const { data: accountsData } = useSWR<AccountsResp>('/api/brokerage/accounts', fetcher, { shouldRetryOnError: false })
  const accounts = accountsData?.accounts ?? []

  const [connection, setConnection] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const accountLabel = (a: BrokerageAccount) => a.name || a.institution || 'Connected account'

  const canOpen = useMemo(() => connection !== '' && !busy, [connection, busy])

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
      {/* Breadcrumb */}
      <nav className="mb-4 flex items-center gap-2 text-sm">
        <Link href="/live" className="text-gray-500 transition-colors hover:text-white" style={{ color: accent }}>Live</Link>
        <span className="text-gray-600">›</span>
        <Link href="/live" className="capitalize transition-colors hover:text-white" style={{ color: accent }}>{plan.name}</Link>
        <span className="text-gray-600">›</span>
        <span className="text-gray-400">Open Account</span>
      </nav>

      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 sm:p-8">
        {/* Header */}
        <div className="flex items-start gap-5">
          <img src={plan.mascot} alt="" className="h-20 w-20 shrink-0 object-contain sm:h-24 sm:w-24"
            style={{ filter: `drop-shadow(0 0 22px ${accent}66)` }} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-bold text-white sm:text-3xl">Open {plan.name} Account</h1>
              <span className="rounded-full border px-3 py-1 text-xs font-medium"
                style={{ borderColor: `${accent}66`, color: accent }}>Simple Setup</span>
              <span className="rounded-full border px-3 py-1 text-xs font-medium"
                style={{ borderColor: `${accent}66`, color: accent }}>
                ${plan.priceMonthly} <span className="text-gray-400">/ month</span>
              </span>
            </div>
            <p className="mt-2 text-sm text-gray-400">{plan.blurb}</p>
          </div>
        </div>

        {/* Form */}
        <div className="mt-8 space-y-6">
          <Field label="Account Type">
            <div className="relative">
              <select disabled className="w-full appearance-none rounded-lg border border-forge-border bg-forge-bg/60 px-4 py-3 pr-10 text-sm text-white outline-none transition focus:border-white/30 disabled:cursor-not-allowed disabled:opacity-70" defaultValue="dedicated">
                <option value="dedicated">Dedicated {plan.name} Account</option>
              </select>
              <Chevron />
            </div>
          </Field>

          <Field label="Separate Brokerage Account"
            help={`${plan.name} should use its own brokerage account so strategy activity stays separate from your other active strategies.`}>
            <div className="relative">
              <select disabled className="w-full appearance-none rounded-lg border border-forge-border bg-forge-bg/60 px-4 py-3 pr-10 text-sm text-white outline-none transition focus:border-white/30 disabled:cursor-not-allowed disabled:opacity-70" defaultValue="yes">
                <option value="yes">Yes, use a separate brokerage account</option>
              </select>
              <Chevron />
            </div>
          </Field>

          <Field label="Brokerage Connection" help="Choose an existing connected brokerage or connect a new one.">
            <div className="relative">
              <select
                className="w-full appearance-none rounded-lg border border-forge-border bg-forge-bg/60 px-4 py-3 pr-10 text-sm text-white outline-none transition focus:border-white/30 disabled:cursor-not-allowed disabled:opacity-70"
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
          </Field>
        </div>

        {/* Info strip */}
        <div className="mt-6 grid grid-cols-1 divide-y divide-forge-border rounded-xl border border-forge-border sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4">
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
        <div className="mt-6 rounded-xl border border-forge-border bg-forge-bg/40 p-5">
          <div className="text-sm font-semibold text-white">What this means</div>
          <ul className="mt-3 space-y-2 text-sm text-gray-300">
            {[
              `${plan.name} will trade through a dedicated brokerage account.`,
              `Using a separate account keeps ${plan.name} activity independent from your other bots.`,
              'You can choose an existing connected brokerage or add a new one.',
            ].map((t) => (
              <li key={t} className="flex items-start gap-2">
                <svg className="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" opacity="0.5" /><path d="M8 12.5l2.5 2.5L16 9.5" /></svg>
                <span>{t}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm text-gray-400">
            {plan.name} is billed <span className="font-medium" style={{ color: accent }}>${plan.priceMonthly} / month</span> after a 5-day free trial.
          </p>
        </div>

        {error && (
          <p className="mt-5 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        )}

        {/* Actions */}
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <Link
            href="/onboarding/brokerage"
            className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-forge-border px-4 py-3.5 text-sm font-semibold text-gray-200 transition hover:bg-white/5"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><path d="M12 8v8M8 12h8" strokeLinecap="round" /></svg>
            Connect New Brokerage
          </Link>
          <button
            onClick={openAccount}
            disabled={!canOpen}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-3.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{ backgroundColor: accent }}
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M13 3L4 14h6l-1 7 9-11h-6l1-7z" strokeLinejoin="round" /></svg>
            {busy ? 'Starting…' : `Open ${plan.name} Account — $${plan.priceMonthly} / month`}
          </button>
        </div>
        <p className="mt-3 flex items-center justify-center gap-1.5 text-center text-xs text-gray-500">
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
      <label className="pt-3 text-sm font-medium text-gray-300">{label}</label>
      <div>
        {children}
        {help && <p className="mt-2 text-xs leading-relaxed text-gray-500">{help}</p>}
      </div>
    </div>
  )
}
