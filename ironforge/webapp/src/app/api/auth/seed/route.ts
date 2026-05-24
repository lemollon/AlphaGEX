import { NextRequest, NextResponse } from 'next/server'
import { randomBytes } from 'crypto'
import { dbQuery, dbExecute, escapeSql } from '@/lib/db'
import { hashPassword } from '@/lib/auth/password'
import { safeEqual } from '@/lib/auth/session'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const SEED_USERS = [
  { username: 'user', name: 'User', person: 'User' },
  { username: 'matt', name: 'Matt', person: 'Matt' },
  { username: 'logan', name: 'Logan', person: 'Logan' },
]

function genPassword(): string {
  return randomBytes(12).toString('base64url')
}

export async function POST(req: NextRequest) {
  const expected = process.env.IRONFORGE_SEED_TOKEN
  const provided = req.headers.get('x-ironforge-seed-token')
  if (!expected || !provided || !safeEqual(provided, expected)) {
    return NextResponse.json({ error: 'forbidden' }, { status: 403 })
  }
  try {
    const body = await req.json().catch(() => ({} as Record<string, unknown>))
    const overrides = (body.passwords as Record<string, string>) || {}
    const created: Array<{ username: string; password: string | null; status: string }> = []

    for (const u of SEED_USERS) {
      const existing = await dbQuery<{ id: number }>(
        `SELECT id FROM ironforge_users WHERE username = '${escapeSql(u.username)}' LIMIT 1`,
      )
      if (existing.length > 0) {
        created.push({ username: u.username, password: null, status: 'exists' })
        continue
      }
      const plain = overrides[u.username] || genPassword()
      const hash = await hashPassword(plain)
      await dbExecute(
        `INSERT INTO ironforge_users (username, name, person, password_hash, must_change_password)
         VALUES ($1, $2, $3, $4, TRUE)`,
        [u.username, u.name, u.person, hash],
      )
      created.push({ username: u.username, password: plain, status: 'created' })
    }
    return NextResponse.json({ ok: true, users: created })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
