import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/auth/customer-identity', () => ({ getCustomerIdentity: vi.fn() }))
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerExecute: vi.fn(async () => 1),
  customerQuery: vi.fn(async () => [{ c: 0 }]),
}))

import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerExecute, customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { POST } from '../route'

function call(body: unknown) {
  return POST(
    new NextRequest('https://app.test/api/v1/events', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(getCustomerIdentity as any).mockResolvedValue(null)
  ;(customerExecute as any).mockResolvedValue(1)
  ;(customerQuery as any).mockResolvedValue([{ c: 0 }])
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
})

describe('POST /api/v1/events', () => {
  it('400 with no session and no anon_id', async () => {
    const res = await call({ event: 'cta_click', props: { cta: 'create_account' }, surface: 'web' })
    expect(res.status).toBe(400)
  })

  it('accepts an anonymous single event with anon_id', async () => {
    const res = await call({
      event: 'cta_click',
      props: { cta: 'create_account', placement: 'hero' },
      surface: 'web',
      anon_id: 'anon-123',
    })
    const json = await res.json()
    expect(res.status).toBe(201)
    expect(json).toEqual({ ok: true, accepted: 1 })
    const [sql, params] = (customerExecute as any).mock.calls[0]
    expect(sql).toContain('INSERT INTO analytics_events')
    expect(params[0]).toBeNull() // user_id
    expect(params[1]).toBe('anon-123') // anon_id
    expect(params[2]).toBe('cta_click')
    expect(JSON.parse(params[3])).toEqual({ cta: 'create_account', placement: 'hero' })
    expect(params[4]).toBe('web')
  })

  it('accepts an authenticated event without anon_id, and does not persist anon_id', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'u1', source: 'cookie' })
    const res = await call({ event: 'enroll_step_complete', props: { step: 'legal', ms_on_step: 4200 }, surface: 'web' })
    expect(res.status).toBe(201)
    const [, params] = (customerExecute as any).mock.calls[0]
    expect(params[0]).toBe('u1')
    expect(params[1]).toBeNull()
  })

  it('rejects an event name not on the allowlist', async () => {
    const res = await call({ event: 'made_up_event', surface: 'web', anon_id: 'anon-1' })
    expect(res.status).toBe(400)
    expect(customerExecute).not.toHaveBeenCalled()
  })

  it('drops props not declared for that event', async () => {
    const res = await call({
      event: 'legal_accept_all',
      props: { signature: 'John Smith', anything: 'x' },
      surface: 'web',
      anon_id: 'anon-1',
    })
    expect(res.status).toBe(201)
    const [, params] = (customerExecute as any).mock.calls[0]
    expect(params[3]).toBeNull()
  })

  it('strips a PII-shaped prop value even under an allowlisted key name', async () => {
    const res = await call({
      event: 'waitlist_error',
      props: { placement: 'hero', field: 'shairan2016@gmail.com' },
      surface: 'web',
      anon_id: 'anon-1',
    })
    expect(res.status).toBe(201)
    const [, params] = (customerExecute as any).mock.calls[0]
    const props = JSON.parse(params[3] as string)
    expect(props).toEqual({ placement: 'hero' })
  })

  it('accepts a mobile-shaped batch under {events:[...]}', async () => {
    const res = await call({
      events: [
        { event: 'tab_view', props: { tab: 'forge' } },
        { event: 'app_open' },
      ],
      surface: 'ios',
      anon_id: 'anon-9',
    })
    const json = await res.json()
    expect(res.status).toBe(201)
    expect(json.accepted).toBe(1)
    expect(customerExecute).toHaveBeenCalledTimes(1)
    const [sql, params] = (customerExecute as any).mock.calls[0]
    expect(sql).toContain('($1, $2, $3, $4, $5), ($6, $7, $8, $9, $10)')
    expect(params).toHaveLength(10)
    expect(params[4]).toBe('ios')
    expect(params[9]).toBe('ios')
  })

  it('400 when the batch exceeds the per-request cap', async () => {
    const events = Array.from({ length: 51 }, () => ({ event: 'app_open' }))
    const res = await call({ events, surface: 'ios', anon_id: 'anon-9' })
    expect(res.status).toBe(400)
  })

  it('429 when the rate limit window is exceeded', async () => {
    ;(customerQuery as any).mockResolvedValue([{ c: 999 }])
    const res = await call({ event: 'app_open', surface: 'ios', anon_id: 'anon-9' })
    expect(res.status).toBe(429)
    expect(customerExecute).not.toHaveBeenCalled()
  })

  it('accepts and no-ops when the customers DB is not configured', async () => {
    ;(isCustomersDbConfigured as any).mockReturnValue(false)
    const res = await call({ event: 'app_open', surface: 'ios', anon_id: 'anon-9' })
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json).toEqual({ ok: true, accepted: 0 })
    expect(customerExecute).not.toHaveBeenCalled()
  })
})
