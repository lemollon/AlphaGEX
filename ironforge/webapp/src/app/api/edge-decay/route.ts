import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { getEdgeDecaySnapshot } from '@/lib/edge-decay'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/edge-decay — operator surface for the edge-decay CUSUM alarm
 * (FLINT, CallDiag, EBB). Read-only: current EDGE_DECAY_MODE, each
 * strategy's live CUSUM statistic / status / calibrated (mu0, k, h), and the
 * most recent alarm/resume log rows. See lib/edge-decay.ts for the state
 * machine this reads.
 *
 * Operator-gated the same way as /api/ops/traffic and /api/ops/customers: a
 * public-mode deployment has no login wall at all (already-authorized);
 * everyone else needs an operator session. Classified under
 * OPERATOR_API_PREFIXES in lib/surface.ts — never served on the customer
 * deployment.
 */
async function requireOperator(): Promise<{ ok: true } | { ok: false; res: NextResponse }> {
  if (isPublicMode()) return { ok: true }
  const ops = await getSession()
  if (!ops.userId) {
    return { ok: false, res: NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 }) }
  }
  return { ok: true }
}

export async function GET() {
  const gate = await requireOperator()
  if (!gate.ok) return gate.res

  const snapshot = await getEdgeDecaySnapshot()
  return NextResponse.json({ ok: true, ...snapshot })
}
