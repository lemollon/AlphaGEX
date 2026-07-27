import { NextRequest, NextResponse } from 'next/server'

import { LEDGER_PERIODS, type LedgerPeriod } from '@/lib/bot-ledger/constants'
import { getLedgerSummary, LedgerRequestError } from '@/lib/bot-ledger/ledger'
import { LedgerInvariantError } from '@/lib/bot-ledger/assertions'
import { requestIdFrom } from '@/lib/bot-ledger/request-id'

/**
 * PUBLIC Bot Ledger summary — KPI cards for Spark and Flame.
 *
 * Closed trades only. No balance, no open position, no per-customer state, no
 * strikes, no timestamps. Do not widen this to anything that reads
 * `ironforge_accounts` or a live broker balance.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const requestId = requestIdFrom(req.headers)
  const noStore = { 'Cache-Control': 'no-store', 'x-request-id': requestId }

  const raw = req.nextUrl.searchParams.get('period') ?? '30d'
  if (!(LEDGER_PERIODS as readonly string[]).includes(raw)) {
    return NextResponse.json(
      { error: 'Unsupported period.', error_code: 'INVALID_PERIOD', request_id: requestId },
      { status: 400, headers: noStore },
    )
  }

  try {
    const data = await getLedgerSummary({ period: raw as LedgerPeriod, now: Date.now() })
    return NextResponse.json(data, {
      headers: {
        'Cache-Control': 'public, max-age=300, stale-while-revalidate=600',
        'x-request-id': requestId,
      },
    })
  } catch (err: unknown) {
    if (err instanceof LedgerRequestError) {
      return NextResponse.json(
        { error: err.message, error_code: err.code, request_id: requestId, ...err.extra },
        { status: err.status, headers: noStore },
      )
    }
    // A reconciliation failure must not be cached, and must not be dressed up
    // as data. Suppressing the cards is the correct outcome.
    if (err instanceof LedgerInvariantError) {
      return NextResponse.json(
        {
          error: 'Performance figures are being verified.',
          error_code: 'LEDGER_INVARIANT_VIOLATION',
          request_id: requestId,
        },
        { status: 500, headers: noStore },
      )
    }
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json(
      { error: msg, error_code: 'LEDGER_UNAVAILABLE', request_id: requestId },
      { status: 500, headers: noStore },
    )
  }
}
