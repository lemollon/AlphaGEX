'use client'

import { useState } from 'react'
import type { CustomerState } from '@/lib/live/types'
import type { AccentTheme } from './accent'

/**
 * Pause / Resume control for a customer's own live bot.
 *
 * No password field. `/api/{bot}/production-pause` authorizes an owner by
 * SESSION + BOT OWNERSHIP *before* it ever looks at `password`, so for the
 * person this panel is rendered to, any value typed here was accepted — the
 * input implied a per-customer secret that does not exist. The shared-password
 * branch still exists in the route as the legacy operator fallback; it is just
 * not something a customer should be prompted for.
 *
 * The caller is responsible for not rendering this on a paper account: the
 * route answers 400 for any non-production bot, which surfaced as a generic
 * failure when a Flame/Spark-paper owner pressed the button.
 */
export default function PauseTradingPanel({
  state,
  pending,
  onToggle,
  accent,
  botLabel,
}: {
  state: CustomerState | null
  pending: boolean
  onToggle: (nextPaused: boolean) => Promise<void>
  accent: AccentTheme
  /** Customer-facing agent name, e.g. "Spark" — the copy used to hardcode it. */
  botLabel: string
}) {
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const paused = state?.paused ?? false
  const showResume = paused && (state?.can_resume ?? false)
  const disabled = pending || !state || (paused && !state.can_resume)

  async function handleConfirm() {
    setError(null)
    try {
      await onToggle(!paused)
      setConfirming(false)
    } catch {
      setError("That didn't go through — please try again.")
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
              : accent.button
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
          <p className="flex-1 self-center text-sm text-gray-300">
            {showResume
              ? `Resume ${botLabel} and allow new trades?`
              : `Pause ${botLabel} and stop new trades?`}
          </p>
          <button
            onClick={handleConfirm}
            disabled={pending}
            autoFocus
            className={`rounded-lg px-5 py-3 font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              showResume ? 'bg-emerald-600 hover:bg-emerald-500' : accent.button
            }`}
          >
            {pending
              ? (showResume ? 'Resuming…' : 'Pausing…')
              : (showResume ? 'Confirm Resume' : 'Confirm Pause')}
          </button>
          <button
            onClick={() => { setConfirming(false); setError(null) }}
            disabled={pending}
            className="rounded-lg border border-forge-border px-5 py-3 text-sm text-gray-400 transition-colors hover:text-white"
          >
            Cancel
          </button>
        </div>
      )}
      <p className="mt-3 text-center text-xs leading-relaxed text-gray-500">
        {paused
          ? `Trading is paused — ${botLabel} will not open new trades. Current positions continue to be managed safely.`
          : `Pausing prevents ${botLabel} from opening new trades. Current positions will continue to be managed safely.`}
      </p>
      {error && (
        <p className="mt-1 text-center text-xs text-red-400">{error}</p>
      )}
    </section>
  )
}
