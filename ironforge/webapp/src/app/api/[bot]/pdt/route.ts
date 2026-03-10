import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

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
    // PDT config
    const configRows = await query(
      `SELECT pdt_enabled, day_trade_count, max_day_trades,
              max_trades_per_day, window_days,
              last_reset_at, last_reset_by
       FROM ${botTable(bot, 'pdt_config')}
       WHERE bot_name = $1
       LIMIT 1`,
      [botName],
    )

    // Defaults if no row (shouldn't happen after seed, but be safe)
    const cfg = configRows[0] ?? {
      pdt_enabled: true,
      day_trade_count: 0,
      max_day_trades: 3,
      max_trades_per_day: 1,
      window_days: 5,
      last_reset_at: null,
      last_reset_by: null,
    }

    const pdtEnabled = cfg.pdt_enabled !== false
    const maxDayTrades = int(cfg.max_day_trades) || 3
    const maxTradesPerDay = int(cfg.max_trades_per_day) || 1
    const windowDays = int(cfg.window_days) || 5

    // Count day trades from pdt_log (source of truth — matches trader.py logic)
    const countRows = await query(
      `SELECT COUNT(*) as cnt FROM ${botTable(bot, 'pdt_log')}
       WHERE is_day_trade = TRUE AND dte_mode = $1
       AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
       AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`,
      [dte],
    )
    const dayTradeCount = int(countRows[0]?.cnt)

    // Check if already traded today
    const todayRows = await query(
      `SELECT COUNT(*) as cnt
       FROM ${botTable(bot, 'pdt_log')}
       WHERE trade_date = CURRENT_DATE AND dte_mode = $1`,
      [dte],
    )
    const tradedToday = int(todayRows[0]?.cnt) >= maxTradesPerDay

    // Determine block status
    let isBlocked = false
    let blockReason: string | null = null

    if (pdtEnabled) {
      if (dayTradeCount >= maxDayTrades) {
        isBlocked = true
        blockReason = `PDT limit reached: ${dayTradeCount}/${maxDayTrades} day trades in rolling ${windowDays} days`
      } else if (tradedToday) {
        isBlocked = true
        blockReason = `Already traded today (max ${maxTradesPerDay}/day)`
      }
    }

    const tradesRemaining = Math.max(0, maxDayTrades - dayTradeCount)

    // Get the actual day trade dates that count + when each falls off
    const triggerTrades = await getTriggerTrades(bot, dte)
    const nextSlotOpens = triggerTrades.length > 0 ? triggerTrades[0].falls_off : null

    return NextResponse.json({
      bot_name: botName,
      pdt_enabled: pdtEnabled,
      day_trade_count: dayTradeCount,
      max_day_trades: maxDayTrades,
      trades_remaining: tradesRemaining,
      max_trades_per_day: maxTradesPerDay,
      traded_today: tradedToday,
      can_trade: !isBlocked,
      window_days: windowDays,
      last_reset_at: cfg.last_reset_at?.toISOString?.() ?? cfg.last_reset_at ?? null,
      last_reset_by: cfg.last_reset_by ?? null,
      is_blocked: isBlocked,
      block_reason: blockReason,
      trigger_trades: triggerTrades,
      next_slot_opens: nextSlotOpens,
    })
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
    // Return current status with no log entry
    return fetchAndReturnStatus(bot, botName)
  }

  // Update
  await query(
    `UPDATE ${botTable(bot, 'pdt_config')}
     SET pdt_enabled = $1, updated_at = NOW()
     WHERE bot_name = $2`,
    [enabled, botName],
  )

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
      'User toggled PDT enforcement',
      'user',
    ],
  )

  return fetchAndReturnStatus(bot, botName)
}

/* ------------------------------------------------------------------ */
/*  Reset day trade counter                                            */
/* ------------------------------------------------------------------ */

async function handleReset(
  bot: string,
  botName: string,
): Promise<NextResponse> {
  const dte = dteMode(bot)!

  // Count actual day trades from pdt_log (source of truth)
  const countRows = await query(
    `SELECT COUNT(*) as cnt FROM ${botTable(bot, 'pdt_log')}
     WHERE is_day_trade = TRUE AND dte_mode = $1
     AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
     AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`,
    [dte],
  )
  const currentCount = parseInt(countRows[0]?.cnt ?? '0', 10)

  // No-op if already 0
  if (currentCount === 0) {
    return fetchAndReturnStatus(bot, botName)
  }

  // Clear is_day_trade flags in pdt_log so trader.py also sees the reset
  await query(
    `UPDATE ${botTable(bot, 'pdt_log')}
     SET is_day_trade = FALSE
     WHERE is_day_trade = TRUE AND dte_mode = $1
     AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
     AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`,
    [dte],
  )

  // Also zero the config counter (keeps display consistent)
  await query(
    `UPDATE ${botTable(bot, 'pdt_config')}
     SET day_trade_count = 0,
         last_reset_at = NOW(),
         last_reset_by = 'manual',
         updated_at = NOW()
     WHERE bot_name = $1`,
    [botName],
  )

  // Audit log
  await query(
    `INSERT INTO ${botTable(bot, 'pdt_audit_log')}
       (bot_name, action, old_value, new_value, reason, performed_by)
     VALUES ($1, $2, $3, $4, $5, $6)`,
    [
      botName,
      'reset',
      JSON.stringify({ day_trade_count: currentCount, pdt_log_cleared: true }),
      JSON.stringify({ day_trade_count: 0 }),
      'Manual reset by user — cleared is_day_trade flags in pdt_log',
      'user',
    ],
  )

  return fetchAndReturnStatus(bot, botName)
}

