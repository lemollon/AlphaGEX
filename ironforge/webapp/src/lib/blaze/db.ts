/**
 * BLAZE — DB helpers. Wraps queries against blaze_* tables.
 */
import { query } from '../db'
import { DailyState, SetupType } from './types'

export interface OpenBlazePosition {
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
       FROM blaze_daily_state WHERE trade_date = $1`,
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
    `INSERT INTO blaze_daily_state (trade_date, ${col}, last_signal_minute)
     VALUES ($1, 1, $2)
     ON CONFLICT (trade_date) DO UPDATE SET
       ${col} = blaze_daily_state.${col} + 1,
       last_signal_minute = $2,
       updated_at = NOW()`,
    [trade_date, signalMinute],
  )
}

export async function getOpenBlazePositions(): Promise<OpenBlazePosition[]> {
  try {
    const res = await query(
      `SELECT id, setup_type, direction, long_strike, short_strike,
              long_symbol, short_symbol, debit, contracts, expiration, open_time
       FROM blaze_positions
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

export async function insertBlazePosition(input: InsertPositionInput): Promise<number> {
  const position_id = `blaze_${Date.now()}`
  // blaze_positions auto-created with IC schema PLUS directional columns appended via ALTER.
  // Required IC columns: ticker, expiration, put_short_strike, put_long_strike, put_credit,
  //   call_short_strike, call_long_strike, call_credit, open_time, status
  // We fill the IC columns with 0s for the unused side; the directional columns carry the real data.
  const isCall = input.direction === 'call'
  const callShort = isCall ? input.short_strike : 0
  const callLong = isCall ? input.long_strike : 0
  const putShort = isCall ? 0 : input.short_strike
  const putLong = isCall ? 0 : input.long_strike

  const res = await query(
    `INSERT INTO blaze_positions (
       position_id, ticker, expiration,
       put_short_strike, put_long_strike, put_credit,
       call_short_strike, call_long_strike, call_credit,
       underlying_at_entry, total_credit, collateral_required,
       setup_type, direction, long_strike, short_strike,
       long_symbol, short_symbol, debit, contracts,
       status, open_time, open_date, account_type, person, dte_mode
     ) VALUES (
       $1, 'SPY', $2,
       $3, $4, 0,
       $5, $6, 0,
       $7, 0, 0,
       $8, $9, $10, $11,
       $12, $13, $14, $15,
       'open', NOW(), (NOW() AT TIME ZONE 'America/Chicago')::date, 'sandbox', 'User', '1DTE'
     )
     RETURNING id`,
    [
      position_id, input.expiration,
      putShort, putLong,
      callShort, callLong,
      input.spot_at_entry,
      input.setup_type, input.direction, input.long_strike, input.short_strike,
      input.long_symbol, input.short_symbol, input.debit, input.contracts,
    ],
  )
  return Number(res[0]?.id || 0)
}

export async function closeBlazePosition(
  id: number,
  args: { mark_to_close: number; exit_reason: string; realized_pnl: number },
): Promise<void> {
  await query(
    `UPDATE blaze_positions
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
      `UPDATE blaze_paper_account
       SET cumulative_pnl = COALESCE(cumulative_pnl, 0) + $1,
           current_balance = starting_capital + COALESCE(cumulative_pnl, 0) + $1,
           updated_at = NOW()
       WHERE is_active = TRUE AND dte_mode = '1DTE' AND COALESCE(account_type, 'sandbox') = 'sandbox'`,
      [args.realized_pnl],
    )
  } catch { /* paper account row may not exist */ }
}

export async function getPaperBalance(): Promise<number> {
  try {
    const res = await query(
      `SELECT current_balance FROM blaze_paper_account
       WHERE is_active = TRUE AND dte_mode = '1DTE' AND COALESCE(account_type, 'sandbox') = 'sandbox'
       ORDER BY id DESC LIMIT 1`,
    )
    if (!res.length) return 10000
    return Number(res[0].current_balance) || 10000
  } catch {
    return 10000
  }
}

export async function insertSignalActivity(args: {
  outcome: string  // 'TRADE' | 'NO_TRADE' | 'SKIP' | 'ERROR'
  detail: string
  spot?: number
  regime?: string
}): Promise<void> {
  try {
    await query(
      `INSERT INTO blaze_logs (log_time, level, message, details, dte_mode, account_type, person)
       VALUES (NOW(), $1, $2, $3, '1DTE', 'sandbox', 'User')`,
      [
        args.outcome === 'ERROR' ? 'ERROR' : 'INFO',
        args.outcome,
        args.detail.substring(0, 500),
      ],
    )
  } catch { /* table may not have these columns; non-fatal */ }
}
