/**
 * CRM outbox — durable delivery of lifecycle events to Attio.
 *
 * Call sites do one thing: `enqueueCrmEvent(...)`. It never throws and never blocks on Attio, so
 * a CRM outage can't fail a signup, a checkout, or a brokerage callback. Delivery, retry,
 * ordering and dead-lettering all happen here.
 *
 * Idempotency is the `event_id` primary key, supplied by the caller and stable per business
 * event (Stripe event id, connection attempt id, submission id …). A replayed webhook or a
 * double-fired emitter inserts nothing the second time, so the CRM never sees a duplicate
 * (AC-CRM-002). The Attio write itself is an upsert on a unique matching attribute, so even a
 * retry after an ambiguous timeout converges on one record.
 *
 * Terminal `status='failed'` after MAX_CRM_ATTEMPTS is the replayable dead-letter queue
 * (AC-CRM-010) — nothing is silently dropped, and POST /api/ops/crm/replay puts rows back.
 */

import { customerExecute, customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { isAttioConfigured } from '@/lib/crm/client'
import { deliverCrmEvent, type CrmEventType } from '@/lib/crm/events'

/** Give up after this many attempts so one poison record can't loop forever. */
export const MAX_CRM_ATTEMPTS = 6

/**
 * Retry schedule in seconds, indexed by attempt number. Roughly 30s → 2m → 8m → 30m → 2h,
 * which covers a transient blip and a multi-hour Attio incident without hammering either.
 */
const BACKOFF_SECONDS = [30, 120, 480, 1800, 7200]

function backoffSeconds(attempts: number): number {
  return BACKOFF_SECONDS[Math.min(attempts, BACKOFF_SECONDS.length - 1)]
}

export interface CrmEventInput {
  /** Stable per business event. THIS is the idempotency guarantee — never use a random uuid. */
  eventId: string
  eventType: CrmEventType
  payload: Record<string, unknown>
  userId?: string | null
  correlationId?: string | null
}

export interface EnqueueResult {
  enqueued: boolean
  duplicate?: boolean
  skipped?: boolean
  error?: string
}

/**
 * Queue a CRM event. Never throws — a CRM failure must not take down the caller's request.
 * Returns {skipped:true} when the customers DB is unconfigured (local dev / operator service).
 */
export async function enqueueCrmEvent(input: CrmEventInput): Promise<EnqueueResult> {
  if (!isCustomersDbConfigured()) return { enqueued: false, skipped: true }
  try {
    const inserted = await customerExecute(
      `INSERT INTO crm_outbox (event_id, event_type, payload, user_id, correlation_id)
       VALUES ($1, $2, $3::jsonb, $4, $5)
       ON CONFLICT (event_id) DO NOTHING`,
      [
        input.eventId,
        input.eventType,
        JSON.stringify(input.payload),
        input.userId ?? null,
        input.correlationId ?? null,
      ],
    )
    // 0 rows means we've already seen this business event — the desired no-op, not an error.
    return inserted > 0 ? { enqueued: true } : { enqueued: false, duplicate: true }
  } catch (e) {
    console.error('[crm] enqueue failed (non-fatal):', e)
    return { enqueued: false, error: e instanceof Error ? e.message : 'crm enqueue failed' }
  }
}

export interface DrainResult {
  processed: number
  delivered: number
  retrying: number
  deadLettered: number
  skipped?: boolean
}

interface OutboxRow {
  event_id: string
  event_type: string
  payload: Record<string, unknown>
  attempts: number
}

/**
 * Deliver due events. Safe to call concurrently with itself only in the sense that duplicates are
 * harmless (upserts + event_id PK); the caller still guards re-entrancy so a slow Attio can't
 * stack drains.
 */
export async function drainCrmOutbox(limit = 25): Promise<DrainResult> {
  const empty: DrainResult = { processed: 0, delivered: 0, retrying: 0, deadLettered: 0 }
  if (!isCustomersDbConfigured() || !isAttioConfigured()) return { ...empty, skipped: true }

  let rows: OutboxRow[]
  try {
    rows = await customerQuery<OutboxRow>(
      `SELECT event_id, event_type, payload, attempts
         FROM crm_outbox
        WHERE status = 'pending'
          AND attempts < $1
          AND next_attempt_at <= now()
        ORDER BY created_at ASC
        LIMIT $2`,
      [MAX_CRM_ATTEMPTS, limit],
    )
  } catch (e) {
    console.error('[crm] drain query failed:', e)
    return empty
  }

  const out = { ...empty }

  for (const row of rows) {
    out.processed++
    const result = await deliverCrmEvent(row.event_type as CrmEventType, row.payload)

    if (result.ok) {
      await customerExecute(
        `UPDATE crm_outbox
            SET status = 'delivered', delivered_at = now(), updated_at = now(),
                attio_record_id = COALESCE($2, attio_record_id), last_error = NULL
          WHERE event_id = $1`,
        [row.event_id, result.recordId ?? null],
      ).catch((e) => console.error('[crm] mark delivered failed:', e))
      out.delivered++
      continue
    }

    const attempts = row.attempts + 1
    // A permanent error (4xx that isn't 429, or an unmapped event type) will never succeed —
    // dead-letter it immediately rather than burning five more attempts on it.
    const terminal = attempts >= MAX_CRM_ATTEMPTS || result.retryable === false
    await customerExecute(
      `UPDATE crm_outbox
          SET attempts = $2,
              status = $3,
              last_error = $4,
              next_attempt_at = now() + ($5 || ' seconds')::interval,
              updated_at = now()
        WHERE event_id = $1`,
      [
        row.event_id,
        attempts,
        terminal ? 'failed' : 'pending',
        (result.error ?? 'unknown error').slice(0, 500),
        String(backoffSeconds(attempts)),
      ],
    ).catch((e) => console.error('[crm] mark retry failed:', e))

    if (terminal) out.deadLettered++
    else out.retrying++
  }

  return out
}

export interface ReplayResult {
  replayed: number
  skipped?: boolean
}

/**
 * Put dead-lettered events back in the queue. Replay is safe by construction: delivery is an
 * upsert keyed on a unique matching attribute, so re-running an event updates the same record
 * rather than creating a second one — the spec's "replay without creating duplicate records or
 * duplicate tasks" requirement (§10).
 */
export async function replayCrmDeadLetters(limit = 100, eventId?: string): Promise<ReplayResult> {
  if (!isCustomersDbConfigured()) return { replayed: 0, skipped: true }
  const replayed = await customerExecute(
    eventId
      ? `UPDATE crm_outbox
            SET status = 'pending', attempts = 0, next_attempt_at = now(), updated_at = now()
          WHERE status = 'failed' AND event_id = $1`
      : `UPDATE crm_outbox
            SET status = 'pending', attempts = 0, next_attempt_at = now(), updated_at = now()
          WHERE event_id IN (
            SELECT event_id FROM crm_outbox WHERE status = 'failed' ORDER BY created_at ASC LIMIT $1
          )`,
    eventId ? [eventId] : [limit],
  )
  return { replayed }
}
