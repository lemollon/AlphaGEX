import { describe, it, expect } from 'vitest'
import { GET } from '../route'
import { COMMUNITY_PLAN, BOT_PLANS, BOTH_PLAN, TRIAL_DAYS } from '@/lib/billing/plans'

describe('GET /api/public/plans', () => {
  it('serves the exact catalogue lib/billing/plans.ts exports, never a hardcoded copy', async () => {
    const res = await GET()
    const json = await res.json()

    expect(json.community).toEqual({
      key: COMMUNITY_PLAN.key,
      name: COMMUNITY_PLAN.name,
      price_monthly: COMMUNITY_PLAN.priceMonthly,
    })
    expect(json.both).toEqual({ price_monthly: BOTH_PLAN.priceMonthly })
    expect(json.trial_days).toBe(TRIAL_DAYS)

    const spark = json.bots.find((b: { slug: string }) => b.slug === 'spark')
    const flame = json.bots.find((b: { slug: string }) => b.slug === 'flame')
    expect(spark.price_monthly).toBe(BOT_PLANS.spark.priceMonthly)
    expect(flame.price_monthly).toBe(BOT_PLANS.flame.priceMonthly)
    expect(spark.name).toBe(BOT_PLANS.spark.name)
  })

  it('is cacheable but never store-private (no auth, no PII)', async () => {
    const res = await GET()
    expect(res.headers.get('Cache-Control')).toContain('public')
  })
})
