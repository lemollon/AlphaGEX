import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * Operator-driven correction for a single closed position's realized_pnl.
 *
 * Used when reconciliation against Tradier order/transaction history can't
 * recover the true outcome (e.g., position expired ITM with assignment, no
 * close order to match) and the operator has the actual P&L from the broker
 * statement. Rather than guessing, the operator passes the exact value.
 *
 * Updates atomically:
 *   1. {bot}_positions: realized_pnl + close_price + close_reason
 *   2. {bot}_daily_perf: recomputes the day's realized_pnl as SUM of all
 *      closed positions for that (date, person, account_type)
 *
 * close_price is optional — if not provided, back-computed from realized_pnl
 * so that (entry_credit - close_price) * 100 * contracts == realized_pnl.
 *
 * GET  preview only (returns what the update would do, no writes)
 * POST applies when ?confirm=true
 *
 * Usage:
 *   GET  /api/spark/manual-correct-trade?position_id=X&realized_pnl=-20
 *   POST /api/spark/manual-correct-trade?position_id=X&realized_pnl=-20&confirm=true
 *   POST /api/spark/manual-correct-trade?position_id=X&realized_pnl=-20&close_reason=expired_itm_assigned&confirm=true
 */

interface CorrectionPlan {
  position_id: string
  person: string | null
  account_type: string
  trade_date_ct: string | null
  contracts: number
  entry_credit: number
  stored_before: {
    close_price: number
    realized_pnl: number
    close_reason: string | null
  }
  proposed: {
    close_price: number
    realized_pnl: number
    close_reason: string
  }
  delta: {
    close_price_change: number
    realized_pnl_change: number
  }
  daily_perf_recompute: {
    trade_date: string | null
    person: string | null
    account_type: string
    new_sum: number | null
  }
}

