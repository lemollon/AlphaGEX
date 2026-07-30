import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { isUuid } from '@/lib/enrollment/ids'
import { TRIAL_ELIGIBLE_DAYS } from '@/lib/enrollment/trading-days'

/**
 * DASH-FIRST-01 — the first-entry activation confirmation (July 29 handoff).
 *
 * Returned by /api/live/summary while the newest activation's confirmation has not
 * been shown; the client stamps it via POST /api/v1/activations/{id}/confirmation-seen
 * and later visits render the normal runtime states. Server-persisted (a column on the
 * activation row) because the flow crosses a hard redirect and a fresh device must not
 * re-show it — "show once per activation ID" is a property of the activation, not of a
 * browser.
 *
 * Fails SOFT: this is decoration on the Live payload; an unreadable customers DB must
 * never take the dashboard down.
 */

export interface ActivationConfirmation {
  activation_id: string
  agent: string
  account_mask: string | null
  trial_day: number
  trial_total: number
}

export async function getActivationConfirmation(
  customerId: string | null | undefined,
): Promise<ActivationConfirmation | null> {
  if (!customerId || !isUuid(customerId) || !isCustomersDbConfigured()) return null
  try {
    const rows = await customerQuery<{
      id: string
      agent_code: string
      display_mask: string | null
      used: string | null
    }>(
      `SELECT a.id, ac.agent_code, ba.display_mask, t.eligible_days_used::text AS used
         FROM activations a
         JOIN agent_configs ac ON ac.id = a.config_id
         LEFT JOIN broker_accounts ba ON ba.id = ac.broker_account_id
         LEFT JOIN trials t ON t.activation_id = a.id
        WHERE a.user_id = $1 AND a.status = 'active' AND a.confirmation_shown_at IS NULL
        ORDER BY a.activated_at DESC
        LIMIT 1`,
      [customerId],
    )
    const r = rows[0]
    if (!r) return null
    return {
      activation_id: r.id,
      agent: r.agent_code,
      account_mask: r.display_mask,
      trial_day: Math.min(TRIAL_ELIGIBLE_DAYS, Number(r.used ?? 0)),
      trial_total: TRIAL_ELIGIBLE_DAYS,
    }
  } catch {
    return null
  }
}
