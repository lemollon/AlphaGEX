'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CustomerShell from '@/components/customer/CustomerShell'
import type { LiveSummary } from '@/lib/live/types'

/**
 * Brokerage settings — what you have linked, and what to do about it.
 *
 * The sidebar's "Brokerage Settings" used to point straight at /onboarding/brokerage,
 * which is a FUNNEL STEP: it drops the app chrome, greets you with "Connect your
 * brokerage" whether or not you already have one, never shows what you linked, offers
 * "Skip for now", and on success pushes you to /onboarding/complete — a welcome screen.
 * A returning customer was being walked through signup again to check a setting.
 *
 * This is the settings half, split out. Connecting still hands off to the funnel step,
 * because that flow owns the OAuth handshake and there is no reason to have two of those.
 */

interface Account {
  mask: string | null
  eligibility: string | null
  ineligible_reason: string | null
  buying_power_cents: number | null
}
interface Connection {
  id: string
  provider: string
  status: string
  connected_on: string
  last_synced_at: string | null
  accounts: Account[]
}

const PROVIDER_LABEL: Record<string, string> = {
  tradier: 'Tradier',
  snaptrade: 'Robinhood (via SnapTrade)',
}

function usd(cents: number | null): string {
  if (cents == null) return '—'
  return (cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

export default function BrokerageSettingsClient() {
  const { data, error, isLoading } = useSWR<{ ok: boolean; connections: Connection[] }>(
    '/api/brokerage/connections',
    fetcher,
  )
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher)

  const connections = data?.connections ?? []
  const hasAny = connections.length > 0

  return (
    <CustomerShell membership={summary?.membership ?? null}>
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-bold text-white">Brokerage</h1>
        <p className="mt-1 text-sm text-gray-400">
          Your funds stay in your own account, in your name. IronForge never holds your money.
        </p>

        {isLoading && (
          <div className="mt-6 space-y-3" aria-busy="true">
            <div className="h-24 animate-pulse rounded-xl border border-forge-border bg-forge-card/40" />
          </div>
        )}

        {error && (
          <p className="mt-6 rounded-lg border border-red-700/40 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            Could not load your connections. Refresh to try again.
          </p>
        )}

        {!isLoading && !error && !hasAny && (
          <div className="mt-6 rounded-xl border border-forge-border bg-forge-card/60 p-6 text-center">
            <p className="text-sm font-medium text-white">No brokerage connected</p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-gray-400">
              Connect the brokerage you already use so your strategies can place trades in your
              account. You can disconnect at any time.
            </p>
            <Link
              href="/onboarding/brokerage"
              className="mt-4 inline-flex rounded-lg bg-[#FD5301] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#e04a00]"
            >
              Connect a brokerage
            </Link>
          </div>
        )}

        {hasAny && (
          <div className="mt-6 space-y-3">
            {connections.map((c) => {
              const broken = c.status !== 'active'
              return (
                <div key={c.id} className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-sm font-semibold text-white">
                      {PROVIDER_LABEL[c.provider] ?? c.provider}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                        broken ? 'bg-amber-500/15 text-amber-400' : 'bg-emerald-500/15 text-emerald-400'
                      }`}
                    >
                      {broken ? c.status.replace(/_/g, ' ') : 'Connected'}
                    </span>
                    <span className="ml-auto text-xs text-gray-500">Since {c.connected_on}</span>
                  </div>

                  {/* A broken link is the one state that silently stops trading, so it
                      gets the explicit repair path rather than just a badge. */}
                  {broken && (
                    <div className="mt-3 rounded-lg border border-amber-700/40 bg-amber-950/20 px-3 py-2">
                      <p className="text-xs text-amber-200">
                        This connection needs attention — trading is paused until it is restored.
                      </p>
                      <Link href="/onboarding/brokerage" className="mt-1 inline-block text-xs font-semibold text-amber-400 underline">
                        Reconnect
                      </Link>
                    </div>
                  )}

                  {c.accounts.length > 0 && (
                    <ul className="mt-4 space-y-2">
                      {c.accounts.map((a, i) => {
                        const eligible = a.eligibility === 'eligible'
                        return (
                          <li
                            key={`${c.id}-${i}`}
                            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-black/20 px-3 py-2"
                          >
                            <span className="font-mono text-sm text-gray-300">{a.mask ?? '••••'}</span>
                            <span className="text-xs text-gray-500">Option buying power {usd(a.buying_power_cents)}</span>
                            <span
                              className={`ml-auto text-[10px] font-bold uppercase tracking-wider ${
                                eligible ? 'text-emerald-400' : 'text-gray-500'
                              }`}
                            >
                              {eligible ? 'Eligible' : 'Not eligible'}
                            </span>
                            {/* The remediable reason, not just a red state. */}
                            {!eligible && a.ineligible_reason && (
                              <p className="w-full text-xs text-gray-500">{a.ineligible_reason}</p>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              )
            })}

            <Link
              href="/onboarding/brokerage"
              className="inline-flex rounded-lg border border-forge-border px-4 py-2.5 text-sm font-semibold text-gray-300 transition hover:text-white"
            >
              Connect another brokerage
            </Link>
          </div>
        )}
      </div>
    </CustomerShell>
  )
}
