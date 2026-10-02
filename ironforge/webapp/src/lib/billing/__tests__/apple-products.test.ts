import { describe, it, expect } from 'vitest'
import { APPLE_PRODUCTS, productIdFor, planFor } from '../apple-products'
import { BOT_PLANS, BOTH_PLAN, COMMUNITY_PLAN } from '../plans'

describe('apple-products', () => {
  it('has exactly the four catalogue rows the spec defines', () => {
    expect(APPLE_PRODUCTS.map((p) => p.productId).sort()).toEqual([
      'ironforge.both.monthly',
      'ironforge.community.monthly',
      'ironforge.flame.monthly',
      'ironforge.spark.monthly',
    ])
  })

  it('mirrors the Stripe lookup keys exactly — same catalogue, second rail', () => {
    expect(productIdFor(BOTH_PLAN.lookupKey)).toBe('ironforge.both.monthly')
    expect(productIdFor(BOT_PLANS.spark.lookupKey)).toBe('ironforge.spark.monthly')
    expect(productIdFor(BOT_PLANS.flame.lookupKey)).toBe('ironforge.flame.monthly')
    expect(productIdFor(COMMUNITY_PLAN.lookupKey)).toBe('ironforge.community.monthly')
  })

  it('returns null for a lookup key with no Apple product', () => {
    expect(productIdFor('nonexistent_monthly')).toBeNull()
  })

  it('maps each Apple product id back to the right bots and bundle flag', () => {
    expect(planFor('ironforge.both.monthly')).toEqual({
      productId: 'ironforge.both.monthly',
      lookupKey: 'both_monthly',
      bots: ['spark', 'flame'],
      bundle: true,
    })
    expect(planFor('ironforge.spark.monthly')?.bots).toEqual(['spark'])
    expect(planFor('ironforge.spark.monthly')?.bundle).toBe(false)
    expect(planFor('ironforge.flame.monthly')?.bots).toEqual(['flame'])
    expect(planFor('ironforge.community.monthly')?.bots).toEqual(['community'])
  })

  it('round-trips productIdFor -> planFor -> lookupKey for every catalogue row', () => {
    for (const product of APPLE_PRODUCTS) {
      const id = productIdFor(product.lookupKey)
      expect(id).toBe(product.productId)
      expect(planFor(id!)?.lookupKey).toBe(product.lookupKey)
    }
  })

  it('returns null for an unknown product id', () => {
    expect(planFor('com.someone.else.monthly')).toBeNull()
  })
})
