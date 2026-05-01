/**
 * One-shot reconciliation for {bot}_daily_perf when sandbox + production
 * rows for the same (trade_date, person) collapsed onto a single row
 * because the legacy unique key ignored account_type. Rebuilds the table
 * from {bot}_positions, grouped by (trade_date, person, account_type),
 * so dashboards reading daily_perf show the correct per-account totals.
 *
 * GET  /api/{bot}/fix-daily-perf
 *   Dry run. Returns one row per (trade_date, person, account_type) where
 *   the positions-derived totals diverge from what daily_perf currently
 *   stores. Safe to call anytime.
 *
 * POST /api/{bot}/fix-daily-perf?confirm=true
 *   Inside a transaction:
 *     1. DELETE all rows from {bot}_daily_perf
 *     2. INSERT one row per (trade_date, person, account_type) computed
 *        from {bot}_positions:
 *          trades_executed   = COUNT(*) (every position counts as one trade)
 *          positions_closed  = COUNT(*) FILTER (WHERE status IN closed/expired)
 *          realized_pnl      = SUM(realized_pnl) FILTER (closed/expired)
 *     3. The unique index (trade_date, person, account_type) is created by
 *        ensureTables() in @/lib/db.ts on first connection — this route
 *        does NOT recreate it, so the index swap is decoupled from the
 *        data rebuild.
 *
 * Pure DB reconciliation. No trading logic, no order placement.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, withTransaction, botTable, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

interface ExpectedRow {
  trade_date: string
  person: string
  account_type: string
  trades_executed: number
  positions_closed: number
  realized_pnl: number
}

interface CurrentRow {
  trade_date: string
  person: string | null
  account_type: string | null
  trades_executed: number | null
  positions_closed: number | null
  realized_pnl: number | null
}

async function loadExpected(bot: string, dte: string): Promise<ExpectedRow[]> {
  const rows = await dbQuery(
    `SELECT (open_time AT TIME ZONE 'America/Chicago')::date AS trade_date,
            COALESCE(person, 'User') AS person,
            COALESCE(account_type, 'sandbox') AS account_type,
            COUNT(*)::int AS trades_executed,
            COUNT(*) FILTER (WHERE status IN ('closed', 'expired'))::int AS positions_closed,
            COALESCE(SUM(realized_pnl) FILTER (WHERE status IN ('closed', 'expired')), 0)::numeric AS realized_pnl
     FROM ${botTable(bot, 'positions')}
     WHERE dte_mode = $1 AND open_time IS NOT NULL
     GROUP BY 1, 2, 3
     ORDER BY 1 DESC, 2, 3`,
    [dte],
  )
  return rows.map((r) => ({
    trade_date: typeof r.trade_date === 'string' ? r.trade_date : new Date(r.trade_date).toISOString().slice(0, 10),
    person: r.person,
    account_type: r.account_type,
    trades_executed: Number(r.trades_executed) || 0,
    positions_closed: Number(r.positions_closed) || 0,
    realized_pnl: Math.round(Number(r.realized_pnl ?? 0) * 100) / 100,
  }))
}

async function loadCurrent(bot: string): Promise<CurrentRow[]> {
  const rows = await dbQuery(
    `SELECT trade_date, person, account_type, trades_executed, positions_closed, realized_pnl
     FROM ${botTable(bot, 'daily_perf')}
     ORDER BY trade_date DESC, person, account_type`,
  )
  return rows.map((r) => ({
    trade_date: typeof r.trade_date === 'string' ? r.trade_date : new Date(r.trade_date).toISOString().slice(0, 10),
    person: r.person ?? null,
    account_type: r.account_type ?? null,
    trades_executed: r.trades_executed != null ? Number(r.trades_executed) : null,
    positions_closed: r.positions_closed != null ? Number(r.positions_closed) : null,
    realized_pnl: r.realized_pnl != null ? Math.round(Number(r.realized_pnl) * 100) / 100 : null,
  }))
}

function diffRows(expected: ExpectedRow[], current: CurrentRow[]): {
  mismatched: Array<ExpectedRow & { current: CurrentRow | null }>
  totalPnlDelta: number
} {
  const currentMap = new Map<string, CurrentRow>()
  for (const c of current) {
    const key = `${c.trade_date}|${c.person ?? ''}|${c.account_type ?? 'sandbox'}`
    currentMap.set(key, c)
  }
  const mismatched: Array<ExpectedRow & { current: CurrentRow | null }> = []
  let totalPnlDelta = 0
  for (const e of expected) {
    const key = `${e.trade_date}|${e.person}|${e.account_type}`
    const cur = currentMap.get(key) ?? null
    const curPnl = cur?.realized_pnl ?? 0
    const curClosed = cur?.positions_closed ?? 0
    const curExecuted = cur?.trades_executed ?? 0
    if (
      cur == null
      || Math.abs((curPnl ?? 0) - e.realized_pnl) > 0.01
      || curClosed !== e.positions_closed
      || curExecuted !== e.trades_executed
    ) {
      mismatched.push({ ...e, current: cur })
      totalPnlDelta += e.realized_pnl - (curPnl ?? 0)
    }
  }
  // Surface stale rows in current that have no counterpart in expected
  // (typical after a positions table rebuild). Treat them as candidates
  // for deletion.
  const expectedKeys = new Set(expected.map((e) => `${e.trade_date}|${e.person}|${e.account_type}`))
  for (const c of current) {
    const key = `${c.trade_date}|${c.person ?? ''}|${c.account_type ?? 'sandbox'}`
    if (!expectedKeys.has(key)) {
      mismatched.push({
        trade_date: c.trade_date,
        person: c.person ?? '',
        account_type: c.account_type ?? 'sandbox',
        trades_executed: 0,
        positions_closed: 0,
        realized_pnl: 0,
        current: c,
      })
      totalPnlDelta -= c.realized_pnl ?? 0
    }
  }
  return { mismatched, totalPnlDelta: Math.round(totalPnlDelta * 100) / 100 }
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })
  try {
    const [expected, current] = await Promise.all([loadExpected(bot, dte), loadCurrent(bot)])
    const diff = diffRows(expected, current)
    return NextResponse.json({
      bot,
      dry_run: true,
      expected_row_count: expected.length,
      current_row_count: current.length,
      mismatches: diff.mismatched.length,
      total_pnl_delta_if_rebuilt: diff.totalPnlDelta,
      instructions: `POST /api/${bot}/fix-daily-perf?confirm=true to rebuild ${botTable(bot, 'daily_perf')} from ${botTable(bot, 'positions')}.`,
      sample: diff.mismatched.slice(0, 30),
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
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  const confirm = req.nextUrl.searchParams.get('confirm') === 'true'
  if (!confirm) {
    return NextResponse.json(
      { error: 'Refusing to rebuild daily_perf without ?confirm=true — call GET first to preview.' },
      { status: 400 },
    )
  }

  try {
    const expected = await loadExpected(bot, dte)
    const result = await withTransaction(async (client) => {
      // Wipe the dte-mode-relevant rows. positions_only-derived expected
      // covers the same dte slice; deleting all rows for this bot keeps
      // schema simple. (Each bot has its own table per botTable().)
      await client.query(`DELETE FROM ${botTable(bot, 'daily_perf')}`)
      let inserted = 0
      for (const e of expected) {
        await client.query(
          `INSERT INTO ${botTable(bot, 'daily_perf')}
             (trade_date, person, account_type, trades_executed, positions_closed, realized_pnl, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, NOW())`,
          [e.trade_date, e.person, e.account_type, e.trades_executed, e.positions_closed, e.realized_pnl],
        )
        inserted += 1
      }
      return { inserted }
    })

    return NextResponse.json({
      bot,
      rebuilt_from: botTable(bot, 'positions'),
      table: botTable(bot, 'daily_perf'),
      rows_inserted: result.inserted,
      note: `daily_perf rebuilt from ${botTable(bot, 'positions')}. Refresh /${bot} to see updated daily totals.`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    // The new unique index is created by ensureTables on first DB
    // connection, so this should never collide. If it does, surface the
    // root cause clearly so the operator can investigate.
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
