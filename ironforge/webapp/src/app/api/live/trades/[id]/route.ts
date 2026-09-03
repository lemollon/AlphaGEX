import { NextRequest, NextResponse } from 'next/server'
import { resolveLiveViewer } from '@/lib/live/viewer'
import { getCustomerTradeDetail } from '@/lib/live/trades-history'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * ONE closed trade's detail (APP-019/022) — scoped exactly like GET
 * /api/live/trades: a customer can only ever fetch a trade that belongs to
 * one of their own mapped bots. An id that does not exist, belongs to
 * another account, or is still open (this route only serves closed trades,
 * same as the list) all fall through to the same 404 — the response never
 * distinguishes "not yours" from "doesn't exist".
 */
export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  try {
    const viewer = await resolveLiveViewer(req)
    if (viewer.allowedBots.length === 0 || !params.id) {
      return NextResponse.json(
        { ok: false, error: 'not_found', message: 'This trade could not be found.' },
        { status: 404 },
      )
    }

    const found = await getCustomerTradeDetail(
      params.id,
      viewer.allowedBots,
      viewer.persons,
      viewer.paperBots,
      viewer.isOperator,
    )
    if (!found) {
      return NextResponse.json(
        { ok: false, error: 'not_found', message: 'This trade could not be found.' },
        { status: 404 },
      )
    }

    return NextResponse.json(found)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}
