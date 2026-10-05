import { NextResponse } from 'next/server'
import { resolveEmberOwner } from '@/lib/ember-entitlement'
import { getEmberStatus } from '@/lib/ember-trades'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/ember/status — REFLEX's last reported state + heartbeat (synced
 * in by reflex_sync.py), for the signed-in customer who owns Ember. See
 * /api/ember/trades for the matching trade book and the same 403-not-401
 * reasoning.
 */
export async function GET() {
  const owner = await resolveEmberOwner()
  if (!owner) {
    return NextResponse.json({ ok: false, error: 'not entitled to Ember', status: null }, { status: 403 })
  }
  try {
    const status = await getEmberStatus()
    return NextResponse.json({ ok: true, status })
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ ok: false, error: msg, status: null }, { status: 500 })
  }
}
