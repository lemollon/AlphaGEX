import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db'
import { getSession } from '@/lib/auth/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  const session = await getSession()
  if (!session.userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }
  const rows = await dbQuery<{ must_change_password: boolean }>(
    `SELECT must_change_password FROM ironforge_users WHERE id = ${session.userId} LIMIT 1`,
  )
  return NextResponse.json({
    username: session.username ?? null,
    name: session.name ?? null,
    person: session.person ?? null,
    mustChangePassword: rows[0]?.must_change_password ?? false,
  })
}
