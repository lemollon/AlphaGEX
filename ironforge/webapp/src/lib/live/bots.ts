/**
 * Live-page bot registry — pure constants, no server imports.
 *
 * This module is imported by BOTH client components and server code, so it must
 * stay free of `next/server`, the DB client, and auth. `viewer.ts` re-exports
 * everything here so existing server-side imports keep working.
 *
 * `billing/plans` is safe to import from here: it has no imports of its own and
 * touches neither the DB nor `next/server`.
 */
import { botTagline } from '@/lib/billing/plans'

export const LIVE_BOTS = ['spark', 'spark2', 'flame'] as const
export type LiveBot = (typeof LIVE_BOTS)[number]

/**
 * Which ledger a bot's Live page reads.
 *
 * 'production' — real money. Rows carry account_type='production'; account value
 *   comes from the Tradier broker balance.
 * 'paper'      — simulated. No broker account exists, so the page reads the
 *   non-production rows and derives value from the paper ledger.
 *
 * This drives the customer-facing "Paper" badge. A paper bot must NEVER render
 * as though it were real money — see PAPER_DISCLOSURE below.
 */
export type LiveAccountMode = 'production' | 'paper'

export const LIVE_BOT_MODE: Record<LiveBot, LiveAccountMode> = {
  spark: 'production',
  // SPARK2 is paper (operator, 2026-07-21). Its sandbox paper_account carried
  // the ex-KINDLE $500 seed, which is what made the first attempt at this render
  // $500 - $208 = $292; reseeded to the $10k house default at the same time.
  // Paper capital is arbitrary, so the seed is a choice, not a measurement.
  spark2: 'paper',
  flame: 'paper',
}

/** Customer-facing agent name (drives hero copy, pause text, disclosures).
 *  spark2 is "Spark paper", not "Spark" — otherwise the two accounts render as
 *  two identical "Spark" rows in the strategy rail and on Performance. */
export const LIVE_BOT_LABEL: Record<LiveBot, string> = {
  spark: 'Spark',
  spark2: 'Spark paper',
  flame: 'Flame',
}

/** Toggle-pill label — distinguishes the two SPARK accounts. */
export const LIVE_BOT_PILL: Record<LiveBot, string> = {
  spark: 'SPARK',
  spark2: 'SPARK PAPER',
  flame: 'FLAME',
}

/**
 * Strategy accent token. Identity, NOT account mode — Flame stays orange
 * whether it is on paper or live money.
 */
export const LIVE_BOT_ACCENT: Record<LiveBot, 'flame' | 'spark'> = {
  spark: 'spark',
  spark2: 'spark',
  flame: 'flame',
}

/** Strategy one-liner shown under the hero headline.
 *  Must describe the strategy the bot ACTUALLY runs: spark2 reports
 *  "0DTE Paper Iron Condor" (dte 0) from /api/spark2/status, but this said
 *  "Next-day SPY spreads" — SPARK's 1DTE line — so the customer page made a
 *  false statement about what Spark paper trades. */
/**
 * DERIVED for the two sellable bots, never typed here.
 *
 * These were literals, and they drifted. On 2026-08-16 Flame's was corrected
 * from "Two-day" to "Same-day" because `dteMode('flame')` had become '0DTE' —
 * but Spark's said "Next-day SPY spreads" and was left untouched, even though
 * `dteMode('spark')` changed to '0DTE' in the very same commit. That false line
 * was served on `/api/public/track-record` (unauthenticated) via
 * `track-record.ts`, telling anyone who asked that a customer's money was doing
 * something it was not.
 *
 * `botTagline()` reads `BOT_PLANS[...].structure`, the same field the checkout
 * blurb is composed from, so the sales page and the customer page cannot
 * disagree about the product again.
 *
 * SPARK2 stays a literal on purpose: it is an operator-side bot with no
 * BOT_PLANS entry, and it genuinely does run a different structure (1DTE iron
 * condors) — see `dteMode('spark2')`.
 */
export const LIVE_BOT_TAGLINE: Record<LiveBot, string> = {
  spark: botTagline('spark'),
  // dteMode('spark2') is '1DTE' — next-day expiry. This said "Same-day",
  // the same class of false statement as Spark's, on the same map.
  spark2: 'Next-day SPY iron condors',
  flame: botTagline('flame'),
}

/** Simulated-results disclosure, named for the bot it is shown against.
 *  More than one bot is on paper now, so this must never hardcode a name —
 *  a disclosure that says "Flame" on Spark paper's page is a false statement
 *  about which account is simulated. */
export function paperDisclosure(bot: LiveBot): string {
  return `Simulated results. ${LIVE_BOT_LABEL[bot]} is in paper trading — no real orders are placed and no real money is at risk.`
}

export function accountMode(bot: LiveBot): LiveAccountMode {
  return LIVE_BOT_MODE[bot]
}

export function isPaperBot(bot: LiveBot): boolean {
  return LIVE_BOT_MODE[bot] === 'paper'
}

export function isLiveBot(v: string | null | undefined): v is LiveBot {
  return v != null && (LIVE_BOTS as readonly string[]).includes(v)
}
