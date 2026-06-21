import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import { getIronSession } from 'iron-session'
import { sessionOptions, hasValidServiceToken, type SessionData } from '@/lib/auth/session'
import { confirmHedgeForToday, declineHedgeForToday, runHedgeProposal } from '@/lib/hedge/place.server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/** Authorized = valid internal service token OR a logged-in operator (dashboard button). */
async function authorized(req: NextRequest): Promise<boolean> {
  if (hasValidServiceToken(req.headers.get('x-ironforge-service'))) return true
  try {
    const s = await getIronSession<SessionData>(cookies(), sessionOptions)
    return Boolean(s.userId)
  } catch {
    return false
  }
}

/**
 * Hedge actions (Phase 3). REAL-MONEY placement (`?action=confirm`) requires explicit
 * authorization — this is the operator pressing the "Place hedge" button, never the
 * scanner. `?action=decline` dismisses today's proposal. Default re-runs the proposal.
 */
export async function POST(req: NextRequest) {
  if (!(await authorized(req))) {
    return NextResponse.json({ ok: false, error: 'forbidden' }, { status: 403 })
  }
  const action = req.nextUrl.searchParams.get('action')
  try {
    const result =
      action === 'confirm' ? await confirmHedgeForToday()
      : action === 'decline' ? await declineHedgeForToday()
      : await runHedgeProposal()
    return NextResponse.json({ ok: true, action: action ?? 'propose', ...result })
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 })
  }
}
