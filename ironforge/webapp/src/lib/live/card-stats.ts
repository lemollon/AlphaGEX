import { num } from '@/lib/db'

/**
 * Forge agent-card stat row (handoff/ledger-kpis.md PART 2) — Account Capital,
 * Growth, Last 10, Best Trade, all LIFETIME (no filter), computed per bot for
 * GET /api/live/agents. Pure and DB-independent so it is unit-testable
 * without a live Postgres connection, same reasoning as computeTradesTotals
 * in trades-history.ts.
 */

export interface CardStats {
  account_capital_cents: number | null
  growth_pct: number | null
  last10: { wins: number; losses: number }
  best_trade_cents: number | null
}

/**
 * Lifetime return on starting capital, 2dp — the single definition every
 * consumer (Home wealth snapshot, Forge card stats) must share so the
 * percentage never drifts between screens. Lifted out of home.ts's
 * getHomeData, which computed this inline before this stat row existed.
 */
export function lifetimeReturnPct(totalRealizedPnl: number, startingCapital: number): number | null {
  return startingCapital > 0 ? Math.round((totalRealizedPnl / startingCapital) * 10000) / 100 : null
}

/**
 * `closedTradesDesc` must already be ordered newest-close-first (the same
 * order loadBotTrades' `ORDER BY close_time DESC` produces) — "Last 10" is
 * literally the first 10 of that list, not a re-sort here. `realized_pnl`
 * is accepted as `unknown` and parsed with `num()` because it may arrive as
 * a pg NUMERIC string or as an already-parsed number (loadBotTrades hands
 * back HistoryTrade.pnl, which is already a JS number).
 */
export function computeCardStats(
  startingCapital: number,
  totalRealizedPnl: number,
  closedTradesDesc: Array<{ realized_pnl: unknown }>,
): CardStats {
  const last10Trades = closedTradesDesc.slice(0, 10)
  const wins = last10Trades.reduce((a, t) => (num(t.realized_pnl) > 0 ? a + 1 : a), 0)
  const losses = last10Trades.length - wins

  // "Best Trade" reads as a win on the mock (+$122, green) — a bot whose
  // largest closed trade is still a loss has no "best trade" to show, so
  // that's an honest "—", not the least-bad loss dressed up as a profit.
  const winningPnls = closedTradesDesc.map((t) => num(t.realized_pnl)).filter((p) => p > 0)
  const bestTrade = winningPnls.length > 0 ? Math.max(...winningPnls) : null

  return {
    account_capital_cents: startingCapital > 0 ? Math.round(startingCapital * 100) : null,
    growth_pct: lifetimeReturnPct(totalRealizedPnl, startingCapital),
    last10: { wins, losses },
    best_trade_cents: bestTrade != null ? Math.round(bestTrade * 100) : null,
  }
}
