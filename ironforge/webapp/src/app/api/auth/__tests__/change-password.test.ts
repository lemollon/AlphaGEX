import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * /api/auth/change-password is the CUSTOMER password change.
 *
 * It used to read the operator session and write to `ironforge_users`, while the
 * only page calling it (/change-password) is a customer screen — so a customer
 * got a 401 every time and could never change their password. These tests now
 * exercise the customer session and the customers database, which is where
 * customer password hashes actually live.
 */
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(),
}))
vi.mock('@/lib/auth/password', () => ({ verifyPassword: vi.fn(), hashPassword: vi.fn() }))
vi.mock('@/lib/auth/customer-session-server', () => ({ getCustomerSession: vi.fn() }))

import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { verifyPassword, hashPassword } from '@/lib/auth/password'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { POST } from '../change-password/route'

let session: Record<string, unknown> = { customerId: 'cus_123' }

function post(body: unknown) {
  return new NextRequest('https://app.test/api/auth/change-password', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

beforeEach(() => {
  vi.mocked(customerQuery).mockReset()
  vi.mocked(customerExecute).mockReset()
  vi.mocked(verifyPassword).mockReset()
  vi.mocked(hashPassword).mockReset()
  vi.mocked(isCustomersDbConfigured).mockReturnValue(true)
  vi.mocked(customerExecute).mockResolvedValue(1 as never)
  session = { customerId: 'cus_123' }
  // mockImplementation reads `session` at call time, so the 401 test can reassign it.
  vi.mocked(getCustomerSession).mockImplementation(async () => session as never)
})

describe('POST /api/auth/change-password (customer)', () => {
  it('changes the password when the current one is correct', async () => {
    vi.mocked(customerQuery).mockResolvedValue([{ password_hash: 'old' }] as never)
    vi.mocked(verifyPassword).mockResolvedValue(true)
    vi.mocked(hashPassword).mockResolvedValue('newhash')

    const res = await POST(post({ currentPassword: 'old', newPassword: 'a-very-long-password' }))

    expect(res.status).toBe(200)
    expect(customerExecute).toHaveBeenCalledOnce()
    expect(hashPassword).toHaveBeenCalledWith('a-very-long-password')
    // Scoped to the session's own customer id — never a value from the body.
    expect(vi.mocked(customerExecute).mock.calls[0][1]).toEqual(['newhash', 'cus_123'])
  })

  it('rejects a short new password with 400', async () => {
    const res = await POST(post({ currentPassword: 'old', newPassword: 'short' }))
    expect(res.status).toBe(400)
    expect(customerExecute).not.toHaveBeenCalled()
  })

  it('rejects reusing the current password with 400', async () => {
    const same = 'a-very-long-password'
    const res = await POST(post({ currentPassword: same, newPassword: same }))
    expect(res.status).toBe(400)
    expect(customerExecute).not.toHaveBeenCalled()
  })

  it('rejects a wrong current password with 400', async () => {
    vi.mocked(customerQuery).mockResolvedValue([{ password_hash: 'old' }] as never)
    vi.mocked(verifyPassword).mockResolvedValue(false)

    const res = await POST(post({ currentPassword: 'wrong', newPassword: 'a-very-long-password' }))

    expect(res.status).toBe(400)
    expect(customerExecute).not.toHaveBeenCalled()
  })

  it('rejects when there is no customer session with 401', async () => {
    session = {}
    const res = await POST(post({ currentPassword: 'old', newPassword: 'a-very-long-password' }))
    expect(res.status).toBe(401)
    expect(customerQuery).not.toHaveBeenCalled()
  })

  it('degrades to 503 when the customers database is not configured', async () => {
    vi.mocked(isCustomersDbConfigured).mockReturnValue(false)
    const res = await POST(post({ currentPassword: 'old', newPassword: 'a-very-long-password' }))
    expect(res.status).toBe(503)
    expect(customerExecute).not.toHaveBeenCalled()
  })
})
