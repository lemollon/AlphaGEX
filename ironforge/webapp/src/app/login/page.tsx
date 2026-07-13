'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'
import HomeLink from '@/components/HomeLink'

export default function CustomerLoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [unverified, setUnverified] = useState(false)
  const [resendMsg, setResendMsg] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    setUnverified(false)
    try {
      const res = await fetch('/api/auth/customer-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok) {
        window.location.href = data.next || '/onboarding/complete'
        return
      }
      if (data.code === 'email_unverified') {
        setUnverified(true)
      } else {
        setError(data.error || 'Invalid email or password.')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    setResendMsg(null)
    try {
      await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      setResendMsg('If that email needs verification, we just sent a new link.')
    } catch {
      setResendMsg('Could not send right now. Please try again shortly.')
    }
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md">
        <div className="mb-6 flex justify-center"><Link href="/" aria-label="IronForge home"><Wordmark /></Link></div>
        <div className="mb-4 flex items-center text-sm text-gray-400">
          <HomeLink />
        </div>
        <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
          <h1 className="text-2xl font-bold text-white">Sign in</h1>
          <p className="mt-1 text-sm text-gray-400">Welcome back to IronForge.</p>

          {unverified ? (
            <div className="mt-6 space-y-4">
              <p className="rounded-md border border-amber-700/40 bg-amber-950/30 px-3 py-2 text-sm text-amber-200">
                Please verify your email before signing in.
              </p>
              <button
                onClick={resend}
                className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500"
              >
                Resend verification email
              </button>
              {resendMsg && <p className="text-xs text-gray-400">{resendMsg}</p>}
              <button onClick={() => setUnverified(false)} className="w-full text-center text-xs text-gray-500 hover:text-gray-300">
                Back to sign in
              </button>
            </div>
          ) : (
            <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
              <div>
                <label htmlFor="email" className="block text-xs text-gray-400">Email</label>
                <input
                  id="email" name="email" type="email" autoComplete="email" autoFocus required
                  value={email} onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                />
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <label htmlFor="password" className="block text-xs text-gray-400">Password</label>
                  <Link href="/forgot-password" className="text-xs text-amber-500 hover:text-amber-400">Forgot password?</Link>
                </div>
                <input
                  id="password" name="password" type="password" autoComplete="current-password" required
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                />
              </div>
              {error && (
                <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
              )}
              <button
                type="submit" disabled={busy}
                className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          )}

          <p className="mt-6 text-center text-xs text-gray-500">
            Don&apos;t have an account?{' '}
            <Link href="/signup" className="font-semibold text-amber-500 hover:text-amber-400">Create one</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
