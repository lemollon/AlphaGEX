'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'
import HomeLink from '@/components/HomeLink'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    try {
      await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
    } catch { /* enumeration-safe: show the same confirmation regardless */ }
    setSent(true)
    setBusy(false)
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md">
        <div className="mb-6 flex justify-center"><Link href="/" aria-label="IronForge home"><Wordmark /></Link></div>
        <div className="mb-4 flex items-center text-sm text-gray-400">
          <HomeLink />
        </div>
        <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
          {sent ? (
            <>
              <h1 className="text-xl font-bold text-white">Check your email</h1>
              <p className="mt-2 text-sm leading-relaxed text-gray-400">
                If an account exists for <span className="font-medium text-amber-500">{email}</span>, we&apos;ve sent a
                link to reset your password. The link expires in 1 hour.
              </p>
              <p className="mt-6 text-center text-xs text-gray-500">
                <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">Back to sign in</Link>
              </p>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-bold text-white">Reset your password</h1>
              <p className="mt-1 text-sm text-gray-400">Enter your email and we&apos;ll send you a reset link.</p>
              <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
                <div>
                  <label htmlFor="email" className="block text-xs text-gray-400">Email</label>
                  <input
                    id="email" type="email" autoComplete="email" autoFocus required
                    value={email} onChange={(e) => setEmail(e.target.value)}
                    className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                  />
                </div>
                <button
                  type="submit" disabled={busy}
                  className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? 'Sending…' : 'Send reset link'}
                </button>
              </form>
              <p className="mt-6 text-center text-xs text-gray-500">
                <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">Back to sign in</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
