import { describe, it, expect } from 'vitest'
import { canManageBillingInApp } from '@/billing/store-policy'

describe('canManageBillingInApp', () => {
  it('is false on iOS — Apple rejected the restricted portal itself as a 3.1.1 access path', () => {
    expect(canManageBillingInApp('ios')).toBe(false)
  })

  it('is true on android and web — the portal-config restriction still applies there', () => {
    expect(canManageBillingInApp('android')).toBe(true)
    expect(canManageBillingInApp('web')).toBe(true)
  })
})
