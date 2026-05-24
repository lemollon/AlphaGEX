import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/db', () => ({ dbQuery: vi.fn(), dbExecute: vi.fn() }))
vi.mock('@/lib/auth/password', () => ({ verifyPassword: vi.fn(), hashPassword: vi.fn() }))
vi.mock('@/lib/auth/server', () => ({ getSession: vi.fn() }))

import { dbQuery, dbExecute } from '@/lib/db'
import { verifyPassword, hashPassword } from '@/lib/auth/password'
import { getSession } from '@/lib/auth/server'
import { POST } from '../change-password/route'

let session: Record<string, unknown> = { userId: 7 }

function post(body: unknown) {
  return new NextRequest('https://app.test/api/auth/change-password', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

beforeEach(() => {
  vi.mocked(dbQuery).mockReset()
  vi.mocked(dbExecute).mockReset()
  vi.mocked(verifyPassword).mockReset()
  vi.mocked(hashPassword).mockReset()
  vi.mocked(dbExecute).mockResolvedValue(1)
  session = { userId: 7 }
  // mockImplementation reads `session` at call time, so the 401 test can reassign it.
  vi.mocked(getSession).mockImplementation(async () => session as never)
})

describe('POST /api/auth/change-password', () => {
  it('changes the password when the current one is correct', async () => {
    vi.mocked(dbQuery).mockResolvedValue([{ password_hash: 'old' }] as never)
    vi.mocked(verifyPassword).mockResolvedValue(true)
    vi.mocked(hashPassword).mockResolvedValue('newhash')
    const res = await POST(post({ currentPassword: 'old', newPassword: 'a-very-long-password' }))
    expect(res.status).toBe(200)
    expect(dbExecute).toHaveBeenCalledOnce()
    expect(hashPassword).toHaveBeenCalledWith('a-very-long-password')
  })

  it('rejects a short new password with 400', async () => {
    const res = await POST(post({ currentPassword: 'old', newPassword: 'short' }))
    expect(res.status).toBe(400)
    expect(dbExecute).not.toHaveBeenCalled()
  })

  it('rejects a wrong current password with 400', async () => {
    vi.mocked(dbQuery).mockResolvedValue([{ password_hash: 'old' }] as never)
    vi.mocked(verifyPassword).mockResolvedValue(false)
    const res = await POST(post({ currentPassword: 'wrong', newPassword: 'a-very-long-password' }))
    expect(res.status).toBe(400)
    expect(dbExecute).not.toHaveBeenCalled()
  })

  it('rejects when there is no session with 401', async () => {
    session = {}
    const res = await POST(post({ currentPassword: 'old', newPassword: 'a-very-long-password' }))
    expect(res.status).toBe(401)
  })
})
