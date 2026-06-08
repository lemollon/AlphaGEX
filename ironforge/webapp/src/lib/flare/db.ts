/**
 * FLARE — DB helpers. Wraps queries against flare_* tables.
 * Cloned from blaze/db.ts; only difference is table names (flare_ prefix).
 */
import { query } from '../db'
import { DailyState, SetupType } from './types'

export interface OpenFlarePosition {
  id: number
  setup_type: string
  direction: 'call' | 'put'
  long_strike: number
  short_strike: number
  long_symbol: string
  short_symbol: string
  debit: number
  contracts: number
  expiration: string
  open_time: Date
}

/** YYYY-MM-DD in America/Chicago today. */
function ctTodayStr(now: Date = new Date()): string {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
  })
  return fmt.format(now)
}

const BLANK_STATE = (trade_date: string): DailyState => ({
  trade_date,
  wall_fade_count: 0,
  wall_break_count: 0,
  flip_cross_count: 0,
  last_signal_minute: null,
})

export async function loadDailyState(date?: string): Promise<DailyState> {
  const trade_date = date || ctTodayStr()
  try {
    const res = await query(
      `SELECT trade_date, wall_fade_count, wall_break_count, flip_cross_count, last_signal_minute
       FROM flare_daily_state WHERE trade_date = $1`,
      [trade_date],
    )
    if (!res.length) return BLANK_STATE(trade_date)
    const r = res[0]
    return {
      trade_date: typeof r.trade_date === 'string' ? r.trade_date : ctTodayStr(r.trade_date),
      wall_fade_count: Number(r.wall_fade_count) || 0,
      wall_break_count: Number(r.wall_break_count) || 0,
      flip_cross_count: Number(r.flip_cross_count) || 0,
      last_signal_minute: r.last_signal_minute == null ? null : Number(r.last_signal_minute),
    }
  } catch {
    return BLANK_STATE(trade_date)
  }
}

const SETUP_COLUMN: Record<SetupType, string> = {
  wall_fade: 'wall_fade_count',
  wall_break: 'wall_break_count',
  flip_cross: 'flip_cross_count',
}

export async function bumpDailyState(
  setup: SetupType,
  signalMinute: number,
  date?: string,
): Promise<void> {
  const trade_date = date || ctTodayStr()
  const col = SETUP_COLUMN[setup]
  await query(
    `INSERT INTO flare_daily_state (trade_date, ${col}, last_signal_minute)
     VALUES ($1, 1, $2)
     ON CONFLICT (trade_date) DO UPDATE SET
       ${col} = flare_daily_state.${col} + 1,
       last_signal_minute = $2,
       updated_at = NOW()`,
    [trade_date, signalMinute],
  )
}

export async function getOpenFlarePositions(): Promise<OpenFlarePosition[]> {
  try {
    const res = await query(
      `SELECT id, setup_type, direction, long_strike, short_strike,
              long_symbol, short_symbol, debit, contracts, expiration, open_time
       FROM flare_positions
       WHERE status = 'open' AND COALESCE(account_type, 'sandbox') = 'sandbox'
       ORDER BY open_time ASC`,
    )
    return res.map((r: any) => ({
      id: Number(r.id),
      setup_type: String(r.setup_type || ''),
      direction: (r.direction === 'put' ? 'put' : 'call') as 'call' | 'put',
      long_strike: Number(r.long_strike) || 0,
      short_strike: Number(r.short_strike) || 0,
      long_symbol: String(r.long_symbol || ''),
      short_symbol: String(r.short_symbol || ''),
      debit: Number(r.debit) || 0,
      contracts: Number(r.contracts) || 1,
      expiration: typeof r.expiration === 'string' ? r.expiration : ctTodayStr(r.expiration),
      open_time: r.open_time instanceof Date ? r.open_time : new Date(r.open_time),
    }))
  } catch {
    return []
  }
}

export interface InsertPositionInput {
  setup_type: SetupType
  direction: 'call' | 'put'
  long_strike: number
  short_strike: number
  long_symbol: string
  short_symbol: string
  debit: number
  contracts: number
  expiration: string  // YYYY-MM-DD
  spot_at_entry: number
}

export async function insertFlarePosition(input: InsertPositionInput): Promise<number> {
  const position_id = `flare_${Date.now()}`
  // flare_positions mirrors blaze_positions schema: IC columns (unused side zeroed)
  // plus directional columns appended via ALTER.
  const isCall = input.direction === 'call'
  const callShort = isCall ? input.short_strike : 0
  const callLong = isCall ? input.long_strike : 0
  const putShort = isCall ? 0 : input.short_strike
  const putLong = isCall ? 0 : input.long_strike

  const spreadWidth = Math.abs(input.long_strike - input.short_strike)
  const maxLoss = Math.round(input.debit * 100 * input.contracts * 100) / 100
  const maxProfit = Math.round((spreadWidth - input.debit) * 100 * input.contracts * 100) / 100

  const res = await query(
    `INSERT INTO flare_positions (
       position_id, ticker, expiration,
       put_short_strike, put_long_strike, put_credit,
       call_short_strike, call_long_strike, call_credit,
       underlying_at_entry, total_credit, collateral_required,
       spread_width, max_loss, max_profit,
       setup_type, direction, long_strike, short_strike,
       long_symbol, short_symbol, debit, contracts,
       status, open_time, open_date, account_type, person, dte_mode
     ) VALUES (
       $1, 'SPY', $2,
       $3, $4, 0,
       $5, $6, 0,
       $7, 0, 0,
       $8, $9, $10,
       $11, $12, $13, $14,
       $15, $16, $17, $18,
       'open', NOW(), (NOW() AT TIME ZONE 'America/Chicago')::date, 'sandbox', 'User', '0DTE'
     )
     RETURNING id`,
    [
      position_id, input.expiration,
      putShort, putLong,
      callShort, callLong,
      input.spot_at_entry,
      spreadWidth, maxLoss, maxProfit,
      input.setup_type, input.direction, input.long_strike, input.short_strike,
      input.long_symbol, input.short_symbol, input.debit, input.contracts,
    ],
  )
  return Number(res[0]?.id || 0)
}

