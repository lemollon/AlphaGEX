import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---- mocks so the route's orchestration is testable offline ----
vi.mock('@/lib/auth/customer-identity', () => ({ getCustomerIdentity: vi.fn() }))
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
}))
vi.mock('@/lib/customer-executor/executor', () => ({ isExecutorArmed: vi.fn(() => false) }))
vi.mock('@/lib/live/executing-broker', () => ({ resolveExecutingBroker: vi.fn() }))

import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { isExecutorArmed } from '@/lib/customer-executor/executor'
import { resolveExecutingBroker } from '@/lib/live/executing-broker'
import { GET } from '../route'

beforeEach(() => {
  vi.clearAllMocks()
  ;(getCustomerIdentity as any).mockResolvedValue({ customerId: 'cust1' })
  ;(isExecutorArmed as any).mockReturnValue(false)
  ;(resolveExecutingBroker as any).mockResolvedValue(null)
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
  ;(customerQuery as any).mockResolvedValue([])
})

describe('GET /api/brokerage/connections', () => {
  it('401s with no customer identity', async () => {
    ;(getCustomerIdentity as any).mockResolvedValue(null)
    const res = await GET()
    expect(res.status).toBe(401)
  })

  it('reports the real executing Tradier account, never the stale SnapTrade row, when the customer-executor is disarmed', async () => {
    ;(resolveExecutingBroker as any).mockResolvedValue({ bot: 'flame', broker: 'Tradier', last4: '2434' })
    // Even if a (stale/irrelevant) SnapTrade connection row exists for this customer,
    // it must never reach the response once the real executing account resolves —
    // this is the exact "Tastytrade •••• ••••2434" bug: the SnapTrade row is what
    // the customer onboarded with, not what their money is actually trading through.
    ;(customerQuery as any).mockResolvedValue([
      { id: 'c1', provider: 'snaptrade', authorization_id: 'auth1', brokerage_slug: 'tastytrade', account_name: null, status: 'active', created_at: '2026-01-01', last_synced_at: null },
    ])
    const res = await GET()
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.connections).toHaveLength(1)
    expect(body.connections[0].broker).toBe('Tradier')
    expect(body.connections[0].accounts[0].mask).toBe('••••2434')
    // The house account cannot be disconnected from this screen.
    expect(body.connections[0].authorization_id).toBeNull()
    // The real brokerage_connections query is never even consulted.
    expect(customerQuery).not.toHaveBeenCalled()
  })

  it('falls back to the brokerage_connections row for a genuine self-custody customer (executor armed)', async () => {
    ;(isExecutorArmed as any).mockReturnValue(true)
    ;(customerQuery as any)
      .mockResolvedValueOnce([
        { id: 'c1', provider: 'snaptrade', authorization_id: 'auth1', brokerage_slug: 'tastytrade', account_name: null, status: 'active', created_at: '2026-01-01', last_synced_at: null },
      ])
      .mockResolvedValueOnce([
        { id: 'a1', connection_id: 'c1', display_mask: '••••9988', eligibility: 'eligible', ineligible_reason: null, buying_power_cents: '100000' },
      ])
    const res = await GET()
    const body = await res.json()
    expect(body.connections[0].broker).toBe('tastytrade')
    expect(body.connections[0].accounts[0].mask).toBe('••••9988')
    // Armed means a genuine self-custody path — never ask the house-account resolver.
    expect(resolveExecutingBroker).not.toHaveBeenCalled()
  })

  it('falls back to the brokerage_connections row when no bot resolves to a house account', async () => {
    ;(resolveExecutingBroker as any).mockResolvedValue(null)
    ;(customerQuery as any).mockResolvedValueOnce([]).mockResolvedValueOnce([])
    const res = await GET()
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.connections).toEqual([])
  })
})
