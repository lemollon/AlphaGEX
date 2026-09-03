import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/auth/customer-identity', () => ({ getCustomerIdentity: vi.fn() }))
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerExecute: vi.fn(async () => 1),
}))

import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'
import { POST } from '../events/route'

function call(body: unknown) {
  return POST(
    new NextRequest('https://app.test/api/v1/analytics/events', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1' })
  ;(customerExecute as any).mockResolvedValue(1)
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
})

describe('POST /api/v1/analytics/events', () => {
  it('401 without a bearer identity', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue(null)
    const res = await call({ events: [{ event: 'screen_view', ts: Date.now() }] })
    expect(res.status).toBe(401)
  })

  it('400 on a non-array events field', async () => {
    const res = await call({ events: 'nope' })
    expect(res.status).toBe(400)
  })

  it('400 when events exceeds the 50-event cap', async () => {
    const events = Array.from({ length: 51 }, (_, i) => ({ event: `e${i}`, ts: Date.now() }))
    const res = await call({ events })
    expect(res.status).toBe(400)
  })

  it('accepts a valid batch and writes one row per event', async () => {
    const events = [
      { event: 'screen_view', props: { path: '/live' }, ts: Date.now(), app_version: '1.0.0', platform: 'ios' },
      { event: 'trade_detail_opened', ts: Date.now() },
    ]
    const res = await call({ events })
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json).toEqual({ ok: true, accepted: 1 })
    expect(customerExecute).toHaveBeenCalledTimes(1)
    const [sql, params] = (customerExecute as any).mock.calls[0]
    expect(sql).toContain('INSERT INTO mobile_analytics_events')
    // 2 events x 6 columns = 12 bound params, both rows owned by the bearer identity.
    expect(params).toHaveLength(12)
    expect(params[0]).toBe('u1')
    expect(params[6]).toBe('u1')
  })

  it('strips sensitive prop keys server-side even if the client forgot to', async () => {
    const events = [
      {
        event: 'sign_in_attempted',
        props: { accountId: 'acct_1', authToken: 'tok', screen: 'sign-in' },
        ts: Date.now(),
      },
    ]
    await call({ events })
    const [, params] = (customerExecute as any).mock.calls[0]
    const props = JSON.parse(params[2] as string)
    expect(props).toEqual({ screen: 'sign-in' })
  })

  it('accepts and drops the batch when the customers DB is not configured', async () => {
    ;(isCustomersDbConfigured as any).mockReturnValue(false)
    const res = await call({ events: [{ event: 'screen_view', ts: Date.now() }] })
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json).toEqual({ ok: true, accepted: 0 })
    expect(customerExecute).not.toHaveBeenCalled()
  })
})
