'use client'

import { useState, useEffect, type ReactNode } from 'react'

const STORAGE_KEY = 'ironforge_accounts_unlocked'

/**
 * Client-side password gate. Prompts for a password before rendering children.
 * Stores unlock state in sessionStorage (cleared when browser tab closes).
 *
 * Set NEXT_PUBLIC_ACCOUNTS_PASSWORD env var to the required password.
 * If the env var is not set, the gate is disabled (always shows content).
 */
export default function PasswordGate({ children }: { children: ReactNode }) {
  const requiredPassword = process.env.NEXT_PUBLIC_ACCOUNTS_PASSWORD || ''
  const [unlocked, setUnlocked] = useState(false)
  const [input, setInput] = useState('')
  const [error, setError] = useState(false)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    // If no password configured, skip the gate
    if (!requiredPassword) {
      setUnlocked(true)
      setChecking(false)
      return
    }
    // Check if already unlocked this session
    if (sessionStorage.getItem(STORAGE_KEY) === 'true') {
      setUnlocked(true)
    }
    setChecking(false)
  }, [requiredPassword])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (input === requiredPassword) {
      sessionStorage.setItem(STORAGE_KEY, 'true')
      setUnlocked(true)
      setError(false)
    } else {
      setError(true)
      setInput('')
    }
  }

  if (checking) return null

  if (unlocked) return <>{children}</>

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <div className="rounded-xl border border-forge-border bg-forge-card p-8 space-y-5">
          <div className="text-center">
            <div className="text-2xl mb-1">&#128274;</div>
            <h2 className="text-lg font-semibold text-white">Accounts Protected</h2>
            <p className="text-sm text-forge-muted mt-1">
              Enter password to access sandbox accounts.
            </p>
          </div>

          <div>
            <input
              type="password"
              value={input}
              onChange={(e) => { setInput(e.target.value); setError(false) }}
              placeholder="Password"
              autoFocus
              className={`w-full bg-forge-bg border rounded px-4 py-2.5 text-sm text-white placeholder-forge-muted focus:outline-none focus:ring-1 ${
                error
                  ? 'border-red-500 focus:ring-red-500'
                  : 'border-forge-border focus:ring-amber-500'
              }`}
            />
            {error && (
              <p className="text-xs text-red-400 mt-1.5">Incorrect password. Try again.</p>
            )}
          </div>

          <button
            type="submit"
            className="w-full py-2.5 text-sm font-medium bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
          >
            Unlock
          </button>
        </div>
      </form>
    </div>
  )
}
