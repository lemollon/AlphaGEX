/**
 * SPARK-only "actual vs hypothetical 2:59 PM" historical-analysis endpoint.
 *
 * Read-only aggregations across the spark_positions table. Built to answer
 * the operator's "did our PT-tier discipline beat or trail the late-day
 * hold?" question at four granularities:
 *
 *   1. coverage          — what % of closed trades have hypo data
 *   2. all_time          — total P&L actual vs hypo + win rate comparison
 *   3. by_close_reason   — which PT tier (morning / midday / PM / EOD) is
 *                          leaving the most money on the table
 *   4. by_month          — monthly actual vs hypo for the last 12 months
 *
 * Only SPARK has the `hypothetical_eod_pnl` column (Commit L). Other bots
 * get a 400 with an explanatory message.
 *
 * GET /api/spark/hypo-stats[?account_type=sandbox|production]
 *   200 → { coverage, all_time, by_close_reason, by_month }
 *
 * Trades older than Tradier's ~40-day option timesales window will have
 * `hypothetical_eod_pnl IS NULL` and are excluded from every comparison
 * aggregate (so the delta is apples-to-apples). The `coverage` block
 * shows how many trades that excludes.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, num, int, escapeSql, validateBot } from '@/lib/db'

export const dynamic = 'force-dynamic'

interface AllTime {
  trades_total: number
  trades_with_hypo: number
  actual_pnl_total: number
  hypo_pnl_total: number
  delta: number
  actual_win_rate: number   // %
  hypo_win_rate: number     // %
  actual_avg_per_trade: number
  hypo_avg_per_trade: number
  delta_avg_per_trade: number
}

interface CloseReasonRow {
  close_reason: string
  trades: number
  actual_pnl_total: number
  hypo_pnl_total: number
  delta: number
  delta_avg_per_trade: number
  actual_avg_per_trade: number
  hypo_avg_per_trade: number
}

interface MonthRow {
  month: string  // 'YYYY-MM'
  trades: number
  actual_pnl_total: number
  hypo_pnl_total: number
  delta: number
}

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'spark') {
    return NextResponse.json(
      { error: 'SPARK-only — hypothetical 2:59 PM tracking only exists on the 1DTE same-day-exit bot.' },
      { status: 400 },
    )
  }

  const accountTypeParam = req.nextUrl.searchParams.get('account_type')
  const accountTypeFilter = accountTypeParam
    ? `AND COALESCE(account_type, 'sandbox') = '${escapeSql(accountTypeParam)}'`
    : ''
  const personParam = req.nextUrl.searchParams.get('person')
  const personFilter = personParam && personParam !== 'all'
    ? `AND person = '${escapeSql(personParam)}'`
    : ''

  // Common WHERE for "closed SPARK trades with realized P&L". Hypo
  // aggregates layer on `hypothetical_eod_pnl IS NOT NULL` to keep
  // comparisons apples-to-apples.
  const baseWhere = `WHERE status IN ('closed', 'expired')
    AND realized_pnl IS NOT NULL
    AND dte_mode = '1DTE'
    ${personFilter} ${accountTypeFilter}`

  try {
    /* ---------- Coverage ---------- */
    const covRows = await dbQuery(
      `SELECT
         COUNT(*) AS total,
         COUNT(*) FILTER (WHERE hypothetical_eod_pnl IS NOT NULL) AS with_hypo,
         COUNT(*) FILTER (
           WHERE hypothetical_eod_pnl IS NULL
             AND close_time >= NOW() - INTERVAL '40 days'
         ) AS recent_uncomputed
       FROM spark_positions
       ${baseWhere}`,
    )
    const total = int(covRows[0]?.total)
    const withHypo = int(covRows[0]?.with_hypo)
    const recentUncomputed = int(covRows[0]?.recent_uncomputed)
    const coverage = {
      trades_closed: total,
      trades_with_hypo: withHypo,
      coverage_pct: total > 0 ? Math.round((withHypo / total) * 1000) / 10 : 0,
      recent_uncomputed: recentUncomputed,
      note: recentUncomputed > 0
        ? `${recentUncomputed} recent trade(s) lack hypo — try POST /api/spark/backfill-hypo-eod?confirm=true to fill them in.`
        : null,
    }

    /* ---------- All-time ---------- */
    // Apples-to-apples: only trades where BOTH sides exist.
    const atRows = await dbQuery(
      `SELECT
         COUNT(*) AS trades,
         COALESCE(SUM(realized_pnl), 0) AS actual_total,
         COALESCE(SUM(hypothetical_eod_pnl), 0) AS hypo_total,
         COUNT(*) FILTER (WHERE realized_pnl > 0) AS actual_wins,
         COUNT(*) FILTER (WHERE hypothetical_eod_pnl > 0) AS hypo_wins
       FROM spark_positions
       ${baseWhere}
       AND hypothetical_eod_pnl IS NOT NULL`,
    )
    const atTrades = int(atRows[0]?.trades)
    const actualTotal = num(atRows[0]?.actual_total)
    const hypoTotal = num(atRows[0]?.hypo_total)
    const actualWins = int(atRows[0]?.actual_wins)
    const hypoWins = int(atRows[0]?.hypo_wins)
    const allTime: AllTime = {
      trades_total: total,
      trades_with_hypo: atTrades,
      actual_pnl_total: round2(actualTotal),
      hypo_pnl_total: round2(hypoTotal),
      delta: round2(actualTotal - hypoTotal),
      actual_win_rate: atTrades > 0 ? round1((actualWins / atTrades) * 100) : 0,
      hypo_win_rate: atTrades > 0 ? round1((hypoWins / atTrades) * 100) : 0,
      actual_avg_per_trade: atTrades > 0 ? round2(actualTotal / atTrades) : 0,
      hypo_avg_per_trade: atTrades > 0 ? round2(hypoTotal / atTrades) : 0,
      delta_avg_per_trade: atTrades > 0 ? round2((actualTotal - hypoTotal) / atTrades) : 0,
    }

    /* ---------- By close_reason (which PT tier wins or loses?) ---------- */
    const crRows = await dbQuery(
      `SELECT
         COALESCE(NULLIF(close_reason, ''), 'unknown') AS close_reason,
         COUNT(*) AS trades,
         COALESCE(SUM(realized_pnl), 0) AS actual_total,
         COALESCE(SUM(hypothetical_eod_pnl), 0) AS hypo_total
       FROM spark_positions
       ${baseWhere}
       AND hypothetical_eod_pnl IS NOT NULL
       GROUP BY 1
       ORDER BY trades DESC`,
    )
    const byCloseReason: CloseReasonRow[] = crRows.map((r) => {
      const trades = int(r.trades)
      const actual = num(r.actual_total)
      const hypo = num(r.hypo_total)
      return {
        close_reason: String(r.close_reason),
        trades,
        actual_pnl_total: round2(actual),
        hypo_pnl_total: round2(hypo),
        delta: round2(actual - hypo),
        delta_avg_per_trade: trades > 0 ? round2((actual - hypo) / trades) : 0,
        actual_avg_per_trade: trades > 0 ? round2(actual / trades) : 0,
        hypo_avg_per_trade: trades > 0 ? round2(hypo / trades) : 0,
      }
    })

    /* ---------- By month (last 12) ---------- */
    const monRows = await dbQuery(
      `SELECT
         TO_CHAR(DATE_TRUNC('month', close_time AT TIME ZONE 'America/Chicago'), 'YYYY-MM') AS month,
         COUNT(*) AS trades,
         COALESCE(SUM(realized_pnl), 0) AS actual_total,
         COALESCE(SUM(hypothetical_eod_pnl), 0) AS hypo_total
       FROM spark_positions
       ${baseWhere}
       AND hypothetical_eod_pnl IS NOT NULL
       AND close_time >= NOW() - INTERVAL '12 months'
       GROUP BY 1
       ORDER BY 1 DESC`,
    )
    const byMonth: MonthRow[] = monRows.map((r) => {
      const trades = int(r.trades)
      const actual = num(r.actual_total)
      const hypo = num(r.hypo_total)
      return {
        month: String(r.month),
        trades,
        actual_pnl_total: round2(actual),
        hypo_pnl_total: round2(hypo),
        delta: round2(actual - hypo),
      }
    })

    return NextResponse.json({
      bot: 'spark',
      account_type: accountTypeParam ?? 'all',
      person: personParam ?? 'all',
      coverage,
      all_time: allTime,
      by_close_reason: byCloseReason,
      by_month: byMonth,
      legend: {
        delta: 'Actual − Hypothetical. Positive = PT tier exit beat 2:59 PM hold; negative = left money on the table by exiting early.',
        coverage: 'Hypothetical P&L is only available for trades closed within Tradier\'s ~40-day option timesales window.',
      },
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

function round2(n: number): number { return Math.round(n * 100) / 100 }
function round1(n: number): number { return Math.round(n * 10) / 10 }
