/**
 * One-shot ledger re-tag for the SPARK2 paper correction.
 *
 * Context: SPARK2 runs the SPARK config on a NON-funded account — it is paper,
 * confirmed by the operator 2026-07-21. Its rows were written with
 * account_type='production' before that was established. lib/live/bots.ts now
 * declares spark2 as 'paper', and ledgerFilter() reads a paper bot's rows with
 * `account_type <> 'production'` — so without this re-tag the mis-tagged rows
 * fall outside the filter and the Live page renders an empty history.
 *
 * GET  /api/spark2/retag-paper-ledger
 *   Read-only. Reports the account_type breakdown per table so an operator can
 *   see exactly what would change. Safe to call anytime.
 *
 * POST /api/spark2/retag-paper-ledger?confirm=true
 *   Re-tags production rows to 'sandbox' in spark2_positions and
 *   spark2_daily_perf. Requires ?confirm=true so a drive-by GET can't flip.
 *
 * DELIBERATELY LIMITED TO TWO TABLES. spark2_equity_snapshots and
 * spark2_paper_account are dual-written and already hold BOTH a production and
 * a sandbox row for the same instant; re-tagging their production rows would
 * collide with the sandbox ones and double-count the equity curve. Only
 * positions and daily_perf are production-only, so only they are stranded.
 *
 * Idempotent: once the rows are 'sandbox' the WHERE clause matches nothing.
 * Reversible: swap 'sandbox' and 'production' in the same statements.
 *
 * SPARK2-specific by design — returns 400 for any other bot so the blast
 * radius is stated, not implied.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, int, validateBot } from '@/lib/db'

export const dynamic = 'force-dynamic'

const PAPER_CORRECTION_BOT = 'spark2'

/** Production-only tables. See the header note on why the others are excluded. */
const RETAG_TABLES = ['positions', 'daily_perf'] as const

/** Guard rail: this correction is a handful of rows, not a bulk migration. */
const MAX_EXPECTED_ROWS = 25

async function breakdown(bot: string) {
  const out: Record<string, Record<string, number>> = {}
  for (const t of RETAG_TABLES) {
    const rows = await dbQuery<{ account_type: string | null; n: number }>(
      `SELECT COALESCE(account_type, '(null)') AS account_type, COUNT(*) AS n
         FROM ${botTable(bot, t)}
        GROUP BY 1 ORDER BY 1`,
    )
    out[t] = Object.fromEntries(rows.map((r) => [r.account_type ?? '(null)', int(r.n)]))
  }
  return out
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== PAPER_CORRECTION_BOT) {
    return NextResponse.json(
      { error: `retag-paper-ledger applies only to ${PAPER_CORRECTION_BOT}` },
      { status: 400 },
    )
  }

  const before = await breakdown(bot)
  const pending = RETAG_TABLES.reduce((n, t) => n + (before[t]?.production ?? 0), 0)
  return NextResponse.json({
    bot,
    tables: RETAG_TABLES,
    breakdown: before,
    rows_to_retag: pending,
    done: pending === 0,
  })
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== PAPER_CORRECTION_BOT) {
    return NextResponse.json(
      { error: `retag-paper-ledger applies only to ${PAPER_CORRECTION_BOT}` },
      { status: 400 },
    )
  }
  if (req.nextUrl.searchParams.get('confirm') !== 'true') {
    return NextResponse.json(
      { error: 'Refusing to write without ?confirm=true' },
      { status: 400 },
    )
  }

  const before = await breakdown(bot)
  const pending = RETAG_TABLES.reduce((n, t) => n + (before[t]?.production ?? 0), 0)
  if (pending > MAX_EXPECTED_ROWS) {
    // More rows than this correction ever described means the assumption behind
    // it no longer holds. Stop rather than rewrite a ledger nobody reviewed.
    return NextResponse.json(
      { error: `Refusing: ${pending} production rows exceeds the ${MAX_EXPECTED_ROWS}-row guard`, breakdown: before },
      { status: 409 },
    )
  }

  for (const t of RETAG_TABLES) {
    await dbExecute(
      `UPDATE ${botTable(bot, t)}
          SET account_type = 'sandbox'
        WHERE account_type = 'production'`,
    )
  }

  const after = await breakdown(bot)
  return NextResponse.json({
    bot,
    retagged: pending,
    before,
    after,
    ok: RETAG_TABLES.every((t) => (after[t]?.production ?? 0) === 0),
  })
}
