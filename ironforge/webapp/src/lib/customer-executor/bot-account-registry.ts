/**
 * Registry of Tradier account NUMBERS the bots already trade directly — the input
 * list for the bot-account-guard (6YB71371 double-trade guard).
 *
 * Env-sourced, not DB-sourced. SPARK's production account lives only as a row in the
 * `ironforge_accounts` table on the BOT database (@/lib/db) — a separate Postgres
 * instance from customers-db.ts, which the customer-executor has no connection to
 * today. Reading it live on every mirror cycle would add a new cross-database
 * dependency for a value that changes only when an operator provisions an account.
 *
 * This is not a gap for the account this guard exists to protect: SPARK and FLAME
 * are on record (tradier.ts) as sharing the SAME physical Tradier account —
 * "SPARK is allowlisted on production account 6YB71371 ... and FLAME is about to
 * gain a live order path on that SAME account" — so TRADIER_FLAME_ACCOUNT_ID's
 * value alone already covers 6YB71371 regardless of which bot's credentials are
 * "for". Any FUTURE bot-traded account that is Tradier-side only (no env var, only
 * an ironforge_accounts row, e.g. a brand-new production person) will not be
 * covered until either (a) a matching env var is added below, or (b) it is listed
 * in BOT_TRADED_TRADIER_ACCOUNT_IDS.
 *
 * Sandbox (User/Matt/Logan) accounts are Tradier's own fake-money sandbox
 * environment; their account numbers are resolved dynamically from Tradier's API
 * and never appear in env or here. They are not a double-trade risk for THIS guard
 * because a customer's real SnapTrade/Tradier-OAuth brokerage account can never be
 * the same physical account as one of Tradier's own sandbox test accounts — they
 * live in different environments with disjoint account pools.
 */
export function getKnownBotTradedTradierAccountNumbers(): string[] {
  const ids = [
    process.env.TRADIER_FLAME_ACCOUNT_ID,
    process.env.TRADIER_KINDLE_ACCOUNT_ID,
    process.env.TRADIER_PROD_ACCOUNT_ID,
    process.env.TRADIER_SANDBOX_ACCOUNT_ID,
    ...(process.env.BOT_TRADED_TRADIER_ACCOUNT_IDS ?? '').split(','),
  ]
  return ids.map((s) => (s ?? '').trim()).filter((s) => s.length > 0)
}
