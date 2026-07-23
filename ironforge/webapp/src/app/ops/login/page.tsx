'use client'

import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Wordmark } from '@/components/Brand'

function LoginForm() {
  const router = useRouter()
  const params = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data.error || 'Login failed')
        return
      }
      if (data.mustChangePassword) {
        router.push('/change-password')
        return
      }
      router.push(params.get('next') || '/')
      router.refresh()
    } catch {
      setError('Network error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-24">
      <div className="flex items-center justify-center mb-6">
        <Wordmark markClass="h-8 w-auto" textClass="text-2xl" />
      </div>
      {params.get('verified') === '1' && (
        <p className="mb-4 rounded border border-amber-700/40 bg-amber-950/30 px-3 py-2 text-center text-sm text-amber-300">
          Email verified — you can sign in now.
        </p>
      )}
      {params.get('verifyError') === '1' && (
        <p className="mb-4 rounded border border-red-700/40 bg-red-950/30 px-3 py-2 text-center text-sm text-red-300">
          That verification link is invalid or has expired. Please request a new one.
        </p>
      )}
      <form onSubmit={onSubmit} className="bg-forge-card border border-amber-900/30 rounded-lg p-6 space-y-4">
        <h1 className="text-lg font-semibold text-gray-100">Sign in</h1>
        <div className="space-y-1">
          <label htmlFor="username" className="block text-xs text-gray-400">Username</label>
          <input
            id="username" name="username" autoComplete="username" autoFocus
            value={username} onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="password" className="block text-xs text-gray-400">Password</label>
          <input
            id="password" name="password" type="password" autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500"
          />
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit" disabled={busy}
          className="w-full rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-black font-medium py-2 text-sm transition-colors"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        Don&apos;t have an account?{' '}
        <a href="/signup" className="font-semibold text-amber-500 hover:text-amber-400">Create account</a>
      </p>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  )
}
