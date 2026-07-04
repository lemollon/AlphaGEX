'use client'

import { useState } from 'react'
import type { CustomerState } from '@/lib/live/types'

export default function PauseTradingPanel({
  state,
  pending,
  onToggle,
}: {
  state: CustomerState | null
  pending: boolean
  onToggle: (nextPaused: boolean, password: string) => Promise<void>
}) {
  const [confirming, setConfirming] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const paused = state?.paused ?? false
  const showResume = paused && (state?.can_resume ?? false)
  const disabled = pending || !state || (paused && !state.can_resume)

  async function handleConfirm() {
    if (!password) {
      setError('Enter the trading password to continue.')
      return
    }
    setError(null)
    try {
      await onToggle(!paused, password)
      setConfirming(false)
      setPassword('')
    } catch (e: unknown) {
      setError(
        e instanceof Error && e.message === 'password_required'
          ? 'Incorrect password.'
          : "That didn't go through — please try again.",
      )
    }
  }

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      {!confirming ? (
        <button
          onClick={() => { setError(null); setConfirming(true) }}
          disabled={disabled}
          className={`flex w-full items-center justify-center gap-2 rounded-lg py-3 font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
            showResume
              ? 'bg-emerald-600 hover:bg-emerald-500'
              : 'bg-spark hover:bg-spark-dark'
          }`}
        >
          {showResume ? (
            <>
              <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
                <path d="M8 5v14l11-7z" />
              </svg>
              Resume Trading
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
                <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
              </svg>
              Pause Trading
            </>
          )}
        </button>
      ) : (
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleConfirm() }}
            placeholder="Trading password"
            autoFocus
            className="flex-1 rounded-lg border border-forge-border bg-forge-bg px-3 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-spark"
          />
          <button
            onClick={handleConfirm}
            disabled={pending}
            className={`rounded-lg px-5 py-3 font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              showResume ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-spark hover:bg-spark-dark'
            }`}
          >
            {pending
              ? (showResume ? 'Resuming…' : 'Pausing…')
              : (showResume ? 'Confirm Resume' : 'Confirm Pause')}
          </button>
          <button
            onClick={() => { setConfirming(false); setPassword(''); setError(null) }}
            disabled={pending}
            className="rounded-lg border border-forge-border px-5 py-3 text-sm text-gray-400 transition-colors hover:text-white"
          >
            Cancel
          </button>
        </div>
      )}
      <p className="mt-3 text-center text-xs leading-relaxed text-gray-500">
        {paused
          ? 'Trading is paused — Spark will not open new trades. Current positions continue to be managed safely.'
          : 'Pausing prevents Spark from opening new trades. Current positions will continue to be managed safely.'}
      </p>
      {error && (
        <p className="mt-1 text-center text-xs text-red-400">{error}</p>
      )}
    </section>
  )
}
