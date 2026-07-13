'use client'

import { Suspense, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Wordmark } from '@/components/Brand'
import HomeLink from '@/components/HomeLink'
import { checkPassword } from '@/lib/signup-validation'

const RULE_LABELS: { key: keyof ReturnType<typeof checkPassword>['rules']; label: string }[] = [
  { key: 'minLength', label: 'At least 12 characters' },
  { key: 'upper', label: 'An uppercase letter' },
  { key: 'lower', label: 'A lowercase letter' },
  { key: 'number', label: 'A number' },
  { key: 'special', label: 'A special character' },
]

function ResetInner() {
  const params = useSearchParams()
  const token = params.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const check = useMemo(() => checkPassword(password), [password])
  const canSubmit = !!token && check.valid && password === confirm && !busy

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password, confirmPassword: confirm }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok) {
        setDone(true)
      } else {
        setError(data.error || 'Could not reset your password.')
        setBusy(false)
      }
    } catch {
      setError('Network error. Please try again.')
      setBusy(false)
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
          {done ? (
            <>
              <h1 className="text-xl font-bold text-white">Password updated</h1>
              <p className="mt-2 text-sm text-gray-400">Your password has been reset. You can now sign in.</p>
              <p className="mt-6 text-center text-xs text-gray-500">
                <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">Go to sign in</Link>
              </p>
            </>
          ) : !token ? (
            <>
              <h1 className="text-xl font-bold text-white">Invalid reset link</h1>
              <p className="mt-2 text-sm text-gray-400">This link is missing its token. Request a new one.</p>
              <p className="mt-6 text-center text-xs text-gray-500">
                <Link href="/forgot-password" className="font-semibold text-amber-500 hover:text-amber-400">Request a reset link</Link>
              </p>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-bold text-white">Choose a new password</h1>
              <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
                <div>
                  <label htmlFor="password" className="block text-xs text-gray-400">New password</label>
                  <input
                    id="password" type="password" autoComplete="new-password" autoFocus required
                    value={password} onChange={(e) => setPassword(e.target.value)}
                    className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                  />
                </div>
                <ul className="space-y-1">
                  {RULE_LABELS.map((r) => (
                    <li key={r.key} className={`text-xs ${check.rules[r.key] ? 'text-gray-300' : 'text-gray-500'}`}>
                      {check.rules[r.key] ? '✓' : '○'} {r.label}
                    </li>
                  ))}
                </ul>
                <div>
                  <label htmlFor="confirm" className="block text-xs text-gray-400">Confirm password</label>
                  <input
                    id="confirm" type="password" autoComplete="new-password" required
                    value={confirm} onChange={(e) => setConfirm(e.target.value)}
                    className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                  />
                </div>
                {error && (
                  <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
                )}
                <button
                  type="submit" disabled={!canSubmit}
                  className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? 'Updating…' : 'Update password'}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ResetPasswordPage() {
  // useSearchParams requires a Suspense boundary in the App Router.
  return (
    <Suspense fallback={<div className="min-h-screen bg-forge-bg" />}>
      <ResetInner />
    </Suspense>
  )
}
