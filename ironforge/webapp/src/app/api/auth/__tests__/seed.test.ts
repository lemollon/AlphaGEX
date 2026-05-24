import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/db', () => ({
  dbQuery: vi.fn(),
  dbExecute: vi.fn(),
  escapeSql: (s: string) => s.replace(/'/g, "''"),
}))
vi.mock('@/lib/auth/password', () => ({ hashPassword: vi.fn() }))

import { dbQuery, dbExecute } from '@/lib/db'
import { hashPassword } from '@/lib/auth/password'
import { POST } from '../seed/route'

const origToken = process.env.IRONFORGE_SEED_TOKEN
beforeEach(() => {
  vi.mocked(dbQuery).mockReset()
  vi.mocked(dbExecute).mockReset()
  vi.mocked(dbExecute).mockResolvedValue(1)
  vi.mocked(hashPassword).mockResolvedValue('hashed')
  process.env.IRONFORGE_SEED_TOKEN = 'seed-secret'
})
afterEach(() => { process.env.IRONFORGE_SEED_TOKEN = origToken })

function post(token: string | null, body: unknown = {}) {
  const headers: Record<string, string> = { 'content-type': 'application/json' }
  if (token !== null) headers['x-ironforge-seed-token'] = token
  return new NextRequest('https://app.test/api/auth/seed', { method: 'POST', headers, body: JSON.stringify(body) })
}

describe('POST /api/auth/seed', () => {
  it('forbids requests without the seed token', async () => {
    const res = await POST(post(null))
    expect(res.status).toBe(403)
    expect(dbExecute).not.toHaveBeenCalled()
  })

  it('forbids a wrong seed token', async () => {
    const res = await POST(post('wrong'))
    expect(res.status).toBe(403)
  })

  it('creates missing users and returns generated passwords once', async () => {
    vi.mocked(dbQuery).mockResolvedValue([] as never) // no existing users
    const res = await POST(post('seed-secret'))
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json.users).toHaveLength(3)
    expect(json.users.every((u: { status: string }) => u.status === 'created')).toBe(true)
    expect(json.users.every((u: { password: string }) => typeof u.password === 'string' && u.password.length > 0)).toBe(true)
    expect(dbExecute).toHaveBeenCalledTimes(3)
  })

  it('is idempotent — skips users that already exist', async () => {
    vi.mocked(dbQuery).mockResolvedValue([{ id: 1 }] as never) // every user exists
    const res = await POST(post('seed-secret'))
    const json = await res.json()
    expect(json.users.every((u: { status: string }) => u.status === 'exists')).toBe(true)
    expect(dbExecute).not.toHaveBeenCalled()
  })
})
