/**
 * One-shot cleanup for {bot}_equity_snapshots rows where the balance is
 * implausibly low — e.g. SPARK Logan/sandbox wrote thousands of rows at
 * ~$15,118 (= $10K starting + realized) while surrounding rows were at
 * ~$76,000. Those bad rows make the equity chart "dive" mid-day. The
 * underlying writer mis-sync is fixed at the source in scanner.ts; this
 * endpoint exists to clean up the historical pollution.
 *
 * GET  /api/{bot}/fix-equity-snapshots
 *   Dry run. Returns counts + samples of rows that would be deleted.
 *   Safe to call anytime.
 *
 * POST /api/{bot}/fix-equity-snapshots?confirm=true
 *   Deletes rows where balance is less than 50% of that day's MAX balance
 *   for the same (person, account_type, dte_mode). The 50%-of-day-max
 *   heuristic targets "balance dropped to starting_capital baseline"
 *   pollution without touching legitimate intraday drawdowns. No order
 *   placement, no scanner side-effects.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

const ANOMALY_RATIO = 0.5

function buildAnomalySql(table: string, dte: string): { sql: string; params: any[] } {
  // Two-step: per (person, account_type, day) compute the daily max; flag
  // every row whose balance is < ANOMALY_RATIO * that max. The day_max CTE
  // intentionally stays inside this single query so the dry-run / apply
  // paths use identical row-selection logic.
  const sql = `
    WITH daily_max AS (
      SELECT person,
             COALESCE(account_type, 'sandbox') AS account_type,
             dte_mode,
             (snapshot_time AT TIME ZONE 'America/Chicago')::date AS d,
             MAX(balance) AS max_bal
      FROM ${table}
      WHERE dte_mode = $1
      GROUP BY 1, 2, 3, 4
    )
    SELECT eq.id,
           eq.snapshot_time,
           eq.person,
           COALESCE(eq.account_type, 'sandbox') AS account_type,
           eq.balance,
           eq.realized_pnl,
           eq.note,
           dm.max_bal AS day_max_balance
    FROM ${table} eq
    JOIN daily_max dm
      ON dm.person = eq.person
     AND dm.account_type = COALESCE(eq.account_type, 'sandbox')
     AND dm.dte_mode = eq.dte_mode
     AND dm.d = (eq.snapshot_time AT TIME ZONE 'America/Chicago')::date
    WHERE eq.dte_mode = $1
      AND eq.balance < ${ANOMALY_RATIO} * dm.max_bal
    ORDER BY eq.snapshot_time DESC
  `
  return { sql, params: [dte] }
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
    const table = botTable(bot, 'equity_snapshots')
    const { sql, params: queryParams } = buildAnomalySql(table, dte)
    const rows = await dbQuery(sql, queryParams)
    const sample = rows.slice(0, 30)
    const byBucket: Record<string, number> = {}
    for (const r of rows) {
      const k = `${r.person ?? ''}|${r.account_type}`
      byBucket[k] = (byBucket[k] ?? 0) + 1
    }
    return NextResponse.json({
      bot,
      dry_run: true,
      table,
      anomaly_ratio: ANOMALY_RATIO,
      candidates: rows.length,
      by_bucket: byBucket,
      instructions: `POST /api/${bot}/fix-equity-snapshots?confirm=true to delete these rows.`,
      sample,
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
      { error: 'Refusing to delete snapshots without ?confirm=true — call GET first to preview.' },
      { status: 400 },
    )
  }

  try {
    const table = botTable(bot, 'equity_snapshots')
    // Reuse the same SELECT to materialize ids, then DELETE in a single
    // statement so we never lose track of which rows we removed.
    const { sql: selectSql, params: selectParams } = buildAnomalySql(table, dte)
    const candidates = await dbQuery(selectSql, selectParams)
    if (candidates.length === 0) {
      return NextResponse.json({ bot, table, rows_deleted: 0, note: 'No anomalous rows found.' })
    }
    const ids = candidates.map((r) => Number(r.id)).filter((n) => Number.isFinite(n))
    let totalDeleted = 0
    const CHUNK = 5000
    for (let i = 0; i < ids.length; i += CHUNK) {
      const chunk = ids.slice(i, i + CHUNK)
      const deleted = await dbExecute(`DELETE FROM ${table} WHERE id = ANY($1::bigint[])`, [chunk])
      totalDeleted += deleted
    }
    return NextResponse.json({
      bot,
      table,
      rows_deleted: totalDeleted,
      note: `Deleted ${totalDeleted} snapshot rows whose balance was below ${(ANOMALY_RATIO * 100).toFixed(0)}% of the day's max for the same (person, account_type). Refresh /${bot} equity chart to verify.`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