export async function closeFlarePosition(
  id: number,
  args: { mark_to_close: number; exit_reason: string; realized_pnl: number },
): Promise<void> {
  await query(
    `UPDATE flare_positions
     SET status = 'closed',
         close_time = NOW(),
         close_price = $1,
         exit_reason = $2,
         close_reason = $2,
         realized_pnl = $3,
         updated_at = NOW()
     WHERE id = $4`,
    [args.mark_to_close, args.exit_reason, args.realized_pnl, id],
  )
  // Update paper_account realized_pnl + current_balance to stay in sync (mirrors other bots)
  try {
    await query(
      `UPDATE flare_paper_account
       SET cumulative_pnl = COALESCE(cumulative_pnl, 0) + $1,
           current_balance = starting_capital + COALESCE(cumulative_pnl, 0) + $1,
           updated_at = NOW()
       WHERE is_active = TRUE AND dte_mode = '0DTE' AND COALESCE(account_type, 'sandbox') = 'sandbox'`,
      [args.realized_pnl],
    )
  } catch { /* paper account row may not exist */ }
}

export async function getPaperBalance(): Promise<number> {
  try {
    const res = await query(
      `SELECT current_balance FROM flare_paper_account
       WHERE is_active = TRUE AND dte_mode = '0DTE' AND COALESCE(account_type, 'sandbox') = 'sandbox'
       ORDER BY id DESC LIMIT 1`,
    )
    if (!res.length) return 10000
    return Number(res[0].current_balance) || 10000
  } catch {
    return 10000
  }
}

// ---------------------------------------------------------------------------
// Per-direction risk halt. When runMonitorCycle force-closes one side (its
// aggregate unrealized P&L breached -perdir_force_close_pct * balance), it
// records a halt row so runEntryCycle stops opening that side for the rest of
// the day. Persisted in DB (not module memory) so a scanner restart can't
// silently un-halt a side that's getting run over by a trend.
// ---------------------------------------------------------------------------
let _riskHaltEnsured = false
async function ensureRiskHaltTable(): Promise<void> {
  if (_riskHaltEnsured) return
  try {
    await query(
      `CREATE TABLE IF NOT EXISTS flare_risk_halts (
         trade_date DATE NOT NULL,
         direction  TEXT NOT NULL,
         reason     TEXT,
         halted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
         PRIMARY KEY (trade_date, direction)
       )`,
    )
    _riskHaltEnsured = true
  } catch { /* non-fatal — fail open (no halt) rather than block the scanner */ }
}

/**
 * True if `direction` was force-closed within the last `cooldownMinutes`.
 *
 * The per-direction force-close used to halt a side for the REST OF THE DAY,
 * which turned a single adverse cluster into an all-day shutdown (operator wants
 * FLARE to keep trading all day). It now applies a timed COOLDOWN instead: the
 * side resumes once `cooldownMinutes` have elapsed since the last force-close.
 *
 * No schema change — the flare_risk_halts row (refreshed on every force-close
 * via setDirectionHalted's ON CONFLICT) doubles as the cooldown marker; we just
 * check how recent `halted_at` is. The row still persists all day for audit.
 */
export async function isDirectionInCooldown(
  direction: 'call' | 'put',
  cooldownMinutes: number,
  date?: string,
): Promise<boolean> {
  await ensureRiskHaltTable()
  if (!_riskHaltEnsured) return false
  const trade_date = date || ctTodayStr()
  try {
    const res = await query(
      `SELECT 1 FROM flare_risk_halts
        WHERE trade_date = $1 AND direction = $2
          AND halted_at > NOW() - (INTERVAL '1 minute' * $3)
        LIMIT 1`,
      [trade_date, direction, cooldownMinutes],
    )
    return res.length > 0
  } catch {
    return false
  }
}

export async function setDirectionHalted(
  direction: 'call' | 'put',
  reason: string,
  date?: string,
): Promise<void> {
  await ensureRiskHaltTable()
  if (!_riskHaltEnsured) return
  const trade_date = date || ctTodayStr()
  try {
    await query(
      `INSERT INTO flare_risk_halts (trade_date, direction, reason)
       VALUES ($1, $2, $3)
       ON CONFLICT (trade_date, direction) DO UPDATE SET
         reason = EXCLUDED.reason, halted_at = NOW()`,
      [trade_date, direction, reason.substring(0, 300)],
    )
  } catch { /* non-fatal */ }
}

export async function insertSignalActivity(args: {
  outcome: string  // 'TRADE' | 'NO_TRADE' | 'SKIP' | 'ERROR'
  detail: string
  spot?: number
  regime?: string
}): Promise<void> {
  try {
    await query(
      `INSERT INTO flare_logs (log_time, level, message, details, dte_mode, account_type, person)
       VALUES (NOW(), $1, $2, $3, '0DTE', 'sandbox', 'User')`,
      [
        args.outcome === 'ERROR' ? 'ERROR' : 'INFO',
        args.outcome,
        args.detail.substring(0, 500),
      ],
    )
  } catch { /* table may not have these columns; non-fatal */ }
}
