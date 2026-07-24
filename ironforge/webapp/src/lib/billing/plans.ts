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
    blurb: 'Set up a dedicated Spark account for automated 0DTE income trading.',
    priceMonthly: 50,
    lookupKey: 'spark_monthly',
    accent: '#2F80ED', // Spark blue
    mascot: '/home/spark-mascot-glow.png',
    liveHref: '/live',
  },
  flame: {
    slug: 'flame',
    name: 'Flame',
    productName: 'IronForge Flame',
    blurb: 'Set up a dedicated Flame account for automated near-term upside trading.',
    priceMonthly: 50,
    lookupKey: 'flame_monthly',
    accent: '#FD5301', // Flame / brand orange
    mascot: '/home/flame-mascot-glow.png',
    liveHref: '/live',
  },
}

/** The two-bot bundle — offered as an upsell, priced below 2× a single bot. */
export const BOTH_PLAN = {
  lookupKey: 'both_monthly',
  priceMonthly: 75,
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
 * never drift from what checkout actually bills. COMMUNITY has no Stripe product yet
 * (it is not sellable through checkout) — $15 is the /pricing figure, which is the page
 * that was reconciled against real billing on 2026-07-23.
 */
export const MARKETING_TIERS = {
  /** Community/education tier — no bot execution, not yet wired to Stripe. */
  community: { name: 'Forge Community', priceMonthly: 15 },
  /** One automated bot. Same price checkout bills for a single bot. */
  starter: { name: 'Forge Starter', priceMonthly: BOT_PLANS.spark.priceMonthly },
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
