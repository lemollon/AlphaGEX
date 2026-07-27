import { NextRequest, NextResponse } from 'next/server'

import {
  DEFAULT_TRADE_LIMIT,
  LEDGER_BOT_FILTERS,
  MAX_TRADE_LIMIT,
  type LedgerBotFilter,
} from '@/lib/bot-ledger/constants'
import { getLedgerTrades, LedgerRequestError } from '@/lib/bot-ledger/ledger'
import { LedgerInvariantError } from '@/lib/bot-ledger/assertions'

/**
 * PUBLIC Bot Ledger trade log — the evidence behind the KPI cards.
 *
 * Allowlisted DTO only (see calc.toPublicTrade + assertions.assertPublicTradeShape):
 * no strikes, no exact timestamps, no close_reason, no spread width, no
 * position_id, no person, no account_type.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const NO_STORE = { 'Cache-Control': 'no-store' }

function bad(code: string, message: string) {
  return NextResponse.json({ error: message, error_code: code }, { status: 400, headers: NO_STORE })
}

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams

  const bot = sp.get('bot') ?? 'all'
  if (!(LEDGER_BOT_FILTERS as readonly string[]).includes(bot)) {
    return bad('INVALID_BOT_FILTER', 'Unsupported bot filter.')
  }

  const limitRaw = sp.get('limit')
  let limit = DEFAULT_TRADE_LIMIT
  if (limitRaw !== null) {
    const parsed = Number(limitRaw)
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > MAX_TRADE_LIMIT) {
      return bad('INVALID_LIMIT', `limit must be an integer between 1 and ${MAX_TRADE_LIMIT}.`)
    }
    limit = parsed
  }

  try {
    const data = await getLedgerTrades({
      bot: bot as LedgerBotFilter,
      limit,
      cursor: sp.get('cursor'),
      snapshotId: sp.get('snapshot_id'),
      now: Date.now(),
    })
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
    if (err instanceof LedgerInvariantError) {
      return NextResponse.json(
        { error: 'Recent paper trades are being verified.', error_code: 'LEDGER_INVARIANT_VIOLATION' },
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
