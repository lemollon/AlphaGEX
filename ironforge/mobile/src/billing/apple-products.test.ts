import { describe, it, expect } from 'vitest'
import { APPLE_PRODUCTS, productIdFor, planFor } from '@/billing/apple-products'

describe('apple-products mapping', () => {
  it('maps every Stripe lookup key to an Apple product ID', () => {
    expect(productIdFor('both_monthly')).toBe('ironforge.both.monthly')
    expect(productIdFor('spark_monthly')).toBe('ironforge.spark.monthly')
    expect(productIdFor('flame_monthly')).toBe('ironforge.flame.monthly')
    expect(productIdFor('community_monthly')).toBe('ironforge.community.monthly')
  })

  it('returns null for a lookup key Apple does not sell', () => {
    expect(productIdFor('not_a_real_key')).toBeNull()
  })

  it('maps every Apple product ID back to its plan, bots, and lookup key', () => {
    expect(planFor('ironforge.both.monthly')).toEqual({
      productId: 'ironforge.both.monthly',
      lookupKey: 'both_monthly',
      bots: ['spark', 'flame'],
      bundle: true,
    })
    expect(planFor('ironforge.spark.monthly')?.bots).toEqual(['spark'])
    expect(planFor('ironforge.flame.monthly')?.bots).toEqual(['flame'])
    expect(planFor('ironforge.community.monthly')?.bots).toEqual(['community'])
  })

  it('returns null for an unknown Apple product ID — never a guessed plan', () => {
    expect(planFor('com.someoneelse.product')).toBeNull()
  })

  it('round-trips every catalogue entry through both lookup directions', () => {
    for (const entry of APPLE_PRODUCTS) {
      expect(productIdFor(entry.lookupKey)).toBe(entry.productId)
      expect(planFor(entry.productId)).toEqual(entry)
    }
  })

  it('flags exactly one entry as the bundle', () => {
    expect(APPLE_PRODUCTS.filter((p) => p.bundle)).toHaveLength(1)
  })
})
