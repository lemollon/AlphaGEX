import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode, CT_TODAY } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * Record a broker-CONFIRMED iron-condor position that the scanner never wrote
 * to the DB (a "phantom"/untracked trade), as a CLOSED row with operator-supplied
 * realized P&L, then recompute that day's {bot}_daily_perf.
 *
 * WHY THIS EXISTS
 * ---------------
 * On 2026-05-25 (Memorial Day) the scanner had no holiday calendar, queued 7 ICs
 * into a closed market; they filled at the 5/26 open and were dumped for a real
 * −$223 — but were never recorded in spark_positions. The correction endpoints
 * (manual-correct-trade, recover-phantom-trade) all require the row to already
 * exist, and diagnose-live-pnl only inserts OPEN rows + can't classify the
 * single-leg aggregate closes. This endpoint is the missing operator tool:
 * insert a broker-verified CLOSED position from exact numbers off the broker.
 *
 * Inserts status='closed' with all advisory/context fields zeroed (post-hoc,
 * no signal record), mirroring diagnose-live-pnl's canonical insert. realized_pnl
 * is operator-supplied (broker truth); close_price is back-computed if omitted.
 *
 * GET  preview only (no writes)
 * POST applies when ?confirm=true
 *
 * Required params: person, expiration (YYYY-MM-DD), put_short, put_long,
 *   call_short, call_long, contracts, total_credit, realized_pnl
 * Optional: account_type(=production), position_id(auto), close_price(back-computed),
 *   close_reason(=reconcile_untracked), open_date(=expiration−1), ticker(=SPY)
 */

interface RecordInputs {
  positionId: string
  person: string
  accountType: string
  ticker: string
  expiration: string
  openDate: string
  putShort: number
  putLong: number
  callShort: number
  callLong: number
  contracts: number
  totalCredit: number
  realizedPnl: number
  closePrice: number
  closeReason: string
  confirm: boolean
}

