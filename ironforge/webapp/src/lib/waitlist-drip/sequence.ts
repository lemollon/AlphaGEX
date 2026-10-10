/**
 * Waitlist drip — subscriber lifecycle: enrollment, backfill, preferences, and unsubscribe.
 *
 * Everything here is idempotent on lower(email): enrolling the same person twice, or
 * backfilling twice, changes nothing the second time. Nothing here sends mail; the drain
 * (drain.ts) does that on its own tick.
 */

import { randomBytes } from 'crypto'
import { customerExecute, customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { DRIP_FINAL_STAGE } from './copy'
import { firstSendAt, defaultFirstSendDate, type DateKey } from './schedule'
import type { SuppressionReason } from './suppression'

export type SequenceStatus = 'active' | 'sending' | 'completed' | 'suppressed' | 'failed'

export interface SequenceRow {
  id: string
  email: string
  first_name: string | null
  submission_id: string | null
  stage: number
  status: SequenceStatus
  next_send_at: string | null
  last_sent_at: string | null
  send_attempts: number
  last_error: string | null
  suppression_reason: string | null
  suppressed_at: string | null
  unsubscribe_token: string
  created_at: string
  updated_at: string
}

/** 128 bits of randomness, URL-safe. Opaque and per-row, so revocation is a row update. */
export function newUnsubscribeToken(): string {
  return randomBytes(16).toString('base64url')
}

/** Tokens are base64url of 16 bytes → 22 chars. Anything else is rejected before the query. */
export function isPlausibleToken(t: unknown): t is string {
  return typeof t === 'string' && /^[A-Za-z0-9_-]{22}$/.test(t)
}

export interface EnrollInput {
  email: string
  firstName?: string | null
  submissionId?: string | null
  /** When Email 1 is due. Defaults to now (the kit: "immediately after confirmed enrollment"). */
  firstSendAt?: Date
}

export interface EnrollResult {
  enrolled: boolean
  /** Row already existed — nothing changed except a refreshed first name. */
  existing?: boolean
  skipped?: boolean
  error?: string
  id?: string
}

/**
 * Create the sequence row for a confirmed waitlist submission. Never throws — a drip
 * failure must not fail the signup that triggered it.
 *
 * A resubmit by someone already enrolled refreshes their first name and nothing else: the
 * stage, the schedule and — deliberately — a suppression all survive. Someone who
 * unsubscribed and later re-enters the form has the preferences page to opt back in; the
 * form must not silently undo an unsubscribe.
 */
export async function enrollInWaitlistSequence(input: EnrollInput): Promise<EnrollResult> {
  if (!isCustomersDbConfigured()) return { enrolled: false, skipped: true }
  const email = input.email.trim().toLowerCase()
  if (!email) return { enrolled: false, error: 'no email' }
  try {
    const rows = await customerQuery<{ id: string; existed: boolean }>(
      `INSERT INTO waitlist_sequence (email, first_name, submission_id, stage, status, next_send_at, unsubscribe_token)
       VALUES ($1, $2, $3, 0, 'active', $4, $5)
       ON CONFLICT (lower(email)) DO UPDATE SET
         first_name = COALESCE(NULLIF(EXCLUDED.first_name, ''), waitlist_sequence.first_name),
         submission_id = COALESCE(EXCLUDED.submission_id, waitlist_sequence.submission_id),
         updated_at = now()
       RETURNING id, (xmax <> 0) AS existed`,
      [
        email,
        (input.firstName ?? '').trim() || null,
        input.submissionId ?? null,
        (input.firstSendAt ?? new Date()).toISOString(),
        newUnsubscribeToken(),
      ],
    )
    const r = rows[0]
    return { enrolled: true, existing: r?.existed === true, id: r?.id }
  } catch (e) {
    console.error('[waitlist-drip] enroll failed (non-fatal):', e)
    return { enrolled: false, error: e instanceof Error ? e.message : 'enroll failed' }
  }
}

export interface BackfillInput {
  /** YYYY-MM-DD (Chicago). Deferred to the next business day when it is not one. */
  firstSendDate?: DateKey
  dryRun?: boolean
  now?: Date
}

export interface BackfillResult {
  dryRun: boolean
  firstSendDate: DateKey
  firstSendAt: string
  /** Waitlist rows with no sequence row before this run. */
  candidates: number
  /** Enrolled as active (dry run: would be). */
  enrolled: number
  /** Enrolled directly as suppressed, by reason (dry run: would be). */
  suppressed: Record<string, number>
  /** Already had a sequence row — untouched. */
  alreadyEnrolled: number
}

/**
 * Seed a sequence row for every waitlist submission that has none (the existing list). Rows
 * whose address is already unsubscribed / hard-bounced / complained / holds an account are
 * inserted as `suppressed` WITH their reason, so the ops view shows why nobody wrote to them.
 *
 * Idempotent: ON CONFLICT DO NOTHING on lower(email), so re-running after a partial failure
 * only fills the gaps and never re-dates a row that already has a schedule.
 *
 * `firstSendDate` is the ops parameter; default = the next business day strictly after
 * today (Chicago), so firing the backfill can never send the same day without saying so.
 */
export async function backfillWaitlistSequence(input: BackfillInput = {}): Promise<BackfillResult> {
  const now = input.now ?? new Date()
  const requested = input.firstSendDate ?? defaultFirstSendDate(now)
  const at = firstSendAt(requested)
  const dryRun = input.dryRun === true

  const candidates = await customerQuery<{
    email: string
    first_name: string
    submission_id: string
    reason: SuppressionReason | null
  }>(
    `SELECT w.email, w.first_name, w.submission_id,
            CASE
              WHEN COALESCE(p.unsubscribed, FALSE) THEN 'unsubscribed'
              WHEN EXISTS (SELECT 1 FROM email_events ev
                            WHERE lower(ev.email) = lower(w.email) AND ev.event_type = 'email.complained') THEN 'complaint'
              WHEN EXISTS (SELECT 1 FROM email_events ev
                            WHERE lower(ev.email) = lower(w.email) AND ev.event_type = 'email.bounced'
                              AND ev.bounce_type = 'Permanent') THEN 'hard_bounce'
              WHEN EXISTS (SELECT 1 FROM users u WHERE lower(u.email) = lower(w.email)) THEN 'onboarding'
              ELSE NULL
            END AS reason
       FROM waitlist_submissions w
       LEFT JOIN email_preferences p ON p.email = lower(w.email)
      WHERE NOT EXISTS (SELECT 1 FROM waitlist_sequence s WHERE lower(s.email) = lower(w.email))
      ORDER BY w.created_at ASC`,
  )
  const already = await customerQuery<{ n: string }>(`SELECT count(*)::text AS n FROM waitlist_sequence`)

  const out: BackfillResult = {
    dryRun,
    firstSendDate: requested,
    firstSendAt: at.toISOString(),
    candidates: candidates.length,
    enrolled: 0,
    suppressed: {},
    alreadyEnrolled: Number(already[0]?.n ?? 0),
  }

  for (const c of candidates) {
    const reason = c.reason
    if (reason) out.suppressed[reason] = (out.suppressed[reason] ?? 0) + 1
    else out.enrolled++
    if (dryRun) continue
    await customerExecute(
      `INSERT INTO waitlist_sequence
         (email, first_name, submission_id, stage, status, next_send_at, suppression_reason, suppressed_at, unsubscribe_token)
       VALUES ($1, $2, $3, 0, $4, $5, $6, CASE WHEN $6::text IS NULL THEN NULL ELSE now() END, $7)
       ON CONFLICT (lower(email)) DO NOTHING`,
      [
        c.email.trim().toLowerCase(),
        (c.first_name ?? '').trim() || null,
        c.submission_id ?? null,
        reason ? 'suppressed' : 'active',
        reason ? null : at.toISOString(),
        reason,
        newUnsubscribeToken(),
      ],
    )
  }
  return out
}

// ---------------------------------------------------------------------------
// Preferences / unsubscribe (token-addressed)
// ---------------------------------------------------------------------------

export interface PreferenceState {
  email: string
  firstName: string | null
  unsubscribed: boolean
  /** Sequence status for context on the preferences page ("you have received 3 of 6"). */
  stage: number
  status: SequenceStatus
  finalStage: number
}

export async function preferenceStateForToken(token: string): Promise<PreferenceState | null> {
  if (!isPlausibleToken(token)) return null
  const rows = await customerQuery<{
    email: string
    first_name: string | null
    stage: number
    status: SequenceStatus
    unsubscribed: boolean | null
  }>(
    `SELECT s.email, s.first_name, s.stage, s.status, p.unsubscribed
       FROM waitlist_sequence s
       LEFT JOIN email_preferences p ON p.email = lower(s.email)
      WHERE s.unsubscribe_token = $1`,
    [token],
  )
  const r = rows[0]
  if (!r) return null
  return {
    email: r.email,
    firstName: r.first_name,
    unsubscribed: r.unsubscribed === true,
    stage: Number(r.stage),
    status: r.status,
    finalStage: DRIP_FINAL_STAGE,
  }
}

export type PreferenceSource = 'link' | 'one-click' | 'preferences' | 'ops'

/**
 * Unsubscribe the address behind a token. Writes the durable per-address preference AND
 * suppresses the sequence row immediately, so no drain tick between now and the next send
 * check can pick it up. Idempotent.
 */
export async function unsubscribeByToken(token: string, source: PreferenceSource): Promise<PreferenceState | null> {
  const state = await preferenceStateForToken(token)
  if (!state) return null
  const email = state.email.toLowerCase()
  await customerExecute(
    `INSERT INTO email_preferences (email, unsubscribed, unsubscribed_at, source, updated_at)
     VALUES ($1, TRUE, now(), $2, now())
     ON CONFLICT (email) DO UPDATE SET
       unsubscribed = TRUE,
       unsubscribed_at = COALESCE(email_preferences.unsubscribed_at, now()),
       source = EXCLUDED.source,
       updated_at = now()`,
    [email, source],
  )
  await customerExecute(
    `UPDATE waitlist_sequence
        SET status = 'suppressed', suppression_reason = 'unsubscribed', suppressed_at = now(),
            next_send_at = NULL, updated_at = now()
      WHERE unsubscribe_token = $1 AND status IN ('active', 'sending', 'failed')`,
    [token],
  )
  return { ...state, unsubscribed: true, status: state.status === 'completed' ? 'completed' : 'suppressed' }
}

/**
 * Opt back in from the preferences page. Only an `unsubscribed` suppression is reversible —
 * a hard bounce, a complaint, or an account are not the subscriber's choice to undo here.
 * Resumes at the stage they left, due immediately (the drain re-checks every rule first).
 */
export async function resubscribeByToken(token: string, source: PreferenceSource): Promise<PreferenceState | null> {
  const state = await preferenceStateForToken(token)
  if (!state) return null
  const email = state.email.toLowerCase()
  await customerExecute(
    `INSERT INTO email_preferences (email, unsubscribed, resubscribed_at, source, updated_at)
     VALUES ($1, FALSE, now(), $2, now())
     ON CONFLICT (email) DO UPDATE SET
       unsubscribed = FALSE, resubscribed_at = now(), source = EXCLUDED.source, updated_at = now()`,
    [email, source],
  )
  await customerExecute(
    `UPDATE waitlist_sequence
        SET status = CASE WHEN stage >= $2 THEN 'completed' ELSE 'active' END,
            suppression_reason = NULL, suppressed_at = NULL,
            next_send_at = CASE WHEN stage >= $2 THEN NULL ELSE now() END,
            updated_at = now()
      WHERE unsubscribe_token = $1 AND status = 'suppressed' AND suppression_reason = 'unsubscribed'`,
    [token, DRIP_FINAL_STAGE],
  )
  const after = await preferenceStateForToken(token)
  return after ?? { ...state, unsubscribed: false }
}

/**
 * Suppress every live sequence row for an address, from a provider event (bounce/complaint).
 * Returns the number of rows changed.
 */
export async function suppressSequenceByEmail(email: string, reason: SuppressionReason): Promise<number> {
  return customerExecute(
    `UPDATE waitlist_sequence
        SET status = 'suppressed', suppression_reason = $2, suppressed_at = now(),
            next_send_at = NULL, updated_at = now()
      WHERE lower(email) = $1 AND status IN ('active', 'sending', 'failed')`,
    [email.trim().toLowerCase(), reason],
  )
}
