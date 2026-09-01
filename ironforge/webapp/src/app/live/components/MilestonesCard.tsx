'use client'

import type { LiveSummary } from '@/lib/live/types'
import type { AccentTheme } from './accent'

/**
 * Non-P&L tenure/system-health badges: "N days connected", "N scans
 * completed", "Month N live". Deliberately NOT performance-based — no dollar
 * amount, no win rate. Each pill is independent: an operator view might only
 * ever have `scanNumber` populated, and that must still render on its own.
 *
 * Renders nothing when `milestones` is null, or when all three fields are
 * null (nothing to show).
 */
export default function MilestonesCard({
  milestones,
  accent,
}: {
  milestones: LiveSummary['milestones']
  accent: AccentTheme
}) {
  if (!milestones) return null
  const { daysConnected, scanNumber, monthNumber } = milestones
  if (daysConnected == null && scanNumber == null && monthNumber == null) return null

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className={`text-xs font-semibold uppercase tracking-widest ${accent.text}`}>
        Milestones
      </h3>
      <div className="mt-3 flex flex-wrap gap-2">
        {daysConnected != null && (
          <span className="rounded-full border border-forge-border bg-white/5 px-3 py-1.5 text-xs text-gray-300">
            {daysConnected} day{daysConnected === 1 ? '' : 's'} connected
          </span>
        )}
        {scanNumber != null && (
          <span className="rounded-full border border-forge-border bg-white/5 px-3 py-1.5 text-xs text-gray-300">
            {scanNumber} scan{scanNumber === 1 ? '' : 's'} completed
          </span>
        )}
        {monthNumber != null && (
          <span className="rounded-full border border-forge-border bg-white/5 px-3 py-1.5 text-xs text-gray-300">
            Month {monthNumber} live
          </span>
        )}
      </div>
    </section>
  )
}
