import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(),
  customerTransaction: vi.fn(),
  CustomersDbNotConfiguredError: class extends Error {},
}))
vi.mock('@/lib/auth/password', () => ({ hashPassword: vi.fn(async () => 'bcrypt$hash') }))

import {
  isCustomersDbConfigured,
  customerQuery,
  customerExecute,
  customerTransaction,
} from '@/lib/customers-db'
import { hashPassword } from '@/lib/auth/password'
import { POST } from '../signup/route'

function validBody() {
  return {
    firstName: 'Ada',
    lastName: 'Lovelace',
    email: 'Ada@Example.com',
    phone: '(555) 123-4567',
    state: 'CA',
    password: 'Forge!Strong9x',
    confirmPassword: 'Forge!Strong9x',
    referralCode: 'launch24',
    ageConfirmed: true,
    noAdviceAcknowledged: true,
    electronicCommConsent: true,
  }
}

function post(body: unknown) {
  return new NextRequest('https://app.test/api/auth/signup', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-forwarded-for': '203.0.113.7' },
    body: JSON.stringify(body),
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
  ;(customerExecute as any).mockResolvedValue(1)
})

describe('POST /api/auth/signup', () => {
  it('rejects an invalid payload with 400 and never touches the DB', async () => {
    const res = await POST(post({ ...validBody(), email: 'nope' }))
    expect(res.status).toBe(400)
    const data = await res.json()
    expect(data.ok).toBe(false)
    expect(data.fields?.email).toBeTruthy()
    expect(customerQuery).not.toHaveBeenCalled()
    expect(customerTransaction).not.toHaveBeenCalled()
  })

  it('returns 503 when the customer DB is not configured', async () => {
    ;(isCustomersDbConfigured as any).mockReturnValue(false)
    const res = await POST(post(validBody()))
    expect(res.status).toBe(503)
    const data = await res.json()
    expect(data.ok).toBe(false)
  })

  it('returns 409 + logs DUPLICATE_EMAIL_ATTEMPT for an existing email', async () => {
    ;(customerQuery as any).mockResolvedValue([{ id: 'existing-uuid' }])
    const res = await POST(post(validBody()))
    expect(res.status).toBe(409)
    const data = await res.json()
    expect(data.code).toBe('duplicate_email')
    expect(customerTransaction).not.toHaveBeenCalled()
    const auditCall = (customerExecute as any).mock.calls.find((c: any[]) =>
      String(c[0]).includes('audit_events'),
    )
    expect(auditCall).toBeTruthy()
    expect(JSON.stringify(auditCall)).toContain('DUPLICATE_EMAIL_ATTEMPT')
  })

  it('creates the user + token + ACCOUNT_CREATED audit and returns ok', async () => {
    ;(customerQuery as any).mockResolvedValue([]) // no duplicate
    const run = vi.fn(async (sql: string) =>
      /INSERT INTO users/i.test(sql) ? [{ id: 'new-user-uuid' }] : [],
    )
    ;(customerTransaction as any).mockImplementation(async (fn: any) => fn(run))

    const res = await POST(post(validBody()))
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.ok).toBe(true)

    expect(hashPassword).toHaveBeenCalledWith('Forge!Strong9x')
    // transaction inserted a user and a verification token
    const sqls = run.mock.calls.map((c: any[]) => String(c[0]))
    expect(sqls.some((s) => /INSERT INTO users/i.test(s))).toBe(true)
    expect(sqls.some((s) => /INSERT INTO email_verification_tokens/i.test(s))).toBe(true)
    // ACCOUNT_CREATED audit written for the new user id
    const auditCall = (customerExecute as any).mock.calls.find((c: any[]) =>
      String(c[0]).includes('audit_events'),
    )
    expect(JSON.stringify(auditCall)).toContain('ACCOUNT_CREATED')
    expect(JSON.stringify(auditCall)).toContain('new-user-uuid')
  })

  it('stores the email lowercased and the password only as a hash', async () => {
    ;(customerQuery as any).mockResolvedValue([])
    const run = vi.fn(async (sql: string) =>
      /INSERT INTO users/i.test(sql) ? [{ id: 'new-user-uuid' }] : [],
    )
    ;(customerTransaction as any).mockImplementation(async (fn: any) => fn(run))

    await POST(post(validBody()))
    const userInsert = run.mock.calls.find((c: any[]) => /INSERT INTO users/i.test(String(c[0])))
    const params = userInsert?.[1] as any[]
    expect(params).toContain('ada@example.com')
    expect(params).toContain('bcrypt$hash')
    expect(params).not.toContain('Forge!Strong9x')
  })
})
