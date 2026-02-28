import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, validateBot, dteMode, heartbeatName } from '@/lib/databricks'
import { getIcMarkToMarket, isConfigured } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/** Escape a string for safe SQL interpolation. */
function esc(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/'/g, "''")
}

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

  const dte = dteMode(bot)
  const botName = heartbeatName(bot)

  try {
    const body = await req.json()
    const { position_id, close_price: overridePrice } = body

    if (!position_id || typeof position_id !== 'string') {
      return NextResponse.json(
        { error: 'position_id is required' },
        { status: 400 },
      )
    }

    // Validate position_id format to prevent SQL injection
    if (!/^[A-Z]+-\d{8}-[A-F0-9]{1,8}$/.test(position_id)) {
      return NextResponse.json(
        { error: 'Invalid position_id format' },
        { status: 400 },
      )
    }

    // 1. Look up the open position
    const rows = await query(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit, max_loss,
              collateral_required
       FROM ${botTable(bot, 'positions')}
       WHERE position_id = '${position_id}' AND status = 'open' AND dte_mode = '${dte}'
       LIMIT 1`,
    )

    if (rows.length === 0) {
      return NextResponse.json(
        { error: `No open position found: ${position_id}` },
        { status: 404 },
      )
    }

    const pos = rows[0]
    const totalCredit = num(pos.total_credit)
    const contracts = num(pos.contracts)
    const collateral = num(pos.collateral_required)

    // 2. Determine close price
    let closePrice: number
    if (overridePrice != null && overridePrice >= 0) {
      closePrice = overridePrice
    } else if (isConfigured()) {
      const mtm = await getIcMarkToMarket(
        pos.ticker || 'SPY',
        String(pos.expiration).slice(0, 10),
        num(pos.put_short_strike),
        num(pos.put_long_strike),
        num(pos.call_short_strike),
        num(pos.call_long_strike),
      )
      closePrice = mtm?.cost_to_close ?? 0
    } else {
      // Market closed / no API — close at zero (full credit kept)
      closePrice = 0
    }

    // 3. Calculate P&L
    const pnlPerContract = (totalCredit - closePrice) * 100
    const realizedPnl = Math.round(pnlPerContract * contracts * 100) / 100

    // 4. Close the position
    await query(`
      UPDATE ${botTable(bot, 'positions')}
      SET status = 'closed', close_time = CURRENT_TIMESTAMP(),
          close_price = ${closePrice}, realized_pnl = ${realizedPnl},
          close_reason = 'manual_close', updated_at = CURRENT_TIMESTAMP()
      WHERE position_id = '${position_id}' AND status = 'open' AND dte_mode = '${dte}'
    `)

    // 5. Update paper account (add realized P&L, refund collateral)
    await query(`
      UPDATE ${botTable(bot, 'paper_account')}
      SET current_balance = current_balance + ${realizedPnl},
          cumulative_pnl = cumulative_pnl + ${realizedPnl},
          total_trades = total_trades + 1,
          collateral_in_use = GREATEST(0, collateral_in_use - ${collateral}),
          buying_power = buying_power + ${collateral} + ${realizedPnl},
          high_water_mark = GREATEST(high_water_mark, current_balance + ${realizedPnl}),
          max_drawdown = GREATEST(max_drawdown,
            GREATEST(high_water_mark, current_balance + ${realizedPnl}) - (current_balance + ${realizedPnl})),
          updated_at = CURRENT_TIMESTAMP()
      WHERE dte_mode = '${dte}' AND is_active IS NOT NULL
    `)

    // 6. Update PDT log
    await query(`
      UPDATE ${botTable(bot, 'pdt_log')}
      SET closed_at = CURRENT_TIMESTAMP(), exit_cost = ${closePrice}, pnl = ${realizedPnl},
          close_reason = 'manual_close',
          is_day_trade = (CAST(opened_at AS DATE) = CURRENT_DATE())
      WHERE position_id = '${position_id}' AND dte_mode = '${dte}'
    `)

    // 7. Save equity snapshot
    const acctRows = await query(
      `SELECT current_balance, cumulative_pnl FROM ${botTable(bot, 'paper_account')}
       WHERE dte_mode = '${dte}' ORDER BY id DESC LIMIT 1`,
    )
    const openCount = await query(
      `SELECT COUNT(*) as cnt FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = '${dte}'`,
    )
    const bal = num(acctRows[0]?.current_balance)
    const cumPnl = num(acctRows[0]?.cumulative_pnl)
    const openCnt = num(openCount[0]?.cnt)

    await query(`
      INSERT INTO ${botTable(bot, 'equity_snapshots')}
      (snapshot_time, balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode, created_at)
      VALUES (CURRENT_TIMESTAMP(), ${bal}, ${cumPnl}, 0, ${openCnt},
        '${esc(`force_close:${position_id}`)}', '${dte}', CURRENT_TIMESTAMP())
    `)

    // 8. Log
    const logDetails = esc(JSON.stringify({
      position_id,
      close_price: closePrice,
      realized_pnl: realizedPnl,
      close_reason: 'manual_close',
      entry_credit: totalCredit,
      source: 'force_close_api',
    }))
    await query(`
      INSERT INTO ${botTable(bot, 'logs')} (log_time, level, message, details, dte_mode)
      VALUES (CURRENT_TIMESTAMP(), 'TRADE_CLOSE',
        '${esc(`FORCE CLOSE: ${position_id} @ $${closePrice.toFixed(4)} P&L=$${realizedPnl.toFixed(2)}`)}',
        '${logDetails}', '${dte}')
    `)

    // 9. Update daily_perf (MERGE INTO for Databricks upsert)
    await query(`
      MERGE INTO ${botTable(bot, 'daily_perf')} AS target
      USING (SELECT CURRENT_DATE() AS trade_date) AS source
      ON target.trade_date = source.trade_date
      WHEN MATCHED THEN UPDATE SET
        positions_closed = target.positions_closed + 1,
        realized_pnl = target.realized_pnl + ${realizedPnl},
        updated_at = CURRENT_TIMESTAMP()
      WHEN NOT MATCHED THEN INSERT (trade_date, trades_executed, positions_closed, realized_pnl, updated_at)
        VALUES (CURRENT_DATE(), 0, 1, ${realizedPnl}, CURRENT_TIMESTAMP())
    `)

    return NextResponse.json({
      success: true,
      position_id,
      close_price: closePrice,
      realized_pnl: realizedPnl,
      entry_credit: totalCredit,
      contracts,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
