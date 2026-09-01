/**
 * Win/Loss Streak — last N closed trades as win/loss chips, plus the CURRENT
 * streak (win OR losing). Both sides must always render honestly: a losing
 * streak is exactly as visible as a winning one, never suppressed or
 * de-emphasized. Every render of this data must carry the "not a guarantee
 * of future performance" disclosure at the same visual weight as the numbers
 * — see WinLossStreakCard.tsx.
 */

export const RECENT_TRADES_LIMIT = 10

export type TradeResult = 'win' | 'loss'

export interface StreakSummary {
  /** Oldest-first — the display order for the chip row (reads left-to-right
   *  like a timeline: left = oldest, right = most recent). */
  trades: TradeResult[]
  winsCount: number
  lossesCount: number
  currentStreak: { count: number; type: TradeResult } | null
}

/**
 * A trade with realized P&L of exactly $0.00 counts as a LOSS, not a win.
 * This is a deliberate conservative default (a scratch trade is not a win),
 * documented here so it reads as a choice, not an accident.
 */
export function classifyTrade(realizedPnl: number): TradeResult {
  return realizedPnl > 0 ? 'win' : 'loss'
}

/**
 * Pure, no DB access. `realizedPnls` is ordered NEWEST-FIRST (index 0 = most
 * recent closed trade) — matching `ORDER BY close_time DESC LIMIT
 * RECENT_TRADES_LIMIT`. The returned `trades` array is reversed to
 * OLDEST-FIRST for display.
 */
export function buildStreakSummary(realizedPnls: number[]): StreakSummary {
  if (realizedPnls.length === 0) {
    return { trades: [], winsCount: 0, lossesCount: 0, currentStreak: null }
  }

  const resultsNewestFirst = realizedPnls.map(classifyTrade)
  const trades = [...resultsNewestFirst].reverse()

  const winsCount = resultsNewestFirst.filter((r) => r === 'win').length
  const lossesCount = resultsNewestFirst.filter((r) => r === 'loss').length

  // Walk from the most recent trade (index 0 of the newest-first input, i.e.
  // the LAST element of `trades`) backward, counting consecutive identical
  // results until it changes or the input ends.
  const mostRecentType = resultsNewestFirst[0]
  let streakCount = 0
  for (const r of resultsNewestFirst) {
    if (r !== mostRecentType) break
    streakCount++
  }

  return {
    trades,
    winsCount,
    lossesCount,
    currentStreak: { count: streakCount, type: mostRecentType },
  }
}
