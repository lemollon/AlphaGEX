import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

// ---- mocks (brokers + DB + session) so the route's orchestration is testable offline ----
vi.mock('@/lib/auth/customer-session-server', () => ({ getCustomerSession: vi.fn() }))
// requireIdentityWithStepUp() calls next/headers directly once there's no cookie-sourced
// identity (see mobile-step-up.ts) — next/headers throws outside a real Next.js request
// scope, so it needs a stub here the same way mobile-step-up.test.ts stubs it. Its own
// pending/step-up/unauthorized branching is unit-tested there, not re-derived here.
vi.mock('next/headers', () => ({ headers: vi.fn(() => ({ get: () => null })) }))
vi.mock('@/lib/auth/mobile-step-up', async () => {
  const actual = await vi.importActual<typeof import('@/lib/auth/mobile-step-up')>('@/lib/auth/mobile-step-up')
  return { ...actual, requireIdentityWithStepUp: vi.fn(actual.requireIdentityWithStepUp) }
})
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(async () => 1),
}))
vi.mock('@/lib/snaptrade', () => ({
  isSnapTradeConfigured: vi.fn(() => true),
  getSnapTrade: vi.fn(),
}))
vi.mock('@/lib/tradier-oauth', () => ({
  isTradierOAuthConfigured: vi.fn(() => true),
  placeOrder: vi.fn(),
}))
vi.mock('@/lib/crypto/secret-box', () => ({ decryptSecret: vi.fn(() => 'plain-token') }))
vi.mock('@/lib/brokerage/snaptrade-user', () => ({ loadSnapTradeCreds: vi.fn() }))

import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { requireIdentityWithStepUp } from '@/lib/auth/mobile-step-up'
import { customerQuery, customerExecute } from '@/lib/customers-db'
import { getSnapTrade } from '@/lib/snaptrade'
import { placeOrder as tradierPlaceOrder } from '@/lib/tradier-oauth'
import { loadSnapTradeCreds } from '@/lib/brokerage/snaptrade-user'
import { POST } from '../[id]/approve/route'

const future = () => new Date(Date.now() + 60_000).toISOString()
const past = () => new Date(Date.now() - 60_000).toISOString()

function approval(over: Record<string, unknown> = {}) {
  return {
    id: 'appr1', user_id: 'u1', status: 'pending', expires_at: future(),
    provider: 'snaptrade', snaptrade_trade_id: 't1',
    account_id: 'acc1', symbol: 'AAPL', action: 'BUY', units: '1', order_type: 'Market',
    ...over,
  }
}
const call = () => POST(new NextRequest('https://app.test/x', { method: 'POST' }), { params: { id: 'appr1' } })
function lastStatusWrites() {
  return (customerExecute as any).mock.calls.map((c: any[]) => String(c[0])).filter((s: string) => /UPDATE trade_approvals SET status/.test(s))
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(getCustomerSession as any).mockResolvedValue({ customerId: 'u1' })
  ;(customerExecute as any).mockResolvedValue(1)
  ;(loadSnapTradeCreds as any).mockResolvedValue({ snaptradeUserId: 'st1', userSecret: 's' })
  ;(getSnapTrade as any).mockReturnValue({
    trading: { placeOrder: vi.fn(async () => ({ data: { brokerage_order_id: 'ORD-1' } })) },
  })
  ;(tradierPlaceOrder as any).mockResolvedValue({ orderId: 'TORD-1' })
})

