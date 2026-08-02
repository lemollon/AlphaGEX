import { NextResponse } from 'next/server'
import { MOBILE_SESSION_POLICY } from '@/lib/auth/mobile-policy'

export const runtime = 'nodejs'

/**
 * Session policy (APP-010). Public — it is a set of constants with no account data, and
 * the app needs it before sign-in to size its lock timers. Serving it from the server
 * rather than baking it into the binary means timeouts can be tightened without an app
 * store release.
 */
export async function GET() {
  return NextResponse.json(
    { ok: true, policy: MOBILE_SESSION_POLICY },
    { headers: { 'Cache-Control': 'public, max-age=300' } },
  )
}
