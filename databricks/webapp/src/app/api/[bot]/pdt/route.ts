import { NextRequest, NextResponse } from 'next/server'
import { query, t, botTable, int, validateBot, dteMode, heartbeatName } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

const PDT_TABLE = t('ironforge_pdt_config')
const LOG_TABLE = t('ironforge_pdt_log')

// Scanner will read these tables directly from the Databricks notebook.
// When the scanner is updated, it should:
// - Before opening: query ironforge_pdt_config for the bot. If pdt_enabled == false, skip PDT checks.
// - After same-day close: increment day_trade_count, log to ironforge_pdt_log.
// - On first scan of each day: recalculate day_trade_count based on rolling window.

function esc(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/'/g, "''")
}

/**
 * GET /api/[bot]/pdt
 * Returns current PDT enforcement state.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const botName = heartbeatName(bot)
  const dte = dteMode(bot)

  try {
    const [pdtRows, tradedTodayRows] = await Promise.all([
      query(
        `SELECT pdt_enabled, day_trade_count, max_day_trades, window_days,
                max_trades_per_day, last_reset_at, last_reset_by
         FROM ${PDT_TABLE}
         WHERE bot_name = '${botName}'
         LIMIT 1`,
      ),
      query(
        `SELECT COUNT(*) AS cnt
         FROM ${botTable(bot, 'positions')}
         WHERE dte_mode = '${dte}'
           AND CAST(open_time AS DATE) = CURRENT_DATE()
           AND status IN ('open', 'closed')`,
      ),
    ])

    const cfg = pdtRows[0] as any
    if (!cfg) {
      return NextResponse.json({
        bot_name: botName,
        pdt_enabled: true,
        day_trade_count: 0,
        max_day_trades: 3,
        trades_remaining: 3,
        max_trades_per_day: 1,
        traded_today: false,
        can_trade: true,
        window_days: 5,
        last_reset_at: null,
        last_reset_by: null,
        is_blocked: false,
        block_reason: null,
      })
    }

    const pdtEnabled = cfg.pdt_enabled === 'true' || cfg.pdt_enabled === '1'
    const dayTradeCount = int(cfg.day_trade_count)
    const maxDayTrades = int(cfg.max_day_trades) || 3
    const maxTradesPerDay = int(cfg.max_trades_per_day) || 1
    const windowDays = int(cfg.window_days) || 5
    const tradedToday = int((tradedTodayRows[0] as any)?.cnt) > 0
    const tradesRemaining = Math.max(0, maxDayTrades - dayTradeCount)

    let isBlocked = false
    let blockReason: string | null = null

    if (pdtEnabled) {
      if (dayTradeCount >= maxDayTrades) {
        isBlocked = true
        blockReason = 'PDT limit reached'
      } else if (tradedToday) {
        isBlocked = true
        blockReason = 'Already traded today'
      }
    }

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
      last_reset_at: cfg.last_reset_at || null,
      last_reset_by: cfg.last_reset_by || null,
      is_blocked: isBlocked,
      block_reason: blockReason,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

/**
 * POST /api/[bot]/pdt
 * Dispatches to toggle or reset based on body.action.
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const botName = heartbeatName(bot)

  try {
    const body = await req.json()
    const action = body.action

    if (action === 'toggle') {
      const enabled = Boolean(body.enabled)

      // Get old state for audit
      const oldRows = await query(
        `SELECT pdt_enabled FROM ${PDT_TABLE} WHERE bot_name = '${botName}' LIMIT 1`,
      )
      const oldEnabled = oldRows[0] ? ((oldRows[0] as any).pdt_enabled === 'true' || (oldRows[0] as any).pdt_enabled === '1') : true

      await query(
        `UPDATE ${PDT_TABLE}
         SET pdt_enabled = ${enabled}, updated_at = CURRENT_TIMESTAMP()
         WHERE bot_name = '${botName}'`,
      )

      // Audit log
      const logId = crypto.randomUUID()
      const oldVal = esc(JSON.stringify({ pdt_enabled: oldEnabled }))
      const newVal = esc(JSON.stringify({ pdt_enabled: enabled }))
      await query(
        `INSERT INTO ${LOG_TABLE}
           (log_id, bot_name, action, old_value, new_value, reason, performed_by, created_at)
         VALUES (
           '${logId}', '${botName}', '${enabled ? 'toggle_on' : 'toggle_off'}',
           '${oldVal}', '${newVal}', 'User toggled PDT enforcement', 'user',
           CURRENT_TIMESTAMP()
         )`,
      )

      return NextResponse.json({ success: true, pdt_enabled: enabled })
    }

    if (action === 'reset') {
      // Get old count
      const oldRows = await query(
        `SELECT day_trade_count FROM ${PDT_TABLE} WHERE bot_name = '${botName}' LIMIT 1`,
      )
      const oldCount = int((oldRows[0] as any)?.day_trade_count)

      // No-op if already 0
      if (oldCount === 0) {
        return NextResponse.json({ success: true, day_trade_count: 0, message: 'Already at 0' })
      }

      await query(
        `UPDATE ${PDT_TABLE}
         SET day_trade_count = 0, last_reset_at = CURRENT_TIMESTAMP(), last_reset_by = 'manual',
             updated_at = CURRENT_TIMESTAMP()
         WHERE bot_name = '${botName}'`,
      )

      // Audit log
      const logId = crypto.randomUUID()
      const oldVal = esc(JSON.stringify({ day_trade_count: oldCount }))
      const newVal = esc(JSON.stringify({ day_trade_count: 0 }))
      await query(
        `INSERT INTO ${LOG_TABLE}
           (log_id, bot_name, action, old_value, new_value, reason, performed_by, created_at)
         VALUES (
           '${logId}', '${botName}', 'reset',
           '${oldVal}', '${newVal}', 'Manual counter reset', 'user',
           CURRENT_TIMESTAMP()
         )`,
      )

      return NextResponse.json({ success: true, day_trade_count: 0 })
    }

    return NextResponse.json({ error: 'Unknown action. Use "toggle" or "reset"' }, { status: 400 })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
