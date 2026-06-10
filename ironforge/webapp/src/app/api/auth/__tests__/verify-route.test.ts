import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(),
  customerTransaction: vi.fn(),
  CustomersDbNotConfiguredError: class extends Error {},
}))

import {
  isCustomersDbConfigured,
  customerQuery,
  customerExecute,
  customerTransaction,
} from '@/lib/customers-db'
import { GET } from '../verify/route'

function get(query: string) {
  return new NextRequest(`https://app.test/api/auth/verify${query}`)
}

function tokenRow(over: Record<string, unknown> = {}) {
  return {
    id: 'tok-1',
    user_id: 'user-1',
    token_hash: 'hash',
    expires_at: new Date(Date.now() + 3600_000).toISOString(),
    consumed_at: null,
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
  ;(customerExecute as any).mockResolvedValue(1)
})

function loc(res: Response): string {
  return res.headers.get('location') || ''
}

describe('GET /api/auth/verify', () => {
  it('redirects with an error when the token is missing', async () => {
    const res = await GET(get(''))
    expect(loc(res)).toContain('verifyError=1')
    expect(customerTransaction).not.toHaveBeenCalled()
  })

  it('redirects with an error for an unknown token', async () => {
    ;(customerQuery as any).mockResolvedValue([])
    const res = await GET(get('?token=abc'))
    expect(loc(res)).toContain('verifyError=1')
    expect(customerTransaction).not.toHaveBeenCalled()
  })

  it('redirects with an error for an expired token', async () => {
    ;(customerQuery as any).mockResolvedValue([
      tokenRow({ expires_at: new Date(Date.now() - 1000).toISOString() }),
    ])
    const res = await GET(get('?token=abc'))
    expect(loc(res)).toContain('verifyError=1')
    expect(customerTransaction).not.toHaveBeenCalled()
  })

  it('redirects with an error for an already-consumed token', async () => {
    ;(customerQuery as any).mockResolvedValue([
      tokenRow({ consumed_at: new Date().toISOString() }),
    ])
    const res = await GET(get('?token=abc'))
    expect(loc(res)).toContain('verifyError=1')
    expect(customerTransaction).not.toHaveBeenCalled()
  })

  it('verifies a valid token: updates user + token, logs EMAIL_VERIFIED, redirects verified=1', async () => {
    ;(customerQuery as any).mockResolvedValue([tokenRow()])
    const run = vi.fn(async () => [])
    ;(customerTransaction as any).mockImplementation(async (fn: any) => fn(run))

    const res = await GET(get('?token=abc'))
    expect(loc(res)).toContain('verified=1')

    const sqls = run.mock.calls.map((c: any[]) => String(c[0]))
    expect(sqls.some((s) => /UPDATE users/i.test(s) && /email_verified/i.test(s))).toBe(true)
    expect(sqls.some((s) => /email_verification_tokens/i.test(s) && /consumed_at/i.test(s))).toBe(true)

    const auditCall = (customerExecute as any).mock.calls.find((c: any[]) =>
      String(c[0]).includes('audit_events'),
    )
    expect(JSON.stringify(auditCall)).toContain('EMAIL_VERIFIED')
    expect(JSON.stringify(auditCall)).toContain('user-1')
  })
})
