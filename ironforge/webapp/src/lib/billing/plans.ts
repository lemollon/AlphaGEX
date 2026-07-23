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
