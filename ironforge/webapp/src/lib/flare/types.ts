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

export type FlareConfig = BlazeConfig

// FLARE = 0DTE, validated config: PT 20% / SL 100% of debit (vs BLAZE's SL 30%).
//
// Sizing: with SL=100 the debit deployed IS the max loss per trade, so BLAZE's
// risk_per_trade_pct 0.20 x buying_power_usage_pct 0.85 = ~17%/trade would be
// ruinous here (a 3-loss cluster ~= -45%, and account_sim.py shows 25%/trade
// backtested to a -66% drawdown). Cut to ~4%/trade (0.05 x 0.85 = 4.25% of the
// account deployed) for a sane drawdown profile (~-15% on the historical path).
export const DEFAULT_FLARE_CONFIG: FlareConfig = {
  ...DEFAULT_BLAZE_CONFIG,
  stop_loss_pct: 100.0,
  risk_per_trade_pct: 0.05,
}
