import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * Bug fix (brokerage webhook audit): CONNECTION_FIXED/ADDED/UPDATED must clear
 * reauthorization_required + last_error_* and restore users.brokerage_connected — and must
 * never run a blanket UPDATE across a user's connections when authorizationId is missing
 * (which could reactivate an unrelated, previously-removed connection row).
 */

process.env.SNAPTRADE_WEBHOOK_SECRET = 'legacy-secret-for-tests'

const executed: Array<{ sql: string; params: unknown[] }> = []

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerExecute: vi.fn(async (sql: string, params: unknown[] = []) => {
    executed.push({ sql, params })
    return []
  }),
  customerQuery: vi.fn(async () => []),
}))

vi.mock('@/lib/crm/outbox', () => ({
  enqueueCrmEvent: vi.fn(async () => {}),
  recurringEventId: (s: string) => s,
}))

vi.mock('@/lib/crm/brokerage-status', () => ({
  mapBrokerageStatusToCrm: () => ({ connectionStatus: 'disabled' }),
}))

const { POST } = await import('../route')

beforeEach(() => {
  executed.length = 0
})

function webhookRequest(body: Record<string, unknown>) {
  return new NextRequest('https://x/api/brokerage/webhook', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ webhookSecret: 'legacy-secret-for-tests', ...body }),
  })
}

describe('POST /api/brokerage/webhook — CONNECTION_FIXED/ADDED/UPDATED', () => {
  it('CONNECTION_FIXED clears reauthorization_required/last_error_* and restores brokerage_connected', async () => {
    const res = await POST(
      webhookRequest({
        eventType: 'CONNECTION_FIXED',
        userId: 'st-user-1',
        brokerageAuthorizationId: 'auth-1',
      }),
    )
    expect(res.status).toBe(200)

    const connUpdate = executed.find((e) => e.sql.includes('UPDATE brokerage_connections'))
    expect(connUpdate).toBeDefined()
    expect(connUpdate!.sql).toContain('reauthorization_required = FALSE')
    expect(connUpdate!.sql).toContain('last_error_code = NULL')
    expect(connUpdate!.sql).toContain('last_error_summary = NULL')
    expect(connUpdate!.sql).toContain('authorization_id = $2')
    expect(connUpdate!.params).toEqual(['st-user-1', 'auth-1'])

    const userUpdate = executed.find((e) => e.sql.includes('UPDATE users'))
    expect(userUpdate).toBeDefined()
    expect(userUpdate!.sql).toContain('brokerage_connected = TRUE')
  })

  it('CONNECTION_ADDED with a missing authorizationId does NOT run a blanket update', async () => {
    const res = await POST(
      webhookRequest({
        eventType: 'CONNECTION_ADDED',
        userId: 'st-user-2',
        // brokerageAuthorizationId intentionally omitted
      }),
    )
    expect(res.status).toBe(200)

    // No UPDATE of any kind should have run for this user — the specific-row guard must skip.
    expect(executed).toHaveLength(0)
  })

  it('CONNECTION_UPDATED with an authorizationId only touches that row, never a blanket update', async () => {
    await POST(
      webhookRequest({
        eventType: 'CONNECTION_UPDATED',
        userId: 'st-user-3',
        brokerageAuthorizationId: 'auth-3',
      }),
    )
    const connUpdate = executed.find((e) => e.sql.includes('UPDATE brokerage_connections'))
    expect(connUpdate).toBeDefined()
    // Must filter on the specific authorization_id — never "($2::text IS NULL OR ...)" which
    // would fall through to every row for the user when the id is absent.
    expect(connUpdate!.sql).not.toContain('IS NULL OR')
  })
})

describe('POST /api/brokerage/webhook — CONNECTION_DELETED/REMOVED', () => {
  it('CONNECTION_DELETED with an authorizationId only marks that one row removed', async () => {
    await POST(
      webhookRequest({
        eventType: 'CONNECTION_DELETED',
        userId: 'st-user-4',
        brokerageAuthorizationId: 'auth-4',
      }),
    )
    const connUpdate = executed.find((e) => e.sql.includes('UPDATE brokerage_connections'))
    expect(connUpdate).toBeDefined()
    expect(connUpdate!.sql).toContain('authorization_id = $2')
    expect(connUpdate!.sql).not.toContain('IS NULL OR')
    expect(connUpdate!.params).toEqual(['st-user-4', 'auth-4', 'removed'])
  })

  it('CONNECTION_REMOVED with a missing authorizationId does NOT run a blanket update (regression: previously flipped every connection for the user to removed)', async () => {
    const res = await POST(
      webhookRequest({
        eventType: 'CONNECTION_REMOVED',
        userId: 'st-user-5',
        // brokerageAuthorizationId intentionally omitted
      }),
    )
    expect(res.status).toBe(200)
    expect(executed).toHaveLength(0)
  })
})