/* ------------------------------------------------------------------ */
/*  Helper: get trigger trades (dates that count toward PDT)           */
/* ------------------------------------------------------------------ */

async function getTriggerTrades(bot: string, dte: string) {
  const rows = await query(
    `SELECT DISTINCT trade_date FROM ${botTable(bot, 'pdt_log')}
     WHERE is_day_trade = TRUE AND dte_mode = $1
     AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
     AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5
     ORDER BY trade_date ASC`,
    [dte],
  )
  return rows.map((r: any) => {
    const td = typeof r.trade_date === 'string'
      ? new Date(r.trade_date + 'T00:00:00')
      : new Date(r.trade_date)
    // Trade exits window after 7 calendar days (trade_date + 7)
    const fallsOff = new Date(td)
    fallsOff.setDate(fallsOff.getDate() + 7)
    // If falls on weekend, advance to Monday
    const dow = fallsOff.getDay()
    if (dow === 0) fallsOff.setDate(fallsOff.getDate() + 1)  // Sun → Mon
    if (dow === 6) fallsOff.setDate(fallsOff.getDate() + 2)  // Sat → Mon
    return {
      trade_date: td.toISOString().split('T')[0],
      falls_off: fallsOff.toISOString().split('T')[0],
    }
  })
}

/* ------------------------------------------------------------------ */
/*  Helper: fetch full PDT status and return as JSON response          */
/* ------------------------------------------------------------------ */

async function fetchAndReturnStatus(
  bot: string,
  botName: string,
): Promise<NextResponse> {
  const dte = dteMode(bot)!

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
    max_day_trades: 3,
    max_trades_per_day: 1,
    window_days: 5,
    last_reset_at: null,
    last_reset_by: null,
  }

  const pdtEnabled = cfg.pdt_enabled !== false
  const maxDayTrades = parseInt(cfg.max_day_trades ?? '3', 10) || 3
  const maxTradesPerDay = parseInt(cfg.max_trades_per_day ?? '1', 10) || 1
  const windowDays = parseInt(cfg.window_days ?? '5', 10) || 5

  // Count from pdt_log (source of truth — matches trader.py logic)
  const countRows = await query(
    `SELECT COUNT(*) as cnt FROM ${botTable(bot, 'pdt_log')}
     WHERE is_day_trade = TRUE AND dte_mode = $1
     AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
     AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`,
    [dte],
  )
  const dayTradeCount = parseInt(countRows[0]?.cnt ?? '0', 10)

  const todayRows = await query(
    `SELECT COUNT(*) as cnt
     FROM ${botTable(bot, 'pdt_log')}
     WHERE trade_date = CURRENT_DATE AND dte_mode = $1`,
    [dte],
  )
  const tradedToday = parseInt(todayRows[0]?.cnt ?? '0', 10) >= maxTradesPerDay

  let isBlocked = false
  let blockReason: string | null = null

  if (pdtEnabled) {
    if (dayTradeCount >= maxDayTrades) {
      isBlocked = true
      blockReason = `PDT limit reached: ${dayTradeCount}/${maxDayTrades} day trades in rolling ${windowDays} days`
    } else if (tradedToday) {
      isBlocked = true
      blockReason = `Already traded today (max ${maxTradesPerDay}/day)`
    }
  }

  const triggerTrades = await getTriggerTrades(bot, dte)
  const nextSlotOpens = triggerTrades.length > 0 ? triggerTrades[0].falls_off : null

  return NextResponse.json({
    bot_name: botName,
    pdt_enabled: pdtEnabled,
    day_trade_count: dayTradeCount,
    max_day_trades: maxDayTrades,
    trades_remaining: Math.max(0, maxDayTrades - dayTradeCount),
    max_trades_per_day: maxTradesPerDay,
    traded_today: tradedToday,
    can_trade: !isBlocked,
    window_days: windowDays,
    last_reset_at: cfg.last_reset_at?.toISOString?.() ?? cfg.last_reset_at ?? null,
    last_reset_by: cfg.last_reset_by ?? null,
    is_blocked: isBlocked,
    block_reason: blockReason,
    trigger_trades: triggerTrades,
    next_slot_opens: nextSlotOpens,
  })
}
