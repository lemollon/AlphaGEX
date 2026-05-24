import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

// Inline factories (no outer-variable refs) to avoid vitest's hoisting TDZ trap.
vi.mock('@/lib/db', () => ({
  dbQuery: vi.fn(),
  dbExecute: vi.fn(),
  escapeSql: (s: string) => s.replace(/'/g, "''"),
}))
vi.mock('@/lib/auth/password', () => ({ verifyPassword: vi.fn() }))
vi.mock('@/lib/auth/server', () => ({ getSession: vi.fn() }))

import { dbQuery, dbExecute } from '@/lib/db'
import { verifyPassword } from '@/lib/auth/password'
import { getSession } from '@/lib/auth/server'
import { POST } from '../login/route'

const save = vi.fn()
const sessionObj: Record<string, unknown> = {}

function post(body: unknown) {
  return new NextRequest('https://app.test/api/auth/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

const activeUser = {
  id: 7, username: 'matt', name: 'Matt', person: 'Matt',
  password_hash: 'hash', is_active: true, must_change_password: true,
}

beforeEach(() => {
  vi.mocked(dbQuery).mockReset()
  vi.mocked(dbExecute).mockReset()
  vi.mocked(verifyPassword).mockReset()
  save.mockReset()
  for (const k of Object.keys(sessionObj)) delete sessionObj[k]
  sessionObj.save = save
  vi.mocked(getSession).mockResolvedValue(sessionObj as never)
  vi.mocked(dbExecute).mockResolvedValue(1)
})

describe('POST /api/auth/login', () => {
  it('logs in a valid active user and reports mustChangePassword', async () => {
    vi.mocked(dbQuery).mockResolvedValue([activeUser] as never)
    vi.mocked(verifyPassword).mockResolvedValue(true)
    const res = await POST(post({ username: 'Matt', password: 'pw' }))
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json).toEqual({ ok: true, mustChangePassword: true })
    expect(save).toHaveBeenCalledOnce()
    expect(sessionObj.userId).toBe(7)
  })

  it('rejects a wrong password with 401', async () => {
    vi.mocked(dbQuery).mockResolvedValue([activeUser] as never)
    vi.mocked(verifyPassword).mockResolvedValue(false)
    const res = await POST(post({ username: 'matt', password: 'bad' }))
    expect(res.status).toBe(401)
    expect(save).not.toHaveBeenCalled()
  })

  it('rejects an inactive user with 401', async () => {
    vi.mocked(dbQuery).mockResolvedValue([{ ...activeUser, is_active: false }] as never)
    vi.mocked(verifyPassword).mockResolvedValue(true)
    const res = await POST(post({ username: 'matt', password: 'pw' }))
    expect(res.status).toBe(401)
  })

  it('rejects an unknown user with 401', async () => {
    vi.mocked(dbQuery).mockResolvedValue([] as never)
    const res = await POST(post({ username: 'ghost', password: 'pw' }))
    expect(res.status).toBe(401)
  })

  it('rejects a missing body with 400', async () => {
    const res = await POST(post({ username: '' }))
    expect(res.status).toBe(400)
  })
})
