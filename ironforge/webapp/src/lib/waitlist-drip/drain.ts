/**
 * Waitlist drip drain — the send loop. Runs on the scanner's 30-second cadence (scanner.ts,
 * next to the CRM outbox drain) and on demand from POST /api/ops/waitlist/drip.
 *
 * Per tick:
 *   1. refuse outright when a send-time precondition is missing (business address, public
 *      origin, Resend config) — logged loudly, rows untouched;
 *   2. return rows stuck in `sending` for >10 min to `active` (a process died mid-tick; the
 *      Resend idempotency key makes a re-send of that stage a no-op at the provider);
 *   3. CLAIM due rows with `FOR UPDATE SKIP LOCKED` + a status flip to `sending`, so two
 *      ticks — two instances, or the ops endpoint racing the scanner — can never both hold
 *      the same subscriber;
 *   4. per row: re-run suppression, render, send, log the send, advance the stage, and
 *      compute the next due time FROM THE ACTUAL SEND INSTANT (the kit's restart rule);
 *   5. mirror the stage to Attio through the CRM outbox — fire-and-forget, never blocking.
 *
 * Idempotency is layered: the claim (one tick per row), the send log's partial unique index
 * (one `sent` per (subscriber, stage)), the suppression check's `alreadySentThisStage`, and
 * Resend's Idempotency-Key. Any one of them alone would be enough for the common case; the
 * layers are for the uncommon ones.
 */

