import { NextRequest, NextResponse } from 'next/server'
import { isValidUsername } from '@/lib/signup-validation'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/public/username-check?u=<name> — live availability for the signup form
 * (same pattern as /api/public/promo). Usernames are public handles, so
 * availability is not sensitive. The signup POST re-checks under the unique
 * index — this endpoint is UX, not enforcement.
 */
export async function GET(req: NextRequest) {
  const u = String(req.nextUrl.searchParams.get('u') ?? '').trim()
  if (!isValidUsername(u)) {
    return NextResponse.json({ ok: true, valid: false, available: false })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, valid: true, available: true })
  }
  try {
    const rows = await customerQuery<{ id: string }>(
      `SELECT id FROM users WHERE lower(username) = lower($1) LIMIT 1`,
      [u],
    )
    return NextResponse.json({ ok: true, valid: true, available: rows.length === 0 })
  } catch {
    // Fail soft: the form continues, the signup POST is the enforcement point.
    return NextResponse.json({ ok: true, valid: true, available: true })
  }
}
