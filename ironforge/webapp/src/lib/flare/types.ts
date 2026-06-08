/**
 * FLARE — types. Re-exports all shared types from BLAZE, then defines
 * FLARE's own config with a wide stop (SL = 100% of debit).
 *
 * The only config difference vs BLAZE is stop_loss_pct: 100.0
 * (BLAZE uses 30.0). PT stays at 20% (same as DEFAULT_BLAZE_CONFIG).
 * FLARE is 0DTE, so expiration is always the same trading day.
 */
export * from '../blaze/types'
import { DEFAULT_BLAZE_CONFIG, BlazeConfig } from '../blaze/types'

export interface FlareConfig extends BlazeConfig {
  // Per-direction force-close stop. When the aggregate UNREALIZED P&L of one
  // side (all open call OR all open put debit spreads) drops below
  //   -perdir_force_close_pct * current_account_balance,
  // force-close that entire side, then COOL DOWN new entries on it for
  // perdir_cooldown_minutes (NOT the rest of the session — the operator wants
  // FLARE to keep trading all day). Evaluated every scan tick by runMonitorCycle.
  //
  // Why per-side + force-close (not an account-level entry halt): FLARE's blow-ups
  // were always one-directional — it stacked the wrong side into a trend (6/04:
  // 138 put fades, 3 wins, -$52k). A realized-PnL daily stop never fired (loss was
  // unrealized until the 14:45 time-stop guillotine), and an account-level halt
  // still let already-open losers ride. A per-side force-close checked on the
  // timer guillotines the bleeding side fast — whether it bleeds quick (6/04) or
  // slow (6/03) — while a healthy side keeps running.
  // Backtest on FLARE's own 8-day live tape (reset $10k, flat 5%/trade):
  //   baseline   -$30,451  PF 0.54  maxDD 570%
  //   per-dir FC 5% + cap20  +$12,790  PF 3.15  maxDD 33%  worst day -$618
  perdir_force_close_pct: number
  // Minutes a side is blocked from re-entry after a force-close. A short cooldown
  // (the signal-reset gate already spaces same-setup re-entries ~15min, so this
  // is nearly free) so the side keeps trading all day rather than halting.
  perdir_cooldown_minutes: number
  // Post-force-close SIZE-DOWN. After each force-close on a side, that side's
  // next entries are sized by perdir_size_mult_after_fc ^ (force-closes today).
  // A repeatedly-wrong side keeps trading all day but at rapidly shrinking size
  // (1 -> 0.33 -> 0.11 -> 0.037 ...), so a one-way trend day can't run away.
  // Resets each morning (counter is keyed on trade_date). This is the lever that
  // manages risk WITHOUT ever stopping a direction from trading.
  perdir_size_mult_after_fc: number
  // Hard ceiling on simultaneously-open positions per direction. Bounds the
  // intraday swing / blast radius independent of the force-close stop.
  max_concurrent_per_direction: number
}

// FLARE = 0DTE, validated config: PT 20% / SL 100% of debit (vs BLAZE's SL 30%).
//
// Sizing: with SL=100 the debit deployed IS the max loss per trade, so BLAZE's
// risk_per_trade_pct 0.20 x buying_power_usage_pct 0.85 = ~17%/trade would be
// ruinous here (a 3-loss cluster ~= -45%, and account_sim.py shows 25%/trade
// backtested to a -66% drawdown). Cut to ~4%/trade (0.05 x 0.85 = 4.25% of the
// account deployed) for a sane drawdown profile (~-15% on the historical path).
//
// Per-setup daily cap effectively removed: backtest showed cap=3 leaves real
// money on the table (2.25 trades/day) vs 5.46/day at 74.6% WR / PF 2.72 when
// only the signal-reset gate enforces re-entry discipline.
export const DEFAULT_FLARE_CONFIG: FlareConfig = {
  ...DEFAULT_BLAZE_CONFIG,
  stop_loss_pct: 100.0,
  risk_per_trade_pct: 0.05,
  max_trades_per_setup_per_day: 999,
  // Per-direction risk controls (see FlareConfig doc above). The "trade all day
  // AND manage risk" equilibrium (operator decision 2026-06-08): 5% per-side
  // force-close caps each adverse cluster; a 15-min cooldown keeps the side
  // trading all day (no halt); and each force-close shrinks that side's next
  // entries x0.33 so a repeatedly-wrong side throttles itself instead of being
  // shut off. 20 concurrent-per-side cap bounds the blast radius.
  // Validated on FLARE's own 8-day tape (flare_equilibrium.py, flat $500/trade):
  //   FC5% + cd15 + size x0.33/FC + cap20 = +$12,681  PF 2.66  maxDD 47%
  //     worst day -$1,967  (~41 trades/day, NEVER halts a direction)
  // vs permanent-halt (+$12,790 / 31/day / -$618) and flat-45m cooldown
  //   (+$14,128 / 37/day / -$2,073 / DD50%). Size-down = most all-day trading
  //   with the lowest drawdown of any >=40/day policy. Loosening FC% was worse.
  perdir_force_close_pct: 0.05,
  perdir_cooldown_minutes: 15,
  perdir_size_mult_after_fc: 0.33,
  max_concurrent_per_direction: 20,
  // 0DTE timing override (vs BLAZE's 1DTE 15:55).
  //   - Entries cut off at 14:30 in scanner.ts:isMarketHours.
  //   - 14:45 TIME_STOP closes anything still open 15min before 15:00 settlement.
  // The earlier eod_time_ct also forces close BEFORE Tradier stops quoting
  // expired 0DTE contracts, avoiding the stranded-open reconciliation case.
  eod_time_ct: '14:45',
}
