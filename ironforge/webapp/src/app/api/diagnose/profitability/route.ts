import { NextRequest, NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * Cross-bot profitability diagnostic.
 *
 * Bundles 12 SQL queries that together explain why one bot is losing money
 * while others are profitable.  Designed to be hit from a browser or curl
 * so the user does NOT need shell access to the database.
 *
 * GET  /api/diagnose/profitability             → JSON with all 12 sections
 * GET  /api/diagnose/profitability?format=text → Plain-text report (easier to paste back)
 * GET  /api/diagnose/profitability?focus=flame → Adds extra forensic queries for that bot
 *
 * All values are read-only.  Nothing is written.
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const format = url.searchParams.get('format') || 'json'
  const focus = (url.searchParams.get('focus') || 'flame').toLowerCase()
  const focusBot = ['flame', 'spark', 'inferno'].includes(focus) ? focus : 'flame'

  try {
    // ─── [1] P&L summary across all three bots ────────────────────────
    const pnlSummary = await dbQuery(`
      WITH p AS (
        SELECT 'flame'   AS bot, status, realized_pnl, contracts, total_credit, collateral_required FROM flame_positions
        UNION ALL SELECT 'spark',   status, realized_pnl, contracts, total_credit, collateral_required FROM spark_positions
        UNION ALL SELECT 'inferno', status, realized_pnl, contracts, total_credit, collateral_required FROM inferno_positions
      )
      SELECT bot,
        COUNT(*)                                                                    AS total,
        COUNT(*) FILTER (WHERE status='open')                                       AS open_now,
        COUNT(*) FILTER (WHERE status IN ('closed','expired'))                      AS closed,
        COUNT(*) FILTER (WHERE status IN ('closed','expired') AND realized_pnl>0)   AS wins,
        COUNT(*) FILTER (WHERE status IN ('closed','expired') AND realized_pnl<0)   AS losses,
        ROUND(100.0 * COUNT(*) FILTER (WHERE status IN ('closed','expired') AND realized_pnl>0)
              / NULLIF(COUNT(*) FILTER (WHERE status IN ('closed','expired') AND realized_pnl IS NOT NULL),0), 1) AS win_rate_pct,
        ROUND(SUM(realized_pnl) FILTER (WHERE status IN ('closed','expired'))::numeric, 2) AS total_pnl,
        ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl>0)::numeric, 2)          AS avg_win,
        ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl<0)::numeric, 2)          AS avg_loss,
        ROUND(MAX(realized_pnl)::numeric, 2)                                        AS best,
        ROUND(MIN(realized_pnl)::numeric, 2)                                        AS worst,
        ROUND(AVG(contracts)::numeric, 1)                                           AS avg_contracts,
        ROUND(AVG(total_credit)::numeric, 3)                                        AS avg_credit,
        ROUND(AVG(collateral_required)::numeric, 2)                                 AS avg_collateral
      FROM p GROUP BY bot ORDER BY bot
    `)

    // ─── [2] Close-reason breakdown ───────────────────────────────────
    const closeReasons = await dbQuery(`
      WITH p AS (
        SELECT 'flame'   AS bot, close_reason, realized_pnl, status FROM flame_positions
        UNION ALL SELECT 'spark',   close_reason, realized_pnl, status FROM spark_positions
        UNION ALL SELECT 'inferno', close_reason, realized_pnl, status FROM inferno_positions
      )
      SELECT bot, COALESCE(close_reason,'(null)') AS close_reason,
             COUNT(*) AS n,
             ROUND(SUM(realized_pnl)::numeric,2) AS total_pnl,
             ROUND(AVG(realized_pnl)::numeric,2) AS avg_pnl,
             ROUND(MIN(realized_pnl)::numeric,2) AS worst,
             ROUND(MAX(realized_pnl)::numeric,2) AS best
      FROM p WHERE status IN ('closed','expired')
      GROUP BY bot, close_reason ORDER BY bot, total_pnl
    `)

    // ─── [3] Daily P&L (last 90 rows, descending) ─────────────────────
    const dailyPnl = await dbQuery(`
      WITH p AS (
        SELECT 'flame'   AS bot, close_time, realized_pnl, status FROM flame_positions
        UNION ALL SELECT 'spark',   close_time, realized_pnl, status FROM spark_positions
        UNION ALL SELECT 'inferno', close_time, realized_pnl, status FROM inferno_positions
      )
      SELECT (close_time AT TIME ZONE 'America/Chicago')::date AS trade_date, bot,
             COUNT(*) AS trades,
             ROUND(SUM(realized_pnl)::numeric,2) AS pnl
      FROM p WHERE status IN ('closed','expired') AND close_time IS NOT NULL
      GROUP BY trade_date, bot ORDER BY trade_date DESC, bot LIMIT 90
    `)

    // ─── [4] VIX / expected-move regime at entry ──────────────────────
    const vixRegime = await dbQuery(`
      WITH p AS (
        SELECT 'flame'   AS bot, vix_at_entry, expected_move, underlying_at_entry, realized_pnl, status FROM flame_positions
        UNION ALL SELECT 'spark',   vix_at_entry, expected_move, underlying_at_entry, realized_pnl, status FROM spark_positions
        UNION ALL SELECT 'inferno', vix_at_entry, expected_move, underlying_at_entry, realized_pnl, status FROM inferno_positions
      )
      SELECT bot,
             ROUND(AVG(vix_at_entry)::numeric,2)  AS avg_vix,
             ROUND(MIN(vix_at_entry)::numeric,2)  AS min_vix,
             ROUND(MAX(vix_at_entry)::numeric,2)  AS max_vix,
             ROUND(AVG(expected_move)::numeric,2) AS avg_em,
             ROUND(AVG(expected_move/NULLIF(underlying_at_entry,0)*100)::numeric,3) AS avg_em_pct_spot,
             ROUND(AVG(realized_pnl) FILTER (WHERE vix_at_entry < 15)::numeric,2)              AS avg_pnl_vix_lt15,
             ROUND(AVG(realized_pnl) FILTER (WHERE vix_at_entry BETWEEN 15 AND 22)::numeric,2) AS avg_pnl_vix_15_22,
             ROUND(AVG(realized_pnl) FILTER (WHERE vix_at_entry > 22)::numeric,2)              AS avg_pnl_vix_gt22
      FROM p WHERE status IN ('closed','expired')
      GROUP BY bot ORDER BY bot
    `)

    // ─── [5] Strike distance vs expected move ─────────────────────────
    const strikeDistance = await dbQuery(`
      WITH p AS (
        SELECT 'flame'   AS bot, put_short_strike, call_short_strike, put_long_strike, call_long_strike, underlying_at_entry, expected_move, realized_pnl, status FROM flame_positions
        UNION ALL SELECT 'spark',   put_short_strike, call_short_strike, put_long_strike, call_long_strike, underlying_at_entry, expected_move, realized_pnl, status FROM spark_positions
        UNION ALL SELECT 'inferno', put_short_strike, call_short_strike, put_long_strike, call_long_strike, underlying_at_entry, expected_move, realized_pnl, status FROM inferno_positions
      )
      SELECT bot,
             ROUND(AVG(underlying_at_entry - put_short_strike)::numeric,2) AS avg_put_dist,
             ROUND(AVG(call_short_strike - underlying_at_entry)::numeric,2) AS avg_call_dist,
             ROUND(AVG((underlying_at_entry - put_short_strike)/NULLIF(expected_move,0))::numeric,2) AS avg_put_sd_mult,
             ROUND(AVG((call_short_strike - underlying_at_entry)/NULLIF(expected_move,0))::numeric,2) AS avg_call_sd_mult,
             ROUND(AVG(call_long_strike - call_short_strike)::numeric,2) AS avg_call_width,
             ROUND(AVG(put_short_strike - put_long_strike)::numeric,2)    AS avg_put_width
      FROM p WHERE status IN ('closed','expired')
      GROUP BY bot ORDER BY bot
    `)

    // ─── [6] Top 20 losing trades for the focus bot ──────────────────
    const focusLosses = await dbQuery(`
      SELECT position_id,
             (open_time  AT TIME ZONE 'America/Chicago')::timestamp AS open_ct,
             (close_time AT TIME ZONE 'America/Chicago')::timestamp AS close_ct,
             ROUND(EXTRACT(EPOCH FROM (close_time - open_time))/3600.0, 1) AS hours_held,
             expiration, status, close_reason,
             ROUND(underlying_at_entry::numeric,2) AS spot_in,
             ROUND(spot_at_close::numeric,2)       AS spot_out,
             ROUND(vix_at_entry::numeric,2)        AS vix_in,
             put_long_strike, put_short_strike, call_short_strike, call_long_strike,
             contracts,
             ROUND(total_credit::numeric,3) AS credit,
             ROUND(max_loss::numeric,2)     AS max_loss,
             ROUND(realized_pnl::numeric,2) AS pnl,
             wings_adjusted,
             sandbox_order_id IS NOT NULL AS has_sandbox
      FROM ${focusBot}_positions
      WHERE status IN ('closed','expired') AND realized_pnl < 0
      ORDER BY realized_pnl ASC LIMIT 20
    `)

    // ─── [7] Signal skip-reason distribution ──────────────────────────
    const skipReasons = await dbQuery(`
      WITH s AS (
        SELECT 'flame'   AS bot, was_executed, COALESCE(skip_reason,'(executed)') AS reason FROM flame_signals
        UNION ALL SELECT 'spark',   was_executed, COALESCE(skip_reason,'(executed)') FROM spark_signals
        UNION ALL SELECT 'inferno', was_executed, COALESCE(skip_reason,'(executed)') FROM inferno_signals
      )
      SELECT bot, reason, COUNT(*) AS n
      FROM s GROUP BY bot, reason ORDER BY bot, n DESC
    `)

    // ─── [8] Live config (catches DB overrides) ───────────────────────
    const liveConfig = await dbQuery(`
      SELECT 'flame' AS bot, dte_mode, sd_multiplier, spread_width, min_credit, profit_target_pct,
             stop_loss_pct, vix_skip, max_contracts, max_trades_per_day,
             buying_power_usage_pct, min_win_probability, entry_start, entry_end, starting_capital
      FROM flame_config
      UNION ALL
      SELECT 'spark', dte_mode, sd_multiplier, spread_width, min_credit, profit_target_pct,
             stop_loss_pct, vix_skip, max_contracts, max_trades_per_day,
             buying_power_usage_pct, min_win_probability, entry_start, entry_end, starting_capital
      FROM spark_config
      UNION ALL
      SELECT 'inferno', dte_mode, sd_multiplier, spread_width, min_credit, profit_target_pct,
             stop_loss_pct, vix_skip, max_contracts, max_trades_per_day,
             buying_power_usage_pct, min_win_probability, entry_start, entry_end, starting_capital
      FROM inferno_config
      ORDER BY 1
    `)

    // ─── [9] Paper-account state ──────────────────────────────────────
    const paperAccounts = await dbQuery(`
      SELECT 'flame' AS bot, is_active, starting_capital, current_balance, cumulative_pnl,
             collateral_in_use, buying_power, high_water_mark, max_drawdown,
             (updated_at AT TIME ZONE 'America/Chicago') AS updated_ct
      FROM flame_paper_account
      UNION ALL SELECT 'spark', is_active, starting_capital, current_balance, cumulative_pnl,
             collateral_in_use, buying_power, high_water_mark, max_drawdown,
             (updated_at AT TIME ZONE 'America/Chicago') FROM spark_paper_account
      UNION ALL SELECT 'inferno', is_active, starting_capital, current_balance, cumulative_pnl,
             collateral_in_use, buying_power, high_water_mark, max_drawdown,
             (updated_at AT TIME ZONE 'America/Chicago') FROM inferno_paper_account
      ORDER BY 1
    `)

    // ─── [10] FLAME sandbox mirror coverage ───────────────────────────
    const sandboxCoverage = await dbQuery(`
      SELECT
        COUNT(*) AS total_flame_pos,
        COUNT(*) FILTER (WHERE sandbox_order_id IS NULL) AS missing_sandbox_id,
        COUNT(*) FILTER (WHERE sandbox_close_order_id IS NULL AND status IN ('closed','expired')) AS closed_without_sandbox_close,
        ROUND(AVG(realized_pnl) FILTER (WHERE sandbox_order_id IS NOT NULL AND status IN ('closed','expired'))::numeric, 2) AS avg_pnl_with_sandbox,
        ROUND(AVG(realized_pnl) FILTER (WHERE sandbox_order_id IS NULL     AND status IN ('closed','expired'))::numeric, 2) AS avg_pnl_no_sandbox
      FROM flame_positions
    `)

    // ─── [11] Open positions (any stuck/stale?) ───────────────────────
    const openPositions = await dbQuery(`
      WITH p AS (
        SELECT 'flame'   AS bot, position_id, open_time, expiration, contracts, total_credit, underlying_at_entry, put_short_strike, call_short_strike, status FROM flame_positions
        UNION ALL SELECT 'spark',   position_id, open_time, expiration, contracts, total_credit, underlying_at_entry, put_short_strike, call_short_strike, status FROM spark_positions
        UNION ALL SELECT 'inferno', position_id, open_time, expiration, contracts, total_credit, underlying_at_entry, put_short_strike, call_short_strike, status FROM inferno_positions
      )
      SELECT bot, position_id,
             (open_time AT TIME ZONE 'America/Chicago')::timestamp AS open_ct,
             expiration,
             CASE WHEN expiration < CURRENT_DATE THEN 'STALE' ELSE 'ok' END AS staleness,
             contracts, total_credit, underlying_at_entry, put_short_strike, call_short_strike
      FROM p WHERE status='open' ORDER BY bot, open_time
    `)

    // ─── [12] Time-of-day entry distribution ──────────────────────────
    const timeOfDay = await dbQuery(`
      WITH p AS (
        SELECT 'flame'   AS bot, open_time, realized_pnl, status FROM flame_positions
        UNION ALL SELECT 'spark',   open_time, realized_pnl, status FROM spark_positions
        UNION ALL SELECT 'inferno', open_time, realized_pnl, status FROM inferno_positions
      )
      SELECT bot,
             EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago')::int AS ct_hour,
             COUNT(*) AS trades,
             ROUND(SUM(realized_pnl)::numeric,2) AS total_pnl,
             ROUND(AVG(realized_pnl)::numeric,2) AS avg_pnl
      FROM p WHERE status IN ('closed','expired')
      GROUP BY bot, ct_hour ORDER BY bot, ct_hour
    `)

    const payload = {
      generated_at: new Date().toISOString(),
      focus_bot: focusBot,
      sections: {
        '01_pnl_summary':         { description: 'Headline P&L, win rate, avg win vs avg loss per bot.',          rows: pnlSummary },
        '02_close_reasons':       { description: 'Where do trades die — stop loss, profit target, EOD, expiry.', rows: closeReasons },
        '03_daily_pnl':           { description: 'Per-day P&L for each bot (last 90 rows).',                     rows: dailyPnl },
        '04_vix_regime':          { description: 'VIX bucket P&L — exposes regime sensitivity.',                 rows: vixRegime },
        '05_strike_distance':     { description: 'Realized SD multiple on strikes — checks for drift.',          rows: strikeDistance },
        '06_focus_losses':        { description: `Top 20 worst losing trades for ${focusBot.toUpperCase()}.`,   rows: focusLosses },
        '07_skip_reasons':        { description: 'Why each bot skipped signals — over/under-filtering.',         rows: skipReasons },
        '08_live_config':         { description: 'Live DB config — catches silent overrides.',                   rows: liveConfig },
        '09_paper_accounts':      { description: 'Per-bot balance, drawdown, collateral state.',                 rows: paperAccounts },
        '10_flame_sandbox_cov':   { description: 'FLAME-specific: sandbox mirror coverage and P&L delta.',       rows: sandboxCoverage },
        '11_open_positions':      { description: 'Any open positions right now (flag stale ones).',              rows: openPositions },
        '12_time_of_day':         { description: 'Entry-hour P&L distribution per bot (CT).',                    rows: timeOfDay },
      },
    }

    if (format === 'text') {
      return new NextResponse(toTextReport(payload), {
        status: 200,
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      })
    }

    return NextResponse.json(payload)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

// ── Plain-text renderer (so the user can curl & paste back easily) ──
function toTextReport(payload: any): string {
  const lines: string[] = []
  lines.push('IRONFORGE PROFITABILITY DIAGNOSTIC')
  lines.push(`Generated: ${payload.generated_at}`)
  lines.push(`Focus bot: ${payload.focus_bot.toUpperCase()}`)
  lines.push('')

  for (const [key, section] of Object.entries<any>(payload.sections)) {
    lines.push('='.repeat(70))
    lines.push(`[${key}] ${section.description}`)
    lines.push('='.repeat(70))
    if (!section.rows || section.rows.length === 0) {
      lines.push('(no rows)')
      lines.push('')
      continue
    }
    const cols = Object.keys(section.rows[0])
    lines.push(cols.join('\t'))
    for (const row of section.rows) {
      lines.push(cols.map(c => formatCell(row[c])).join('\t'))
    }
    lines.push('')
  }
  return lines.join('\n')
}

function formatCell(v: any): string {
  if (v == null) return ''
  if (v instanceof Date) return v.toISOString()
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
