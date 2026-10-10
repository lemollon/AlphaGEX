import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { listPendingMessages, getPendingMessage, publishPendingMessage, rejectPendingMessage } from '@/lib/community/store'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Operator backstop for #218's held posts — the retry job (scanner.ts,
 * safePendingModerationRetry) clears most of community_pending_messages on its
 * own every few minutes; this exists for the ones that don't, because the
 * scorer itself stays down long enough that "wait for the next retry" is no
 * longer a real answer.
 *
 * GET  — list held posts, oldest first.
 * POST — {id, action: 'approve' | 'reject'} — same publish/reject paths the
 * retry job itself uses, so an operator action can never diverge from what
 * the automatic path would have done with a real verdict.
 */

async function gate() {
  if (isPublicMode()) return null
  const ops = await getSession()
  if (!ops.userId) {
    return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
  }
  return null
}

export async function GET() {
  const blocked = await gate()
  if (blocked) return blocked
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Customers DB not configured.' }, { status: 503 })
  }
  const pending = await listPendingMessages(200)
  return NextResponse.json({ ok: true, count: pending.length, pending })
}

export async function POST(req: NextRequest) {
  const blocked = await gate()
  if (blocked) return blocked
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Customers DB not configured.' }, { status: 503 })
  }

  const body = await req.json().catch(() => ({}))
  const id = typeof body.id === 'string' ? body.id.trim() : ''
  const action = body.action
  if (!id || (action !== 'approve' && action !== 'reject')) {
    return NextResponse.json(
      { ok: false, error: 'Body must be { id: string, action: "approve" | "reject" }.' },
      { status: 400 },
    )
  }

  const pending = await getPendingMessage(id)
  if (!pending) {
    return NextResponse.json({ ok: false, error: 'Not found — already resolved or never existed.' }, { status: 404 })
  }

  if (action === 'approve') {
    const messageId = await publishPendingMessage(pending)
    return NextResponse.json({ ok: true, action: 'approved', messageId })
  }
  await rejectPendingMessage(pending, { category: 'OPERATOR_REJECTED' })
  return NextResponse.json({ ok: true, action: 'rejected' })
}
