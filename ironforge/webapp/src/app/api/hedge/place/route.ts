import { NextRequest, NextResponse } from 'next/server'
import { hasValidServiceToken } from '@/lib/auth/session'
import { placeHedgeForToday } from '@/lib/hedge/place.server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Trigger today's hedge flow (Phase 3). Service-token gated (operator/internal only).
 * `?dryRun=true` → preview + record only, never places. A real order additionally
 * requires `HEDGE_AUTO_PLACE=true` in the environment (the master arm flag), so even
 * `dryRun=false` is a no-op placement until the operator explicitly arms it.
 */
export async function POST(req: NextRequest) {
  if (!hasValidServiceToken(req.headers.get('x-ironforge-service'))) {
    return NextResponse.json({ ok: false, error: 'forbidden' }, { status: 403 })
  }
  const dryRun = req.nextUrl.searchParams.get('dryRun') === 'true'
  try {
    const result = await placeHedgeForToday({ dryRun })
    return NextResponse.json({ ok: true, dryRun, ...result })
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 })
  }
}
