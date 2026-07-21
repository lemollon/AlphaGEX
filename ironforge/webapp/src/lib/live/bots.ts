/**
 * Live-page bot registry — pure constants, no server imports.
 *
 * This module is imported by BOTH client components and server code, so it must
 * stay free of `next/server`, the DB client, and auth. `viewer.ts` re-exports
 * everything here so existing server-side imports keep working.
 */

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
  // SPARK2 stays 'production' — the account holds real money (7/16 first trade
  // moved option BP $2,000 -> $1,526.64). Briefly flipped to 'paper' on 7/21;
  // that made the page read the stale ex-KINDLE $500 sandbox seed and render
  // $500 - $208 = $292. Reverted. Don't flip it without fixing that seed first.
  spark2: 'production',
  flame: 'paper',
}

/** Customer-facing agent name (drives hero copy, pause text, disclosures).
 *  spark2 is "Spark 2", not "Spark" — otherwise the two live accounts render as
 *  two identical "Spark" rows in the strategy rail and on Performance. */
export const LIVE_BOT_LABEL: Record<LiveBot, string> = {
  spark: 'Spark',
  spark2: 'Spark 2',
  flame: 'Flame',
}

/** Toggle-pill label — distinguishes the two SPARK accounts. */
export const LIVE_BOT_PILL: Record<LiveBot, string> = {
  spark: 'SPARK',
  spark2: 'SPARK2',
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

/** Strategy one-liner shown under the hero headline. */
export const LIVE_BOT_TAGLINE: Record<LiveBot, string> = {
  spark: 'Next-day SPY spreads',
  spark2: 'Next-day SPY spreads',
  flame: 'Two-day SPY put credit spreads',
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
