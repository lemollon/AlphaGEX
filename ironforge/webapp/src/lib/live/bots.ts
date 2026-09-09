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

export const LIVE_BOTS = ['spark', 'flame'] as const
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

/**
 * 🚨 SPARK IS PAPER (2026-08-28). It was declared 'production' here long after it
 * stopped having a production account, and the two facts drifted apart silently:
 *
 *   - `describeLiveGate('spark')` returns the constant `'spark_is_paper_only'`.
 *   - `/api/health` on ironforge-customer reports `live_accounts.spark: 0` —
 *     `resolveEligibleAccounts('spark')` reaches zero real accounts, because the
 *     one `ironforge_accounts` production row for SPARK (`Logan[production]`,
 *     bot='SPARK,INFERNO') was deactivated on 2026-08-23 as a dead key.
 *
 * Declaring it 'production' sent the customer read down the production branch of
 * `scopeFilter`, which resolves to an inactive $5,000 row with zero trades — or,
 * for a customer with no `person` mapping, to `AND FALSE` and the "isn't connected
 * to your account yet" empty state. Either way SPARK's REAL book (the paper
 * ledger the scanner actually writes) was unreachable on ironforge.trade.
 *
 * It also suppressed the Paper badge on a simulated bot, which is the dangerous
 * direction of the PAPER_DISCLOSURE rule above: a paper bot rendered as real money.
 *
 * If SPARK is ever given a live account again, flip this back in the SAME commit
 * that activates the account row — `live-bots.test.ts` pins this declaration
 * against `describeLiveGate` so the two cannot drift apart silently a second time.
 */
export const LIVE_BOT_MODE: Record<LiveBot, LiveAccountMode> = {
  spark: 'paper',
  flame: 'paper',
}

/** Customer-facing agent name (drives hero copy, pause text, disclosures). */
export const LIVE_BOT_LABEL: Record<LiveBot, string> = {
  spark: 'Spark',
  flame: 'Flame',
}

/** Toggle-pill label. */
export const LIVE_BOT_PILL: Record<LiveBot, string> = {
  spark: 'SPARK',
  flame: 'FLAME',
}

/**
 * Strategy accent token. Identity, NOT account mode — Flame stays orange
 * whether it is on paper or live money.
 */
export const LIVE_BOT_ACCENT: Record<LiveBot, 'flame' | 'spark'> = {
  spark: 'spark',
  flame: 'flame',
}

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
 */
export const LIVE_BOT_TAGLINE: Record<LiveBot, string> = {
  spark: botTagline('spark'),
  flame: botTagline('flame'),
}

/** Simulated-results disclosure, named for the bot it is shown against.
 *  More than one bot is on paper now, so this must never hardcode a name —
 *  a disclosure that says "Flame" on Flame paper's page but Spark is shown
 *  is a false statement about which account is simulated. */
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
