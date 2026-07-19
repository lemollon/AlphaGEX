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
  spark2: 'production',
  flame: 'paper',
}

/** Customer-facing agent name (drives hero copy, pause text, disclosures). */
export const LIVE_BOT_LABEL: Record<LiveBot, string> = {
  spark: 'Spark',
  spark2: 'Spark',
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

export const PAPER_DISCLOSURE =
  'Simulated results. Flame is in paper trading — no real orders are placed and no real money is at risk.'

export function accountMode(bot: LiveBot): LiveAccountMode {
  return LIVE_BOT_MODE[bot]
}

export function isPaperBot(bot: LiveBot): boolean {
  return LIVE_BOT_MODE[bot] === 'paper'
}

export function isLiveBot(v: string | null | undefined): v is LiveBot {
  return v != null && (LIVE_BOTS as readonly string[]).includes(v)
}
