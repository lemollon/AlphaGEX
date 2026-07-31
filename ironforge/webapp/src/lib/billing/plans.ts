/**
 * Bot plan catalogue — the single source of truth for what a customer can subscribe to and at
 * what price. The `lookupKey` matches the Stripe Price lookup key set up in the dashboard
 * (spark_monthly / flame_monthly / both_monthly), so checkout resolves the right Price without
 * hardcoding environment-specific price IDs. Colours/mascots drive the Open Account page theming
 * (Flame = brand orange, Spark = blue).
 */

export type BotSlug = 'spark' | 'flame'

export interface BotPlan {
  slug: BotSlug
  /** Short display name, e.g. "Flame". */
  name: string
  /** Stripe product-ish label, e.g. "IronForge Flame". */
  productName: string
  /** One-line description of what the bot does (mirrors the mockup subtitle). */
  blurb: string
  /** Monthly price in whole dollars. */
  priceMonthly: number
  /** Stripe Price lookup key. */
  lookupKey: string
  /** Brand accent hex for this bot. */
  accent: string
  /** Mascot glow image under /public. */
  mascot: string
  /** Path of the bot's live dashboard (post-subscribe landing). */
  liveHref: string
}

export const BOT_PLANS: Record<BotSlug, BotPlan> = {
  spark: {
    slug: 'spark',
    name: 'Spark',
    productName: 'IronForge Spark',
    // 1DTE — dteMode('spark') === '1DTE'. This said "0DTE", which is INFERNO's
    // expiry, not Spark's. Wording matches the canonical tagline used on /live,
    // /onboarding/complete and the Bot Ledger, and describes the mechanics rather
    // than promising an outcome.
    blurb: 'Set up a dedicated Spark account that trades next-day (1DTE) SPY spreads automatically.',
    priceMonthly: 50,
    lookupKey: 'spark_monthly',
    accent: '#2F80ED', // Spark blue
    mascot: '/home/spark-mascot-glow.png',
    liveHref: '/agents/spark',
  },
  flame: {
    slug: 'flame',
    name: 'Flame',
    productName: 'IronForge Flame',
    // 2DTE put credit spreads. "near-term upside trading" implied a directional
    // long — Flame sells premium. Matches the canonical tagline.
    blurb: 'Set up a dedicated Flame account that trades two-day (2DTE) SPY put credit spreads automatically.',
    priceMonthly: 50,
    lookupKey: 'flame_monthly',
    accent: '#FD5301', // Flame / brand orange
    mascot: '/home/flame-mascot-glow.png',
    liveHref: '/agents/flame',
  },
}

/** The two-bot bundle — offered as an upsell, priced below 2× a single bot. */
export const BOTH_PLAN = {
  lookupKey: 'both_monthly',
  priceMonthly: 75,
}

/**
 * Community — chat + education access, no trading bot. A standalone paid tier: someone can buy it
 * without a bot, and it's included implicitly for anyone who owns a bot. Tracked as a
 * customer_bot_subscriptions row with bot = COMMUNITY_KEY (the table's `bot` column is free-text).
 * No free trial — it's low-cost, immediate access.
 */
export const COMMUNITY_KEY = 'community'
export const COMMUNITY_PLAN = {
  key: COMMUNITY_KEY,
  name: 'Forge Community',
  lookupKey: 'community_monthly',
  // DISPLAY price. The amount actually charged comes from the Stripe price
  // behind lookupKey 'community_monthly' — if that is still set to 15, the site
  // will advertise $10 and bill $15. Change both together.
  priceMonthly: 10,
}
export function isCommunityKey(v: string | null | undefined): boolean {
  return v === COMMUNITY_KEY
}

/** The other customer bot — spark and flame are the only two, so a "second bot" is the complement. */
export function otherBotSlug(slug: BotSlug): BotSlug {
  return slug === 'spark' ? 'flame' : 'spark'
}

/**
 * What the SECOND bot adds per month. The bundle is one price ($75) covering both bots, so opening
 * a second bot is not another full $50 — it lifts a single-bot subscription to the bundle. The
 * increment is defined off the real prices so it can never drift from what Stripe bills:
 *   $75 (both) − $50 (single) = $25.
 * Used for the "add your second bot" copy on the Open Account page.
 */
export function secondBotIncrement(firstBotSlug: BotSlug): number {
  return BOTH_PLAN.priceMonthly - BOT_PLANS[firstBotSlug].priceMonthly
}

/** Free-trial length granted at checkout (matches the trial card in the dashboard). */
export const TRIAL_DAYS = 5

/**
 * Marketing tier prices — THE single source of truth for every price rendered on the
 * public site (homepage, /pricing, /terms, founding offer).
 *
 * Before this existed the site quoted itself two different numbers: the homepage said
 * Community $10 + "Forge Automate" $50, while /pricing said Community $15 + Starter $50
 * + Pro $100. Two Community prices and two tier vocabularies on the same site is a trust
 * problem, so all copy now reads from here.
 *
 * STARTER/PRO are derived from the Stripe-backed plans above so a marketing number can
 * never drift from what checkout actually bills. COMMUNITY is now Stripe-backed too
 * (COMMUNITY_PLAN, lookup key community_monthly) and sellable through checkout.
 */
export const MARKETING_TIERS = {
  /** Community/education tier — no bot execution. Billed via COMMUNITY_PLAN ($15/mo). */
  community: { name: COMMUNITY_PLAN.name, priceMonthly: COMMUNITY_PLAN.priceMonthly },
  /** One automated bot. Same price checkout bills for a single bot. */
  // Display name for the one-bot tier. Renamed Starter -> Automate 2026-07-29 to match
  // the approved homepage design. Everything that shows it — the homepage card, the
  // Terms of Service billing paragraph, the support knowledge base — reads THIS, so the
  // rename is one line and no surface can be left saying Starter.
  starter: { name: 'Forge Automate', priceMonthly: BOT_PLANS.spark.priceMonthly },
  /** Both bots. Same price checkout bills for the bundle. */
  pro: { name: 'Forge Pro', priceMonthly: BOTH_PLAN.priceMonthly },
} as const

export function getBotPlan(slug: string | undefined | null): BotPlan | null {
  if (slug === 'spark' || slug === 'flame') return BOT_PLANS[slug]
  return null
}

/** Maps a Stripe price lookup key back to the bot it represents (for webhook handling). */
export function botFromLookupKey(lookupKey: string | undefined | null): BotSlug | null {
  if (lookupKey === 'spark_monthly') return 'spark'
  if (lookupKey === 'flame_monthly') return 'flame'
  return null
}
