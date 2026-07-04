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
  onToggle: (nextPaused: boolean) => Promise<void>
}) {
  const [failed, setFailed] = useState(false)
  const paused = state?.paused ?? false
  const showResume = paused && (state?.can_resume ?? false)
  const disabled = pending || !state || (paused && !state.can_resume)

  async function handleClick() {
    setFailed(false)
    try {
      await onToggle(!paused)
    } catch {
      setFailed(true)
    }
  }

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <button
        onClick={handleClick}
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
            {pending ? 'Resuming…' : 'Resume Trading'}
          </>
        ) : (
          <>
            <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
              <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
            </svg>
            {pending ? 'Pausing…' : 'Pause Trading'}
          </>
        )}
      </button>
      <p className="mt-3 text-center text-xs leading-relaxed text-gray-500">
        {paused
          ? 'Trading is paused — Spark will not open new trades. Current positions continue to be managed safely.'
          : 'Pausing prevents Spark from opening new trades. Current positions will continue to be managed safely.'}
      </p>
      {failed && (
        <p className="mt-1 text-center text-xs text-red-400">
          That didn&apos;t go through — please try again.
        </p>
      )}
    </section>
  )
}
