import { describe, it, expect } from 'vitest'
import { LIVE_BOT_TAGLINE, LIVE_BOTS, type LiveBot } from '../bots'
import { BOT_PLANS, botTagline, type BotSlug } from '@/lib/billing/plans'
import { dteMode } from '@/lib/db'

/**
 * A bot's tagline is a statement about what a customer's money is doing, and it
 * is served unauthenticated on `/api/public/track-record`. It has now been wrong
 * twice, the same way both times:
 *
 *  - 2026-08-16, FLAME: said "Two-day" after the roster moved it to 0DTE. Fixed,
 *    and pinned by a test — but only for Flame.
 *  - The same commit moved SPARK to 0DTE and left "Next-day SPY spreads" in
 *    place. Nothing caught it, because the test that would have was written
 *    about one bot rather than about the rule.
 *
 * A third bot was wrong in the other direction: "Same-day" while `dteMode` said
 * 1DTE. Both directions are the same defect.
 *
 * So this suite asserts the RULE over every bot on the roster, not one name.
 * Adding a bot to LIVE_BOTS without a truthful tagline fails here.
 */

/** How each roster bot's expiry is allowed to be described, keyed by dteMode. */
const DTE_WORD: Record<string, string> = {
  '0DTE': 'same-day',
  '1DTE': 'next-day',
}

/** Wording that contradicts a given dteMode. */
const FORBIDDEN: Record<string, string[]> = {
  '0DTE': ['next-day', 'two-day', 'multi-day'],
  '1DTE': ['same-day', 'two-day'],
}

describe('bot taglines describe the product actually being traded', () => {
  it.each(LIVE_BOTS)('%s states its real expiry', (bot: LiveBot) => {
    const dte = dteMode(bot)
    expect(dte, `dteMode('${bot}') must be known`).toBeTruthy()

    const required = DTE_WORD[dte as string]
    expect(required, `no expected wording registered for dteMode ${dte}`).toBeTruthy()

    const tagline = LIVE_BOT_TAGLINE[bot].toLowerCase()
    expect(tagline, `${bot} tagline should say "${required}"`).toContain(required)

    for (const bad of FORBIDDEN[dte as string]) {
      if (bad === required) continue
      expect(tagline, `${bot} tagline must not say "${bad}" when dteMode is ${dte}`).not.toContain(bad)
    }
  })

  /**
   * The real fix was removing the second copy, not correcting it. If someone
   * re-types a literal into LIVE_BOT_TAGLINE for a sellable bot, this fails even
   * though the string may happen to be right today — which is the point.
   */
  it.each(Object.keys(BOT_PLANS) as BotSlug[])(
    '%s tagline is derived from BOT_PLANS, not typed twice',
    (slug) => {
      expect(LIVE_BOT_TAGLINE[slug as LiveBot]).toBe(botTagline(slug))
    },
  )

  it('the two sellable bots describe the SAME structure — one strategy, two clocks', () => {
    // If this ever fails, either the products genuinely diverged (update the
    // marketing comparison too) or someone edited one blurb and not the other.
    expect(BOT_PLANS.spark.structure).toBe(BOT_PLANS.flame.structure)
    expect(BOT_PLANS.spark.cadence).not.toBe(BOT_PLANS.flame.cadence)
  })

  it('the checkout blurb is composed from the same fields as the tagline', () => {
    for (const slug of Object.keys(BOT_PLANS) as BotSlug[]) {
      const plan = BOT_PLANS[slug]
      expect(plan.blurb).toContain(plan.structure)
      expect(plan.blurb).toContain(plan.cadence)
    }
  })
})
