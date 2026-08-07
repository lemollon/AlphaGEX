import { dbQuery, botTable, num } from '@/lib/db'

/** Fallback when a scope matches no active paper_account row at all. */
export const DEFAULT_STARTING_CAPITAL = 10000

/**
 * The starting-capital BASIS for a scoped view of a bot's paper accounts.
 *
 * WHY THIS EXISTS (2026-08-06). Three read routes each derived the basis their
 * own way from the same table, and they disagreed:
 *
 *   /status            SELECT starting_capital ... ORDER BY id DESC LIMIT 1  → $2,000
 *   /equity-curve      SELECT starting_capital ... LIMIT 1  (no ORDER BY)    → $10,000
 *   /equity-curve/intraday   same unordered LIMIT 1                          → $10,000
 *
 * So SPARK's production view reported balance $1,298.75 on one endpoint and
 * $9,298.75 on another off an identical −$701.25 of realized P&L. An unordered
 * LIMIT 1 is not even stable across queries — Postgres may return any row.
 *
 * Worse, every one of those routes SUMS realized_pnl across ALL rows in scope
 * while taking the basis from exactly ONE of them. With no `account_type`
 * filter, SPARK's unscoped curve summed the production book (28 trades) and the
 * sandbox book (3 trades, including a −$10,500 loss sized off a $63,100
 * account) onto a single $10,000 base and plotted the result going negative.
 *
 * The invariant this restores: **the basis must cover the same population as
 * the P&L.** So sum `starting_capital` over every active account in scope. When
 * the scope pins a single account the sum IS that account — behaviour is
 * unchanged for every single-account view. When the scope spans several, the
 * base now grows with the P&L instead of being one arbitrary row's.
 *
 * This mirrors the precedent already set in the intraday route, which sums
 * `balance` across account streams for exactly this reason.
 *
 * @param bot     validated bot name
 * @param filters pre-escaped SQL predicates (dte / account_type / person),
 *                each already prefixed with `AND`
 */
export async function scopedStartingCapital(
  bot: string,
  filters: string,
): Promise<{ startingCapital: number; accountCount: number }> {
  const rows = await dbQuery(
    `SELECT COALESCE(SUM(starting_capital), 0) AS starting_capital,
            COUNT(*) AS account_count
     FROM ${botTable(bot, 'paper_account')}
     WHERE is_active = TRUE ${filters}`,
  )
  const total = num(rows[0]?.starting_capital)
  const accountCount = num(rows[0]?.account_count)
  // A zero/absent sum means no active account matched the scope — fall back to
  // the historical default rather than plotting a curve against a $0 base.
  return {
    startingCapital: accountCount > 0 && total > 0 ? total : DEFAULT_STARTING_CAPITAL,
    accountCount,
  }
}
