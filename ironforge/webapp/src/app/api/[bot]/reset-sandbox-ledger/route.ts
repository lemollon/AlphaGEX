import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * Reset a bot's SANDBOX/paper ledger to a clean start.
 *
 * Why this exists: a paper bot's cumulative curve is only meaningful on ONE
 * capital era. SPARK's paper ledger was sized off a co-tenanted Tradier sandbox
 * balance (fixed in #2583), so its 86-trade history spans a base that moved with
 * unrelated systems — a cumulative-since-inception curve on it is not a track
 * record. This endpoint starts the paper curve fresh from today on the clean,
 * config-driven base without fabricating anything.
 *
 * NOTE: distinct from /api/{bot}/reset-paper-account, which reseeds SPARK from
 * its REAL PRODUCTION balance. This route is SANDBOX-only and never reads a
 * broker — the base is {bot}_config.starting_capital, which the scanner already
 * keeps the sandbox row synced to.
 *
 * Reversible by design — it ARCHIVES, it does not DELETE:
 *   • closed/expired sandbox positions get status = 'archived_reset' (excluded
 *     from the realized-P&L sum and from Trade History, but the rows survive and
 *     can be un-archived by flipping status back).
 *   • sandbox equity_snapshots + daily_perf for this dte_mode are cleared (these
 *     are recomputable telemetry, not the source of truth).
 *   • the sandbox paper_account row is reset to starting_capital.
 *
 * HARD GUARANTEES:
 *   • PRODUCTION is never touched — real-money rows (account_type='production')
 *     are out of every statement here. This runs on sandbox only.
 *   • OPEN positions are never touched — only closed/expired rows are archived,
 *     so nothing that is still being managed is disturbed.
 *   • POST requires an exact confirm string, so it cannot fire by accident.
 *
 *   GET  /api/{bot}/reset-sandbox-ledger   → read-only: exactly what POST would do
 *   POST /api/{bot}/reset-sandbox-ledger   → body { confirm: "RESET {BOT} PAPER" }
 */

const SANDBOX = `COALESCE(account_type, 'sandbox') = 'sandbox'`

function confirmPhrase(bot: string): string {
  return `RESET ${bot.toUpperCase()} PAPER`
}

/** Shared read of the current sandbox ledger state + reset target. */
async function inspect(bot: string, dte: string) {
  const acctRows = await dbQuery(
    `SELECT id, is_active, starting_capital, current_balance, cumulative_pnl,
            collateral_in_use, buying_power, total_trades, high_water_mark, max_drawdown
       FROM ${botTable(bot, 'paper_account')}
      WHERE dte_mode = '${escapeSql(dte)}' AND ${SANDBOX}
      ORDER BY id`,
  )
  const active = acctRows.find((r) => r.is_active === true || r.is_active === 'true') || acctRows[0] || null

  const closed = await dbQuery(
    `SELECT COUNT(*) AS n, COALESCE(SUM(realized_pnl), 0) AS pnl
       FROM ${botTable(bot, 'positions')}
      WHERE status IN ('closed', 'expired') AND dte_mode = '${escapeSql(dte)}' AND ${SANDBOX}`,
  )
  const open = await dbQuery(
    `SELECT COUNT(*) AS n, COALESCE(SUM(collateral_required), 0) AS collateral
       FROM ${botTable(bot, 'positions')}
      WHERE status = 'open' AND dte_mode = '${escapeSql(dte)}' AND ${SANDBOX}`,
  )
  const snaps = await dbQuery(
    `SELECT COUNT(*) AS n FROM ${botTable(bot, 'equity_snapshots')} WHERE dte_mode = '${escapeSql(dte)}'`,
  )
  // {bot}_daily_perf has no dte_mode column (keyed by trade_date UNIQUE) and no
  // account_type — it is the paper bot's daily aggregate — so it is cleared whole,
  // not filtered. Production daily perf lives on a separate path.
  const daily = await dbQuery(
    `SELECT COUNT(*) AS n FROM ${botTable(bot, 'daily_perf')}`,
  )

  // The scanner keeps the sandbox seed synced to the config knob; the reset base
  // is that knob (falling back to whatever the row already carries).
  const startingCapital = active ? num(active.starting_capital) : 0
  const openCollateral = num(open[0]?.collateral)

  return {
    account: active,
    startingCapital,
    openCollateral,
    closedToArchive: int(closed[0]?.n),
    closedPnl: num(closed[0]?.pnl),
    openKept: int(open[0]?.n),
    snapshotsToClear: int(snaps[0]?.n),
    dailyRowsToClear: int(daily[0]?.n),
  }
}

export async function GET(req: NextRequest, { params }: { params: { bot: string } }) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  try {
    const s = await inspect(bot, dte)
    return NextResponse.json({
      bot: bot.toUpperCase(),
      dte,
      mode: 'diagnostic (read-only)',
      confirm_required: confirmPhrase(bot),
      current: s.account,
      will_do: {
        archive_closed_positions: s.closedToArchive,
        archived_realized_pnl_removed_from_curve: s.closedPnl,
        open_positions_kept_untouched: s.openKept,
        clear_equity_snapshots: s.snapshotsToClear,
        clear_daily_perf_rows: s.dailyRowsToClear,
        reset_starting_capital_to: s.startingCapital,
        reset_balance_to: s.startingCapital,
        reset_collateral_to_open_only: s.openCollateral,
      },
      production_touched: false,
      note: 'POST the confirm phrase to apply. Production rows are never affected.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(req: NextRequest, { params }: { params: { bot: string } }) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  let body: { confirm?: unknown }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 })
  }
  const need = confirmPhrase(bot)
  if (body.confirm !== need) {
    return NextResponse.json(
      { error: `Confirmation required. POST { "confirm": "${need}" } to reset ${bot.toUpperCase()}'s paper ledger.` },
      { status: 400 },
    )
  }

  try {
    const before = await inspect(bot, dte)
    if (!before.account) {
      return NextResponse.json({ error: `No active sandbox paper_account for ${bot.toUpperCase()} (${dte}).` }, { status: 404 })
    }

    const startingCapital = before.startingCapital
    const openCollateral = before.openCollateral
    const newBalance = Math.round((startingCapital) * 100) / 100
    const newBp = Math.round((startingCapital - openCollateral) * 100) / 100

    // 1. Archive closed/expired SANDBOX positions (reversible: status flip only).
    const archived = await dbExecute(
      `UPDATE ${botTable(bot, 'positions')}
          SET status = 'archived_reset'
        WHERE status IN ('closed', 'expired') AND dte_mode = '${escapeSql(dte)}' AND ${SANDBOX}`,
    )

    // 2. Clear recomputable telemetry for this dte_mode (sandbox tables).
    const snaps = await dbExecute(
      `DELETE FROM ${botTable(bot, 'equity_snapshots')} WHERE dte_mode = '${escapeSql(dte)}'`,
    )
    const daily = await dbExecute(
      `DELETE FROM ${botTable(bot, 'daily_perf')}`,
    )

    // 3. Reset the sandbox paper_account row to a clean start on the config base.
    //    collateral_in_use is set to the collateral of the OPEN positions we kept,
    //    so buying power stays honest if a trade is currently live.
    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
          SET cumulative_pnl = 0,
              current_balance = ${newBalance},
              collateral_in_use = ${openCollateral},
              buying_power = ${newBp},
              high_water_mark = ${newBalance},
              max_drawdown = 0,
              total_trades = 0,
              updated_at = NOW()
        WHERE id = ${int(before.account.id)}`,
    )

    // 4. Leave a breadcrumb in the log (audit trail, not deleted).
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ('CONFIG', 'PAPER LEDGER RESET',
                 '${escapeSql(`archived ${archived} closed positions, cleared ${snaps} snapshots / ${daily} daily rows, base=$${startingCapital}`)}',
                 '${escapeSql(dte)}')`,
      )
    } catch { /* logging is best-effort */ }

    const after = await inspect(bot, dte)
    return NextResponse.json({
      bot: bot.toUpperCase(),
      dte,
      applied: true,
      archived_positions: archived,
      cleared_snapshots: snaps,
      cleared_daily_rows: daily,
      reset_to: { starting_capital: startingCapital, balance: newBalance, buying_power: newBp, collateral_in_use: openCollateral },
      production_touched: false,
      after: after.account,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
