'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function ChangePasswordPage() {
  const router = useRouter()
  const [currentPassword, setCurrent] = useState('')
  const [newPassword, setNew] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (newPassword !== confirm) {
      setError('New passwords do not match')
      return
    }
    if (newPassword.length < 12) {
      setError('New password must be at least 12 characters')
      return
    }
    setBusy(true)
    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ currentPassword, newPassword }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data.error || 'Could not change password')
        return
      }
      router.push('/')
      router.refresh()
    } catch {
      setError('Network error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-24">
      <form onSubmit={onSubmit} className="bg-forge-card border border-amber-900/30 rounded-lg p-6 space-y-4">
        <h1 className="text-lg font-semibold text-gray-100">Change password</h1>
        <div className="space-y-1">
          <label htmlFor="current" className="block text-xs text-gray-400">Current password</label>
          <input id="current" type="password" autoComplete="current-password"
            value={currentPassword} onChange={(e) => setCurrent(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500" />
        </div>
        <div className="space-y-1">
          <label htmlFor="new" className="block text-xs text-gray-400">New password (min 12 chars)</label>
          <input id="new" type="password" autoComplete="new-password"
            value={newPassword} onChange={(e) => setNew(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500" />
        </div>
        <div className="space-y-1">
          <label htmlFor="confirm" className="block text-xs text-gray-400">Confirm new password</label>
          <input id="confirm" type="password" autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500" />
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={busy}
          className="w-full rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-black font-medium py-2 text-sm transition-colors">
          {busy ? 'Saving…' : 'Update password'}
        </button>
      </form>
    </div>
  )
}
