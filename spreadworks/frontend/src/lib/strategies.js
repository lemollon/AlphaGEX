/**
 * Single source of truth for strategy metadata.
 *
 * IMPORTANT: When adding a new strategy, update BOTH objects below.
 * The backend mirror lives in spreadworks/backend/routes.py (CREDIT_STRATEGIES, STRATEGY_LABELS).
 */

/** Short display labels shown in cards, modals, and badges. */
export const STRAT_LABELS = {
  double_diagonal: 'DD',
  double_calendar: 'DC',
  iron_condor: 'IC',
  butterfly: 'BF',
  iron_butterfly: 'IBF',
};

/**
 * Credit strategies receive cash at entry (entry_cost < 0, entry_price > 0).
 * Debit strategies pay cash at entry (entry_cost > 0, entry_price stored as |cost|).
 *
 * This distinction drives:
 *   - P&L formula sign (credit: entry-val, debit: -(val+entry))
 *   - Display labels ("Entry Credit" vs "Entry Debit")
 *   - Close modal wording
 *
 * The backend also returns `is_credit` on the /pnl response as a runtime check.
 */
export const CREDIT_STRATEGIES = new Set(['iron_condor', 'iron_butterfly']);

/** Helper — returns true if the strategy is a credit strategy. */
export function isCreditStrategy(strategy) {
  return CREDIT_STRATEGIES.has(strategy);
}
