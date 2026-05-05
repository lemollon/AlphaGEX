import { query } from '../db'
import { getRawQuotes } from '../tradier'
import { listForBot } from './repo'
import type { BotKey, BriefType, GatheredContext, MacroRibbon, SparklinePoint } from './types'

const PER_BOT_DTE: Record<Exclude<BotKey, 'portfolio'>, string> = {
  flame: '2DTE', spark: '1DTE', inferno: '0DTE',
}

function num(v: any): number {
  if (v == null || v === '') return 0
  const n = parseFloat(v)
  return isNaN(n) ? 0 : n
}

async function fetchDashboardState(bot: Exclude<BotKey, 'portfolio'>, baseUrl: string): Promise<any | null> {
  try {
    const [statusR, posR, perfR] = await Promise.all([
      fetch(`${baseUrl}/api/${bot}/status`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${baseUrl}/api/${bot}/positions`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${baseUrl}/api/${bot}/performance`).then(r => r.ok ? r.json() : null).catch(() => null),
    ])
    if (!statusR && !posR && !perfR) return null
    return { status: statusR, positions: posR, performance: perfR }
  } catch {
    return null
  }
}

async function fetchMacroRibbon(): Promise<MacroRibbon> {
  const fallback: MacroRibbon = {
    spy_open: 0, spy_close: 0, spy_range_pct: 0, em_pct: 0,
    vix: 0, vix_change: 0, regime: 'Unknown', pin_risk: 'Medium',
  }
  try {
    const q = await getRawQuotes(['SPY', 'VIX', 'VIX3M'])
    const spy = q['SPY'] as any
    const vix = q['VIX'] as any
    const vix3m = q['VIX3M'] as any
    const spyOpen = num(spy?.open)
    const spyClose = num(spy?.last)
    const spyHigh = num(spy?.high)
    const spyLow  = num(spy?.low)
    const range = spyClose > 0 ? ((spyHigh - spyLow) / spyClose) * 100 : 0
    const vixVal = num(vix?.last)
    const vixChange = num(vix?.change)
    const em = spyClose > 0 ? (vixVal / 100 / Math.sqrt(252)) * 100 : 0
    const ts = num(vix3m?.last) > 0 && vixVal > 0 ? (num(vix3m.last) / vixVal - 1) : 0
    const regime = ts > 0.05 ? 'Negative Gamma' : ts < -0.05 ? 'Positive Gamma' : 'Mixed Gamma'
    const pin: 'Low' | 'Medium' | 'High' = vixVal < 14 ? 'High' : vixVal < 22 ? 'Medium' : 'Low'
    return {
      spy_open: spyOpen, spy_close: spyClose, spy_range_pct: +range.toFixed(2),
      em_pct: +em.toFixed(2), vix: +vixVal.toFixed(2), vix_change: +vixChange.toFixed(2),
      regime, pin_risk: pin,
    }
  } catch {
    return fallback
  }
}

async function fetchEquityCurve7d(bot: Exclude<BotKey, 'portfolio'>): Promise<SparklinePoint[]> {
  const rows = await query<any>(`
    SELECT (close_time AT TIME ZONE 'America/Chicago')::date AS d,
           SUM(realized_pnl) AS day_pnl
    FROM ${bot}_positions
    WHERE status IN ('closed', 'expired')
      AND close_time >= NOW() - INTERVAL '7 days'
    GROUP BY d ORDER BY d ASC
  `).catch(() => [])
  let cum = 0
  return rows.map((r: any) => {
    cum += num(r.day_pnl)
    const dStr = r.d?.toISOString?.()?.slice(0, 10) ?? String(r.d)
    return { date: dStr, cumulative_pnl: +cum.toFixed(2) }
  })
}

async function fetchTodayContext(bot: Exclude<BotKey, 'portfolio'>): Promise<{ today_positions: any[]; today_trades: any[]; daily_perf: any }> {
  const dte = PER_BOT_DTE[bot]
  const [positions, trades, perf] = await Promise.all([
    query(`SELECT position_id, status, put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                  total_credit, contracts, realized_pnl, close_reason, open_time, close_time
           FROM ${bot}_positions
           WHERE (open_time AT TIME ZONE 'America/Chicago')::date = (NOW() AT TIME ZONE 'America/Chicago')::date
             AND dte_mode = $1`,
          [dte]).catch(() => []),
    query(`SELECT position_id, total_credit, realized_pnl, close_reason, contracts
           FROM ${bot}_positions
           WHERE status IN ('closed','expired')
             AND (close_time AT TIME ZONE 'America/Chicago')::date = (NOW() AT TIME ZONE 'America/Chicago')::date
             AND dte_mode = $1`,
          [dte]).catch(() => []),
    query(`SELECT * FROM ${bot}_daily_perf
           WHERE trade_date = (NOW() AT TIME ZONE 'America/Chicago')::date LIMIT 1`).catch(() => []),
  ])
  return { today_positions: positions, today_trades: trades, daily_perf: perf[0] ?? null }
}

