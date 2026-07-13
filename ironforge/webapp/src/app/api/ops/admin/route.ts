import { NextRequest, NextResponse } from 'next/server'
import { getIronSession } from 'iron-session'
import { cookies } from 'next/headers'
import { sessionOptions, safeEqual, type SessionData } from '@/lib/auth/session'
import { publicOrigin } from '@/lib/public-origin'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Magic admin link — credential-free operator access for the site owner
 * while developing. Bookmark once:
 *
 *   /api/ops/admin?key=<IRONFORGE_ADMIN_KEY>
 *
 * One click mints a full operator session (30 days, same cookie as
 * /ops/login), so the floating ADMIN badge and every operator surface just
 * work. The key is a long random secret in the Render env — unguessable and
 * shared with no one. If IRONFORGE_ADMIN_KEY is unset the route is inert.
 * The comparison is constant-time. Nothing is revealed on a wrong key.
 */
export async function GET(req: NextRequest) {
  const expected = process.env.IRONFORGE_ADMIN_KEY
  const key = req.nextUrl.searchParams.get('key') ?? ''

  if (!expected || !key || !safeEqual(key, expected)) {
    return NextResponse.json({ ok: false, error: 'Not found.' }, { status: 404 })
  }

  const session = await getIronSession<SessionData>(cookies(), sessionOptions)
  session.userId = 999_999 // sentinel — no operators-table row; middleware only checks truthiness
  session.username = 'admin-link'
  session.name = 'Admin'
  await session.save()

  const next = req.nextUrl.searchParams.get('next') ?? '/'
  const dest = next.startsWith('/') && !next.startsWith('//') ? next : '/'
  return NextResponse.redirect(new URL(dest, publicOrigin(req)))
}
