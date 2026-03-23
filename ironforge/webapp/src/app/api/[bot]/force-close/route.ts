import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, escapeSql, validateBot, CT_TODAY } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, closeIcOrderAllAccounts, type SandboxCloseInfo, type SandboxOrderInfo } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * POST /api/[bot]/force-close
 *
 * Force-close an open Iron Condor position.
 * Uses Tradier MTM for close price, or accepts an override.
 *
 * Body: { "position_id": string, "close_price"?: number }
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : bot === 'spark' ? '1DTE' : '0DTE'
  const botName = bot.toUpperCase()

  try {
    const body = await req.json()
    const { position_id, close_price: overridePrice } = body

    if (!position_id) {
      return NextResponse.json(
        { error: 'position_id is required' },
        { status: 400 },
      )
    }

    // Person validation: if ?person= provided, only allow closing positions belonging to that person
    const personParam = req.nextUrl.searchParams.get('person')

    // 1. Look up the open position
    const rows = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit, max_loss,
              collateral_required, sandbox_order_id, person, account_type
       FROM ${botTable(bot, 'positions')}
       WHERE position_id = $1 AND status = 'open'
         AND dte_mode = $2
       LIMIT 1`,
      [position_id, dte],
    )

    if (rows.length === 0) {
      return NextResponse.json(
        { error: `No open position found: ${position_id}` },
        { status: 404 },
      )
    }

    const pos = rows[0]

    // Person ownership check
    if (personParam && personParam !== 'all' && pos.person && pos.person !== personParam) {
      return NextResponse.json(
        { error: `Position ${position_id} belongs to ${pos.person}, not ${personParam}` },
        { status: 403 },
      )
    }

    const totalCredit = num(pos.total_credit)
    const contracts = num(pos.contracts)
    const collateral = num(pos.collateral_required)

    // 2. Determine close price
    let closePrice: number
    if (overridePrice != null && overridePrice >= 0) {
      closePrice = overridePrice
    } else if (isConfigured()) {
      const mtm = await getIcMarkToMarket(
        pos.ticker,
        pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10),
        num(pos.put_short_strike),
        num(pos.put_long_strike),
        num(pos.call_short_strike),
        num(pos.call_long_strike),
        totalCredit,
      )
      closePrice = mtm?.cost_to_close ?? 0
    } else {
      closePrice = 0
    }

    // 3. Mirror close to sandbox accounts
    let sandboxCloseInfo: Record<string, SandboxCloseInfo> = {}
    let sandboxOpenInfo: Record<string, SandboxOrderInfo | number> | null = null
    if (pos.sandbox_order_id) {
      try { sandboxOpenInfo = JSON.parse(pos.sandbox_order_id) } catch {
        // Malformed sandbox JSON — proceed without mirror
      }
    }
    try {
      sandboxCloseInfo = await closeIcOrderAllAccounts(
        pos.ticker,
        pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10),
        num(pos.put_short_strike),
        num(pos.put_long_strike),
        num(pos.call_short_strike),
        num(pos.call_long_strike),
        contracts,
        closePrice,
        position_id,
        sandboxOpenInfo,
      )
    } catch (sbErr: unknown) {
      const sbMsg = sbErr instanceof Error ? sbErr.message : String(sbErr)
      console.warn(`Sandbox close mirror failed for ${position_id}: ${sbMsg}`)
    }

    // 4. Use User's actual fill price if available
    let effectivePrice = closePrice
    const userClose = sandboxCloseInfo['User']
    if (userClose?.fill_price != null && userClose.fill_price > 0) {
      effectivePrice = userClose.fill_price
    }

    // 5. Calculate P&L
    const pnlPerContract = (totalCredit - effectivePrice) * 100
    const realizedPnl = Math.round(pnlPerContract * contracts * 100) / 100

    // 6. Close the position (atomically — only if still open)
    const sandboxCloseJson = Object.keys(sandboxCloseInfo).length > 0
      ? `'${escapeSql(JSON.stringify(sandboxCloseInfo))}'`
      : 'NULL'
    const rowsAffected = await dbExecute(
      `UPDATE ${botTable(bot, 'positions')}
       SET status = 'closed', close_time = NOW(),
           close_price = ${effectivePrice}, realized_pnl = ${realizedPnl},
           close_reason = 'manual_close', updated_at = NOW(),
           sandbox_close_order_id = ${sandboxCloseJson}
       WHERE position_id = '${escapeSql(position_id)}' AND status = 'open'
         AND dte_mode = '${escapeSql(dte)}'`,
    )

    if (rowsAffected === 0) {
      // Position was already closed by scanner or another process
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ('SKIP',
                 '${escapeSql(`FORCE CLOSE SKIP: ${position_id} already closed (would have been $${realizedPnl.toFixed(2)})`)}',
                 '${escapeSql(JSON.stringify({ position_id, skipped_pnl: realizedPnl, source: 'force_close_api', skip_reason: 'already_closed' }))}',
                 '${escapeSql(dte)}')`,
      )
      return NextResponse.json({
        success: false,
        position_id,
        error: 'Position already closed by another process',
        skipped_pnl: realizedPnl,
      })
    }

    // 7. Update paper account — reconcile collateral from actual open positions
    //    Route to the correct paper_account row based on the position's account_type
    const posAccountType = pos.account_type || 'sandbox'
    const accountTypeFilter = posAccountType === 'production'
      ? `AND account_type = 'production' AND person = '${escapeSql(pos.person || '')}'`
      : `AND COALESCE(account_type, 'sandbox') = 'sandbox'`

    const remainingCollateral = await dbQuery(
      `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = '${escapeSql(dte)}' ${accountTypeFilter}`,
    )
    const actualCollateral = num(remainingCollateral[0]?.total_collateral)
    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET current_balance = current_balance + ${realizedPnl},
           cumulative_pnl = cumulative_pnl + ${realizedPnl},
           total_trades = total_trades + 1,
           collateral_in_use = ${actualCollateral},
           buying_power = current_balance + ${realizedPnl} - ${actualCollateral},
           high_water_mark = GREATEST(high_water_mark, current_balance + ${realizedPnl}),
           max_drawdown = GREATEST(max_drawdown,
             GREATEST(high_water_mark, current_balance + ${realizedPnl}) - (current_balance + ${realizedPnl})),
           updated_at = NOW()
       WHERE is_active IS NOT NULL AND dte_mode = '${escapeSql(dte)}'
         ${accountTypeFilter}`,
    )

    // 8. Update PDT log
    await dbExecute(
      `UPDATE ${botTable(bot, 'pdt_log')}
       SET closed_at = NOW(), exit_cost = ${effectivePrice}, pnl = ${realizedPnl},
           close_reason = 'manual_close',
           is_day_trade = ((opened_at AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY})
       WHERE position_id = '${escapeSql(position_id)}' AND dte_mode = '${escapeSql(dte)}'`,
    )

    // 9. Equity snapshot
    const acctRows = await dbQuery(
      `SELECT current_balance, cumulative_pnl FROM ${botTable(bot, 'paper_account')}
       WHERE dte_mode = '${escapeSql(dte)}' ORDER BY id DESC LIMIT 1`,
    )
    const bal = num(acctRows[0]?.current_balance)
    const cumPnl = num(acctRows[0]?.cumulative_pnl)
    const openCount = await dbQuery(
      `SELECT COUNT(*) as cnt FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = '${escapeSql(dte)}'`,
    )
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'equity_snapshots')}
       (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
       VALUES (${bal}, ${cumPnl}, 0, ${num(openCount[0]?.cnt)},
               '${escapeSql(`force_close:${position_id}`)}', '${escapeSql(dte)}')`,
    )

    // 10. Log
    const logDetails = escapeSql(JSON.stringify({
      position_id,
      close_price_estimated: closePrice,
      close_price_actual: effectivePrice,
      realized_pnl: realizedPnl,
      close_reason: 'manual_close',
      entry_credit: totalCredit,
      source: 'force_close_api',
      sandbox_close_info: sandboxCloseInfo,
    }))
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ('TRADE_CLOSE',
               '${escapeSql(`FORCE CLOSE: ${position_id} @ $${effectivePrice.toFixed(4)} P&L=$${realizedPnl.toFixed(2)}`)}',
               '${logDetails}',
               '${escapeSql(dte)}')`,
    )

    // 11. Daily perf upsert
    const dailyTable = botTable(bot, 'daily_perf')
    await dbExecute(
      `INSERT INTO ${dailyTable} (trade_date, trades_executed, positions_closed, realized_pnl)
       VALUES (${CT_TODAY}, 0, 1, ${realizedPnl})
       ON CONFLICT (trade_date) DO UPDATE SET
         positions_closed = ${dailyTable}.positions_closed + 1,
         realized_pnl = ${dailyTable}.realized_pnl + ${realizedPnl}`,
    )

    return NextResponse.json({
      success: true,
      position_id,
      close_price: effectivePrice,
      close_price_estimated: closePrice,
      realized_pnl: realizedPnl,
      entry_credit: totalCredit,
      contracts,
      sandbox_close_info: sandboxCloseInfo,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
