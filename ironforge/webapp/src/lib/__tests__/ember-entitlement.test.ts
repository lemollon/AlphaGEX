import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/lib/auth/customer-identity', () => ({ getCustomerIdentity: vi.fn() }))
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
}))

import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { resolveEmberOwner } from '../ember-entitlement'

beforeEach(() => {
  vi.clearAllMocks()
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
})

describe('resolveEmberOwner', () => {
  it('null when no signed-in identity', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue(null)
    expect(await resolveEmberOwner()).toBeNull()
    expect(customerQuery).not.toHaveBeenCalled()
  })

  it('null when the customers DB is not configured', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'cust-1' })
    ;(isCustomersDbConfigured as any).mockReturnValue(false)
    expect(await resolveEmberOwner()).toBeNull()
  })

  it('null when signed in but no live ember subscription row', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'cust-1' })
    ;(customerQuery as any).mockResolvedValue([{ status: 'canceled' }])
    expect(await resolveEmberOwner()).toBeNull()
  })

  it('returns the customerId when a live (trialing/active/past_due) ember row exists', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'cust-1' })
    ;(customerQuery as any).mockResolvedValue([{ status: 'active' }])
    expect(await resolveEmberOwner()).toBe('cust-1')
  })

  it('degrades to null (never throws) on a query failure', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'cust-1' })
    ;(customerQuery as any).mockRejectedValue(new Error('db down'))
    expect(await resolveEmberOwner()).toBeNull()
  })
})
