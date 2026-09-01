'use client'

import type { LiveSummary } from '@/lib/live/types'
import type { AccentTheme } from './accent'

/**
 * "Live gate/health activity feed" — a short list of today's scan activity so
 * the page feels alive even on a 0-trade day. Every `entry.label` is already
 * a curated plain-English string (see lib/live/activityFeed.ts) — this
 * component renders it as plain text and nothing else; the raw internal
 * `reason` string never reaches this component at all.
 *
 * Renders nothing when activityFeed is null (the underlying query failed —
 * an honest empty card beats a fabricated one on a real-money page). An
 * empty `entries` array IS a real, renderable state ("no scans yet today").
 */

const DOT_CLASS: Record<'gate' | 'lifecycle' | 'neutral', string> = {
  gate: 'bg-amber-400',
  lifecycle: 'bg-emerald-400',
  neutral: 'bg-gray-500',
}

export default function ActivityFeedCard({
  activityFeed,
  accent,
}: {
  activityFeed: LiveSummary['activity_feed']
  accent: AccentTheme
}) {
  if (!activityFeed) return null
  const { scans_today: scansToday, gates_held_today: gatesHeldToday, entries } = activityFeed

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className={`text-xs font-semibold uppercase tracking-widest ${accent.text}`}>
        Today&apos;s Activity
      </h3>
      <p className="mt-2 text-sm text-gray-300">
        <span className="font-semibold text-white">
          {scansToday} scan{scansToday === 1 ? '' : 's'}
        </span>{' '}
        today
        {gatesHeldToday > 0 && (
          <> &middot; {gatesHeldToday} gate{gatesHeldToday === 1 ? '' : 's'} held</>
        )}
      </p>
      {entries.length === 0 ? (
        <p className="mt-3 text-sm text-gray-500">No activity yet today.</p>
      ) : (
        <ul className="mt-3 max-h-[168px] space-y-2 overflow-y-auto pr-1">
          {entries.map((entry, i) => (
            <li
              key={i}
              className="flex items-baseline gap-2 border-b border-forge-border/60 pb-2 text-sm last:border-b-0 last:pb-0"
            >
              <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${DOT_CLASS[entry.kind]}`} />
              <span className="w-[92px] shrink-0 font-mono text-xs text-gray-500">{entry.timeLabel}</span>
              <span className="text-gray-300">{entry.label}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
