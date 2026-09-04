/**
 * Decide whether an event may notify a given customer, then send it.
 *
 * The three guards, in order, because each catches something the others cannot:
 *
 *  1. PREFERENCE  — the customer turned this category off.
 *  2. STALENESS    — the event is older than its category allows. Catches the
 *     "dispatch failed and retried twenty minutes later" case, where the underlying
 *     transition is still valid but the notification would be a lie.
 *  3. RE-READ      — the condition healed between detection and send. A transition
 *     check alone cannot catch this; APP-035 asks that stale alerts not fire AFTER
 *     recovery, which means checking at SEND time, not only at detect time.
 *
 * Then dedupe (atomic claim) so an event notifies exactly once per customer even if
 * the scanner retries, two instances race, or the HTTP call is delivered twice.
 */
import { customerQuery, customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'
import { sendExpoPush, isDeviceGone, isPushConfigured, type PushTicket } from '@/lib/push/transport'
import { renderNotification } from '@/lib/push/render'
import { CATEGORY_PREF_COLUMN, STALE_AFTER_SEC, type NotificationEvent } from '@/lib/push/types'

export interface DispatchResult {
  sent: number
  skipped: number
  reasons: string[]
}

interface PrefRow {
  show_amounts_on_lockscreen: boolean
  [key: string]: boolean | string
}

interface DeviceRow {
  id: string
  expo_push_token: string
}

/** Preferences with the schema defaults applied when the customer has no row yet. */
async function loadPrefs(userId: string): Promise<PrefRow> {
  const rows = await customerQuery<PrefRow>(
    `SELECT trade_opened, trade_closed, trade_approval, brokerage_health, billing,
            community, show_amounts_on_lockscreen, sound
       FROM notification_prefs WHERE user_id = $1 LIMIT 1`,
    [userId],
  )
  return (
    rows[0] ?? {
      trade_opened: true,
      trade_closed: true,
      trade_approval: true,
      brokerage_health: true,
      billing: true,
      community: false,
      show_amounts_on_lockscreen: false,
      sound: true,
    }
  )
}

/**
 * Atomic "have we already told this person?".
 *
 * For state-carrying categories the same key recurs with a different `state`, so a
 * conflict updates only when the state actually CHANGED — that is what makes
 * `degraded -> degraded` silent while `ok -> degraded` notifies.
 */
async function claim(event: NotificationEvent, userId: string): Promise<boolean> {
  if (event.state != null) {
    const rows = await customerQuery<{ event_key: string }>(
      `INSERT INTO notification_events (event_key, user_id, category, state)
       VALUES ($1, $2, $3, $4)
       ON CONFLICT (event_key, user_id) DO UPDATE
         SET state = EXCLUDED.state,
             last_sent_at = now(),
             send_count = notification_events.send_count + 1
       WHERE notification_events.state IS DISTINCT FROM EXCLUDED.state
       RETURNING event_key`,
      [event.eventKey, userId, event.category, event.state],
    )
    return rows.length > 0
  }
  const rows = await customerQuery<{ event_key: string }>(
    `INSERT INTO notification_events (event_key, user_id, category, state)
     VALUES ($1, $2, $3, NULL)
     ON CONFLICT (event_key, user_id) DO NOTHING
     RETURNING event_key`,
    [event.eventKey, userId, event.category],
  )
  return rows.length > 0
}

/** Guard 3 — re-read the underlying condition at SEND time. */
async function conditionStillHolds(event: NotificationEvent): Promise<boolean> {
  if (event.category === 'trade_approval') {
    const id = event.routeParams?.approvalId
    if (!id) return true
    const rows = await customerQuery<{ status: string; expired: boolean }>(
      `SELECT status, (expires_at <= now()) AS expired FROM trade_approvals WHERE id = $1 LIMIT 1`,
      [id],
    )
    const row = rows[0]
    // Already approved, declined, or timed out — waking someone is pure noise.
    return !!row && row.status === 'pending' && !row.expired
  }
  if (event.category === 'brokerage_health') {
    const id = event.routeParams?.connectionId
    if (!id) return true
    const rows = await customerQuery<{ status: string }>(
      `SELECT status FROM brokerage_connections WHERE id = $1 LIMIT 1`,
      [id],
    )
    // Reconnected in the interim: do not deliver a "your brokerage is disconnected".
    return !(rows[0]?.status === 'active')
  }
  return true
}

export async function dispatchToCustomers(
  event: NotificationEvent,
  customerIds: string[],
  now: number = Date.now(),
): Promise<DispatchResult> {
  const result: DispatchResult = { sent: 0, skipped: 0, reasons: [] }
  if (!isCustomersDbConfigured() || customerIds.length === 0) return result

  // Guard 2 — staleness. Applied once; it does not vary per customer.
  const ageSec = (now - new Date(event.occurredAt).getTime()) / 1000
  if (ageSec > (STALE_AFTER_SEC[event.category] ?? 900)) {
    result.skipped += customerIds.length
    result.reasons.push('stale')
    return result
  }

  if (!(await conditionStillHolds(event))) {
    result.skipped += customerIds.length
    result.reasons.push('condition_resolved')
    return result
  }

  for (const userId of customerIds) {
    const prefs = await loadPrefs(userId)

    // Guard 1 — the customer turned this category off.
    if (prefs[CATEGORY_PREF_COLUMN[event.category]] !== true) {
      result.skipped++
      result.reasons.push('pref_off')
      continue
    }

    if (!(await claim(event, userId))) {
      result.skipped++
      result.reasons.push('duplicate')
      continue
    }

    const devices = await customerQuery<DeviceRow>(
      `SELECT id, expo_push_token FROM push_devices
        WHERE user_id = $1 AND enabled = TRUE`,
      [userId],
    )
    if (devices.length === 0) {
      result.skipped++
      result.reasons.push('no_device')
      continue
    }

    const base = renderNotification(event, {
      showAmountsOnLockscreen: prefs.show_amounts_on_lockscreen === true,
      sound: prefs.sound !== false,
    })
    const messages = devices.map((d) => ({ ...base, to: d.expo_push_token }))
    const tickets = await sendExpoPush(messages)

    for (let i = 0; i < devices.length; i++) {
      const ticket: PushTicket = tickets[i] ?? { status: 'error', message: 'missing_ticket' }
      if (ticket.status === 'ok') result.sent++
      else result.skipped++

      // A dead token would otherwise accumulate failures forever.
      if (isDeviceGone(ticket)) {
        await customerExecute(
          `UPDATE push_devices
              SET enabled = FALSE, disabled_reason = 'DeviceNotRegistered', updated_at = now()
            WHERE id = $1`,
          [devices[i].id],
        ).catch(() => {})
      }

      await customerExecute(
        `INSERT INTO notification_deliveries
           (user_id, push_device_id, event_key, expo_ticket_id, status, error)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [
          userId,
          devices[i].id,
          event.eventKey,
          ticket.id ?? null,
          ticket.status,
          ticket.status === 'ok' ? null : (ticket.details?.error ?? ticket.message ?? 'unknown'),
        ],
      ).catch(() => {})
    }
  }

  return result
}

export { isPushConfigured }
