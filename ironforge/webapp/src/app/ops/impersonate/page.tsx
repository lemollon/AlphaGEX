'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'

/* Operator impersonation picker — the visible UI over /api/ops/impersonate.
 * Lists customers with one-click "view as" destinations; shows and clears the
 * current impersonation. Requires an operator session (the API refuses
 * everyone else, and this page just surfaces that). */

interface RosterUser {
  email: string
  onboardingStep: string
  verified: boolean
}

interface Roster {
  ok: boolean
  error?: string
  currentlyImpersonating: { customerId: string; email?: string } | null
  users: RosterUser[]
}

const DESTINATIONS = [
  { label: 'Home', next: '/home' },
  { label: 'Community', next: '/community' },
  { label: 'Live', next: '/live' },
  { label: 'Trades', next: '/account/trades' },
]

export default function ImpersonatePage() {
  const [roster, setRoster] = useState<Roster | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = () => {
    fetch('/api/ops/impersonate')
      .then(async (r) => {
        const d = (await r.json().catch(() => null)) as Roster | null
        if (!r.ok || !d?.ok) setFailed(d?.error ?? 'Operator session required.')
        else setRoster(d)
      })
      .catch(() => setFailed('Could not reach the impersonation API.'))
  }
  useEffect(load, [])

  const stop = async () => {
    setBusy(true)
    await fetch('/api/ops/impersonate?clear=true').catch(() => {})
    setBusy(false)
    setRoster(null)
    setFailed(null)
    load()
  }

  return (
    <div className="min-h-screen bg-forge-bg px-4 py-10">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6 flex items-center justify-between">
          <Link href="/" aria-label="IronForge home">
            <Wordmark />
          </Link>
          <span className="rounded-full border border-amber-500/70 px-3 py-1 text-xs font-bold tracking-wider text-amber-500">
            ADMIN
          </span>
        </div>

        <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-6 shadow-2xl">
          <h1 className="text-xl font-bold text-white">View the site as a customer</h1>
          <p className="mt-1 text-sm text-gray-400">
            Pick a customer and destination. Your operator session stays active; the badge in the corner
            shows who you are and lets you stop anytime.
          </p>

          {failed ? (
            <div className="mt-6 rounded-md border border-amber-700/40 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">
              {failed}{' '}
              <Link href="/ops/login" className="font-semibold text-amber-400 underline">
                Operator login
              </Link>
            </div>
          ) : !roster ? (
            <p className="mt-6 text-sm text-gray-500">Loading customers…</p>
          ) : (
            <>
              {roster.currentlyImpersonating ? (
                <div className="mt-5 flex items-center justify-between rounded-md border border-amber-500/40 bg-amber-950/20 px-4 py-2.5 text-sm">
                  <span className="text-gray-200">
                    Currently viewing as{' '}
                    <span className="font-semibold text-white">
                      {roster.currentlyImpersonating.email ?? roster.currentlyImpersonating.customerId}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={stop}
                    disabled={busy}
                    className="rounded-md bg-red-600/90 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-60"
                  >
                    Stop impersonating
                  </button>
                </div>
              ) : null}

              <ul className="mt-5 divide-y divide-white/5">
                {roster.users.length === 0 ? (
                  <li className="py-4 text-sm text-gray-500">No customers in the database yet.</li>
                ) : (
                  roster.users.map((u) => (
                    <li key={u.email} className="flex flex-wrap items-center justify-between gap-2 py-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-white">{u.email}</div>
                        <div className="text-xs text-gray-500">
                          {u.onboardingStep} · {u.verified ? 'verified' : 'unverified'}
                        </div>
                      </div>
                      <div className="flex shrink-0 gap-1.5">
                        {DESTINATIONS.map((d) => (
                          <a
                            key={d.next}
                            href={`/api/ops/impersonate?email=${encodeURIComponent(u.email)}&next=${encodeURIComponent(d.next)}`}
                            className="rounded-md border border-amber-500/50 px-2.5 py-1 text-xs font-semibold text-amber-400 transition-colors hover:bg-amber-500 hover:text-black"
                          >
                            {d.label}
                          </a>
                        ))}
                      </div>
                    </li>
                  ))
                )}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
