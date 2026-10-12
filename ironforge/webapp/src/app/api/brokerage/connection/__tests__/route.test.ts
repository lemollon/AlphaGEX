import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'
import { SnaptradeError } from 'snaptrade-typescript-sdk'

/**
 * Bug fix (brokerage webhook audit): a SnapTrade 404 on removeBrokerageAuthorization — the
 * authorization is already gone upstream — must still fall through to the local cleanup
 * (status='removed', brokerage_connected reset), not a 500 that leaves the row stuck forever.
 */

vi.mock('@/lib/auth/mobile-step-up', () => ({
  requireIdentityWithStepUp: vi.fn(async () => ({ identity: { customerId: 'cust1' }, error: null })),
}))

const removeBrokerageAuthorization = vi.fn()
vi.mock('@/lib/snaptrade', () => ({
  isSnapTradeConfigured: () => true,
  getSnapTrade: () => ({ connections: { removeBrokerageAuthorization } }),
}))

vi.mock('@/lib/crypto/secret-box', () => ({
  decryptSecret: (s: string) => s,
}))

const executed: Array<{ sql: string; params: unknown[] }> = []
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerQuery: vi.fn(async () => [
    { id: 'user1', snaptrade_user_id: 'st-user-1', snaptrade_user_secret: 'enc-secret' },
  ]),
  customerExecute: vi.fn(async (sql: string, params: unknown[] = []) => {
    executed.push({ sql, params })
    return []
  }),
}))

const { DELETE } = await import('../route')

beforeEach(() => {
  executed.length = 0
  removeBrokerageAuthorization.mockReset()
})

function deleteRequest(authorizationId: string) {
  return new NextRequest('https://x/api/brokerage/connection', {
    method: 'DELETE',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ authorizationId }),
  })
}

describe('DELETE /api/brokerage/connection', () => {
  it('treats a SnapTrade 404 (already removed upstream) as success and still runs local cleanup', async () => {
    const fakeAxiosError = {
      message: 'Not Found',
      code: 'ERR_BAD_REQUEST',
      config: { method: 'delete', url: '/connections/x' },
      response: { status: 404, statusText: 'Not Found' },
    }
    const snaptradeError = new SnaptradeError(fakeAxiosError as any, {}, {})
    removeBrokerageAuthorization.mockRejectedValue(snaptradeError)

    const res = await DELETE(deleteRequest('auth-404'))
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.ok).toBe(true)

    const connUpdate = executed.find((e) => e.sql.includes('UPDATE brokerage_connections'))
    expect(connUpdate).toBeDefined()
    expect(connUpdate!.sql).toContain("status = 'removed'")
    expect(connUpdate!.params).toEqual(['user1', 'auth-404'])
  })

  it('still 500s on a genuine (non-404) SnapTrade failure, without running local cleanup', async () => {
    const fakeAxiosError = {
      message: 'Internal Server Error',
      code: 'ERR_BAD_RESPONSE',
      config: { method: 'delete', url: '/connections/x' },
      response: { status: 500, statusText: 'Internal Server Error' },
    }
    const snaptradeError = new SnaptradeError(fakeAxiosError as any, {}, {})
    removeBrokerageAuthorization.mockRejectedValue(snaptradeError)

    const res = await DELETE(deleteRequest('auth-500'))
    expect(res.status).toBe(500)
    expect(executed.find((e) => e.sql.includes('UPDATE brokerage_connections'))).toBeUndefined()
  })

  it('still runs local cleanup on a clean SnapTrade success', async () => {
    removeBrokerageAuthorization.mockResolvedValue({})
    const res = await DELETE(deleteRequest('auth-ok'))
    expect(res.status).toBe(200)
    const connUpdate = executed.find((e) => e.sql.includes('UPDATE brokerage_connections'))
    expect(connUpdate).toBeDefined()
  })
})
