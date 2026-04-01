import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, sharedTable, num, int, escapeSql, validateBot, dteMode, heartbeatName, CT_TODAY } from '@/lib/db'
import { isConfigured, getQuote } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * Diagnostic endpoint: shows exactly which gate is blocking the bot from opening trades.
 * Visit /api/spark/diagnose-trade or /api/flame/diagnose-trade to see the diagnosis.
 *
 * Checks every gate in the scanner's scan_bot() → try_open_trade() flow:
 *  1. Scanner heartbeat (is it running?)
 *  2. Open positions (blocking new trades?)
 *  3. Market hours / entry window
 *  4. PDT config and today's trade count
 *  5. Paper account buying power
 *  6. Tradier connectivity (SPY/VIX quotes)
 *  7. Recent scan logs (skip reasons)
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte!)}'` : ''
  const hbName = heartbeatName(bot)

  try {
    // Run all diagnostic queries in parallel
    const [
      heartbeatRows,
      openPositionRows,
      pdtConfigRows,
      pdtLogRows,
      accountRows,
      recentLogs,
      todayTradeCount,
    ] = await Promise.all([
      // 1. Scanner heartbeat — is the scanner alive?
      dbQuery(
        `SELECT bot_name, last_heartbeat, status, details
         FROM ${sharedTable('bot_heartbeats')}
         WHERE bot_name = '${escapeSql(hbName)}'
         LIMIT 1`,
      ),

      // 2. Open positions — are stale positions blocking?
      dbQuery(
        `SELECT position_id, status, open_time, expiration, ticker,
                put_short_strike, call_short_strike, total_credit
         FROM ${botTable(bot, 'positions')}
         WHERE status = 'open' ${dteFilter}
         ORDER BY open_time DESC`,
      ),

      // 3. PDT config — is PDT enabled? What are the limits?
      dbQuery(
        `SELECT bot_name, pdt_enabled, max_day_trades, window_days,
                max_trades_per_day, day_trade_count
         FROM ${sharedTable('ironforge_pdt_config')}
         WHERE bot_name = '${escapeSql(hbName)}'
         LIMIT 1`,
      ),

      // 4. PDT log — trades recorded today
      dbQuery(
        `SELECT trade_date, position_id, close_reason, is_day_trade
         FROM ${botTable(bot, 'pdt_log')}
         WHERE trade_date = ${CT_TODAY}
         ORDER BY created_at DESC`,
      ),

      // 5. Paper account — buying power, balance
      dbQuery(
        `SELECT current_balance, buying_power, collateral_in_use, cumulative_pnl,
                starting_capital, is_active
         FROM ${botTable(bot, 'paper_account')}
         WHERE is_active = TRUE ${dteFilter}
         LIMIT 1`,
      ),

      // 6. Recent logs — last 30 scan entries to see skip reasons
      dbQuery(
        `SELECT log_time, level, message, details
         FROM ${botTable(bot, 'logs')}
         WHERE (log_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ORDER BY log_time DESC
         LIMIT 30`,
      ),

      // 7. Count of trades opened today
      dbQuery(
        `SELECT COUNT(*) as cnt
         FROM ${botTable(bot, 'positions')}
         WHERE (open_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
           ${dteFilter}`,
      ),
    ])

    // Parse heartbeat
    const hb = heartbeatRows[0]
    let heartbeatDetails: Record<string, unknown> = {}
    if (hb?.details) {
      try {
        heartbeatDetails = typeof hb.details === 'string' ? JSON.parse(hb.details) : hb.details
      } catch {
        heartbeatDetails = { raw: hb.details }
      }
    }

    const lastHeartbeat = hb?.last_heartbeat || null
    let heartbeatAgeSec: number | null = null
    if (lastHeartbeat) {
      heartbeatAgeSec = Math.round((Date.now() - new Date(lastHeartbeat).getTime()) / 1000)
    }

    // Parse account
    const acct = accountRows[0]
    const buyingPower = num(acct?.buying_power)
    const balance = num(acct?.current_balance)
    const isActive = acct?.is_active

    // Parse PDT
    const pdt = pdtConfigRows[0]
    const pdtEnabled = pdt?.pdt_enabled === 'true' || pdt?.pdt_enabled === true
    const maxTradesPerDay = int(pdt?.max_trades_per_day) || 1
    const maxDayTrades = int(pdt?.max_day_trades) || 3
    const dayTradeCount = int(pdt?.day_trade_count)

    // Count trades opened today
    const tradesToday = int(todayTradeCount[0]?.cnt)

    // Current time in CT (approximate — server-side)
    const nowCT = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
    const hhmm = nowCT.getHours() * 100 + nowCT.getMinutes()
    const dayOfWeek = nowCT.getDay() // 0=Sun, 6=Sat

    // Check Tradier
    let tradierStatus: Record<string, unknown> = { configured: false }
    if (isConfigured()) {
      try {
        const [spyQ, vixQ] = await Promise.all([
          getQuote('SPY'),
          getQuote('VIX'),
        ])
        tradierStatus = {
          configured: true,
          spy: spyQ ? { last: spyQ.last, bid: spyQ.bid, ask: spyQ.ask } : null,
          vix: vixQ ? { last: vixQ.last } : null,
          spy_available: !!spyQ?.last,
          vix_available: !!vixQ?.last,
          vix_over_32: vixQ ? num(vixQ.last) > 32 : null,
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        tradierStatus = { configured: true, error: msg }
      }
    }

    // Determine entry window based on bot config
    const entryEnd = bot === 'inferno' ? 1430 : 1400
    const marketOpen = 830
    const marketClose = 1500

    // Build gate checks
    const gates: Array<{ gate: string; pass: boolean; detail: string }> = []

    // Gate 1: Scanner alive
    const scannerAlive = heartbeatAgeSec !== null && heartbeatAgeSec < 300
    gates.push({
      gate: 'scanner_alive',
      pass: scannerAlive,
      detail: scannerAlive
        ? `Last heartbeat ${heartbeatAgeSec}s ago`
        : lastHeartbeat
          ? `STALE — last heartbeat ${heartbeatAgeSec}s ago (${lastHeartbeat})`
          : 'NO HEARTBEAT FOUND',
    })

    // Gate 2: Market open (weekday + 8:30-15:00 CT)
    const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5
    const isMarketHours = hhmm >= marketOpen && hhmm <= marketClose
    gates.push({
      gate: 'market_open',
      pass: isWeekday && isMarketHours,
      detail: `Day=${dayOfWeek} (${isWeekday ? 'weekday' : 'WEEKEND'}), CT time=${Math.floor(hhmm / 100)}:${String(hhmm % 100).padStart(2, '0')} (need ${marketOpen}-${marketClose})`,
    })

    // Gate 3: Entry window (8:30 - 14:00/14:30 CT)
    const inEntryWindow = hhmm >= marketOpen && hhmm <= entryEnd
    gates.push({
      gate: 'entry_window',
      pass: isWeekday && inEntryWindow,
      detail: `CT time=${Math.floor(hhmm / 100)}:${String(hhmm % 100).padStart(2, '0')} (entry window ${marketOpen}-${entryEnd})`,
    })

    // Gate 4: No blocking open positions
    const hasOpenPosition = openPositionRows.length > 0
    const canOpenMore = bot === 'inferno' || !hasOpenPosition
    gates.push({
      gate: 'can_open_more',
      pass: canOpenMore,
      detail: hasOpenPosition
        ? `${openPositionRows.length} open position(s) — ${openPositionRows.map((p) => `${p.position_id} (opened ${p.open_time}, exp ${p.expiration})`).join('; ')}`
        : 'No open positions — clear to trade',
    })

    // Gate 5: Not already traded today (max_trades_per_day)
    const belowDailyLimit = tradesToday < maxTradesPerDay
    gates.push({
      gate: 'daily_trade_limit',
      pass: belowDailyLimit,
      detail: `${tradesToday} trade(s) today, limit=${maxTradesPerDay}`,
    })

    // Gate 6: PDT check
    const pdtOk = !pdtEnabled || dayTradeCount < maxDayTrades
    gates.push({
      gate: 'pdt_check',
      pass: pdtOk,
      detail: pdtEnabled
        ? `PDT enabled: ${dayTradeCount}/${maxDayTrades} day trades used`
        : 'PDT disabled',
    })

    // Gate 7: Buying power
    const bpOk = buyingPower >= 200
    gates.push({
      gate: 'buying_power',
      pass: bpOk,
      detail: `Balance=$${balance.toFixed(2)}, Buying power=$${buyingPower.toFixed(2)} (need >= $200)`,
    })

    // Gate 8: Tradier quotes
    const tCfg = tradierStatus as any
    const tradierOk = tCfg.configured && tCfg.spy_available && tCfg.vix_available
    gates.push({
      gate: 'tradier_quotes',
      pass: tradierOk,
      detail: tCfg.error
        ? `Tradier error: ${tCfg.error}`
        : `SPY=${tCfg.spy?.last ?? 'N/A'}, VIX=${tCfg.vix?.last ?? 'N/A'}`,
    })

    // Gate 9: VIX not too high
    const vixVal = tCfg.vix?.last ? num(tCfg.vix.last) : null
    const vixOk = vixVal === null || vixVal <= 32
    gates.push({
      gate: 'vix_below_32',
      pass: vixOk,
      detail: vixVal !== null ? `VIX=${vixVal}` : 'VIX unavailable',
    })

    // Gate 10: Account active
    gates.push({
      gate: 'account_active',
      pass: !!isActive,
      detail: isActive ? 'Paper account is active' : 'Paper account NOT ACTIVE or NOT FOUND',
    })

    // Determine first failing gate
    const firstBlocker = gates.find((g) => !g.pass)

    // Extract skip reasons from recent logs
    const skipLogs = recentLogs
      .filter((l) => {
        const msg = String(l.message || '').toUpperCase()
        const lvl = String(l.level || '').toUpperCase()
        return msg.includes('SKIP') || msg.includes('NO_TRADE') || msg.includes('BLOCKED') || msg.includes('GATE') || lvl === 'SKIP'
      })
      .map((l) => ({
        log_time: l.log_time,
        level: l.level,
        message: l.message,
        details: l.details,
      }))

    // Also extract scan/heartbeat details for last action/reason
    const scannerAction = heartbeatDetails.action || heartbeatDetails.last_action || null
    const scannerReason = heartbeatDetails.reason || heartbeatDetails.last_reason || null

    return NextResponse.json({
      bot: bot.toUpperCase(),
      dte_mode: dte,
      timestamp: new Date().toISOString(),
      ct_time: `${Math.floor(hhmm / 100)}:${String(hhmm % 100).padStart(2, '0')} CT`,

      diagnosis: firstBlocker
        ? `BLOCKED by: ${firstBlocker.gate} — ${firstBlocker.detail}`
        : 'All gates PASS — bot should be able to trade',

      gates,

      scanner: {
        last_heartbeat: lastHeartbeat,
        heartbeat_age_sec: heartbeatAgeSec,
        status: hb?.status || null,
        last_action: scannerAction,
        last_reason: scannerReason,
        details: heartbeatDetails,
      },

      open_positions: openPositionRows.map((p) => ({
        position_id: p.position_id,
        ticker: p.ticker,
        expiration: p.expiration,
        open_time: p.open_time,
        put_short: num(p.put_short_strike),
        call_short: num(p.call_short_strike),
        credit: num(p.total_credit),
      })),

      pdt: {
        enabled: pdtEnabled,
        day_trade_count: dayTradeCount,
        max_day_trades: maxDayTrades,
        max_trades_per_day: maxTradesPerDay,
        trades_today: tradesToday,
        pdt_log_today: pdtLogRows.map((l) => ({
          trade_date: l.trade_date,
          position_id: l.position_id,
          close_reason: l.close_reason,
          is_day_trade: l.is_day_trade,
        })),
      },

      account: {
        balance,
        buying_power: buyingPower,
        collateral_in_use: num(acct?.collateral_in_use),
        cumulative_pnl: num(acct?.cumulative_pnl),
        starting_capital: num(acct?.starting_capital),
        is_active: isActive,
      },

      tradier: tradierStatus,

      recent_skip_logs: skipLogs,
      recent_logs: recentLogs.slice(0, 15).map((l) => ({
        log_time: l.log_time,
        level: l.level,
        message: l.message,
      })),
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