function parseInputs(req: NextRequest, bot: string): { inputs?: RecordInputs; error?: string } {
  const q = req.nextUrl.searchParams
  const reqNum = (name: string): number | null => {
    const raw = q.get(name)
    if (raw == null || raw === '') return null
    const n = parseFloat(raw)
    return Number.isFinite(n) ? n : null
  }

  const person = q.get('person')
  if (!person) return { error: 'person is required' }
  const expiration = q.get('expiration')
  if (!expiration || !/^\d{4}-\d{2}-\d{2}$/.test(expiration)) return { error: 'expiration (YYYY-MM-DD) is required' }

  const putShort = reqNum('put_short'), putLong = reqNum('put_long')
  const callShort = reqNum('call_short'), callLong = reqNum('call_long')
  const contracts = reqNum('contracts'), totalCredit = reqNum('total_credit')
  const realizedPnl = reqNum('realized_pnl')
  for (const [k, v] of Object.entries({ put_short: putShort, put_long: putLong, call_short: callShort, call_long: callLong, contracts, total_credit: totalCredit, realized_pnl: realizedPnl })) {
    if (v == null) return { error: `${k} is required and must be numeric` }
  }
  if ((contracts as number) <= 0) return { error: 'contracts must be > 0' }

  // close_price back-computed from realized_pnl when omitted:
  //   realized_pnl = (total_credit − close_price) × 100 × contracts
  let closePrice = reqNum('close_price')
  if (closePrice == null) {
    closePrice = Math.round(((totalCredit as number) - (realizedPnl as number) / (100 * (contracts as number))) * 10000) / 10000
  }

  // open_date defaults to the day before expiration (1DTE) for display only.
  let openDate = q.get('open_date')
  if (!openDate) {
    const d = new Date(expiration + 'T12:00:00'); d.setDate(d.getDate() - 1)
    openDate = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }

  return {
    inputs: {
      positionId: q.get('position_id') || `${bot.toUpperCase()}-RECON-${openDate.replace(/-/g, '')}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
      person,
      accountType: q.get('account_type') || 'production',
      ticker: q.get('ticker') || 'SPY',
      expiration,
      openDate,
      putShort: putShort as number,
      putLong: putLong as number,
      callShort: callShort as number,
      callLong: callLong as number,
      contracts: contracts as number,
      totalCredit: totalCredit as number,
      realizedPnl: Math.round((realizedPnl as number) * 100) / 100,
      closePrice,
      closeReason: q.get('close_reason') || 'reconcile_untracked',
      confirm: q.get('confirm') === 'true',
    },
  }
}

async function buildPlan(bot: string, i: RecordInputs) {
  const positionsTable = botTable(bot, 'positions')
  // Refuse if a row with this position_id already exists (idempotency / no dupes).
  const existing = await dbQuery(`SELECT position_id, status, realized_pnl FROM ${positionsTable} WHERE position_id = $1 LIMIT 1`, [i.positionId])
  const spreadWidth = Math.round((i.putShort - i.putLong) * 100) / 100
  const maxProfit = Math.round(i.totalCredit * 100 * i.contracts * 100) / 100
  const collateral = Math.round(Math.max(0, (spreadWidth - i.totalCredit)) * 100 * i.contracts * 100) / 100

  // Preview the resulting daily_perf sum for (close date, person, account_type).
  const sumRows = await dbQuery(
    `SELECT COALESCE(SUM(realized_pnl), 0) AS sum_pnl
     FROM ${positionsTable}
     WHERE (close_time AT TIME ZONE 'America/Chicago')::date = $1
       AND status IN ('closed','expired')
       AND person = $2
       AND COALESCE(account_type,'sandbox') = $3`,
    [i.openDate, i.person, i.accountType],   // close date stamped = today on apply; preview uses open_date label only
  ).catch(() => [{ sum_pnl: 0 }])

  return {
    position_id: i.positionId,
    already_exists: existing.length > 0,
    existing_row: existing[0] ?? null,
    insert: {
      person: i.person,
      account_type: i.accountType,
      ticker: i.ticker,
      expiration: i.expiration,
      open_date: i.openDate,
      strikes: { put_long: i.putLong, put_short: i.putShort, call_short: i.callShort, call_long: i.callLong },
      contracts: i.contracts,
      spread_width: spreadWidth,
      total_credit: i.totalCredit,
      close_price: i.closePrice,
      realized_pnl: i.realizedPnl,
      max_profit: maxProfit,
      collateral_required: collateral,
      close_reason: i.closeReason,
      status: 'closed',
    },
    current_day_realized_excluding_this: num(sumRows[0]?.sum_pnl),
  }
}

function buildInsertSql(bot: string, i: RecordInputs): { sql: string; params: any[] } {
  const spreadWidth = Math.round((i.putShort - i.putLong) * 100) / 100
  const halfCredit = Math.round((i.totalCredit / 2) * 10000) / 10000
  const maxProfit = Math.round(i.totalCredit * 100 * i.contracts * 100) / 100
  const collateral = Math.round(Math.max(0, (spreadWidth - i.totalCredit)) * 100 * i.contracts * 100) / 100
  const dte = dteMode(bot) || '1DTE'
  // Column set mirrors lib/scanner.ts / diagnose-live-pnl canonical INSERT, but
  // status='closed' with close fields populated and advisory fields zeroed.
  const sql = `INSERT INTO ${botTable(bot, 'positions')} (
      position_id, ticker, expiration,
      put_short_strike, put_long_strike, put_credit,
      call_short_strike, call_long_strike, call_credit,
      contracts, spread_width, total_credit, max_loss, max_profit,
      collateral_required,
      underlying_at_entry, vix_at_entry, expected_move,
      call_wall, put_wall, gex_regime, flip_point, net_gex,
      oracle_confidence, oracle_win_probability, oracle_advice,
      oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
      wings_adjusted, original_put_width, original_call_width,
      put_order_id, call_order_id,
      status, open_time, open_date, close_time, close_price, close_reason, realized_pnl,
      dte_mode, person, account_type
    ) VALUES (
      $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
      $11, $12, $13, $14, $15, 0, 0, 0,
      0, 0, 'UNKNOWN', 0, 0,
      0, 0, 'RECONCILE',
      'Recorded by /api/{bot}/record-untracked-trade — broker-confirmed untracked fill', '[]', false,
      false, $11, $11,
      'RECONCILE', 'RECONCILE',
      'closed', ($16::date + TIME '09:00')::timestamptz, $16::date, NOW(), $17, $18, $19,
      $20, $21, $22
    )`
  // NOTE: spark_positions has no unique index on position_id (PK is on id), so we
  // cannot use ON CONFLICT here. Duplicate inserts are prevented by the
  // already_exists SELECT guard + 409 refusal in POST.
  const params = [
    i.positionId, i.ticker, i.expiration,
    i.putShort, i.putLong, halfCredit,
    i.callShort, i.callLong, halfCredit,
    i.contracts, spreadWidth, i.totalCredit, collateral, maxProfit, collateral,
    i.openDate, i.closePrice, i.closeReason, i.realizedPnl,
    dte, i.person, i.accountType,
  ]
  return { sql, params }
}

export async function GET(req: NextRequest, { params }: { params: { bot: string } }) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const { inputs, error } = parseInputs(req, bot)
  if (error) return NextResponse.json({ error }, { status: 400 })
  try {
    const plan = await buildPlan(bot, inputs!)
    return NextResponse.json({ mode: 'preview', note: 'pass &confirm=true via POST to apply', ...plan })
  } catch (e: unknown) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 })
  }
}

export async function POST(req: NextRequest, { params }: { params: { bot: string } }) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const { inputs, error } = parseInputs(req, bot)
  if (error) return NextResponse.json({ error }, { status: 400 })
  const i = inputs!
  try {
    const plan = await buildPlan(bot, i)
    if (plan.already_exists) {
      return NextResponse.json({ error: `position_id ${i.positionId} already exists (status=${plan.existing_row?.status}). Refusing to duplicate.`, ...plan }, { status: 409 })
    }
    if (!i.confirm) {
      return NextResponse.json({ mode: 'preview_via_post', note: 'pass &confirm=true to apply', ...plan })
    }

    const { sql, params: insParams } = buildInsertSql(bot, i)
    const affected = await dbExecute(sql, insParams)

    // Recompute that day's daily_perf as SUM of all closed rows for (date, person, account_type).
    // close_time stamped = today (apply date); recompute on the apply CT date.
    const positionsTable = botTable(bot, 'positions')
    const dailyPerfTable = botTable(bot, 'daily_perf')
    let newDailySum: number | null = null
    try {
      const sumRows = await dbQuery(
        `SELECT COALESCE(SUM(realized_pnl),0) AS s, COUNT(*) AS c
         FROM ${positionsTable}
         WHERE (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
           AND status IN ('closed','expired') AND person = $1
           AND COALESCE(account_type,'sandbox') = $2`,
        [i.person, i.accountType],
      )
      newDailySum = Math.round(num(sumRows[0]?.s) * 100) / 100
      await dbExecute(
        `INSERT INTO ${dailyPerfTable} (trade_date, trades_executed, positions_closed, realized_pnl, updated_at, person, account_type)
         VALUES (${CT_TODAY}, 0, $1, $2, NOW(), $3, $4)
         ON CONFLICT (trade_date, COALESCE(person, ''), COALESCE(account_type, 'sandbox'))
         DO UPDATE SET realized_pnl = EXCLUDED.realized_pnl, positions_closed = EXCLUDED.positions_closed, updated_at = NOW()`,
        [int(sumRows[0]?.c), newDailySum, i.person, i.accountType],
      ).catch(() => { /* daily_perf upsert best-effort (conflict target may differ) */ })
    } catch { /* recompute best-effort */ }

    // Durable audit trail.
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (log_time, level, message, details, dte_mode, account_type)
         VALUES (NOW(), 'RECONCILE', $1, $2, $3, $4)`,
        [
          `record-untracked-trade: inserted ${i.positionId} (${i.contracts}x ${i.putShort}/${i.callShort}) realized_pnl=$${i.realizedPnl}`,
          JSON.stringify({ source: 'record-untracked-trade', inserted: affected, plan }),
          dteMode(bot) || '1DTE', i.accountType,
        ],
      )
    } catch { /* best-effort log */ }

    return NextResponse.json({
      mode: 'applied',
      inserted: affected,
      position_id: i.positionId,
      realized_pnl: i.realizedPnl,
      new_day_realized_sum: newDailySum,
      plan,
    })
  } catch (e: unknown) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 })
  }
}