import { customerExecute, customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { isEmailConfigured, sendEmail, type SendEmailInput, type SendResult } from '@/lib/email'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import { publicOriginFromEnv } from '@/lib/public-origin'
import { DRIP_FINAL_STAGE } from './copy'
import { businessAddressFromEnv, renderDripEmail } from './render'
import { nextSendDate } from './schedule'
import { classifySuppression, isTerminalReason, lookupSuppressionFacts, type SuppressionFacts } from './suppression'

/** Consecutive send failures before a row is parked as `failed` for an operator. */
export const MAX_SEND_ATTEMPTS = 5

/** Retry gap after a failed send, multiplied by the attempt number. */
const RETRY_BASE_MINUTES = 15

/** A `sending` claim older than this is a dead tick, not a slow one. */
const STALE_CLAIM_MINUTES = 10

export interface ClaimedRow {
  id: string
  email: string
  first_name: string | null
  stage: number
  send_attempts: number
  unsubscribe_token: string
}

/** Injectable seams so the loop is testable without Postgres or Resend. */
export interface DrainDeps {
  query: <T = Record<string, unknown>>(sql: string, params?: unknown[]) => Promise<T[]>
  execute: (sql: string, params?: unknown[]) => Promise<number>
  send: (input: SendEmailInput) => Promise<SendResult>
  lookupFacts: (email: string, sequenceId: string, nextStage: number) => Promise<SuppressionFacts>
  enqueueCrm: typeof enqueueCrmEvent
  now: () => Date
  origin: () => string | null
  businessAddress: () => string
  emailConfigured: () => boolean
  dbConfigured: () => boolean
}

const defaultDeps: DrainDeps = {
  query: customerQuery,
  execute: customerExecute,
  send: sendEmail,
  lookupFacts: lookupSuppressionFacts,
  enqueueCrm: enqueueCrmEvent,
  now: () => new Date(),
  origin: publicOriginFromEnv,
  businessAddress: businessAddressFromEnv,
  emailConfigured: isEmailConfigured,
  dbConfigured: isCustomersDbConfigured,
}

export interface DrainOptions {
  limit?: number
  /** Restrict to one address — used by POST /api/waitlist to push Email 1 out immediately. */
  onlyEmail?: string
}

export interface DripDrainResult {
  /** Rows claimed this tick. */
  processed: number
  sent: number
  suppressed: number
  /** Advanced without sending: a `sent` log row already existed for the stage. */
  skippedDuplicate: number
  failed: number
  completed: number
  /** Set when the tick refused to run; nothing was claimed. */
  blocked?: string
  skipped?: boolean
}

/**
 * Names the missing precondition, or null when sends may proceed. Exported for the ops
 * status endpoint so the blocker is visible before anyone fires the backfill.
 */
export function sendPreconditionBlocker(deps: Pick<DrainDeps, 'origin' | 'businessAddress' | 'emailConfigured'> = defaultDeps): string | null {
  if (!deps.emailConfigured()) return 'RESEND_API_KEY / EMAIL_FROM unset — email is not configured'
  if (!deps.businessAddress()) return 'IRONFORGE_BUSINESS_ADDRESS unset — the footer needs a postal address'
  if (!deps.origin()) return 'IRONFORGE_PUBLIC_URL / RENDER_EXTERNAL_URL unset — cannot build absolute links'
  return null
}

export function dripLinks(origin: string, token: string) {
  return {
    privacyUrl: `${origin}/privacy`,
    preferencesUrl: `${origin}/email/preferences/${token}`,
    unsubscribeUrl: `${origin}/email/unsubscribe/${token}`,
  }
}

export function idempotencyKeyFor(sequenceId: string, stage: number): string {
  return `waitlist-drip:${sequenceId}:${stage}`
}

/** After a successful send of `stage` at `at`: the row's new stage/status/next due time. */
export function advanceAfterSend(stage: number, at: Date): { stage: number; status: 'active' | 'completed'; nextSendAt: Date | null } {
  if (stage >= DRIP_FINAL_STAGE) return { stage, status: 'completed', nextSendAt: null }
  return { stage, status: 'active', nextSendAt: nextSendDate(at) }
}

let _lastBlockedLog = 0

export async function drainWaitlistDrip(opts: DrainOptions = {}, deps: DrainDeps = defaultDeps): Promise<DripDrainResult> {
  const out: DripDrainResult = { processed: 0, sent: 0, suppressed: 0, skippedDuplicate: 0, failed: 0, completed: 0 }
  if (!deps.dbConfigured()) return { ...out, skipped: true }

  const blocker = sendPreconditionBlocker(deps)
  if (blocker) {
    // Every 30s would be log spam; every 10 min is a heartbeat an operator can find.
    const t = Date.now()
    if (t - _lastBlockedLog > 10 * 60 * 1000) {
      _lastBlockedLog = t
      console.error(`[waitlist-drip] sends blocked: ${blocker}`)
    }
    return { ...out, blocked: blocker }
  }
  const origin = deps.origin() as string
  const businessAddress = deps.businessAddress()
  const limit = Math.max(1, Math.min(200, opts.limit ?? 25))

  // 2) Dead-tick recovery.
  await deps.execute(
    `UPDATE waitlist_sequence SET status = 'active', updated_at = now()
      WHERE status = 'sending' AND updated_at < now() - ($1 || ' minutes')::interval`,
    [String(STALE_CLAIM_MINUTES)],
  )

  // 3) Claim.
  const only = opts.onlyEmail?.trim().toLowerCase() || null
  const rows = await deps.query<ClaimedRow>(
    `UPDATE waitlist_sequence s
        SET status = 'sending', updated_at = now()
      WHERE s.id IN (
        SELECT id FROM waitlist_sequence
         WHERE status = 'active'
           AND next_send_at IS NOT NULL
           AND next_send_at <= now()
           AND ($2::text IS NULL OR lower(email) = $2)
         ORDER BY next_send_at ASC
         LIMIT $1
         FOR UPDATE SKIP LOCKED
      )
      RETURNING s.id, s.email, s.first_name, s.stage, s.send_attempts, s.unsubscribe_token`,
    [limit, only],
  )

  for (const row of rows) {
    out.processed++
    try {
      await processOne(row, { origin, businessAddress }, deps, out)
    } catch (e) {
      // Belt and braces: nothing below should throw, but a claimed row must never be left in
      // `sending` because of a bug here. Release it with the error attached.
      const msg = e instanceof Error ? e.message : String(e)
      console.error(`[waitlist-drip] unexpected error for ${row.id}: ${msg}`)
      await deps
        .execute(
          `UPDATE waitlist_sequence SET status = 'active', last_error = $2, updated_at = now() WHERE id = $1 AND status = 'sending'`,
          [row.id, msg.slice(0, 500)],
        )
        .catch(() => {})
      out.failed++
    }
  }
  return out
}

async function processOne(
  row: ClaimedRow,
  env: { origin: string; businessAddress: string },
  deps: DrainDeps,
  out: DripDrainResult,
): Promise<void> {
  const nextStage = Number(row.stage) + 1
  if (nextStage > DRIP_FINAL_STAGE) {
    await deps.execute(
      `UPDATE waitlist_sequence SET status = 'completed', next_send_at = NULL, updated_at = now() WHERE id = $1`,
      [row.id],
    )
    out.completed++
    return
  }

  // 4a) Suppression, re-run at send time.
  const facts = await deps.lookupFacts(row.email, row.id, nextStage)
  const reason = classifySuppression(facts)
  if (reason && isTerminalReason(reason)) {
    await deps.execute(
      `UPDATE waitlist_sequence
          SET status = 'suppressed', suppression_reason = $2, suppressed_at = now(), next_send_at = NULL, updated_at = now()
        WHERE id = $1`,
      [row.id, reason],
    )
    out.suppressed++
    return
  }

  const at = deps.now()
  if (reason === 'duplicate') {
    // Already went out (a prior tick sent and died before advancing). Advance, don't resend.
    const adv = advanceAfterSend(nextStage, at)
    await deps.execute(
      `UPDATE waitlist_sequence
          SET stage = $2, status = $3, next_send_at = $4, send_attempts = 0, last_error = NULL, updated_at = now()
        WHERE id = $1`,
      [row.id, adv.stage, adv.status, adv.nextSendAt ? adv.nextSendAt.toISOString() : null],
    )
    out.skippedDuplicate++
    if (adv.status === 'completed') out.completed++
    return
  }

  // 4b) Render + send.
  const links = dripLinks(env.origin, row.unsubscribe_token)
  const rendered = renderDripEmail({
    stage: nextStage,
    firstName: row.first_name,
    links,
    businessAddress: env.businessAddress,
  })
  const result = await deps.send({
    to: row.email,
    subject: rendered.subject,
    html: rendered.html,
    text: rendered.text,
    headers: {
      'List-Unsubscribe': `<${links.unsubscribeUrl}>`,
      'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
    },
    idempotencyKey: idempotencyKeyFor(row.id, nextStage),
  })

  if (result.skipped) {
    // Email became unconfigured mid-tick. Release the claim untouched.
    await deps.execute(`UPDATE waitlist_sequence SET status = 'active', updated_at = now() WHERE id = $1`, [row.id])
    return
  }

  if (!result.sent) {
    const attempts = Number(row.send_attempts) + 1
    const parked = attempts >= MAX_SEND_ATTEMPTS
    const error = (result.error ?? 'send failed').slice(0, 500)
    await deps.execute(
      `INSERT INTO waitlist_sequence_sends (sequence_id, stage, status, error) VALUES ($1, $2, 'failed', $3)`,
      [row.id, nextStage, error],
    )
    await deps.execute(
      `UPDATE waitlist_sequence
          SET status = $2, send_attempts = $3, last_error = $4,
              next_send_at = CASE WHEN $2 = 'failed' THEN NULL ELSE now() + ($5 || ' minutes')::interval END,
              updated_at = now()
        WHERE id = $1`,
      [row.id, parked ? 'failed' : 'active', attempts, error, String(RETRY_BASE_MINUTES * attempts)],
    )
    console.error(`[waitlist-drip] send failed for ${row.id} stage ${nextStage} (attempt ${attempts}): ${error}`)
    out.failed++
    return
  }

  // 4c) Log, advance, schedule from the ACTUAL send instant.
  try {
    await deps.execute(
      `INSERT INTO waitlist_sequence_sends (sequence_id, stage, status, resend_message_id, sent_at)
       VALUES ($1, $2, 'sent', $3, $4)`,
      [row.id, nextStage, result.id ?? null, at.toISOString()],
    )
  } catch (e) {
    // The partial unique index fired: a `sent` row already existed, i.e. this stage went out
    // twice. The provider-side idempotency key should have made the second a no-op, but say so.
    console.error(`[waitlist-drip] DUPLICATE send log for ${row.id} stage ${nextStage}: ${e instanceof Error ? e.message : e}`)
  }
  const adv = advanceAfterSend(nextStage, at)
  await deps.execute(
    `UPDATE waitlist_sequence
        SET stage = $2, status = $3, next_send_at = $4, last_sent_at = $5, send_attempts = 0, last_error = NULL, updated_at = now()
      WHERE id = $1`,
    [row.id, adv.stage, adv.status, adv.nextSendAt ? adv.nextSendAt.toISOString() : null, at.toISOString()],
  )
  out.sent++
  if (adv.status === 'completed') out.completed++

  if (nextStage === 1) {
    // Email 1 is the welcome; keep the legacy column truthful for the ops waitlist views.
    await deps
      .execute(`UPDATE waitlist_submissions SET email_status = 'sent', updated_at = now() WHERE lower(email) = $1`, [
        row.email.toLowerCase(),
      ])
      .catch(() => {})
  }

  // 5) Attio mirror — durable outbox, never awaited for correctness, never a send blocker.
  void deps
    .enqueueCrm({
      eventId: `waitlist_email:${row.id}:${nextStage}`,
      eventType: 'crm.waitlist_email_sent',
      correlationId: row.id,
      payload: {
        email: row.email.toLowerCase(),
        firstName: row.first_name ?? undefined,
        waitlistEmailStage: nextStage,
        waitlistLastEmailAt: at.toISOString(),
      },
    })
    .catch(() => {})
}
