import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/* ------------------------------------------------------------------ */
/*  Shared: build the WHERE clause for counting day trades.            */
/*  If last_reset_at is set, exclude trades created before the reset.  */
/*  This makes reset persistent without needing to UPDATE pdt_log rows.*/
/* ------------------------------------------------------------------ */

function dayTradeWhereClause(table: string, dte: string, lastResetAt: string | null): {
  sql: string
  params: any[]
} {
  // Base: is_day_trade = TRUE, in rolling 6-day window, weekdays only
  let sql = `SELECT COUNT(*) as cnt FROM ${table}
     WHERE is_day_trade = TRUE AND dte_mode = $1
     AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
     AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`
  const params: any[] = [dte]

  // If a reset happened, only count trades created AFTER the reset
  if (lastResetAt) {
    sql += ` AND created_at > $2`
    params.push(lastResetAt)
  }

  return { sql, params }
}

function triggerTradeQuery(table: string, dte: string, lastResetAt: string | null): {
  sql: string
  params: any[]
} {
  let sql = `SELECT trade_date, position_id FROM ${table}
     WHERE is_day_trade = TRUE AND dte_mode = $1
     AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
     AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`
  const params: any[] = [dte]

  if (lastResetAt) {
    sql += ` AND created_at > $2`
    params.push(lastResetAt)
  }

  sql += ` ORDER BY trade_date ASC`
  return { sql, params }
}

