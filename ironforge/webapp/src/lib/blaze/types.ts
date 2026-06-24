/**
 * BLAZE — shared types for the 1DTE directional bot.
 * Port of trading/helios/models.py + gex_client.GexSnapshot to TypeScript.
 */

export type SetupType = 'wall_fade' | 'wall_break' | 'flip_cross' | 'gex_momentum' | 'gex_putcredit' | 'gex_quick_itm'
export type Direction = 'call' | 'put'
export type ExitReason = 'PT' | 'SL' | 'TIME_STOP' | 'DATA_FAILURE'

export interface GexSnapshot {
  symbol: string
  spot: number
  net_gex: number
  flip_point: number
  call_wall: number
  put_wall: number
  vix: number
  regime: string
  sigma_1d_band_width: number // 1-day 1-sigma move in dollars
  snapshot_at: Date           // UTC timestamp
}

export interface SetupAction {
  setup: SetupType
  direction: Direction
  long_strike: number
  short_strike: number
  reason: string
}

export interface DailyState {
  trade_date: string // YYYY-MM-DD
  wall_fade_count: number
  wall_break_count: number
  flip_cross_count: number
  last_signal_minute: number | null
}

export interface BlazeConfig {
  ticker: string
  spread_width: number
  profit_target_pct: number
  stop_loss_pct: number
  eod_time_ct: string
  risk_per_trade_pct: number
  buying_power_usage_pct: number
  gex_stale_max_seconds: number
  wall_fade_em_threshold: number
  wall_break_em_threshold: number
  flip_hysteresis_pct: number
  flip_buffer_minutes: number
  max_trades_per_setup_per_day: number
  quotes_unavailable_max_cycles: number
}

export const DEFAULT_BLAZE_CONFIG: BlazeConfig = {
  ticker: 'SPY',
  spread_width: 1,
  profit_target_pct: 20.0,
  // Widened 30 -> 100 per the full-board backtest + 1DTE cross-check (2026-05-25):
  // SL=100 is GO on 1DTE (SL=30 was NO-GO) — the tight stop was killing a real edge.
  stop_loss_pct: 100.0,
  eod_time_ct: '15:55',
  // Cut 0.20 -> 0.05: with SL=100 the debit deployed IS the max loss, so the old
  // 0.20 x 0.85 = ~17%/trade would be ruinous (25%/trade backtested to -66% DD).
  // ~4.25% deploy now (~-10% backtested DD). See backtest/blaze_gex_0dte/account_sim.py.
  risk_per_trade_pct: 0.05,
  buying_power_usage_pct: 0.85,
  gex_stale_max_seconds: 90,
  wall_fade_em_threshold: 0.30,
  wall_break_em_threshold: 0.20,
  flip_hysteresis_pct: 0.0015,
  flip_buffer_minutes: 5,
  max_trades_per_setup_per_day: 3,
  quotes_unavailable_max_cycles: 10,
}

export function countForSetup(state: DailyState, setup: SetupType): number {
  switch (setup) {
    case 'wall_fade': return state.wall_fade_count
    case 'wall_break': return state.wall_break_count
    case 'flip_cross': return state.flip_cross_count
    case 'gex_momentum': return state.wall_fade_count // FLARE conviction directional (neg-GEX); no per-setup daily counts
    case 'gex_putcredit': return state.wall_fade_count // FLARE bullish put credit (pos-GEX); no per-setup daily counts
    case 'gex_quick_itm': return state.wall_fade_count // FLARE quick ITM call (pos-GEX morning sleeve); no per-setup daily counts
  }
}

export function isCapped(state: DailyState, setup: SetupType, cap: number): boolean {
  return countForSetup(state, setup) >= cap
}
