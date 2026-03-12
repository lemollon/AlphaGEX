import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, sharedTable, botTable, escapeSql, validateBot, dteMode } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

const PDT_CONFIG = sharedTable('ironforge_pdt_config')

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Format a Date as YYYY-MM-DD using local time (NOT toISOString which shifts to UTC). */
function localDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function toInt(val: any): number {
  if (val == null || val === '') return 0
  const n = parseInt(String(val), 10)
  return isNaN(n) ? 0 : n
}

/**
 * Count day trades in the rolling window.
 * Reads from {bot}_pdt_log (per-bot table the scanner writes to).
 * If last_reset_at is set, exclude trades created before the reset.
 */
function dayTradeCountSql(bot: string, dte: string, lastResetAt: string | null): string {
  const table = botTable(bot, 'pdt_log')
  let sql = `SELECT COUNT(*) as cnt FROM ${table}
     WHERE is_day_trade = TRUE AND dte_mode = '${escapeSql(dte)}'
     AND trade_date >= DATE_SUB(CURRENT_DATE(), 6)
     AND DAYOFWEEK(trade_date) BETWEEN 2 AND 6`
  if (lastResetAt) {
    sql += ` AND created_at > '${escapeSql(lastResetAt)}'`
  }
  return sql
}

/**
 * Get trigger trades (dates that count toward PDT) from {bot}_pdt_log.
 */
