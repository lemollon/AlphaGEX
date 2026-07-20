'use client'

import { useEffect, useState } from 'react'
import type { CustomerState, LiveSummary } from '@/lib/live/types'
import { getCTMinutes } from '@/lib/pt-tiers'
import { LIVE_BOT_ACCENT, type LiveBot } from '@/lib/live/bots'
import SparkMascot from './SparkMascot'

const DOT_CLASS: Record<CustomerState['dot'], string> = {
  green: 'bg-emerald-400',
  blue: 'bg-spark animate-pulse',
  amber: 'bg-amber-400',
  red: 'bg-red-400',
  gray: 'bg-gray-500',
}

function closesInLabel(closesAtMin: number): string | null {
  const remaining = closesAtMin - getCTMinutes()
  if (remaining <= 0) return null
  const h = Math.floor(remaining / 60)
  const m = remaining % 60
  return h > 0 ? `Closes in ${h}h ${m}m` : `Closes in ${m}m`
}

export default function SparkHeroCard({
  state,
  market,
  bot = 'spark',
}: {
  state: CustomerState | null
  market: LiveSummary['market'] | null
  /** Active strategy — drives the mascot (orange Flame vs animated blue Spark). */
  bot?: LiveBot
}) {
  const accent = LIVE_BOT_ACCENT[bot] // 'flame' | 'spark' — identity, not mode
  // Re-derive the countdown each minute without refetching.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex flex-1 items-center gap-4">
          <div className={`flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-forge-bg ring-1 sm:h-24 sm:w-24 ${
            accent === 'flame' ? 'ring-flame/25' : 'ring-spark/25'
          }`}>
            <SparkMascot className="h-full w-full rounded-2xl mix-blend-screen" variant={accent} />
          </div>
          <div>
            {state ? (
              <>
                <div className="flex items-center gap-2.5">
                  <h2 className="text-xl font-semibold text-white sm:text-2xl">{state.headline}</h2>
                  <span className={`h-2.5 w-2.5 rounded-full ${DOT_CLASS[state.dot]}`} />
                </div>
                <p className="mt-1 text-sm text-gray-400">{state.subtitle}</p>
                {state.check_line && (
                  <p className="mt-2 flex items-center gap-1.5 text-sm text-gray-300">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                      strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 text-spark">
                      <circle cx="12" cy="12" r="10" />
                      <path d="m9 12 2 2 4-4" />
                    </svg>
                    {state.check_line}
                  </p>
                )}
              </>
            ) : (
              <div className="h-16 w-64 animate-pulse rounded-lg bg-forge-border/50" />
            )}
          </div>
        </div>
        {market && (
          <div className="flex shrink-0 flex-row items-center gap-3 sm:flex-col sm:items-end sm:gap-1.5">
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                market.open
                  ? 'border border-emerald-500/30 bg-emerald-500/15 text-emerald-400'
                  : 'border border-forge-border bg-forge-border/40 text-gray-400'
              }`}
            >
              {market.label}
            </span>
            <span className="text-sm text-gray-400">
              {market.open && market.closes_at_min != null
                ? closesInLabel(market.closes_at_min)
                : market.next_open_label}
            </span>
          </div>
        )}
      </div>
    </section>
  )
}
