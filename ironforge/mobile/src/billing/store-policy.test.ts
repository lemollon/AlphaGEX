import { describe, it, expect } from 'vitest'
import { canManageBillingInApp, canPurchaseInApp, manageSubscriptionUrl } from '@/billing/store-policy'

describe('canManageBillingInApp', () => {
  it('is false on iOS — Apple rejected the restricted portal itself as a 3.1.1 access path', () => {
    expect(canManageBillingInApp('ios')).toBe(false)
  })

  it('is true on android and web — the portal-config restriction still applies there', () => {
    expect(canManageBillingInApp('android')).toBe(true)
    expect(canManageBillingInApp('web')).toBe(true)
  })
})

describe('canPurchaseInApp', () => {
  it('is true on iOS now that StoreKit 2 (expo-iap) is the purchase surface', () => {
    expect(canPurchaseInApp('ios')).toBe(true)
  })

  it('stays false on android and web — Play Billing is out of scope for this PR', () => {
    expect(canPurchaseInApp('android')).toBe(false)
    expect(canPurchaseInApp('web')).toBe(false)
  })
})

describe('manageSubscriptionUrl', () => {
  it('points an iOS + apple membership at the App Store subscription settings', () => {
    expect(manageSubscriptionUrl('apple', 'ios')).toBe('https://apps.apple.com/account/subscriptions')
  })

  it('is null for an iOS + stripe membership — that is handled by plain copy, not a link', () => {
    expect(manageSubscriptionUrl('stripe', 'ios')).toBeNull()
  })

  it('is null when there is no membership at all', () => {
    expect(manageSubscriptionUrl(null, 'ios')).toBeNull()
    expect(manageSubscriptionUrl(undefined, 'ios')).toBeNull()
  })

  it('is null on every non-iOS platform regardless of provider', () => {
    expect(manageSubscriptionUrl('apple', 'android')).toBeNull()
    expect(manageSubscriptionUrl('apple', 'web')).toBeNull()
    expect(manageSubscriptionUrl('stripe', 'android')).toBeNull()
  })
})
