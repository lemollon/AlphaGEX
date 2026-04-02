import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/[bot]/signals
 *
 * Returns recent signal history (executed and skipped).
 * Supports ?limit=N&offset=M query params.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const personParam = req.nextUrl.searchParams.get('person')
  const filterByPerson = personParam && personParam !== 'all'
  const accountType = req.nextUrl.searchParams.get('account_type') || undefined
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const personFilter = filterByPerson ? `AND person = '${escapeSql(personParam)}'` : ''
  // Signals table has no account_type column — signals are global per bot.
  // Always show all signals regardless of view mode.
  const accountTypeFilter = ''

  const url = new URL(req.url)
  const limit = Math.min(Math.max(1, int(url.searchParams.get('limit')) || 50), 200)
  const offset = Math.max(0, int(url.searchParams.get('offset')) || 0)

  try {
    const rows = await dbQuery(
      `SELECT id, signal_time, spot_price, vix, expected_move,
              call_wall, put_wall, gex_regime,
              put_short, put_long, call_short, call_long,
              total_credit, confidence, was_executed,
              skip_reason, reasoning, wings_adjusted, dte_mode
       FROM ${botTable(bot, 'signals')}
       WHERE 1=1 ${dteFilter} ${personFilter} ${accountTypeFilter}
       ORDER BY signal_time DESC
       LIMIT ${limit} OFFSET ${offset}`,
    )

    const signals = rows.map((r) => ({
      id: int(r.id),
      signal_time: r.signal_time || null,
      spot_price: num(r.spot_price),
      vix: num(r.vix),
      expected_move: num(r.expected_move),
      call_wall: num(r.call_wall),
      put_wall: num(r.put_wall),
      gex_regime: r.gex_regime || null,
      put_short: num(r.put_short),
      put_long: num(r.put_long),
      call_short: num(r.call_short),
      call_long: num(r.call_long),
      total_credit: num(r.total_credit),
      confidence: num(r.confidence),
      was_executed: r.was_executed === true || r.was_executed === 'true',
      skip_reason: r.skip_reason || null,
      reasoning: r.reasoning || null,
      wings_adjusted: r.wings_adjusted === true || r.wings_adjusted === 'true',
    }))

    return NextResponse.json({ signals })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