function triggerTradeSql(bot: string, dte: string, lastResetAt: string | null): string {
  const table = botTable(bot, 'pdt_log')
  let sql = `SELECT trade_date, position_id FROM ${table}
     WHERE is_day_trade = TRUE AND dte_mode = '${escapeSql(dte)}'
     AND trade_date >= DATE_SUB(CURRENT_DATE(), 6)
     AND DAYOFWEEK(trade_date) BETWEEN 2 AND 6`
  if (lastResetAt) {
    sql += ` AND created_at > '${escapeSql(lastResetAt)}'`
  }
  sql += ` ORDER BY trade_date ASC`
  return sql
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
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

/* ------------------------------------------------------------------ */
/*  POST /api/[bot]/pdt — dispatch to toggle or reset                  */
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
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
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

  // Read current state from shared table
  const rows = await dbQuery(
    `SELECT pdt_enabled FROM ${PDT_CONFIG}
     WHERE bot_name = '${escapeSql(botName)}' LIMIT 1`,
  )
  const current = rows[0]?.pdt_enabled !== false && rows[0]?.pdt_enabled !== 'false'

  // No-op if already in requested state
  if (current === enabled) {
    return await buildStatusResponse(bot, botName, dteMode(bot)!)
  }

  // Update shared table — when turning OFF, also reset the counter
  if (enabled) {
    await dbExecute(
      `UPDATE ${PDT_CONFIG}
       SET pdt_enabled = ${enabled}, updated_at = CURRENT_TIMESTAMP()
       WHERE bot_name = '${escapeSql(botName)}'`,
    )
  } else {
    await dbExecute(
      `UPDATE ${PDT_CONFIG}
       SET pdt_enabled = FALSE, day_trade_count = 0,
           last_reset_at = CURRENT_TIMESTAMP(), last_reset_by = 'pdt_toggle_off',
           updated_at = CURRENT_TIMESTAMP()
       WHERE bot_name = '${escapeSql(botName)}'`,
    )
    // Clear pdt_log flags (best-effort)
    try {
      const dte = dteMode(bot)!
      await dbExecute(
        `UPDATE ${botTable(bot, 'pdt_log')}
         SET is_day_trade = FALSE
         WHERE is_day_trade = TRUE AND dte_mode = '${escapeSql(dte)}'`,
      )
    } catch { /* non-critical */ }
  }

  // Audit log (per-bot table)
  const oldJson = JSON.stringify({ pdt_enabled: current }).replace(/'/g, "''")
  const newJson = JSON.stringify({ pdt_enabled: enabled }).replace(/'/g, "''")
  const reason = enabled
    ? 'User toggled PDT enforcement on'
    : 'User toggled PDT off — counter auto-reset, unlimited trades enabled'
  await dbExecute(
    `INSERT INTO ${botTable(bot, 'pdt_audit_log')}
       (bot_name, action, old_value, new_value, reason, performed_by, created_at)
     VALUES ('${escapeSql(botName)}', '${enabled ? 'toggle_on' : 'toggle_off'}',
             '${oldJson}', '${newJson}', '${escapeSql(reason)}', 'user', CURRENT_TIMESTAMP())`,
  )

  return await buildStatusResponse(bot, botName, dteMode(bot)!)
}

/* ------------------------------------------------------------------ */
/*  Reset day trade counter                                            */
/* ------------------------------------------------------------------ */

async function handleReset(
  bot: string,
  botName: string,
): Promise<NextResponse> {
  const dte = dteMode(bot)!

  // Read current state from shared table
  const configRows = await dbQuery(
    `SELECT last_reset_at FROM ${PDT_CONFIG}
     WHERE bot_name = '${escapeSql(botName)}' LIMIT 1`,
  )
  const currentResetAt = configRows[0]?.last_reset_at ?? null

  // Count current day trades
  const countRows = await dbQuery(dayTradeCountSql(bot, dte, currentResetAt))
  const currentCount = toInt(countRows[0]?.cnt)

  // No-op if already 0
  if (currentCount === 0) {
    return await buildStatusResponse(bot, botName, dte)
  }

  // Set last_reset_at = NOW() on shared table
  await dbExecute(
    `UPDATE ${PDT_CONFIG}
     SET day_trade_count = 0,
         last_reset_at = CURRENT_TIMESTAMP(),
         last_reset_by = 'manual',
         updated_at = CURRENT_TIMESTAMP()
     WHERE bot_name = '${escapeSql(botName)}'`,
  )

  // Clear pdt_log flags (best-effort)
  try {
    await dbExecute(
      `UPDATE ${botTable(bot, 'pdt_log')}
       SET is_day_trade = FALSE
       WHERE is_day_trade = TRUE AND dte_mode = '${escapeSql(dte)}'`,
    )
  } catch { /* non-critical — last_reset_at is the real reset mechanism */ }

  // Audit log (per-bot table)
  const oldJson = JSON.stringify({ day_trade_count: currentCount }).replace(/'/g, "''")
  const newJson = JSON.stringify({ day_trade_count: 0 }).replace(/'/g, "''")
  await dbExecute(
    `INSERT INTO ${botTable(bot, 'pdt_audit_log')}
       (bot_name, action, old_value, new_value, reason, performed_by, created_at)
     VALUES ('${escapeSql(botName)}', 'reset',
             '${oldJson}', '${newJson}',
             'Manual reset — trades before reset timestamp excluded from count',
             'user', CURRENT_TIMESTAMP())`,
  )

  return await buildStatusResponse(bot, botName, dte)
}

/* ------------------------------------------------------------------ */
/*  Helper: get trigger trades                                         */
/* ------------------------------------------------------------------ */

async function getTriggerTrades(bot: string, dte: string, lastResetAt: string | null) {
  const rows = await dbQuery(triggerTradeSql(bot, dte, lastResetAt))

  // Group by trade_date
  const byDate = new Map<string, string[]>()
  for (const r of rows) {
    const td = typeof r.trade_date === 'string'
      ? new Date(r.trade_date + 'T12:00:00')
      : new Date(r.trade_date)
    const ds = localDateStr(td)
    const existing = byDate.get(ds) || []
    existing.push(r.position_id || 'unknown')
    byDate.set(ds, existing)
  }

  return Array.from(byDate.entries()).map(([ds, posIds]) => {
    const td = new Date(ds + 'T12:00:00')
    // Trade exits window after 7 calendar days (trade_date + 7)
    const fallsOff = new Date(td)
    fallsOff.setDate(fallsOff.getDate() + 7)
    // If falls on weekend, advance to Monday
    const dow = fallsOff.getDay()
    if (dow === 0) fallsOff.setDate(fallsOff.getDate() + 1)  // Sun → Mon
    if (dow === 6) fallsOff.setDate(fallsOff.getDate() + 2)  // Sat → Mon
    return {
      trade_date: ds,
      falls_off: localDateStr(fallsOff),
      position_ids: posIds,
    }
  })
}

/* ------------------------------------------------------------------ */
/*  Helper: build full PDT status JSON response                        */
/*  Reads from ironforge_pdt_config (shared) + {bot}_pdt_log (per-bot) */
/* ------------------------------------------------------------------ */

async function buildStatusResponse(
  bot: string,
  botName: string,
  dte: string,
): Promise<NextResponse> {
  const configRows = await dbQuery(
    `SELECT pdt_enabled, max_day_trades,
            max_trades_per_day, window_days,
            last_reset_at, last_reset_by
     FROM ${PDT_CONFIG}
     WHERE bot_name = '${escapeSql(botName)}'
     LIMIT 1`,
  )

  const cfg = configRows[0] ?? {
    pdt_enabled: true,
    max_day_trades: 4,
    max_trades_per_day: 1,
    window_days: 5,
    last_reset_at: null,
    last_reset_by: null,
  }

  const pdtEnabled = cfg.pdt_enabled !== false && cfg.pdt_enabled !== 'false'
  const maxDayTrades = toInt(cfg.max_day_trades) || 4
  const maxTradesPerDay = toInt(cfg.max_trades_per_day)
  const windowDays = toInt(cfg.window_days) || 5
  const lastResetAt = cfg.last_reset_at ?? null

  // Count from {bot}_pdt_log — respects last_reset_at
  const countRows = await dbQuery(dayTradeCountSql(bot, dte, lastResetAt))
  const dayTradeCount = toInt(countRows[0]?.cnt)

  const todayRows = await dbQuery(
    `SELECT COUNT(*) as cnt, MIN(opened_at) as first_trade_time
     FROM ${botTable(bot, 'pdt_log')}
     WHERE trade_date = CURRENT_DATE() AND dte_mode = '${escapeSql(dte)}'`,
  )
  const todayTradesCount = toInt(todayRows[0]?.cnt)
  const tradedToday = maxTradesPerDay > 0 && todayTradesCount >= maxTradesPerDay
  const todayTradeTime = todayRows[0]?.first_trade_time
    ? String(todayRows[0].first_trade_time)
    : null

  // is_blocked = only rolling PDT limit
  let isBlocked = false
  let blockReason: string | null = null

  if (pdtEnabled && maxDayTrades > 0 && dayTradeCount >= maxDayTrades) {
    isBlocked = true
    blockReason = `${dayTradeCount}/${maxDayTrades} day trades used`
  }

  // pdt_status enum
  let pdtStatus: string
  if (!pdtEnabled) {
    pdtStatus = 'PDT_OFF'
  } else if (isBlocked) {
    pdtStatus = 'BLOCKED'
  } else if (tradedToday) {
    pdtStatus = 'TRADED_TODAY'
  } else {
    pdtStatus = 'CAN_TRADE'
  }

  const triggerTrades = await getTriggerTrades(bot, dte, lastResetAt)
  const nextSlotOpens = triggerTrades.length > 0 ? triggerTrades[0].falls_off : null
  const nextAvailableDate = isBlocked && nextSlotOpens ? nextSlotOpens : null

  return NextResponse.json({
    bot: botName,
    bot_name: botName,
    pdt_enabled: pdtEnabled,
    pdt_status: pdtStatus,
    day_trade_count: dayTradeCount,
    max_day_trades: maxDayTrades,
    trades_remaining: maxDayTrades > 0 ? Math.max(0, maxDayTrades - dayTradeCount) : -1,
    max_trades_per_day: maxTradesPerDay,
    traded_today: tradedToday,
    can_trade: pdtStatus === 'CAN_TRADE' || pdtStatus === 'PDT_OFF',
    window_days: windowDays,
    last_reset: lastResetAt,
    last_reset_at: lastResetAt,
    last_reset_by: cfg.last_reset_by ?? null,
    is_blocked: isBlocked,
    block_reason: blockReason,
    trigger_trades: triggerTrades,
    next_available_date: nextAvailableDate,
    next_slot_opens: nextSlotOpens,
    today_trades_count: todayTradesCount,
    today_trade_time: todayTradeTime,
  })
}
