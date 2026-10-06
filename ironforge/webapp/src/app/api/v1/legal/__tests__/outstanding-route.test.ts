import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/lib/auth/customer-identity', () => ({ getCustomerIdentity: vi.fn() }))
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(async () => []),
}))
vi.mock('@/lib/enrollment/service', () => ({ legalRequirementsFor: vi.fn() }))

import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { legalRequirementsFor } from '@/lib/enrollment/service'
import { GET } from '../outstanding/route'

beforeEach(() => {
  vi.clearAllMocks()
  ;(getCustomerIdentity as any).mockResolvedValue(null)
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
  ;(customerQuery as any).mockResolvedValue([])
  ;(legalRequirementsFor as any).mockResolvedValue({ documents: [], outstanding: [] })
})

describe('GET /api/v1/legal/outstanding', () => {
  it('401 without a signed-in customer', async () => {
    const res = await GET()
    expect(res.status).toBe(401)
  })

  it('uses plan=null (core only) for a customer who owns no automate-family bot', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    ;(customerQuery as any).mockResolvedValue([{ bot: 'community', status: 'active' }])
    await GET()
    expect(legalRequirementsFor).toHaveBeenCalledWith(null, 'u1')
  })

  it('uses plan="automate" for a customer who owns Spark, Flame or Ember', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    ;(customerQuery as any).mockResolvedValue([{ bot: 'spark', status: 'trialing' }])
    await GET()
    expect(legalRequirementsFor).toHaveBeenCalledWith('automate', 'u1')
  })

  it('ignores a cancelled/non-live subscription row', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    ;(customerQuery as any).mockResolvedValue([{ bot: 'spark', status: 'canceled' }])
    await GET()
    expect(legalRequirementsFor).toHaveBeenCalledWith(null, 'u1')
  })

  it('returns the computed outstanding codes', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    ;(legalRequirementsFor as any).mockResolvedValue({
      documents: [{ code: 'TERMS', title: 'Terms of Service', version: '1.1', contentUri: '/terms', accepted: false }],
      outstanding: ['TERMS'],
    })
    const res = await GET()
    const json = await res.json()
    expect(json).toEqual({
      ok: true,
      documents: [{ code: 'TERMS', title: 'Terms of Service', version: '1.1', contentUri: '/terms', accepted: false }],
      outstanding: ['TERMS'],
    })
  })

  it('fails open (nothing outstanding) rather than lock a customer out on a read error', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    ;(legalRequirementsFor as any).mockRejectedValue(new Error('db down'))
    const res = await GET()
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json).toEqual({ ok: true, documents: [], outstanding: [] })
  })
})
