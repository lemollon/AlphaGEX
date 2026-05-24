import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute } from '@/lib/db'
import { getSession } from '@/lib/auth/server'
import { verifyPassword, hashPassword } from '@/lib/auth/password'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MIN_LEN = 12

export async function POST(req: NextRequest) {
  try {
    const session = await getSession()
    if (!session.userId) {
      return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    }
    const body = await req.json().catch(() => ({} as Record<string, unknown>))
    const currentPassword = String(body.currentPassword || '')
    const newPassword = String(body.newPassword || '')
    if (newPassword.length < MIN_LEN) {
      return NextResponse.json({ error: `New password must be at least ${MIN_LEN} characters` }, { status: 400 })
    }
    const rows = await dbQuery<{ password_hash: string }>(
      `SELECT password_hash FROM ironforge_users WHERE id = ${session.userId} LIMIT 1`,
    )
    const hash = rows[0]?.password_hash
    if (!hash || !(await verifyPassword(currentPassword, hash))) {
      return NextResponse.json({ error: 'Current password is incorrect' }, { status: 400 })
    }
    const newHash = await hashPassword(newPassword)
    await dbExecute(
      `UPDATE ironforge_users SET password_hash = $1, must_change_password = FALSE, updated_at = NOW() WHERE id = ${session.userId}`,
      [newHash],
    )
    return NextResponse.json({ ok: true })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