async function fetchMemory(bot: BotKey): Promise<{
  memory_recent: GatheredContext['memory_recent']; memory_codex: GatheredContext['memory_codex']
}> {
  const recent = await listForBot(bot, 'daily_eod', 5).catch(() => [])
  const codex = await listForBot(bot, 'codex_monthly', 1).catch(() => [])
  return {
    memory_recent: recent.map(r => ({
      brief_id: r.brief_id, brief_date: String(r.brief_date),
      summary: r.summary, wisdom: r.wisdom,
    })),
    memory_codex: codex[0] ? { brief_id: codex[0].brief_id, summary: codex[0].summary } : null,
  }
}

async function fetchCalendarContext(): Promise<{
  active_blackout: GatheredContext['active_blackout']; upcoming_blackout: GatheredContext['upcoming_blackout']
}> {
  const active = await query<any>(`
    SELECT title, halt_end_ts FROM ironforge_event_calendar
    WHERE is_active = TRUE AND NOW() BETWEEN halt_start_ts AND halt_end_ts
    ORDER BY halt_end_ts ASC LIMIT 1
  `).catch(() => [])
  const upcoming = await query<any>(`
    SELECT title, halt_start_ts, halt_end_ts FROM ironforge_event_calendar
    WHERE is_active = TRUE AND halt_start_ts > NOW()
    ORDER BY halt_start_ts ASC LIMIT 1
  `).catch(() => [])
  return {
    active_blackout: active[0] ? { title: active[0].title, halt_end_ts: active[0].halt_end_ts } : null,
    upcoming_blackout: upcoming[0] ? {
      title: upcoming[0].title, halt_start_ts: upcoming[0].halt_start_ts, halt_end_ts: upcoming[0].halt_end_ts,
    } : null,
  }
}

export async function gatherContext(opts: {
  bot: BotKey; brief_type: BriefType; brief_date: string; baseUrl: string
}): Promise<GatheredContext> {
  const macro = await fetchMacroRibbon()
  const calendar = await fetchCalendarContext()

  if (opts.bot === 'portfolio') {
    const subs = await Promise.all((['flame', 'spark', 'inferno'] as const).map(async b => ({
      bot: b,
      ...(await fetchTodayContext(b)),
      equity_curve_7d: await fetchEquityCurve7d(b),
      dashboard_state: await fetchDashboardState(b, opts.baseUrl),
    })))
    const memory = await fetchMemory('portfolio')
    return {
      bot: 'portfolio', brief_type: opts.brief_type, brief_date: opts.brief_date,
      today_positions: subs.flatMap(s => s.today_positions.map((p: any) => ({ ...p, _bot: s.bot }))),
      today_trades: subs.flatMap(s => s.today_trades.map((t: any) => ({ ...t, _bot: s.bot }))),
      daily_perf: { per_bot: subs.map(s => ({ bot: s.bot, daily_perf: s.daily_perf })) },
      equity_curve_7d: [],
      dashboard_state: { per_bot: subs.map(s => ({ bot: s.bot, ...s.dashboard_state })) },
      macro,
      memory_recent: memory.memory_recent, memory_codex: memory.memory_codex,
      active_blackout: calendar.active_blackout, upcoming_blackout: calendar.upcoming_blackout,
    }
  }

  const [today, equity, dashboard, memory] = await Promise.all([
    fetchTodayContext(opts.bot),
    fetchEquityCurve7d(opts.bot),
    fetchDashboardState(opts.bot, opts.baseUrl),
    fetchMemory(opts.bot),
  ])
  return {
    bot: opts.bot, brief_type: opts.brief_type, brief_date: opts.brief_date,
    today_positions: today.today_positions, today_trades: today.today_trades, daily_perf: today.daily_perf,
    equity_curve_7d: equity, dashboard_state: dashboard, macro,
    memory_recent: memory.memory_recent, memory_codex: memory.memory_codex,
    active_blackout: calendar.active_blackout, upcoming_blackout: calendar.upcoming_blackout,
  }
}
