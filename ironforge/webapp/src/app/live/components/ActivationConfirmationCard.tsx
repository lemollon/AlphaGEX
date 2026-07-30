'use client'

import { useEffect, useRef } from 'react'
import type { LiveSummary } from '@/lib/live/types'
import SparkMascot from './SparkMascot'

/**
 * DASH-FIRST-01 — the first-entry activation confirmation (July 29 handoff).
 *
 * Temporarily takes the place of the top status card: "«Agent» is active", the
 * trial day counter, and the masked account. Renders exactly once per activation —
 * on mount it stamps the server (`confirmation-seen`), so the next visit shows the
 * normal runtime states. "Active" means authorization is enabled; it does not mean
 * an order is currently live, which is what the WAITING pill conveys.
 */
export default function ActivationConfirmationCard({
  confirmation,
}: {
  confirmation: NonNullable<LiveSummary['activation_confirmation']>
}) {
  const isSpark = confirmation.agent === 'spark'
  const agentName = isSpark ? 'Spark' : 'Flame'
  const accent = isSpark ? 'spark' : 'flame'

  // Stamp exactly once per mount; the IS NULL predicate server-side makes any
  // duplicate a no-op. The card keeps rendering for THIS visit — the stamp only
  // stops future visits from re-showing it.
  const stamped = useRef(false)
  useEffect(() => {
    if (stamped.current) return
    stamped.current = true
    fetch(`/api/v1/activations/${confirmation.activation_id}/confirmation-seen`, { method: 'POST' }).catch(() => {})
  }, [confirmation.activation_id])

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex flex-1 items-center gap-4">
          <div
            className={`flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-forge-bg ring-1 sm:h-24 sm:w-24 ${
              isSpark ? 'ring-spark/25' : 'ring-flame/25'
            }`}
          >
            <SparkMascot className="h-full w-full rounded-2xl mix-blend-screen" variant={accent} />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-xl font-semibold text-white sm:text-2xl">{agentName} is active</h2>
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
            </div>
            <p className="mt-1 text-sm text-gray-400">
              Your {confirmation.trial_total}-trading-day trial is active. {agentName} is waiting for the next
              eligible opportunity.
            </p>
            <p className="mt-2 flex items-center gap-1.5 text-sm text-gray-300">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`h-4 w-4 ${isSpark ? 'text-spark' : 'text-flame'}`}
              >
                <circle cx="12" cy="12" r="10" />
                <path d="m9 12 2 2 4-4" />
              </svg>
              Setup complete.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-row items-center gap-3 sm:flex-col sm:items-end sm:gap-1.5">
          <span
            className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wider ${
              isSpark ? 'border-spark/40 text-spark' : 'border-flame/40 text-flame'
            }`}
          >
            Waiting
          </span>
          <span className="text-sm text-gray-400">
            Trial day {confirmation.trial_day} of {confirmation.trial_total}
          </span>
          {confirmation.account_mask ? (
            <span className="font-mono text-sm text-gray-400">{confirmation.account_mask}</span>
          ) : null}
        </div>
      </div>
    </section>
  )
}
