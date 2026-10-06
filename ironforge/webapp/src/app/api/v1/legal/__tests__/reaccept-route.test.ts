import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/auth/customer-identity', () => ({ getCustomerIdentity: vi.fn() }))
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(async () => [{ first_name: 'Dana', last_name: 'Reyes' }]),
}))
vi.mock('@/lib/enrollment/service', () => ({ recordAcceptedDocuments: vi.fn() }))

import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { recordAcceptedDocuments } from '@/lib/enrollment/service'
import { POST } from '../reaccept/route'

function call(body: unknown) {
  return POST(
    new NextRequest('https://app.test/api/v1/legal/reaccept', { method: 'POST', body: JSON.stringify(body) }),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(getCustomerIdentity as any).mockResolvedValue(null)
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
  ;(customerQuery as any).mockResolvedValue([{ first_name: 'Dana', last_name: 'Reyes' }])
  ;(recordAcceptedDocuments as any).mockResolvedValue({ written: 1, alreadyPresent: 0 })
})

describe('POST /api/v1/legal/reaccept', () => {
  it('401 without a signed-in customer', async () => {
    const res = await call({ codes: ['TERMS'], signature_name: 'Dana Reyes' })
    expect(res.status).toBe(401)
  })

  it('400 with no codes', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    const res = await call({ codes: [], signature_name: 'Dana Reyes' })
    expect(res.status).toBe(400)
  })

  it('422 on a one-word signature', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    const res = await call({ codes: ['TERMS'], signature_name: 'Dana' })
    expect(res.status).toBe(422)
  })

  it('422 when the signature does not match the account name', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    const res = await call({ codes: ['TERMS'], signature_name: 'Someone Else' })
    expect(res.status).toBe(422)
    expect(recordAcceptedDocuments).not.toHaveBeenCalled()
  })

  it('records the acceptance with enrollmentId null, through the same path enrollment uses', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    const res = await call({ codes: ['TERMS', 'RISK'], signature_name: 'Dana Reyes' })
    expect(res.status).toBe(200)
    const json = await res.json()
    expect(json).toEqual({ ok: true, written: 1, alreadyPresent: 0 })
    expect(recordAcceptedDocuments).toHaveBeenCalledWith(
      expect.objectContaining({
        userId: 'u1',
        enrollmentId: null,
        codes: ['TERMS', 'RISK'],
        signatureName: 'Dana Reyes',
      }),
    )
  })

  it('503 when the customers DB is not configured', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
    ;(isCustomersDbConfigured as any).mockReturnValue(false)
    const res = await call({ codes: ['TERMS'], signature_name: 'Dana Reyes' })
    expect(res.status).toBe(503)
  })
})
