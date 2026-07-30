'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'

/**
 * BROKER-01 — Connect brokerage (ported from the retired EnrollClient spine).
 *
 * This revision carries the connect affordance and the per-account eligibility list
 * with the REMEDIABLE reason (never a bare refusal). The approved four-tile provider
 * layout and the OAuth return-to-enroll leg land in the follow-up PR that threads
 * `return_to` through the OAuth state.
 */

interface BrokerAccount {
  id: string
  mask: string | null
  eligibility: string | null
  ineligible_reason: string | null
}

interface Conn {
  id: string
  provider: string
  status: string
  accounts: BrokerAccount[]
}

export default function BrokerClient() {
  const { enrollment, error, setError, call } = useEnrollment('broker')
  const [conns, setConns] = useState<Conn[] | null>(null)

  useEffect(() => {
    if (!enrollment) return
    ;(async () => {
      try {
        const d = await call('/api/brokerage/connections')
        setConns(d.connections ?? [])
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load your brokerage connections.')
      }
    })()
  }, [enrollment, call, setError])

  return (
    <EnrollShell
      headline="Connect securely."
      subline="Authorize IronForge through your broker. We never see or store your brokerage password."
      maxWidthClass="max-w-3xl"
    >
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <h2 className="text-2xl font-bold text-white">Connect your brokerage</h2>
        <p className="mt-1 text-sm text-gray-400">Choose the brokerage account your selected agent will use.</p>

        {error ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}

        {!conns && !error ? (
          <div className="mt-6 h-48 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        {conns && conns.length === 0 ? (
          <>
            <p className="mt-4 text-sm text-gray-400">
              Connect the brokerage you already use. Your funds stay in your own account.
            </p>
            <Link
              href="/onboarding/brokerage"
              className="mt-5 inline-flex rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-black transition hover:bg-amber-400"
            >
              Connect a brokerage
            </Link>
          </>
        ) : null}

        {conns && conns.length > 0 ? (
          <ul className="mt-5 space-y-2">
            {conns.flatMap((c) =>
              c.accounts.map((a, i) => {
                const ok = a.eligibility === 'eligible'
                return (
                  <li key={`${c.id}-${i}`} className="rounded-lg border border-white/10 bg-black/20 px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm text-gray-200">{a.mask ?? '••••'}</span>
                      <span className="text-xs text-gray-500">{c.provider}</span>
                      <span
                        className={`ml-auto text-[10px] font-bold uppercase tracking-wider ${
                          ok ? 'text-emerald-400' : 'text-gray-500'
                        }`}
                      >
                        {ok ? 'Eligible' : 'Not eligible'}
                      </span>
                    </div>
                    {/* The REMEDIABLE reason, never a bare refusal. */}
                    {!ok && a.ineligible_reason ? (
                      <p className="mt-1 text-xs leading-snug text-gray-500">{a.ineligible_reason}</p>
                    ) : null}
                  </li>
                )
              }),
            )}
          </ul>
        ) : null}

        <div className="mt-5 rounded-xl border border-forge-border bg-black/20 p-4">
          <p className="flex items-start gap-2 text-sm text-gray-300">
            <span aria-hidden>🔒</span>
            <span>
              <strong className="text-white">Secure brokerage authorization.</strong> You will sign in directly with
              your broker. IronForge cannot withdraw funds or transfer cash.
            </span>
          </p>
          <p className="mt-2 border-t border-forge-border pt-2 text-xs text-gray-500">
            Recommended: use a dedicated brokerage account for IronForge automation.
          </p>
        </div>

        <p className="mt-6 text-center text-[11px] text-gray-600">
          Brokerage names and marks belong to their respective owners. Availability does not imply endorsement.
        </p>
      </div>
    </EnrollShell>
  )
}
