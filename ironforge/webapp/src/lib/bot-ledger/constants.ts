/**
 * Bot Ledger — shared constants.
 *
 * Pure module: no DB, no clock, no env. Safe to import from tests and from
 * client code that only needs the bot list or the locked copy.
 */

import { botTagline } from '@/lib/billing/plans'

export const LEDGER_BOTS = ['spark', 'flame'] as const
export type LedgerBot = (typeof LEDGER_BOTS)[number]

export function isLedgerBot(v: unknown): v is LedgerBot {
  return typeof v === 'string' && (LEDGER_BOTS as readonly string[]).includes(v)
}

/**
 * Formula version. Bumping this changes every snapshot_id prefix, which 409s
 * every in-flight cursor and forces clients to re-fetch. Bump it whenever the
 * projection or KPI math changes in a way that moves a published number.
 */
export const CALCULATION_VERSION = 1

/**
 * Display metadata.
 *
 * This comment used to claim the taglines "mirror LIVE_BOT_TAGLINE" — they did
 * not. They were a hand-copied snapshot, stale in BOTH slots ("Next-day" for
 * Spark, "Two-day" for Flame, neither true since the 2026-08-16 EBB change). A
 * comment asserting a sync that nothing enforces is worse than no comment: it
 * stops the next reader from checking. Both now derive from BOT_PLANS, which is
 * what LIVE_BOT_TAGLINE derives from too.
 */
export const LEDGER_BOT_NAME: Record<LedgerBot, string> = {
  spark: 'Spark',
  flame: 'Flame',
}

export const LEDGER_BOT_TAGLINE: Record<LedgerBot, string> = {
  spark: botTagline('spark'),
  flame: botTagline('flame'),
}

/**
 * Public execution badge.
 *
 * Both read 'paper', matching the position `src/lib/live/track-record.ts` has
 * held on the public track record since launch: IronForge is a paper system
 * (real Tradier market data, simulated execution — see ironforge/CLAUDE.md),
 * and presenting either record as real-money fills would overstate it. Calling
 * a record simulated can only understate it, which is the safe direction for a
 * public claim.
 */
export const LEDGER_EXECUTION_MODE: Record<LedgerBot, 'paper'> = {
  spark: 'paper',
  flame: 'paper',
}

/** Mascot art key: public/home/{key}-mascot-glow.png */
export const LEDGER_MASCOT: Record<LedgerBot, string> = {
  spark: '/home/spark-mascot-glow.png',
  flame: '/home/flame-mascot-glow.png',
}

/**
 * Public close dates render as the US market date. The rest of the app is on
 * America/Chicago; this is the one deliberate exception, because "market date"
 * in a trader-facing ledger is conventionally ET.
 *
 * Provably a no-op against real data: CT and ET calendar dates diverge only for
 * instants between 23:00 and 24:00 CT, and every IronForge close lands inside
 * the 08:30-15:00 CT session. `ledger.ts` counts any divergence into
 * data_quality.tz_date_divergences so the assumption is monitored, not assumed.
 */
export const PUBLIC_DATE_TZ = 'America/New_York'

/** Snapshot bucket. Matches the route's Cache-Control max-age. */
export const SNAPSHOT_BUCKET_MS = 300_000
/** How long a client may keep paginating against an older snapshot. */
export const SNAPSHOT_TTL_MS = 900_000

export const DEFAULT_TRADE_LIMIT = 20
export const MAX_TRADE_LIMIT = 100

/**
 * Salt for the opaque public_id. A constant, not an env var: public_id must be
 * stable across deploys and reproducible in tests, and it carries no security
 * requirement — it exists only so we don't publish the monotonic internal id,
 * which would leak row counts and insertion order.
 */
export const PUBLIC_ID_SALT = 'ironforge.bot-ledger.v1'

export type LedgerPeriod = '7d' | '30d'
export const LEDGER_PERIODS: readonly LedgerPeriod[] = ['7d', '30d'] as const
export const PERIOD_DAYS: Record<LedgerPeriod, number> = { '7d': 7, '30d': 30 }

export type LedgerBotFilter = 'all' | LedgerBot
export const LEDGER_BOT_FILTERS: readonly LedgerBotFilter[] = ['all', 'spark', 'flame'] as const

/**
 * Results are GROSS of commissions and exchange fees.
 *
 * IronForge stores no fee or commission data on any position row, so any fee
 * figure here would be a model, not a measurement. Rather than publish an
 * assumption as a record, the page states the basis plainly. `net_basis` ships
 * in the API payload so a consumer can never mistake these for net-of-cost.
 */
export const NET_BASIS = 'gross_of_commissions' as const