/* ------------------------------------------------------------------ */
/*  GET /api/[bot]/pdt — PDT status for a bot                         */
/* ------------------------------------------------------------------ */

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const botName = bot.toUpperCase()
  const dte = dteMode(bot)!

  try {
    return await buildStatusResponse(bot, botName, dte)
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

/* ------------------------------------------------------------------ */
/*  POST /api/[bot]/pdt — dispatch to toggle or reset                  */
/*  Body: { "action": "toggle", "enabled": bool }                     */
/*  Body: { "action": "reset" }                                        */
/* ------------------------------------------------------------------ */

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const botName = bot.toUpperCase()

  try {
    const body = await req.json()
    const action = body.action as string

    if (action === 'toggle') {
      return handleToggle(bot, botName, body.enabled)
    } else if (action === 'reset') {
      return handleReset(bot, botName)
    } else {
      return NextResponse.json(
        { error: `Unknown action: ${action}. Use "toggle" or "reset".` },
        { status: 400 },
      )
    }
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

/* ------------------------------------------------------------------ */
/*  Toggle PDT enforcement                                             */
/* ------------------------------------------------------------------ */

async function handleToggle(
  bot: string,
  botName: string,
  enabled: boolean,
): Promise<NextResponse> {
  if (typeof enabled !== 'boolean') {
    return NextResponse.json(
      { error: '"enabled" must be a boolean' },
      { status: 400 },
    )
  }

  // Read current state
  const rows = await query(
    `SELECT pdt_enabled FROM ${botTable(bot, 'pdt_config')}
     WHERE bot_name = $1 LIMIT 1`,
    [botName],
  )

  const current = rows[0]?.pdt_enabled !== false

  // No-op if already in requested state
  if (current === enabled) {
    return await buildStatusResponse(bot, botName, dteMode(bot)!)
  }

  // Update — when turning OFF, also reset the counter so bots can trade immediately
  if (enabled) {
    await query(
      `UPDATE ${botTable(bot, 'pdt_config')}
       SET pdt_enabled = $1, updated_at = NOW()
       WHERE bot_name = $2`,
      [enabled, botName],
    )
  } else {
    await query(
      `UPDATE ${botTable(bot, 'pdt_config')}
       SET pdt_enabled = $1, day_trade_count = 0,
           last_reset_at = NOW(), last_reset_by = 'pdt_toggle_off',
           updated_at = NOW()
       WHERE bot_name = $2`,
      [enabled, botName],
    )
    // Clear pdt_log flags (best-effort)
    try {
      await query(
        `UPDATE ${botTable(bot, 'pdt_log')}
         SET is_day_trade = FALSE
         WHERE is_day_trade = TRUE AND dte_mode = $1`,
        [dteMode(bot)!],
      )
    } catch { /* non-critical */ }
  }

  // Audit log
  await query(
    `INSERT INTO ${botTable(bot, 'pdt_audit_log')}
       (bot_name, action, old_value, new_value, reason, performed_by)
     VALUES ($1, $2, $3, $4, $5, $6)`,
    [
      botName,
      enabled ? 'toggle_on' : 'toggle_off',
      JSON.stringify({ pdt_enabled: current }),
      JSON.stringify({ pdt_enabled: enabled }),
      enabled ? 'User toggled PDT enforcement on' : 'User toggled PDT off — counter auto-reset, unlimited trades enabled',
      'user',
    ],
  )

  return await buildStatusResponse(bot, botName, dteMode(bot)!)
}

/* ------------------------------------------------------------------ */
/*  Reset day trade counter                                            */
/*  Strategy: set last_reset_at = NOW() on pdt_config.                 */
/*  All COUNT queries exclude trades created before last_reset_at.     */
/*  This avoids needing to UPDATE individual pdt_log rows.             */
/* ------------------------------------------------------------------ */

async function handleReset(
  bot: string,
  botName: string,
): Promise<NextResponse> {
  const dte = dteMode(bot)!

  // Read current count for audit
  const configRows = await query(
    `SELECT last_reset_at FROM ${botTable(bot, 'pdt_config')}
     WHERE bot_name = $1 LIMIT 1`,
    [botName],
  )
  const currentResetAt = configRows[0]?.last_reset_at ?? null

  const { sql: countSql, params: countParams } = dayTradeWhereClause(
    botTable(bot, 'pdt_log'), dte, currentResetAt,
  )
  const countRows = await query(countSql, countParams)
  const currentCount = parseInt(countRows[0]?.cnt ?? '0', 10)

  // No-op if already 0
  if (currentCount === 0) {
    return await buildStatusResponse(bot, botName, dte)
  }

  // Set last_reset_at = NOW() — this is the ONLY write needed.
  // All COUNT queries will now exclude trades created before this timestamp.
  await query(
    `UPDATE ${botTable(bot, 'pdt_config')}
     SET day_trade_count = 0,
         last_reset_at = NOW(),
         last_reset_by = 'manual',
         updated_at = NOW()
     WHERE bot_name = $1`,
    [botName],
  )

  // Also try to clear pdt_log flags (best-effort, not critical)
  try {
    await query(
      `UPDATE ${botTable(bot, 'pdt_log')}
       SET is_day_trade = FALSE
       WHERE is_day_trade = TRUE AND dte_mode = $1`,
      [dte],
    )
  } catch { /* non-critical — last_reset_at is the real reset mechanism */ }

  // Audit log
  await query(
    `INSERT INTO ${botTable(bot, 'pdt_audit_log')}
       (bot_name, action, old_value, new_value, reason, performed_by)
     VALUES ($1, $2, $3, $4, $5, $6)`,
    [
      botName,
      'reset',
      JSON.stringify({ day_trade_count: currentCount }),
      JSON.stringify({ day_trade_count: 0 }),
      `Manual reset — trades before reset timestamp excluded from count`,
      'user',
    ],
  )

  return await buildStatusResponse(bot, botName, dte)
}

/* ------------------------------------------------------------------ */
/*  Helper: get trigger trades (dates that count toward PDT)           */
/* ------------------------------------------------------------------ */

async function getTriggerTrades(bot: string, dte: string, lastResetAt: string | null) {
  const { sql, params } = triggerTradeQuery(botTable(bot, 'pdt_log'), dte, lastResetAt)
  const rows = await query(sql, params)

  // Group by trade_date (multiple trades on same day count as 1 for display)
  const byDate = new Map<string, string[]>()
  for (const r of rows) {
    const td = typeof r.trade_date === 'string'
      ? new Date(r.trade_date + 'T00:00:00')
      : new Date(r.trade_date)
    const dateStr = td.toISOString().split('T')[0]
    const existing = byDate.get(dateStr) || []
    existing.push(r.position_id || 'unknown')
    byDate.set(dateStr, existing)
  }

  return Array.from(byDate.entries()).map(([dateStr, posIds]) => {
    const td = new Date(dateStr + 'T00:00:00')
    // Trade exits window after 7 calendar days (trade_date + 7)
    const fallsOff = new Date(td)
    fallsOff.setDate(fallsOff.getDate() + 7)
    // If falls on weekend, advance to Monday
    const dow = fallsOff.getDay()
    if (dow === 0) fallsOff.setDate(fallsOff.getDate() + 1)  // Sun → Mon
    if (dow === 6) fallsOff.setDate(fallsOff.getDate() + 2)  // Sat → Mon
    return {
      trade_date: dateStr,
      falls_off: fallsOff.toISOString().split('T')[0],
      position_ids: posIds,
    }
  })
}

/* ------------------------------------------------------------------ */
/*  Helper: build full PDT status JSON response                        */
/*  All COUNT queries respect last_reset_at for persistent resets.      */
/* ------------------------------------------------------------------ */

async function buildStatusResponse(
  bot: string,
  botName: string,
  dte: string,
): Promise<NextResponse> {
  const configRows = await query(
    `SELECT pdt_enabled, max_day_trades,
            max_trades_per_day, window_days,
            last_reset_at, last_reset_by
     FROM ${botTable(bot, 'pdt_config')}
     WHERE bot_name = $1
     LIMIT 1`,
    [botName],
  )

  const cfg = configRows[0] ?? {
    pdt_enabled: true,
    max_day_trades: 4,
    max_trades_per_day: 1,
    window_days: 5,
    last_reset_at: null,
    last_reset_by: null,
  }

  const pdtEnabled = cfg.pdt_enabled !== false
  const maxDayTrades = cfg.max_day_trades != null ? parseInt(String(cfg.max_day_trades), 10) : 4
  const maxTradesPerDay = cfg.max_trades_per_day != null ? parseInt(String(cfg.max_trades_per_day), 10) : 1
  const windowDays = parseInt(cfg.window_days ?? '5', 10) || 5
  const lastResetAt = cfg.last_reset_at?.toISOString?.() ?? cfg.last_reset_at ?? null

  // Count from pdt_log — respects last_reset_at for persistent resets
  const { sql: countSql, params: countParams } = dayTradeWhereClause(
    botTable(bot, 'pdt_log'), dte, lastResetAt,
  )
  const countRows = await query(countSql, countParams)
  const dayTradeCount = parseInt(countRows[0]?.cnt ?? '0', 10)

  const todayRows = await query(
    `SELECT COUNT(*) as cnt
     FROM ${botTable(bot, 'pdt_log')}
     WHERE trade_date = CURRENT_DATE AND dte_mode = $1`,
    [dte],
  )
  const tradedToday = maxTradesPerDay > 0 && parseInt(todayRows[0]?.cnt ?? '0', 10) >= maxTradesPerDay

  let isBlocked = false
  let blockReason: string | null = null

  if (pdtEnabled && maxDayTrades > 0) {
    if (dayTradeCount >= maxDayTrades) {
      isBlocked = true
      blockReason = `PDT limit reached: ${dayTradeCount}/${maxDayTrades} day trades in rolling ${windowDays} days`
    } else if (tradedToday) {
      isBlocked = true
      blockReason = `Already traded today (max ${maxTradesPerDay}/day)`
    }
  }

  const triggerTrades = await getTriggerTrades(bot, dte, lastResetAt)
  const nextSlotOpens = triggerTrades.length > 0 ? triggerTrades[0].falls_off : null

  return NextResponse.json({
    bot_name: botName,
    pdt_enabled: pdtEnabled,
    day_trade_count: dayTradeCount,
    max_day_trades: maxDayTrades,
    trades_remaining: maxDayTrades > 0 ? Math.max(0, maxDayTrades - dayTradeCount) : -1,
    max_trades_per_day: maxTradesPerDay,
    traded_today: tradedToday,
    can_trade: !isBlocked,
    window_days: windowDays,
    last_reset_at: lastResetAt,
    last_reset_by: cfg.last_reset_by ?? null,
    is_blocked: isBlocked,
    block_reason: blockReason,
    trigger_trades: triggerTrades,
    next_slot_opens: nextSlotOpens,
  })
}
