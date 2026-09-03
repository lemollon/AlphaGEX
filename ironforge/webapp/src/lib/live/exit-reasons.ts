/**
 * Member-safe exit reason dictionary (APP-019/022).
 *
 * `close_reason` on a `{bot}_positions` row is scanner-internal shorthand
 * (profit_target_30pct, stop_loss_2x, eod_cutoff, swing_green_bank,
 * trailing_lockin, broker_gone_close, reconcile_*, expired, manual/force, …)
 * and must never reach a customer verbatim — only one of the six fixed
 * strings below may. The branching mirrors outcomeOf() in trades-history.ts
 * so a trade's list badge and its detail screen never disagree about why it
 * closed, but is kept standalone (no import of trades-history.ts) so this
 * module has no dependency on the query layer and can be unit-tested alone.
 *
 * No advice language — this states what happened, never what to do next.
 */

export type ExitReasonCode = 'profit_target' | 'stop_loss' | 'manual_close' | 'expired' | 'auto_close' | 'other'

const EXIT_REASON_TEXT: Record<ExitReasonCode, string> = {
  profit_target: 'Profit target hit',
  stop_loss: 'Stop loss hit',
  manual_close: 'Closed manually by operator',
  expired: 'Expired',
  auto_close: 'Auto-closed before expiry',
  other: 'Other',
}

export function classifyExitReason(reason: string | null | undefined): { code: ExitReasonCode; text: string } {
  const r = (reason ?? '').toLowerCase()
  let code: ExitReasonCode
  if (r.startsWith('profit_target')) code = 'profit_target'
  else if (r.includes('stop_loss')) code = 'stop_loss'
  else if (r.includes('manual') || r.includes('force')) code = 'manual_close'
  else if (r.includes('expired')) code = 'expired'
  else if (r) code = 'auto_close'
  else code = 'other'
  return { code, text: EXIT_REASON_TEXT[code] }
}
