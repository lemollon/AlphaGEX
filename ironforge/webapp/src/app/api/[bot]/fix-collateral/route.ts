import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import { closeIcOrderAllAccounts } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * GET /api/{bot}/fix-collateral
 * Diagnoses stuck collateral: shows paper_account state, open positions,
 * and what the status API would calculate. Read-only.
 *
 * POST /api/{bot}/fix-collateral
 * Fixes stuck collateral:
 *   1. Closes stale/expired/orphan positions
 *   2. Reconciles paper_account with actual position data
 */

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  try {
    // 1. Paper account state
    const acctRows = await dbQuery(
      `SELECT id, is_active, dte_mode, starting_capital, current_balance,
              cumulative_pnl, collateral_in_use, buying_power, total_trades
       FROM ${botTable(bot, 'paper_account')}
       WHERE dte_mode = '${escapeSql(dte)}'
       ORDER BY id`,
    )

    // 2. ALL open positions (any dte_mode — to find orphans)
    const allOpen = await dbQuery(
      `SELECT position_id, dte_mode, status, collateral_required,
              total_credit, contracts, expiration, open_time
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open'
       ORDER BY open_time`,
    )

    // 3. What status API would calculate (with dte filter)
    const liveStats = await dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl,
              COUNT(*) as total_trades
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND dte_mode = '${escapeSql(dte)}'`,
    )

    const liveColl = await dbQuery(
      `SELECT COALESCE(SUM(collateral_required), 0) as total_collateral
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = '${escapeSql(dte)}'`,
    )

    const apiPnl = num(liveStats[0]?.total_pnl)
    const apiTrades = int(liveStats[0]?.total_trades)
    const apiCollateral = num(liveColl[0]?.total_collateral)
    const apiBalance = Math.round((10000 + apiPnl) * 100) / 100
    const apiBp = Math.round((apiBalance - apiCollateral) * 100) / 100

    // 4. Detect stale positions
    const stalePositions = await dbQuery(
      `SELECT position_id, dte_mode, expiration, total_credit, contracts,
              collateral_required, open_time,
              CAST(expiration AS DATE) AS exp_date,
              CAST(open_time AS DATE) AS open_date,
              CURRENT_DATE() AS today
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open'
         AND (
           CAST(expiration AS DATE) < CURRENT_DATE()
           OR CAST(open_time AS DATE) < CURRENT_DATE()
           OR dte_mode IS NULL
           OR dte_mode != '${escapeSql(dte)}'
         )
       ORDER BY open_time`,
    )

    // Identify issues
    const issues: string[] = []
    const acct = acctRows.find(r => r.is_active === true || r.is_active === 'true') || acctRows[0]
    if (acct) {
      const storedCollateral = num(acct.collateral_in_use)
      const storedBalance = num(acct.current_balance)
      const storedPnl = num(acct.cumulative_pnl)

      if (Math.abs(storedCollateral - apiCollateral) > 0.01) {
        issues.push(`collateral: stored=${storedCollateral.toFixed(2)} vs actual=${apiCollateral.toFixed(2)}`)
      }
      if (Math.abs(storedBalance - apiBalance) > 0.01) {
        issues.push(`balance: stored=${storedBalance.toFixed(2)} vs expected=${apiBalance.toFixed(2)}`)
      }
      if (Math.abs(storedPnl - apiPnl) > 0.01) {
        issues.push(`pnl: stored=${storedPnl.toFixed(2)} vs actual=${apiPnl.toFixed(2)}`)
      }
    }
    if (stalePositions.length > 0) {
      issues.push(`${stalePositions.length} stale/expired/orphan positions still open`)
    }

    return NextResponse.json({
      bot: bot.toUpperCase(),
      dte,
      schema: botTable(bot, 'positions'),
      paper_account: acctRows.map(r => ({
        id: r.id,
        is_active: r.is_active,
        dte_mode: r.dte_mode,
        starting_capital: num(r.starting_capital),
        current_balance: num(r.current_balance),
        cumulative_pnl: num(r.cumulative_pnl),
        collateral_in_use: num(r.collateral_in_use),
        buying_power: num(r.buying_power),
        total_trades: int(r.total_trades),
      })),
      open_positions: allOpen.map(p => ({
        position_id: p.position_id,
        dte_mode: p.dte_mode || 'NULL',
        collateral: num(p.collateral_required),
        credit: num(p.total_credit),
        contracts: int(p.contracts),
        expiration: String(p.expiration || '').slice(0, 10),
        open_time: String(p.open_time || '').slice(0, 19),
        is_orphan: p.dte_mode !== dte,
      })),
      stale_positions: stalePositions.length,
      status_api_would_return: {
        balance: apiBalance,
        cumulative_pnl: apiPnl,
        total_trades: apiTrades,
        collateral_in_use: apiCollateral,
        buying_power: apiBp,
      },
      issues,
      healthy: issues.length === 0,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  try {
    const actions: string[] = []

    // Phase 1: Close stale/expired/orphan positions
    const staleRows = await dbQuery(
      `SELECT position_id, dte_mode, total_credit, contracts,
              collateral_required,
              CAST(expiration AS DATE) AS exp_date,
              CAST(open_time AS DATE) AS open_date,
              CURRENT_DATE() AS today
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open'
         AND (
           CAST(expiration AS DATE) < CURRENT_DATE()
           OR CAST(open_time AS DATE) < CURRENT_DATE()
           OR dte_mode IS NULL
           OR dte_mode != '${escapeSql(dte)}'
         )
       ORDER BY open_time`,
    )

    for (const pos of staleRows) {
      const pid = pos.position_id
      const posDte = pos.dte_mode || 'NULL'
      const entryCredit = num(pos.total_credit)
      const contracts = int(pos.contracts)
      const expDate = String(pos.exp_date || '').slice(0, 10)
      const today = String(pos.today || '').slice(0, 10)
      const isExpired = expDate < today
      const isOrphan = posDte !== dte

      let reason: string
      let closePrice: number
      let realizedPnl: number

      if (isOrphan) {
        reason = 'orphan_force_close'
        closePrice = entryCredit
        realizedPnl = 0
      } else if (isExpired) {
        reason = 'expired_force_close'
        closePrice = 0
        realizedPnl = Math.round(entryCredit * 100 * contracts * 100) / 100
      } else {
        reason = 'stale_holdover_force_close'
        closePrice = entryCredit
        realizedPnl = 0
      }

      const rowsAffected = await dbExecute(
        `UPDATE ${botTable(bot, 'positions')}
         SET status = 'closed',
             close_time = NOW(),
             close_price = ${closePrice},
             realized_pnl = ${realizedPnl},
             close_reason = '${reason}',
             dte_mode = '${escapeSql(dte)}',
             updated_at = NOW()
         WHERE position_id = '${escapeSql(String(pid))}'
           AND status = 'open'`,
      )

      if (rowsAffected === 0) {
        actions.push(`SKIP ${pid}: already closed by another process`)
        continue
      }

      // FLAME: also close on sandbox accounts (cascade close)
      if (bot === 'flame') {
        try {
          const posRows = await dbQuery(
            `SELECT ticker, expiration, put_short_strike, put_long_strike,
                    call_short_strike, call_long_strike, sandbox_order_id
             FROM ${botTable(bot, 'positions')}
             WHERE position_id = '${escapeSql(String(pid))}'`,
          )
          if (posRows.length > 0) {
            const p = posRows[0]
            let sandboxOpenInfo: Record<string, any> | null = null
            if (p.sandbox_order_id) {
              try { sandboxOpenInfo = JSON.parse(p.sandbox_order_id) } catch { /* malformed */ }
            }
            await closeIcOrderAllAccounts(
              String(p.ticker || 'SPY'),
              String(p.expiration || '').slice(0, 10),
              num(p.put_short_strike),
              num(p.put_long_strike),
              num(p.call_short_strike),
              num(p.call_long_strike),
              contracts,
              closePrice,
              String(pid),
              sandboxOpenInfo,
            )
          }
        } catch (sandboxErr) {
          actions.push(`SANDBOX_WARN ${pid}: ${sandboxErr instanceof Error ? sandboxErr.message : String(sandboxErr)}`)
        }
      }

      actions.push(`Closed ${pid}: ${reason} (P&L=$${realizedPnl.toFixed(2)})`)
    }

    // Phase 2: Reconcile paper_account
    const pnlRows = await dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl,
              COUNT(*) as total_trades
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND dte_mode = '${escapeSql(dte)}'`,
    )

    const openRows = await dbQuery(
      `SELECT COALESCE(SUM(collateral_required), 0) as total_collateral,
              COUNT(*) as cnt
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = '${escapeSql(dte)}'`,
    )

    // Read starting_capital from paper_account (not hardcoded)
    const startCapRows = await dbQuery(
      `SELECT COALESCE(starting_capital, 10000) as starting_capital
       FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE AND dte_mode = '${escapeSql(dte)}'
       ORDER BY id DESC LIMIT 1`,
    )
    const startingCapital = num(startCapRows[0]?.starting_capital) || 10000

    const actualPnl = num(pnlRows[0]?.total_pnl)
    const actualTrades = int(pnlRows[0]?.total_trades)
    const actualCollateral = num(openRows[0]?.total_collateral)
    const expectedBalance = Math.round((startingCapital + actualPnl) * 100) / 100
    const correctBp = Math.round((expectedBalance - actualCollateral) * 100) / 100

    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET current_balance = ${expectedBalance},
           cumulative_pnl = ${actualPnl},
           collateral_in_use = ${actualCollateral},
           buying_power = ${correctBp},
           total_trades = ${actualTrades},
           high_water_mark = GREATEST(high_water_mark, ${expectedBalance}),
           updated_at = NOW()
       WHERE dte_mode = '${escapeSql(dte)}'`,
    )

    actions.push(`Reconciled paper_account: balance=$${expectedBalance.toFixed(2)}, pnl=$${actualPnl.toFixed(2)}, collateral=$${actualCollateral.toFixed(2)}, trades=${actualTrades}`)

    // Log the fix
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (log_time, level, message, details, dte_mode)
         VALUES (NOW(), 'RECOVERY',
                 'fix-collateral API: ${actions.length} actions',
                 '${escapeSql(JSON.stringify({ actions, source: 'fix-collateral-api' }))}',
                 '${escapeSql(dte)}')`,
      )
    } catch {
      // Non-fatal
    }

    return NextResponse.json({
      bot: bot.toUpperCase(),
      dte,
      stale_closed: staleRows.length,
      reconciled: {
        balance: expectedBalance,
        cumulative_pnl: actualPnl,
        collateral_in_use: actualCollateral,
        buying_power: correctBp,
        total_trades: actualTrades,
      },
      actions,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
