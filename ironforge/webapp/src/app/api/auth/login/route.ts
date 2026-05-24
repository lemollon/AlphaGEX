import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, escapeSql } from '@/lib/db'
import { verifyPassword } from '@/lib/auth/password'
import { getSession } from '@/lib/auth/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface UserRow {
  id: number
  username: string
  name: string
  person: string | null
  password_hash: string
  is_active: boolean
  must_change_password: boolean
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({} as Record<string, unknown>))
    const username = String(body.username || '').trim().toLowerCase()
    const password = String(body.password || '')
    if (!username || !password) {
      return NextResponse.json({ error: 'Username and password required' }, { status: 400 })
    }

    const rows = await dbQuery<UserRow>(
      `SELECT id, username, name, person, password_hash, is_active, must_change_password
       FROM ironforge_users WHERE username = '${escapeSql(username)}' LIMIT 1`,
    )
    const user = rows[0]
    const ok = !!user && user.is_active && (await verifyPassword(password, user.password_hash))
    if (!ok) {
      return NextResponse.json({ error: 'Invalid username or password' }, { status: 401 })
    }

    const session = await getSession()
    session.userId = user.id
    session.username = user.username
    session.name = user.name
    session.person = user.person
    await session.save()

    // Fire-and-forget audit stamp: a transient failure on this write must not fail
    // an otherwise-successful login (the session is already committed above).
    void dbExecute(
      `UPDATE ironforge_users SET last_login_at = NOW(), updated_at = NOW() WHERE id = ${user.id}`,
    ).catch(() => {})

    return NextResponse.json({ ok: true, mustChangePassword: user.must_change_password })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
