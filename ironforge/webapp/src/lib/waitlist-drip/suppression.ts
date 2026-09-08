/**
 * Send-time suppression for the waitlist drip.
 *
 * The kit: "Before every send, exclude unsubscribed addresses, hard bounces, complaints,
 * duplicates, and users who have moved into a separate activation/onboarding flow."
 *
 * Re-evaluated at EVERY send, not at enrollment — a person can unsubscribe, bounce, or
 * create an account between Email 2 and Email 3. `classifySuppression` is the pure rule
 * (unit-tested); `lookupSuppressionFacts` gathers the facts from the customers DB.
 *
 * "Moved into activation/onboarding" = a row in `users` with this email. That table is the
 * customer account — every enrollment, activation and trial hangs off users.id — so an
 * account's existence is the moment the waitlist stops being the right conversation.
 *
 * Duplicates are prevented structurally (unique index on lower(email) in waitlist_sequence)
 * and re-checked here as a belt-and-braces guard on the send log: a `sent` row for this
 * (subscriber, stage) means the email already went out.
 */

import { customerQuery } from '@/lib/customers-db'

export type SuppressionReason =
  | 'unsubscribed'
  | 'hard_bounce'
  | 'complaint'
  | 'onboarding'
  | 'duplicate'

export interface SuppressionFacts {
  unsubscribed: boolean
  hardBounced: boolean
  complained: boolean
  hasAccount: boolean
  /** A successful send already logged for the stage about to go out. */
  alreadySentThisStage: boolean
}

/** The suppression reason for these facts, or null when the send may proceed. */
export function classifySuppression(f: SuppressionFacts): SuppressionReason | null {
  if (f.unsubscribed) return 'unsubscribed'
  if (f.complained) return 'complaint'
  if (f.hardBounced) return 'hard_bounce'
  if (f.hasAccount) return 'onboarding'
  if (f.alreadySentThisStage) return 'duplicate'
  return null
}

/** True for reasons that end the sequence (vs. 'duplicate', which only skips one stage). */
export function isTerminalReason(r: SuppressionReason): boolean {
  return r !== 'duplicate'
}

/** One round trip: every fact the rule needs, for one subscriber and the stage about to send. */
export async function lookupSuppressionFacts(
  email: string,
  sequenceId: string,
  nextStage: number,
): Promise<SuppressionFacts> {
  const lower = email.trim().toLowerCase()
  const rows = await customerQuery<{
    unsubscribed: boolean
    hard_bounced: boolean
    complained: boolean
    has_account: boolean
    already_sent: boolean
  }>(
    `SELECT
       COALESCE((SELECT unsubscribed FROM email_preferences WHERE email = $1), FALSE) AS unsubscribed,
       EXISTS (SELECT 1 FROM email_events
                WHERE lower(email) = $1 AND event_type = 'email.bounced' AND bounce_type = 'Permanent') AS hard_bounced,
       EXISTS (SELECT 1 FROM email_events
                WHERE lower(email) = $1 AND event_type = 'email.complained') AS complained,
       EXISTS (SELECT 1 FROM users WHERE lower(email) = $1) AS has_account,
       EXISTS (SELECT 1 FROM waitlist_sequence_sends
                WHERE sequence_id = $2 AND stage = $3 AND status = 'sent') AS already_sent`,
    [lower, sequenceId, nextStage],
  )
  const r = rows[0]
  return {
    unsubscribed: r?.unsubscribed === true,
    hardBounced: r?.hard_bounced === true,
    complained: r?.complained === true,
    hasAccount: r?.has_account === true,
    alreadySentThisStage: r?.already_sent === true,
  }
}
