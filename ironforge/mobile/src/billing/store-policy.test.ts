import { describe, it, expect } from 'vitest'
import { canManageBillingInApp, canShowMembershipPrice } from './store-policy'

/**
 * The whole point of this rule is that it says NO on exactly one platform. A test that
 * only checked android would pass against a function that always returned true, which is
 * the failure this file exists to prevent.
 */
describe('canManageBillingInApp', () => {
  it('is false on iOS — the Stripe portal allows changing plan (Guideline 3.1.1)', () => {
    expect(canManageBillingInApp('ios')).toBe(false)
  })

  it('is true on android, where linking to an external portal is permitted', () => {
    expect(canManageBillingInApp('android')).toBe(true)
  })

  it('is true on web, which is not a store surface at all', () => {
    expect(canManageBillingInApp('web')).toBe(true)
  })

  it('does not fail open on an unrecognised platform string', () => {
    // A future platform must not silently become "iOS is the only exception, everything
    // unknown is fine" without someone re-reading the guideline. Documented as true.
    expect(canManageBillingInApp('macos')).toBe(true)
  })
})

describe('canShowMembershipPrice', () => {
  it('allows the price of an existing subscription on iOS', () => {
    // Account information, not a call to action. If this ever flips, the price block in
    // account.tsx must be gated in the same commit.
    expect(canShowMembershipPrice('ios')).toBe(true)
  })
})