describe('POST /api/brokerage/trades/[id]/approve', () => {
  it('401 without a customer session', async () => {
    ;(getCustomerSession as any).mockResolvedValue({})
    expect((await call()).status).toBe(401)
  })

  it('404 when the approval belongs to a different customer (ownership)', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval({ user_id: 'someone-else' })])
    expect((await call()).status).toBe(404)
    expect((getSnapTrade as any)).not.toHaveBeenCalled()
  })

  it('SnapTrade happy path: places, marks placed, returns the order id', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval()])
    const res = await call()
    const body = await res.json()
    expect(res.status).toBe(200)
    expect(body).toMatchObject({ ok: true, status: 'placed', orderId: 'ORD-1' })
    expect(lastStatusWrites().some((s: string) => s.includes("'placed'"))).toBe(true)
  })

  it('Tradier happy path: dispatches to the Tradier placer', async () => {
    ;(customerQuery as any)
      .mockResolvedValueOnce([approval({ provider: 'tradier', snaptrade_trade_id: null })])
      .mockResolvedValueOnce([{ tradier_access_token: 'enc' }])
    const res = await call()
    expect(res.status).toBe(200)
    expect((tradierPlaceOrder as any)).toHaveBeenCalledOnce()
    expect((getSnapTrade as any)).not.toHaveBeenCalled() // did NOT touch the other provider
  })

  it('expired approval: refuses, marks expired, never places', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval({ expires_at: past() })])
    const res = await call()
    expect(res.status).toBe(409)
    expect((getSnapTrade as any)).not.toHaveBeenCalled()
    expect(lastStatusWrites().some((s: string) => s.includes("'expired'"))).toBe(true)
  })

  it('already-decided approval: refuses, never places', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval({ status: 'placed' })])
    expect((await call()).status).toBe(409)
    expect((getSnapTrade as any)).not.toHaveBeenCalled()
  })

  it('unknown provider: refuses rather than guessing a broker', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval({ provider: 'robinhood' })])
    const res = await call()
    expect(res.status).toBe(409)
    expect((getSnapTrade as any)).not.toHaveBeenCalled()
    expect((tradierPlaceOrder as any)).not.toHaveBeenCalled()
  })

  it('broker rejects: marks failed, returns 502', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval()])
    ;(getSnapTrade as any).mockReturnValue({
      trading: { placeOrder: vi.fn(async () => { throw new Error('broker boom') }) },
    })
    const res = await call()
    expect(res.status).toBe(502)
    expect(lastStatusWrites().some((s: string) => s.includes("'failed'"))).toBe(true)
  })

  it('non-market order type: refused, never claims or places (no price is ever captured)', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval({ order_type: 'Limit' })])
    const res = await call()
    expect(res.status).toBe(409)
    expect((getSnapTrade as any)).not.toHaveBeenCalled()
    expect(lastStatusWrites()).toHaveLength(0)
  })

  it('concurrent approve: loses the atomic claim, gets 409, never places a second order', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval()])
    // The claim UPDATE (`... WHERE status='pending' ...`) is the only customerExecute call
    // before placeOrder would run — a concurrent request already won it, so rowCount is 0.
    ;(customerExecute as any).mockResolvedValueOnce(0)
    const res = await call()
    expect(res.status).toBe(409)
    // getSnapTrade() is only called AFTER a successful claim — losing the race means it's
    // never reached, so the broker is never touched by this request.
    expect((getSnapTrade as any)).not.toHaveBeenCalled()
  })

  it('order placed but the status write fails: reports success with a warning, not 502 (order is real and live)', async () => {
    ;(customerQuery as any).mockResolvedValueOnce([approval()])
    ;(customerExecute as any)
      .mockResolvedValueOnce(1) // claim succeeds
      .mockRejectedValueOnce(new Error('db blip')) // the post-placement 'placed' write fails
      .mockResolvedValueOnce(1) // the audit_events insert (best-effort, wrapped in .catch)
    const res = await call()
    const body = await res.json()
    expect(res.status).toBe(200)
    expect(body).toMatchObject({ ok: true, status: 'placed', orderId: 'ORD-1' })
    expect(body.warning).toBeTruthy()
  })

  it('step-up required (new mobile client, plain token but no step-up token): 401, never reaches the DB', async () => {
    ;(requireIdentityWithStepUp as any).mockResolvedValueOnce({ identity: null, error: 'step_up_required' })
    const res = await call()
    const body = await res.json()
    expect(res.status).toBe(401)
    expect(body.error).toBe('step_up_required')
    expect((customerQuery as any)).not.toHaveBeenCalled()
  })
})
