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
export const DEFAULT_FLARE_CONFIG: FlareConfig = { ...DEFAULT_BLAZE_CONFIG, stop_loss_pct: 100.0 }
