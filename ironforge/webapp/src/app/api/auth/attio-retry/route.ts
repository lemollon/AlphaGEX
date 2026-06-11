import { NextRequest, NextResponse } from 'next/server'
import { hasValidServiceToken } from '@/lib/auth/session'
import { drainAttioSyncQueue, isAttioConfigured } from '@/lib/attio'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Drains the Attio sync retry queue (sub-project E). Re-attempts every pending
 * contact that previously failed to sync. Intended for a scheduled cron or operator
 * trigger — NOT public. Guarded by the internal service token (x-ironforge-service /
 * IRONFORGE_SERVICE_TOKEN); this guard holds even while IRONFORGE_PUBLIC_MODE is on.
 */
export async function POST(req: NextRequest) {
  if (!hasValidServiceToken(req.headers.get('x-ironforge-service'))) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }
  if (!isAttioConfigured()) {
    return NextResponse.json({ ok: true, skipped: true, reason: 'ATTIO_API_KEY not set' })
  }
  try {
    const result = await drainAttioSyncQueue()
    return NextResponse.json({ ok: true, ...result })
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : 'drain failed' },
      { status: 500 },
    )
  }
}
