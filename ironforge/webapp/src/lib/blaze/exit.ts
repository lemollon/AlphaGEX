/**
 * BLAZE — exit decision tree. Pure function, no I/O.
 * Mirrors trading/helios/strategy.py.decide_exit.
 *
 * Order of precedence:
 *  1. PT  (pnl_pct >= profit_target_pct)
 *  2. SL  (pnl_pct <= -stop_loss_pct)
 *  3. TIME_STOP  (now_ct >= eod_time_ct)
 *  4. DATA_FAILURE  (quotes_unavail_streak >= max)
 *
 * No trailing stop. Phase 2 of the 1DTE research showed trail kills winners on 1DTE noise.
 */
import { BlazeConfig, ExitReason } from './types'

export interface ExitDecision {
  should_exit: boolean
  reason: ExitReason | null
}

export function decideExit(args: {
  debit: number
  mark_to_close: number
  now_ct: Date
  quotes_unavail_streak: number
  config: BlazeConfig
}): ExitDecision {
  const { debit, mark_to_close, now_ct, quotes_unavail_streak, config } = args
  const pnl_pct = debit > 0 ? (mark_to_close / debit - 1.0) * 100.0 : 0.0

  if (pnl_pct >= config.profit_target_pct) {
    return { should_exit: true, reason: 'PT' }
  }
  if (pnl_pct <= -config.stop_loss_pct) {
    return { should_exit: true, reason: 'SL' }
  }

  const [eodH, eodM] = config.eod_time_ct.split(':').map(Number)
  const h = now_ct.getHours()
  const m = now_ct.getMinutes()
  if (h > eodH || (h === eodH && m >= eodM)) {
    return { should_exit: true, reason: 'TIME_STOP' }
  }

  if (quotes_unavail_streak >= config.quotes_unavailable_max_cycles) {
    return { should_exit: true, reason: 'DATA_FAILURE' }
  }

  return { should_exit: false, reason: null }
}
