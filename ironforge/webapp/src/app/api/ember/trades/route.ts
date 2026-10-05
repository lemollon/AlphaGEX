import { NextResponse } from 'next/server'
import { resolveEmberOwner } from '@/lib/ember-entitlement'
import { getEmberTrades } from '@/lib/ember-trades'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/ember/trades — EMBER's own trade book (synced in from REFLEX by
 * reflex_sync.py), for the signed-in customer who owns Ember. These are the
 * agent's own trades, not a read of the customer's brokerage account — see
 * EmberWorkspaceClient's copy, which must say the same thing.
 *
 * 403 (not 401) when signed in but not entitled, so the client never has to
 * special-case "logged out" vs "doesn't own Ember" to decide whether to show
 * the honest empty state.
 */
export async function GET() {
  const owner = await resolveEmberOwner()
  if (!owner) {
    return NextResponse.json({ ok: false, error: 'not entitled to Ember', trades: [] }, { status: 403 })
  }
  try {
    const trades = await getEmberTrades()
    return NextResponse.json({ ok: true, trades })
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ ok: false, error: msg, trades: [] }, { status: 500 })
  }
}
