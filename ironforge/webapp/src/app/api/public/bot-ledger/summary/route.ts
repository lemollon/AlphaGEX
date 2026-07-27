import { NextRequest, NextResponse } from 'next/server'

import { LEDGER_PERIODS, type LedgerPeriod } from '@/lib/bot-ledger/constants'
import { getLedgerSummary, LedgerRequestError } from '@/lib/bot-ledger/ledger'
import { LedgerInvariantError } from '@/lib/bot-ledger/assertions'

/**
 * PUBLIC Bot Ledger summary — KPI cards for Spark and Flame.
 *
 * Closed trades only. No balance, no open position, no per-customer state, no
 * strikes, no timestamps. Do not widen this to anything that reads
 * `ironforge_accounts` or a live broker balance.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const NO_STORE = { 'Cache-Control': 'no-store' }

export async function GET(req: NextRequest) {
  const raw = req.nextUrl.searchParams.get('period') ?? '30d'
  if (!(LEDGER_PERIODS as readonly string[]).includes(raw)) {
    return NextResponse.json(
      { error: 'Unsupported period.', error_code: 'INVALID_PERIOD' },
      { status: 400, headers: NO_STORE },
    )
  }

  try {
    const data = await getLedgerSummary({ period: raw as LedgerPeriod, now: Date.now() })
    return NextResponse.json(data, {
      headers: { 'Cache-Control': 'public, max-age=300, stale-while-revalidate=600' },
    })
  } catch (err: unknown) {
    if (err instanceof LedgerRequestError) {
      return NextResponse.json(
        { error: err.message, error_code: err.code, ...err.extra },
        { status: err.status, headers: NO_STORE },
      )
    }
    // A reconciliation failure must not be cached, and must not be dressed up
    // as data. Suppressing the cards is the correct outcome.
    if (err instanceof LedgerInvariantError) {
      return NextResponse.json(
        { error: 'Performance figures are being verified.', error_code: 'LEDGER_INVARIANT_VIOLATION' },
        { status: 500, headers: NO_STORE },
      )
    }
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json(
      { error: msg, error_code: 'LEDGER_UNAVAILABLE' },
      { status: 500, headers: NO_STORE },
    )
  }
}
