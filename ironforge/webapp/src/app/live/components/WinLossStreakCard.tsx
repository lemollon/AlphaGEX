'use client'

import type { LiveSummary } from '@/lib/live/types'
import type { AccentTheme } from './accent'

/**
 * Last 10 closed trades as win/loss chips, a wins/losses summary, and the
 * CURRENT streak — win OR losing. A losing streak must render exactly as
 * plainly as a winning one: same size, same weight, no color that buries bad
 * news. The "not a guarantee of future performance" disclosure always
 * accompanies the numbers, at the same visual weight (matches the
 * backtest-envelope disclosure in LiveTradeCard.tsx).
 *
 * Renders nothing when `streak` is null (the underlying query failed).
 */
export default function WinLossStreakCard({
  streak,
  accent,
}: {
  streak: LiveSummary['win_loss_streak']
  accent: AccentTheme
}) {
  if (!streak) return null
  const { trades, winsCount, lossesCount, currentStreak } = streak

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className={`text-xs font-semibold uppercase tracking-widest ${accent.text}`}>
        Recent Results
      </h3>
      {trades.length === 0 ? (
        <p className="mt-3 text-sm text-gray-500">No trades closed yet.</p>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {trades.map((t, i) => (
              <span
                key={i}
                className={`flex h-7 w-7 items-center justify-center rounded text-xs font-bold ${
                  t === 'win' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                }`}
              >
                {t === 'win' ? 'W' : 'L'}
              </span>
            ))}
          </div>
          <p className="mt-3 text-sm text-gray-300">
            Last {trades.length} trade{trades.length === 1 ? '' : 's'}: {winsCount} win{winsCount === 1 ? '' : 's'},{' '}
            {lossesCount} loss{lossesCount === 1 ? '' : 'es'}
          </p>
          {currentStreak && (
            <p className="mt-1 text-sm text-gray-300">
              Currently on a {currentStreak.count}-trade {currentStreak.type === 'win' ? 'win' : 'losing'} streak.
            </p>
          )}
          {/* Same visual weight as the numbers above it — never a footnote,
              matches LiveTradeCard's backtest-envelope disclosure. */}
          <p className="mt-3 font-semibold text-amber-400">
            Past results are not a guarantee of future performance — every trade carries the same risk of loss.
          </p>
        </>
      )}
    </section>
  )
}
