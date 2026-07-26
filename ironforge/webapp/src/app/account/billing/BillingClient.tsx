'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CustomerShell, { type PlanCardData } from '@/components/customer/CustomerShell'
import { BOT_PLANS, BOTH_PLAN } from '@/lib/billing/plans'

interface SummaryResp { membership?: PlanCardData | null }
interface EntitlementsResp { bots?: string[] }

/**
 * Billing home — the real "Manage Membership" destination (the rail item used to
 * point at the marketing /pricing page). Shows the current plan, opens the Stripe
 * Customer Portal for self-service changes, and — for someone with no active plan
 * — routes to opening a strategy instead of a dead end.
 */
export default function BillingClient() {
  const { data: summary } = useSWR<SummaryResp>('/api/live/summary', fetcher, { refreshInterval: 60_000 })
  const { data: entitlements } = useSWR<EntitlementsResp>('/api/billing/entitlements', fetcher, { shouldRetryOnError: false })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const membership = summary?.membership ?? null
  const ownedBots = entitlements?.bots ?? []
  const hasPlan = ownedBots.length > 0
  const planName = membership?.plan ?? (hasPlan ? 'IronForge Membership' : 'No active plan')
  const badge = membership?.badge ?? (hasPlan ? 'Active' : 'None')

  async function openPortal() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/billing/portal', { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.url) { window.location.href = data.url; return }
      if (res.status === 409) { window.location.href = '/pricing'; return }
      setError(data.error && data.error !== 'no_subscription'
        ? data.error
        : 'Billing management isn’t available just yet — please try again shortly.')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const notOwned = (['spark', 'flame'] as const).filter((b) => !ownedBots.includes(b))

  return (
    <CustomerShell membership={membership} planVariant="active" maxWidthClass="max-w-[860px]">
      <h1 className="text-2xl font-bold text-white">Membership &amp; Billing</h1>
      <p className="mt-1 text-sm text-gray-400">Your plan, payment method, and invoices — all in one place.</p>

      {/* Current plan */}
      <div className="mt-5 rounded-xl border border-forge-border bg-forge-card/80 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Current plan</div>
            <div className="mt-1 flex items-center gap-2">
              <span className="font-display text-lg text-amber-500">{planName}</span>
              <span className={`rounded-full border px-2 py-0.5 text-[11px] ${hasPlan ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' : 'border-forge-border text-gray-400'}`}>{badge}</span>
            </div>
            {hasPlan && (
              <div className="mt-1 text-xs text-gray-400">
                {ownedBots.map((b) => BOT_PLANS[b as 'spark' | 'flame']?.name ?? b).join(' + ')} · {ownedBots.length > 1 ? `$${BOTH_PLAN.priceMonthly}/mo` : `$${BOT_PLANS[ownedBots[0] as 'spark' | 'flame']?.priceMonthly ?? 50}/mo`}
              </div>
            )}
          </div>
          {hasPlan ? (
            <button onClick={openPortal} disabled={busy}
              className="rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60">
              {busy ? 'Opening…' : 'Manage billing'}
            </button>
          ) : (
            <Link href="/pricing" className="rounded-lg border border-amber-500 px-4 py-2.5 text-sm font-semibold text-amber-500 transition hover:bg-amber-500/10">See plans</Link>
          )}
        </div>
        {hasPlan && (
          <p className="mt-3 text-xs text-gray-500">Update your card, change plan, download receipts, or cancel — securely on Stripe.</p>
        )}
        {error && <p className="mt-3 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>}
      </div>

      {/* Add / open a strategy */}
      {notOwned.length > 0 && (
        <div className="mt-4 rounded-xl border border-forge-border bg-forge-card/80 p-5">
          <div className="text-sm font-semibold text-white">{hasPlan ? 'Add a strategy' : 'Open your first strategy'}</div>
          <p className="mt-0.5 text-xs text-gray-400">
            {hasPlan ? `Add the second strategy for +$${BOTH_PLAN.priceMonthly - (BOT_PLANS.spark.priceMonthly)}/mo — $${BOTH_PLAN.priceMonthly} total.` : 'Starts a 5-day free trial — no charge today.'}
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {notOwned.map((b) => {
              const plan = BOT_PLANS[b]
              const accent = b === 'flame' ? '#FD5301' : '#2F80ED'
              return (
                <Link key={b} href={`/live/${b}/open`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-forge-border bg-forge-bg/50 px-3 py-2.5 transition hover:border-white/25"
                  style={{ borderLeft: `3px solid ${accent}` }}>
                  <span className="text-sm font-semibold text-white">{hasPlan ? `Add ${plan.name}` : `Open ${plan.name}`}</span>
                  <span className="text-xs font-medium" style={{ color: accent }}>{hasPlan ? `+$${BOTH_PLAN.priceMonthly - BOT_PLANS.spark.priceMonthly}/mo` : `$${plan.priceMonthly}/mo`}</span>
                </Link>
              )
            })}
          </div>
        </div>
      )}
    </CustomerShell>
  )
}
