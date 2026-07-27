import { describe, it, expect } from 'vitest'
import { BOT_PLANS } from '@/lib/billing/plans'
import { dteMode } from '@/lib/db'

/**
 * Plan copy must not describe a strategy the bot does not run.
 *
 * The Spark plan card advertised "automated 0DTE income trading". Spark is 1DTE —
 * 0DTE is INFERNO, an internal bot customers cannot buy. So the billing card
 * described the wrong product, and contradicted the same bot's tagline on /live,
 * /onboarding/complete and the Bot Ledger. Flame's said "near-term upside trading",
 * which implies a directional long; Flame sells put credit spreads.
 *
 * This pins the blurb to the bot's ACTUAL expiry from dteMode() — the same source
 * the scanner and every query use — so the copy cannot silently drift from the
 * strategy again.
 */
describe('plan copy matches the bot it sells', () => {
  const ALL_DTE = ['0DTE', '1DTE', '2DTE']

  for (const [slug, plan] of Object.entries(BOT_PLANS)) {
    const own = dteMode(slug)

    it(`${slug}: blurb states ${own} and no other expiry`, () => {
      expect(plan.blurb).toContain(own)
      for (const wrong of ALL_DTE.filter((d) => d !== own)) {
        expect(plan.blurb).not.toContain(wrong)
      }
    })

    it(`${slug}: blurb makes no performance or income promise`, () => {
      // Marketing rule: describe mechanics, never imply an outcome.
      expect(plan.blurb).not.toMatch(/\b(income|profit|returns?|guarantee\w*|win\w*)\b/i)
    })
  }
})