async function buildCorrectionPlan(
  bot: string,
  positionId: string,
  realizedPnl: number,
  closePriceParam: number | null,
  closeReason: string,
): Promise<{ plan: CorrectionPlan } | { error: string; status: number }> {
  const rows = await dbQuery(
    `SELECT position_id, account_type, person, contracts, total_credit,
            close_price, realized_pnl, close_reason, close_time, status
     FROM ${botTable(bot, 'positions')}
     WHERE position_id = $1
     LIMIT 1`,
    [positionId],
  )
  if (!rows.length) {
    return { error: `position_id ${positionId} not found in ${bot}_positions`, status: 404 }
  }
  const pos = rows[0]
  if (pos.status !== 'closed' && pos.status !== 'expired') {
    return { error: `position is ${pos.status}; manual correction is for closed/expired only`, status: 400 }
  }

  const contracts = int(pos.contracts)
  const entryCredit = num(pos.total_credit)
  const accountType = (pos.account_type || 'sandbox') as string
  const person = pos.person as string | null

  // Back-compute close_price from realized_pnl when not supplied:
  //   realized_pnl = (entry_credit - close_price) * 100 * contracts
  //   close_price = entry_credit - realized_pnl / (100 * contracts)
  let closePrice = closePriceParam
  if (closePrice == null) {
    if (contracts <= 0) {
      return { error: 'cannot back-compute close_price: contracts is zero', status: 400 }
    }
    closePrice = Math.round((entryCredit - realizedPnl / (100 * contracts)) * 10000) / 10000
  }

  // CT-date of the close, for daily_perf reconciliation
  let tradeDateCt: string | null = null
  if (pos.close_time) {
    const ct = new Date(new Date(pos.close_time).toLocaleString('en-US', { timeZone: 'America/Chicago' }))
    tradeDateCt = `${ct.getFullYear()}-${String(ct.getMonth() + 1).padStart(2, '0')}-${String(ct.getDate()).padStart(2, '0')}`
  }

  // Preview the new daily_perf sum (excluding this row's old value, plus the new value)
  let newDailySum: number | null = null
  if (tradeDateCt) {
    const sumRows = await dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) AS sum_pnl
       FROM ${botTable(bot, 'positions')}
       WHERE (close_time AT TIME ZONE 'America/Chicago')::date = $1
         AND status IN ('closed', 'expired')
         AND person ${person ? '= $2' : 'IS NULL'}
         AND COALESCE(account_type, 'sandbox') = $${person ? '3' : '2'}
         AND position_id <> $${person ? '4' : '3'}`,
      person
        ? [tradeDateCt, person, accountType, positionId]
        : [tradeDateCt, accountType, positionId],
    )
    newDailySum = num(sumRows[0]?.sum_pnl) + realizedPnl
    newDailySum = Math.round(newDailySum * 100) / 100
  }

  return {
    plan: {
      position_id: positionId,
      person,
      account_type: accountType,
      trade_date_ct: tradeDateCt,
      contracts,
      entry_credit: entryCredit,
      stored_before: {
        close_price: num(pos.close_price),
        realized_pnl: num(pos.realized_pnl),
        close_reason: pos.close_reason,
      },
      proposed: {
        close_price: closePrice,
        realized_pnl: Math.round(realizedPnl * 100) / 100,
        close_reason: closeReason,
      },
      delta: {
        close_price_change: Math.round((closePrice - num(pos.close_price)) * 10000) / 10000,
        realized_pnl_change: Math.round((realizedPnl - num(pos.realized_pnl)) * 100) / 100,
      },
      daily_perf_recompute: {
        trade_date: tradeDateCt,
        person,
        account_type: accountType,
        new_sum: newDailySum,
      },
    },
  }
}

function parseInputs(req: NextRequest): { positionId: string | null; realizedPnl: number | null; closePrice: number | null; closeReason: string; confirm: boolean; error?: string } {
  const positionId = req.nextUrl.searchParams.get('position_id')
  const pnlRaw = req.nextUrl.searchParams.get('realized_pnl')
  const priceRaw = req.nextUrl.searchParams.get('close_price')
  const closeReason = req.nextUrl.searchParams.get('close_reason') || 'manual_correction'
  const confirm = req.nextUrl.searchParams.get('confirm') === 'true'

  if (!positionId) return { positionId: null, realizedPnl: null, closePrice: null, closeReason, confirm, error: 'position_id query param is required' }
  if (pnlRaw == null) return { positionId, realizedPnl: null, closePrice: null, closeReason, confirm, error: 'realized_pnl query param is required' }
  const realizedPnl = parseFloat(pnlRaw)
  if (!Number.isFinite(realizedPnl)) return { positionId, realizedPnl: null, closePrice: null, closeReason, confirm, error: `realized_pnl must be a finite number (got '${pnlRaw}')` }
  let closePrice: number | null = null
  if (priceRaw != null) {
    closePrice = parseFloat(priceRaw)
    if (!Number.isFinite(closePrice) || closePrice < 0) {
      return { positionId, realizedPnl, closePrice: null, closeReason, confirm, error: `close_price must be a non-negative number (got '${priceRaw}')` }
    }
  }
  return { positionId, realizedPnl, closePrice, closeReason, confirm }
}

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const inputs = parseInputs(req)
  if (inputs.error) return NextResponse.json({ error: inputs.error }, { status: 400 })

  try {
    const result = await buildCorrectionPlan(bot, inputs.positionId!, inputs.realizedPnl!, inputs.closePrice, inputs.closeReason)
    if ('error' in result) return NextResponse.json({ error: result.error }, { status: result.status })
    return NextResponse.json({ mode: 'preview', ...result.plan })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const inputs = parseInputs(req)
  if (inputs.error) return NextResponse.json({ error: inputs.error }, { status: 400 })

  try {
    const result = await buildCorrectionPlan(bot, inputs.positionId!, inputs.realizedPnl!, inputs.closePrice, inputs.closeReason)
    if ('error' in result) return NextResponse.json({ error: result.error }, { status: result.status })

    if (!inputs.confirm) {
      return NextResponse.json({ mode: 'preview_via_post', note: 'pass &confirm=true to apply', ...result.plan })
    }

    const dte = dteMode(bot)
    const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
    const positionsTable = botTable(bot, 'positions')
    const dailyPerfTable = botTable(bot, 'daily_perf')

    // Update the position row
    const positionRows = await dbExecute(
      `UPDATE ${positionsTable}
       SET close_price = $1,
           realized_pnl = $2,
           close_reason = $3,
           updated_at = NOW()
       WHERE position_id = $4 ${dteFilter}`,
      [result.plan.proposed.close_price, result.plan.proposed.realized_pnl, result.plan.proposed.close_reason, inputs.positionId!],
    )

    // Recompute daily_perf for the affected (date, person, account_type) by
    // summing the now-corrected positions table. If the row doesn't exist
    // yet, ON CONFLICT clause will insert it.
    let dailyPerfRows = 0
    if (result.plan.trade_date_ct) {
      const tradeDate = result.plan.trade_date_ct
      const personVal = result.plan.person
      const accountType = result.plan.account_type
      const sumRows = await dbQuery(
        `SELECT
          COUNT(*) FILTER (WHERE status IN ('closed','expired')) AS positions_closed,
          COALESCE(SUM(realized_pnl), 0) AS realized_pnl
         FROM ${positionsTable}
         WHERE (close_time AT TIME ZONE 'America/Chicago')::date = $1
           AND status IN ('closed', 'expired')
           AND person ${personVal ? '= $2' : 'IS NULL'}
           AND COALESCE(account_type, 'sandbox') = $${personVal ? '3' : '2'}`,
        personVal ? [tradeDate, personVal, accountType] : [tradeDate, accountType],
      )
      const newPositionsClosed = int(sumRows[0]?.positions_closed)
      const newRealizedPnl = num(sumRows[0]?.realized_pnl)
      dailyPerfRows = await dbExecute(
        `UPDATE ${dailyPerfTable}
         SET realized_pnl = $1,
             positions_closed = $2,
             updated_at = NOW()
         WHERE trade_date = $3
           AND person ${personVal ? '= $4' : 'IS NULL'}
           AND COALESCE(account_type, 'sandbox') = $${personVal ? '5' : '4'}`,
        personVal
          ? [newRealizedPnl, newPositionsClosed, tradeDate, personVal, accountType]
          : [newRealizedPnl, newPositionsClosed, tradeDate, accountType],
      )
    }

    return NextResponse.json({
      mode: 'applied',
      position_rows_updated: positionRows,
      daily_perf_rows_updated: dailyPerfRows,
      ...result.plan,
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
