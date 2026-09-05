import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'
import { hashCode } from '@/lib/auth/verification-token'

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(),
  customerTransaction: vi.fn(),
  CustomersDbNotConfiguredError: class extends Error {},
}))

import { isCustomersDbConfigured, customerQuery, customerExecute, customerTransaction } from '@/lib/customers-db'
import { POST } from '../verify-code/route'

function post(body: unknown) {
  return new NextRequest('https://app.test/api/auth/verify-code', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-forwarded-for': '203.0.113.9' },
    body: JSON.stringify(body),
  })
}

function tokenRow(userId: string, code: string, over: Record<string, unknown> = {}) {
  return {
    id: 'tok-1',
    user_id: userId,
    code_hash: hashCode(code, userId),
    code_expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    code_attempts: 0,
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
  ;(customerExecute as any).mockResolvedValue(1)
})

describe('POST /api/auth/verify-code', () => {
  it('400 for an invalid email', async () => {
    const res = await POST(post({ email: 'nope', code: '123456' }))
    expect(res.status).toBe(400)
    expect(customerQuery).not.toHaveBeenCalled()
  })

  it('400 for a non-6-digit code', async () => {
    const res = await POST(post({ email: 'a@b.com', code: '12' }))
    expect(res.status).toBe(400)
    expect(customerQuery).not.toHaveBeenCalled()
  })

  it('503 when the customer DB is not configured', async () => {
    ;(isCustomersDbConfigured as any).mockReturnValue(false)
    const res = await POST(post({ email: 'a@b.com', code: '123456' }))
    expect(res.status).toBe(503)
  })

  it('400 generic invalid_code for an unknown email (no enumeration)', async () => {
    ;(customerQuery as any).mockResolvedValue([])
    const res = await POST(post({ email: 'ghost@b.com', code: '123456' }))
    expect(res.status).toBe(400)
    const data = await res.json()
    expect(data.code).toBe('invalid_code')
  })

  it('400 when no active code row exists for the user', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) =>
      /FROM users/i.test(sql) ? [{ id: 'u1', onboarding_step: null }] : [],
    )
    const res = await POST(post({ email: 'ada@b.com', code: '123456' }))
    expect(res.status).toBe(400)
    expect(customerTransaction).not.toHaveBeenCalled()
  })

  it('400 for an expired code', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) =>
      /FROM users/i.test(sql)
        ? [{ id: 'u1', onboarding_step: null }]
        : [tokenRow('u1', '123456', { code_expires_at: new Date(Date.now() - 1000).toISOString() })],
    )
    const res = await POST(post({ email: 'ada@b.com', code: '123456' }))
    expect(res.status).toBe(400)
    expect(customerTransaction).not.toHaveBeenCalled()
  })

  it('410 when a code is already locked (5+ prior attempts)', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) =>
      /FROM users/i.test(sql) ? [{ id: 'u1', onboarding_step: null }] : [tokenRow('u1', '123456', { code_attempts: 5 })],
    )
    const res = await POST(post({ email: 'ada@b.com', code: '123456' }))
    expect(res.status).toBe(410)
    const data = await res.json()
    expect(data.code).toBe('code_locked')
  })

  it('400 + increments attempts on a wrong code', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) =>
      /FROM users/i.test(sql) ? [{ id: 'u1', onboarding_step: null }] : [tokenRow('u1', '123456', { code_attempts: 1 })],
    )
    const res = await POST(post({ email: 'ada@b.com', code: '000000' }))
    expect(res.status).toBe(400)
    const data = await res.json()
    expect(data.error).toContain('3 attempts left')
    const updateCall = (customerExecute as any).mock.calls.find((c: any[]) =>
      /UPDATE email_verification_tokens SET code_attempts/i.test(String(c[0])),
    )
    expect(updateCall?.[1]).toEqual([2, 'tok-1'])
  })

  it('410 code_locked on the 5th wrong attempt (attempts reaches MAX)', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) =>
      /FROM users/i.test(sql) ? [{ id: 'u1', onboarding_step: null }] : [tokenRow('u1', '123456', { code_attempts: 4 })],
    )
    const res = await POST(post({ email: 'ada@b.com', code: '000000' }))
    expect(res.status).toBe(410)
    const data = await res.json()
    expect(data.code).toBe('code_locked')
  })

  it('verifies a correct code: consumes the row, flips the user, writes EMAIL_VERIFIED audit', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) =>
      /FROM users/i.test(sql) ? [{ id: 'u1', onboarding_step: null }] : [tokenRow('u1', '123456')],
    )
    const run = vi.fn(async () => [])
    ;(customerTransaction as any).mockImplementation(async (fn: any) => fn(run))

    const res = await POST(post({ email: 'ada@b.com', code: '123456' }))
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.ok).toBe(true)

    const sqls = run.mock.calls.map((c: any[]) => String(c[0]))
    expect(sqls.some((s) => /UPDATE users/i.test(s) && /email_verified/i.test(s))).toBe(true)
    expect(sqls.some((s) => /email_verification_tokens/i.test(s) && /consumed_at/i.test(s))).toBe(true)

    const auditCall = (customerExecute as any).mock.calls.find((c: any[]) => String(c[0]).includes('audit_events'))
    expect(JSON.stringify(auditCall)).toContain('EMAIL_VERIFIED')
    expect(JSON.stringify(auditCall)).toContain('u1')
  })

  it('429 when the same email is hammered past the rate limit', async () => {
    ;(customerQuery as any).mockResolvedValue([])
    let last: Response | null = null
    for (let i = 0; i < 25; i++) {
      last = await POST(post({ email: 'flood@b.com', code: '123456' }))
    }
    expect(last?.status).toBe(429)
  })
})
