import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode, CT_TODAY } from '@/lib/databricks-sql'
import { getIcMarkToMarket, isConfigured, closeIcOrderAllAccounts, type SandboxCloseInfo, type SandboxOrderInfo } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * POST /api/[bot]/eod-close
 *
 * Automatically close ALL open positions at EOD (2:45 PM CT).
 * Called by the frontend position-monitor poll for faster EOD handling
 * than the 5-minute Databricks scanner cycle.
 *
 * Returns: { closed: number, results: [...] }
 */
export async function POST(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Invalid dte' }, { status: 400 })
  const dteFilter = `AND dte_mode = '${escapeSql(dte)}'`

  // Verify it's actually past 2:45 PM CT (server-side check to prevent abuse)
  const ctNow = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const ctMins = ctNow.getHours() * 60 + ctNow.getMinutes()
  if (ctMins < 885) { // 14:45 = 885 minutes
    return NextResponse.json({ error: 'Not past EOD cutoff (2:45 PM CT)', ct_minutes: ctMins }, { status: 400 })
  }

  try {
    // 1. Find all open positions
    const openPositions = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit, max_loss,
              collateral_required, sandbox_order_id
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}
       ORDER BY open_time DESC`,
    )

    if (openPositions.length === 0) {
      return NextResponse.json({ closed: 0, results: [], message: 'No open positions to close' })
    }

    const results: Array<{
      position_id: string
      close_price: number
      realized_pnl: number
      sandbox_close_info: Record<string, SandboxCloseInfo>
    }> = []

    // 2. Close each position
    for (const pos of openPositions) {
      const positionId = pos.position_id
      const totalCredit = num(pos.total_credit)
      const contracts = int(pos.contracts)
      const ticker = pos.ticker || 'SPY'
      const expiration = pos.expiration ? String(pos.expiration).slice(0, 10) : ''

      // Get MTM close price
      let closePrice = 0
      if (isConfigured()) {
        try {
          const mtm = await getIcMarkToMarket(
            ticker, expiration,
            num(pos.put_short_strike), num(pos.put_long_strike),
            num(pos.call_short_strike), num(pos.call_long_strike),
            totalCredit,
          )
          if (mtm) closePrice = mtm.cost_to_close
        } catch {
          // Use 0 as fallback (expired options worth $0)
        }
      }

      // Mirror close to sandbox accounts
      let sandboxCloseInfo: Record<string, SandboxCloseInfo> = {}
      let sandboxOpenInfo: Record<string, SandboxOrderInfo | number> | null = null
      if (pos.sandbox_order_id) {
        try { sandboxOpenInfo = JSON.parse(pos.sandbox_order_id) } catch { /* ignore */ }
      }
      try {
        sandboxCloseInfo = await closeIcOrderAllAccounts(
          ticker, expiration,
          num(pos.put_short_strike), num(pos.put_long_strike),
          num(pos.call_short_strike), num(pos.call_long_strike),
          contracts, closePrice, positionId, sandboxOpenInfo,
        )
      } catch {
        // Non-fatal — continue with paper close
      }

      // Use User's actual fill price if available
      let effectivePrice = closePrice
      const userClose = sandboxCloseInfo['User']
      if (userClose?.fill_price != null && userClose.fill_price > 0) {
        effectivePrice = userClose.fill_price
      }

      // Calculate P&L
      const pnlPerContract = (totalCredit - effectivePrice) * 100
      const realizedPnl = Math.round(pnlPerContract * contracts * 100) / 100

      // Close the position (atomically — only if still open)
      const sandboxCloseJson = Object.keys(sandboxCloseInfo).length > 0
        ? `'${escapeSql(JSON.stringify(sandboxCloseInfo))}'`
        : 'NULL'
      const rowsAffected = await dbExecute(
        `UPDATE ${botTable(bot, 'positions')}
         SET status = 'closed', close_time = CURRENT_TIMESTAMP(),
             close_price = ${effectivePrice}, realized_pnl = ${realizedPnl},
             close_reason = 'eod_cutoff', updated_at = CURRENT_TIMESTAMP(),
             sandbox_close_order_id = ${sandboxCloseJson}
         WHERE position_id = '${escapeSql(positionId)}' AND status = 'open'
           ${dteFilter}`,
      )

      // Guard: skip paper_account update if position was already closed by scanner
      if (rowsAffected === 0) {
        await dbExecute(
          `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
           VALUES ('SKIP',
                   '${escapeSql(`EOD SKIP: ${positionId} already closed (would have been $${realizedPnl.toFixed(2)})`)}',
                   '${escapeSql(JSON.stringify({ position_id: positionId, skipped_pnl: realizedPnl, source: 'webapp_eod_close', skip_reason: 'already_closed' }))}',
                   '${escapeSql(dte)}')`,
        )
        continue  // Skip to next position — don't double-count P&L
      }

      // Log the close
      const logDetails = escapeSql(JSON.stringify({
        position_id: positionId,
        close_price: effectivePrice,
        realized_pnl: realizedPnl,
        close_reason: 'eod_cutoff',
        entry_credit: totalCredit,
        source: 'webapp_eod_close',
        sandbox_close_info: sandboxCloseInfo,
      }))
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ('TRADE_CLOSE',
                 '${escapeSql(`EOD CLOSE: ${positionId} @ $${effectivePrice.toFixed(4)} P&L=$${realizedPnl.toFixed(2)}`)}',
                 '${logDetails}',
                 '${escapeSql(dte)}')`,
      )

      // Update PDT log
      await dbExecute(
        `UPDATE ${botTable(bot, 'pdt_log')}
         SET closed_at = CURRENT_TIMESTAMP(), exit_cost = ${effectivePrice}, pnl = ${realizedPnl},
             close_reason = 'eod_cutoff',
             is_day_trade = (CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', opened_at) AS DATE) = ${CT_TODAY})
         WHERE position_id = '${escapeSql(positionId)}' AND dte_mode = '${escapeSql(dte)}'`,
      )

      results.push({
        position_id: positionId,
        close_price: effectivePrice,
        realized_pnl: realizedPnl,
        sandbox_close_info: sandboxCloseInfo,
      })
    }

    // 3. Update paper account once (after all positions closed)
    const remainingCollateral = await dbQuery(
      `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}`,
    )
    const actualCollateral = num(remainingCollateral[0]?.total_collateral)
    const totalRealizedPnl = results.reduce((sum, r) => sum + r.realized_pnl, 0)

    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET current_balance = current_balance + ${totalRealizedPnl},
           cumulative_pnl = cumulative_pnl + ${totalRealizedPnl},
           total_trades = total_trades + ${results.length},
           collateral_in_use = ${actualCollateral},
           buying_power = current_balance + ${totalRealizedPnl} - ${actualCollateral},
           high_water_mark = GREATEST(high_water_mark, current_balance + ${totalRealizedPnl}),
           max_drawdown = GREATEST(max_drawdown,
             GREATEST(high_water_mark, current_balance + ${totalRealizedPnl}) - (current_balance + ${totalRealizedPnl})),
           updated_at = CURRENT_TIMESTAMP()
       WHERE is_active IS NOT NULL AND dte_mode = '${escapeSql(dte)}'`,
    )

    // 4. Equity snapshot
    const acctRows = await dbQuery(
      `SELECT current_balance, cumulative_pnl FROM ${botTable(bot, 'paper_account')}
       WHERE dte_mode = '${escapeSql(dte)}' ORDER BY id DESC LIMIT 1`,
    )
    const bal = num(acctRows[0]?.current_balance)
    const cumPnl = num(acctRows[0]?.cumulative_pnl)
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'equity_snapshots')}
       (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
       VALUES (${bal}, ${cumPnl}, 0, 0,
               '${escapeSql(`webapp_eod_close:${results.length}_positions`)}', '${escapeSql(dte)}')`,
    )

    // 5. Daily perf (MERGE upsert)
    await dbExecute(
      `MERGE INTO ${botTable(bot, 'daily_perf')} AS t
       USING (SELECT ${CT_TODAY} AS trade_date) AS s
       ON t.trade_date = s.trade_date
       WHEN MATCHED THEN UPDATE SET
         t.positions_closed = t.positions_closed + ${results.length},
         t.realized_pnl = t.realized_pnl + ${totalRealizedPnl}
       WHEN NOT MATCHED THEN INSERT (trade_date, trades_executed, positions_closed, realized_pnl)
         VALUES (${CT_TODAY}, 0, ${results.length}, ${totalRealizedPnl})`,
    )

    return NextResponse.json({
      closed: results.length,
      total_realized_pnl: Math.round(totalRealizedPnl * 100) / 100,
      results,
      source: 'webapp_eod_close',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
