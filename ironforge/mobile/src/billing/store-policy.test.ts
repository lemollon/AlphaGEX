import { describe, it, expect } from 'vitest'
import { canManageBillingInApp } from '@/billing/store-policy'

describe('canManageBillingInApp', () => {
  it('is true on every platform — the 3.1.1 guarantee is server-side, not client-side', () => {
    expect(canManageBillingInApp('ios')).toBe(true)
    expect(canManageBillingInApp('android')).toBe(true)
    expect(canManageBillingInApp('web')).toBe(true)
  })
})
