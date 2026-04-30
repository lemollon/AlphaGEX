/**
 * Backfill the `hypothetical_eod_pnl` column for closed trades within
 * Tradier's option timesales window (~40 days). Supported on all three bots
 * (FLAME, SPARK, INFERNO).
 *
 * Why a separate endpoint:
 *   The scanner's daily auto-run only covers positions closed TODAY. For
 *   anything older that needs the column populated (e.g. a fresh deploy,
 *   schema added retroactively, or a one-shot historical analysis), this
 *   endpoint walks the table and computes what's recoverable.
 *
 *   Rows older than the Tradier window stay NULL forever — we mark
 *   `hypothetical_eod_computed_at = NOW()` so the cron doesn't keep
 *   retrying them. The `reason: 'leg_quotes_missing_at_2_59'` field in
 *   the response tells the operator which trades were too old.
 *
 * GET  /api/{bot}/backfill-hypo-eod
 *   Dry-run: lists candidates and which ones look recoverable. Safe.
 *
 * POST /api/{bot}/backfill-hypo-eod?confirm=true
 *   Applies. Updates the row + writes a HYPO_EOD_BACKFILL audit log.
 *   Skips rows that already have a non-null hypothetical_eod_pnl OR a
 *   non-null hypothetical_eod_computed_at (to avoid retrying old data).
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, num, int, validateBot, botTable, dteMode } from '@/lib/db'
import { computeHypoEodFor, ctDateString } from '@/lib/hypo-eod'

export const dynamic = 'force-dynamic'

interface CandidateRow {
  position_id: string
  ticker: string
  expiration: string
  put_short: number
  put_long: number
  call_short: number
  call_long: number
  contracts: number
  total_credit: number
  close_time: string
  close_date: string  // CT calendar date
}

async function gatherCandidates(bot: string): Promise<CandidateRow[]> {
  const rows = await dbQuery(
    `SELECT position_id, ticker, expiration,
            put_short_strike, put_long_strike,
            call_short_strike, call_long_strike,
            contracts, total_credit, close_time
     FROM ${botTable(bot, 'positions')}
     WHERE status IN ('closed', 'expired')
       AND realized_pnl IS NOT NULL
       AND hypothetical_eod_pnl IS NULL
       AND hypothetical_eod_computed_at IS NULL
       AND close_time >= NOW() - INTERVAL '40 days'
     ORDER BY close_time DESC`,
  )
  return rows.map((r) => {
    const closeTime = r.close_time instanceof Date ? r.close_time : new Date(r.close_time)
    const expIso = r.expiration instanceof Date
      ? r.expiration.toISOString().slice(0, 10)
      : String(r.expiration).slice(0, 10)
    return {
      position_id: r.position_id,
      ticker: r.ticker || 'SPY',
      expiration: expIso,
      put_short: num(r.put_short_strike),
      put_long: num(r.put_long_strike),
      call_short: num(r.call_short_strike),
      call_long: num(r.call_long_strike),
      contracts: int(r.contracts),
      total_credit: num(r.total_credit),
      close_time: closeTime.toISOString(),
      close_date: ctDateString(closeTime),
    }
  })
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  try {
    const candidates = await gatherCandidates(bot)
    return NextResponse.json({
      bot,
      dry_run: true,
      candidates: candidates.length,
      sample: candidates.slice(0, 5).map((c) => ({
        position_id: c.position_id,
        close_date: c.close_date,
        contracts: c.contracts,
        credit: c.total_credit,
      })),
      instructions: candidates.length > 0
        ? `POST /api/${bot}/backfill-hypo-eod?confirm=true to compute & store.`
        : 'Nothing to backfill (or all candidates are outside Tradier 40-day window).',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  if (req.nextUrl.searchParams.get('confirm') !== 'true') {
    return NextResponse.json(
      { error: 'Refusing to write without ?confirm=true — call GET first to preview.' },
      { status: 400 },
    )
  }

  try {
    const candidates = await gatherCandidates(bot)
    let computed = 0
    let skipped = 0
    const failures: Array<{ position_id: string; reason?: string }> = []

    for (const c of candidates) {
      const result = await computeHypoEodFor({
        position_id: c.position_id,
        ticker: c.ticker,
        expiration: c.expiration,
        put_short_strike: c.put_short,
        put_long_strike: c.put_long,
        call_short_strike: c.call_short,
        call_long_strike: c.call_long,
        contracts: c.contracts,
        total_credit: c.total_credit,
        close_date: c.close_date,
      })

      // Always set hypothetical_eod_computed_at so we don't retry this row.
      // hypothetical_eod_pnl stays NULL when Tradier didn't have leg quotes
      // (most likely cause: trade too old or option chain rolled off).
      await dbExecute(
        `UPDATE ${botTable(bot, 'positions')}
         SET hypothetical_eod_pnl = $1,
             hypothetical_eod_spot = $2,
             hypothetical_eod_computed_at = NOW()
         WHERE position_id = $3`,
        [result.hypothetical_eod_pnl, result.hypothetical_eod_spot, c.position_id],
      )

      if (result.computed) computed++
      else { skipped++; failures.push({ position_id: c.position_id, reason: result.reason }) }
    }

    // Best-effort audit log
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'HYPO_EOD_BACKFILL',
          `Backfilled ${computed}/${candidates.length} hypothetical 2:59 PM P&L rows`,
          JSON.stringify({ candidates: candidates.length, computed, skipped, failures: failures.slice(0, 10) }),
          (dteMode(bot) || '').toLowerCase(),
        ],
      )
    } catch { /* logs table may be missing fields on cold start */ }

    return NextResponse.json({
      bot,
      candidates: candidates.length,
      computed,
      skipped,
      failures,
      note: `Refresh /${bot} Trade History to see Hypo P&L column populated.`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
