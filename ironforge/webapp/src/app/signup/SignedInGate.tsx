'use client'

import { useState } from 'react'
import Link from 'next/link'

/**
 * Shown when a SIGNED-IN visitor lands on /signup (UAT-007). The previous behavior —
 * a silent redirect into /enroll — swallowed the "create a new account" intent and
 * carried the visitor into the EXISTING session's funnel, which read as another
 * user's membership. The intent is ambiguous only the user can resolve it: continue
 * as who they are, or sign out and actually create a new account.
 */
export default function SignedInGate({ email }: { email: string | null }) {
  const [signingOut, setSigningOut] = useState(false)

  async function signOutAndCreate() {
    setSigningOut(true)
    try {
      await fetch('/api/auth/customer-logout', { method: 'POST' })
    } catch { /* reload re-renders the server guard either way */ }
    window.location.reload()
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-forge-bg px-4">
      <div className="w-full max-w-md rounded-2xl border border-forge-border bg-forge-card/60 p-8 text-center">
        <h1 className="text-xl font-bold text-white">You’re already signed in</h1>
        <p className="mt-3 text-sm leading-relaxed text-gray-400">
          {email ? (
            <>This browser is signed in as <span className="text-gray-200">{email}</span>.</>
          ) : (
            'This browser is signed in to an existing IronForge account.'
          )}{' '}
          To create a different account, sign out first.
        </p>
        <div className="mt-6 flex flex-col gap-3">
          <Link
            href="/enroll"
            className="rounded-lg bg-amber-500 px-5 py-3 text-sm font-semibold text-black transition hover:bg-amber-400"
          >
            Continue to my account
          </Link>
          <button
            type="button"
            onClick={signOutAndCreate}
            disabled={signingOut}
            className="rounded-lg border border-forge-border px-5 py-3 text-sm font-semibold text-gray-200 transition hover:border-gray-500 disabled:opacity-60"
          >
            {signingOut ? 'Signing out…' : 'Sign out & create a new account'}
          </button>
        </div>
      </div>
    </main>
  )
}
