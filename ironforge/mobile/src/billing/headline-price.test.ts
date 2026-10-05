import { describe, it, expect } from 'vitest'
import { headlinePriceLabel } from './headline-price'

describe('headlinePriceLabel', () => {
  it('iOS with a loaded StoreKit product: headline matches the Subscribe button exactly', () => {
    expect(
      headlinePriceLabel({ iapEnabled: true, iapProduct: { displayPrice: '$49.99' }, stripePrice: 50 }),
    ).toBe('$49.99/month')
  })

  it('iOS still loading the StoreKit product: falls back to the Stripe price (no button is shown yet)', () => {
    expect(headlinePriceLabel({ iapEnabled: true, iapProduct: null, stripePrice: 50 })).toBe('$50/month')
  })

  it('Android/web: always the Stripe price, even though iapProduct is never populated there', () => {
    expect(headlinePriceLabel({ iapEnabled: false, iapProduct: null, stripePrice: 10 })).toBe('$10/month')
  })

  it('no price available on either rail: renders nothing rather than "$undefined"', () => {
    expect(headlinePriceLabel({ iapEnabled: true, iapProduct: null, stripePrice: null })).toBeNull()
    expect(headlinePriceLabel({ iapEnabled: false, iapProduct: null, stripePrice: undefined })).toBeNull()
  })

  it('never quotes the Stripe price on iOS once the real product is loaded, even if they differ', () => {
    const label = headlinePriceLabel({ iapEnabled: true, iapProduct: { displayPrice: '$9.99' }, stripePrice: 10 })
    expect(label).not.toContain('10')
    expect(label).toBe('$9.99/month')
  })
})
