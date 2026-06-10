import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(),
}))
vi.mock('@/lib/email', () => ({
  isEmailConfigured: vi.fn(() => true),
  sendVerificationEmail: vi.fn(async () => ({ sent: true })),
}))

import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { sendVerificationEmail } from '@/lib/email'
import { POST } from '../resend-verification/route'

function post(body: unknown) {
  return new NextRequest('https://app.test/api/auth/resend-verification', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
  ;(customerExecute as any).mockResolvedValue(1)
})

describe('POST /api/auth/resend-verification', () => {
  it('400 for a missing/invalid email', async () => {
    const res = await POST(post({ email: 'not-an-email' }))
    expect(res.status).toBe(400)
  })

  it('503 when the customer DB is not configured', async () => {
    ;(isCustomersDbConfigured as any).mockReturnValue(false)
    const res = await POST(post({ email: 'a@b.com' }))
    expect(res.status).toBe(503)
  })

  it('returns generic ok and sends nothing for an unknown email (no enumeration)', async () => {
    ;(customerQuery as any).mockResolvedValue([])
    const res = await POST(post({ email: 'ghost@b.com' }))
    expect(res.status).toBe(200)
    expect((await res.json()).ok).toBe(true)
    expect(sendVerificationEmail).not.toHaveBeenCalled()
    expect(customerExecute).not.toHaveBeenCalled()
  })

  it('issues a fresh token and emails an existing unverified user', async () => {
    ;(customerQuery as any).mockResolvedValue([
      { id: 'u1', first_name: 'Ada', email_verified: false },
    ])
    const res = await POST(post({ email: 'Ada@B.com' }))
    expect(res.status).toBe(200)
    const tokenInsert = (customerExecute as any).mock.calls.find((c: any[]) =>
      /INSERT INTO email_verification_tokens/i.test(String(c[0])),
    )
    expect(tokenInsert).toBeTruthy()
    expect(sendVerificationEmail).toHaveBeenCalledTimes(1)
    expect((sendVerificationEmail as any).mock.calls[0][0].to).toBe('ada@b.com')
  })

  it('does nothing for an already-verified user but still returns ok', async () => {
    ;(customerQuery as any).mockResolvedValue([
      { id: 'u1', first_name: 'Ada', email_verified: true },
    ])
    const res = await POST(post({ email: 'ada@b.com' }))
    expect(res.status).toBe(200)
    expect(sendVerificationEmail).not.toHaveBeenCalled()
  })
})
