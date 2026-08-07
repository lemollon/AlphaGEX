import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * READ-ONLY diagnostic: where did a bot's trade history go?
 *
 * Motivating case (SPARK, 2026-08-07). The dashboard's Paper tab plots 3 trades
 * starting 8/4, but `spark_paper_account` holds SIX ledgers and three of them are
 * `is_active = false` — including one with 100 trades / +$11,087 and one with 84
 * trades / +$11,197. Every read route filters `WHERE is_active = TRUE`, so those
 * ledgers are invisible everywhere. Meanwhile `spark_positions` returns only 31
 * closed rows for dte_mode '1DTE', so those ~184 trades have no position rows the
 * equity curve could plot even if the ledgers were switched back on.
 *
 * Every SPARK route pins `dte_mode = '1DTE'` and most also pin `account_type`,
 * `status IN ('closed','expired')`, `realized_pnl IS NOT NULL` and
 * `close_time IS NOT NULL`. Any row failing ANY of those is invisible to all of
 * them, so from outside you cannot tell "deleted" from "filtered out". This
 * endpoint runs the same table with EVERY filter removed and reports what each
 * filter is individually hiding.
 *
 * GET only, by design. There is deliberately no POST: what to do about an
 * orphaned ledger or a mis-tagged position is an operator decision about a
 * real-money book, not something a diagnostic should apply on its own.
 *
 * NOTE for whoever reads this next: do NOT reach for POST /api/{bot}/fix-collateral
 * to "fix" what this reports. That endpoint still assumes one ledger per bot — it
 * compares the active row's balance against P&L summed across EVERY account_type,
 * so on SPARK it reads $52,972 as "should be −$829.25" and would overwrite the
 * sandbox ledger with a blended production+sandbox figure. See PR #2757.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const positions = botTable(bot, 'positions')
  const paperAccount = botTable(bot, 'paper_account')
  const snapshots = botTable(bot, 'equity_snapshots')

  // Each probe is independently guarded: a column that doesn't exist on this
  // bot's tables must degrade to one null section, never 500 the whole report.
  const errors: Record<string, string> = {}
  const safe = async <T>(key: string, fn: () => Promise<T>): Promise<T | null> => {
    try {
      return await fn()
    } catch (e: unknown) {
      errors[key] = e instanceof Error ? e.message : String(e)
      return null
    }
  }

  // ── Every position row, grouped, with NO filters whatsoever ──────────────
  const byGroup = await safe('positions_by_group', async () =>
    (await dbQuery(
      `SELECT COALESCE(dte_mode, '(null)')                AS dte_mode,
              COALESCE(account_type, '(null)')            AS account_type,
              COALESCE(status, '(null)')                  AS status,
              COUNT(*)                                    AS row_count,
              MIN(open_time)                              AS first_open,
              MAX(open_time)                              AS last_open,
              MIN(close_time)                             AS first_close,
              MAX(close_time)                             AS last_close,
              COALESCE(SUM(realized_pnl), 0)              AS realized_sum,
              COUNT(*) FILTER (WHERE realized_pnl IS NULL) AS null_realized_pnl,
              COUNT(*) FILTER (WHERE close_time IS NULL)   AS null_close_time
       FROM ${positions}
       GROUP BY 1, 2, 3
       ORDER BY 1, 2, 3`,
    )).map((r) => ({
      dte_mode: r.dte_mode,
      account_type: r.account_type,
      status: r.status,
      row_count: int(r.row_count),
      first_open: r.first_open,
      last_open: r.last_open,
      first_close: r.first_close,
      last_close: r.last_close,
      realized_sum: Math.round(num(r.realized_sum) * 100) / 100,
      null_realized_pnl: int(r.null_realized_pnl),
      null_close_time: int(r.null_close_time),
    })),
  )

  const totalRows = await safe('positions_total', async () =>
    int((await dbQuery(`SELECT COUNT(*) AS c FROM ${positions}`))[0]?.c),
  )

  // ── What each dashboard filter individually hides ────────────────────────
  // The equity curve requires ALL of: dte_mode match, status closed/expired,
  // realized_pnl NOT NULL, close_time NOT NULL. Counting them separately shows
  // which single predicate is responsible for missing history.
  const dtePredicate = dte ? `dte_mode IS DISTINCT FROM '${escapeSql(dte)}'` : 'FALSE'
  const hiddenBy = await safe('hidden_by_filter', async () => {
    const r = (await dbQuery(
      `SELECT
         COUNT(*) FILTER (WHERE ${dtePredicate})                            AS wrong_dte_mode,
         COUNT(*) FILTER (WHERE status NOT IN ('closed','expired'))         AS not_closed_status,
         COUNT(*) FILTER (WHERE realized_pnl IS NULL)                       AS null_realized_pnl,
         COUNT(*) FILTER (WHERE close_time IS NULL)                         AS null_close_time,
         COUNT(*) FILTER (WHERE status IN ('closed','expired')
                            AND realized_pnl IS NOT NULL
                            AND close_time IS NOT NULL
                            AND NOT (${dtePredicate}))                      AS visible_to_curve
       FROM ${positions}`,
    ))[0]
    return {
      dashboard_dte_filter: dte,
      wrong_dte_mode: int(r?.wrong_dte_mode),
      not_closed_status: int(r?.not_closed_status),
      null_realized_pnl: int(r?.null_realized_pnl),
      null_close_time: int(r?.null_close_time),
      visible_to_curve: int(r?.visible_to_curve),
    }
  })

  // ── ALL paper_account ledgers, including is_active = FALSE ───────────────
  const ledgers = await safe('paper_accounts', async () =>
    (await dbQuery(
      `SELECT id, is_active, dte_mode, person, account_type,
              starting_capital, current_balance, cumulative_pnl, total_trades
       FROM ${paperAccount}
       ORDER BY id`,
    )).map((r) => ({
      id: int(r.id),
      is_active: r.is_active === true || r.is_active === 't',
      dte_mode: r.dte_mode,
      person: r.person,
      account_type: r.account_type,
      starting_capital: num(r.starting_capital),
      current_balance: num(r.current_balance),
      cumulative_pnl: num(r.cumulative_pnl),
      // Counter maintained on the ledger row. When this exceeds the position
      // rows actually present, the trades it counts no longer exist in the
      // table the equity curve reads.
      total_trades: int(r.total_trades),
    })),
  )

  // ── Snapshot coverage, so a chart gap can be attributed ──────────────────
  const snapshotCoverage = await safe('equity_snapshots', async () =>
    (await dbQuery(
      `SELECT COALESCE(dte_mode, '(null)')     AS dte_mode,
              COALESCE(account_type, '(null)') AS account_type,
              COUNT(*)                         AS row_count,
              MIN(snapshot_time)               AS first_snapshot,
              MAX(snapshot_time)               AS last_snapshot
       FROM ${snapshots}
       GROUP BY 1, 2
       ORDER BY 1, 2`,
    )).map((r) => ({
      dte_mode: r.dte_mode,
      account_type: r.account_type,
      row_count: int(r.row_count),
      first_snapshot: r.first_snapshot,
      last_snapshot: r.last_snapshot,
    })),
  )

  // ── Any other table that could be holding the rows ───────────────────────
  // Covers the "left behind by a migration / renamed / _old / _backup" case,
  // which nothing else in the app can see.
  const relatedTables = await safe('related_tables', async () =>
    (await dbQuery(
      `SELECT table_schema, table_name
       FROM information_schema.tables
       WHERE table_name LIKE '${escapeSql(bot)}%'
       ORDER BY table_schema, table_name`,
    )).map((r) => `${r.table_schema}.${r.table_name}`),
  )

  // ── Verdict ──────────────────────────────────────────────────────────────
  const ledgerTradeTotal = (ledgers ?? []).reduce((a, l) => a + l.total_trades, 0)
  const inactiveWithHistory = (ledgers ?? []).filter((l) => !l.is_active && l.total_trades > 0)
  const findings: string[] = []

  if (inactiveWithHistory.length > 0) {
    findings.push(
      `${inactiveWithHistory.length} INACTIVE ledger(s) carry ${inactiveWithHistory
        .reduce((a, l) => a + l.total_trades, 0)} trades between them ` +
        `(ids ${inactiveWithHistory.map((l) => l.id).join(', ')}). Every read route ` +
        `filters is_active = TRUE, so none of it reaches any endpoint.`,
    )
  }
  if (totalRows != null && ledgerTradeTotal > totalRows) {
    findings.push(
      `Ledger counters claim ${ledgerTradeTotal} trades but ${positions} holds only ` +
        `${totalRows} rows in total (all statuses, all dte_modes). ` +
        `${ledgerTradeTotal - totalRows} counted trades have NO position row anywhere ` +
        `in this table — re-activating a ledger will NOT bring them back onto the chart.`,
    )
  }
  if (hiddenBy && hiddenBy.wrong_dte_mode > 0) {
    findings.push(
      `${hiddenBy.wrong_dte_mode} position row(s) carry a dte_mode other than ` +
        `'${dte}'. Every ${bot} route pins that value, so those rows are invisible ` +
        `to the whole dashboard but still exist and are recoverable by re-tagging.`,
    )
  }
  if (hiddenBy && (hiddenBy.null_realized_pnl > 0 || hiddenBy.null_close_time > 0)) {
    findings.push(
      `${hiddenBy.null_realized_pnl} row(s) have NULL realized_pnl and ` +
        `${hiddenBy.null_close_time} have NULL close_time. The equity curve requires ` +
        `both to be non-null, so these are dropped from the chart and from ` +
        `/performance even when closed.`,
    )
  }
  if (findings.length === 0) {
    findings.push('No orphaned ledgers, mis-tagged rows or null close fields found.')
  }

  return NextResponse.json({
    bot: bot.toUpperCase(),
    read_only: true,
    dashboard_pins: {
      dte_mode: dte,
      note:
        'Every route for this bot also pins account_type on the Paper/Live toggle ' +
        '(sandbox vs production) and requires status closed/expired with non-null ' +
        'realized_pnl and close_time.',
    },
    positions_total_rows: totalRows,
    positions_by_group: byGroup,
    hidden_by_filter: hiddenBy,
    paper_account_ledgers: ledgers,
    ledger_trade_counter_total: ledgerTradeTotal,
    equity_snapshot_coverage: snapshotCoverage,
    related_tables: relatedTables,
    findings,
    probe_errors: Object.keys(errors).length > 0 ? errors : null,
  })
}
