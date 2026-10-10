/**
 * Waitlist drip autostart — the sequence starts from configuration, not from an operator
 * clicking POST /api/ops/waitlist/drip {action:"backfill"}.
 *
 *   WAITLIST_DRIP_START_DATE      YYYY-MM-DD (Chicago). When set and valid, every waitlist
 *                                 submission with no sequence row is enrolled with Email 1 due
 *                                 at the send hour on that date (deferred to the next business
 *                                 day by the scheduler). Unset or invalid = nothing happens.
 *   WAITLIST_DRIP_FOUNDER_EMAILS  Comma-separated. Default leron@ + logan@ironforge.trade. Each
 *                                 founder gets a sequence row on the same schedule so they
 *                                 receive every email at the same time as the list.
 *
 * Runs once at scanner boot and again on every drain tick (scanner.ts). Idempotent and cheap:
 * the backfill is ON CONFLICT DO NOTHING on lower(email), the founder upsert only ever inserts
 * a missing row or lifts an 'onboarding' suppression, so the second run changes nothing and
 * the tick's cost is one NOT EXISTS query over a small table plus two founder statements.
 *
 * Founders are exempt from ONE suppression rule — "has a customer account" (they do; that is
 * the point) — at enrollment here and at send time in drain.ts. Unsubscribe, complaint and
 * hard-bounce rules still apply to them exactly as to everyone else. Founders are never
 * written to waitlist_submissions or mirrored to Attio (drain.ts skips the CRM event).
 */

import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { firstSendAt, isDateKey, type DateKey } from './schedule'
import { backfillWaitlistSequence, newUnsubscribeToken, type BackfillResult } from './sequence'
import { classifySuppression, type SuppressionReason } from './suppression'

export const DEFAULT_FOUNDER_EMAILS: readonly string[] = ['leron@ironforge.trade', 'logan@ironforge.trade']

export interface AutostartConfig {
  enabled: boolean
  /** The validated start date, or null when unset/invalid. */
  startDate: DateKey | null
  /** Lower-cased, de-duplicated founder addresses (always populated — the default applies). */
  founders: string[]
  /** Why `enabled` is false when WAITLIST_DRIP_START_DATE is present but unusable. */
  invalidReason?: string
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Comma-separated addresses → lower-cased, trimmed, de-duplicated, invalid entries dropped. */
export function parseFounderEmails(raw: string | undefined | null): string[] {
  const source = raw === undefined || raw === null || raw.trim() === '' ? DEFAULT_FOUNDER_EMAILS.join(',') : raw
  const out: string[] = []
  for (const part of source.split(',')) {
    const email = part.trim().toLowerCase()
    if (!email || !EMAIL_RE.test(email) || out.includes(email)) continue
    out.push(email)
  }
  return out
}

/** "leron@ironforge.trade" → "Leron"; "mary.ann@x" → "Mary.ann". Personalisation only. */
export function founderFirstName(email: string): string {
  const local = email.split('@')[0]?.trim() ?? ''
  if (!local) return ''
  return local.charAt(0).toUpperCase() + local.slice(1)
}

export function autostartConfig(env: Record<string, string | undefined> = process.env): AutostartConfig {
  const founders = parseFounderEmails(env.WAITLIST_DRIP_FOUNDER_EMAILS)
  const raw = env.WAITLIST_DRIP_START_DATE
  if (raw === undefined || raw.trim() === '') return { enabled: false, startDate: null, founders }
  const trimmed = raw.trim()
  if (!isDateKey(trimmed)) {
    return {
      enabled: false,
      startDate: null,
      founders,
      invalidReason: `WAITLIST_DRIP_START_DATE="${trimmed}" is not a valid YYYY-MM-DD date — autostart disabled`,
    }
  }
  return { enabled: true, startDate: trimmed, founders }
}

export function isFounderEmail(email: string, config: Pick<AutostartConfig, 'founders'> = autostartConfig()): boolean {
  return config.founders.includes(email.trim().toLowerCase())
}

/** The facts the founder enrollment needs. `hasAccount` is looked up so the log can say so, then ignored. */
export interface FounderFacts {
  unsubscribed: boolean
  complained: boolean
  hardBounced: boolean
  hasAccount: boolean
}

export async function lookupFounderFacts(email: string): Promise<FounderFacts> {
  const lower = email.trim().toLowerCase()
  const rows = await customerQuery<{ unsubscribed: boolean; complained: boolean; hard_bounced: boolean; has_account: boolean }>(
    `SELECT
       COALESCE((SELECT unsubscribed FROM email_preferences WHERE email = $1), FALSE) AS unsubscribed,
       EXISTS (SELECT 1 FROM email_events WHERE lower(email) = $1 AND event_type = 'email.complained') AS complained,
       EXISTS (SELECT 1 FROM email_events
                WHERE lower(email) = $1 AND event_type = 'email.bounced' AND bounce_type = 'Permanent') AS hard_bounced,
       EXISTS (SELECT 1 FROM users WHERE lower(email) = $1) AS has_account`,
    [lower],
  )
  const r = rows[0]
  return {
    unsubscribed: r?.unsubscribed === true,
    complained: r?.complained === true,
    hardBounced: r?.hard_bounced === true,
    hasAccount: r?.has_account === true,
  }
}

/** The founder's enrollment status: every rule except the account rule. Pure; unit-tested. */
export function founderSuppressionReason(f: FounderFacts): SuppressionReason | null {
  return classifySuppression({ ...f, hasAccount: false, alreadySentThisStage: false })
}

/** Injectable seams so the orchestration is testable without Postgres. */
export interface AutostartDeps {
  config: () => AutostartConfig
  dbConfigured: () => boolean
  backfill: (input: { firstSendDate: DateKey; dryRun: false }) => Promise<BackfillResult>
  founderFacts: (email: string) => Promise<FounderFacts>
  query: <T = Record<string, unknown>>(sql: string, params?: unknown[]) => Promise<T[]>
  log: (line: string) => void
}

const defaultDeps: AutostartDeps = {
  config: autostartConfig,
  dbConfigured: isCustomersDbConfigured,
  backfill: backfillWaitlistSequence,
  founderFacts: lookupFounderFacts,
  query: customerQuery,
  log: (line) => console.log(line),
}

export interface FounderEnrollOutcome {
  email: string
  /** 'inserted' = new row; 'reactivated' = an 'onboarding' suppression lifted; 'exists' = untouched. */
  outcome: 'inserted' | 'reactivated' | 'exists'
  /** Non-null when the row was inserted as suppressed (unsubscribed / complaint / hard bounce). */
  reason: SuppressionReason | null
}

export interface AutostartResult {
  enabled: boolean
  skipped?: boolean
  startDate: DateKey | null
  /** Waitlist submissions enrolled by the backfill this run (0 on every run after the first). */
  enrolled: number
  /** Backfill rows inserted directly as suppressed, by reason. */
  suppressed: Record<string, number>
  founders: FounderEnrollOutcome[]
  error?: string
}

/**
 * Enroll one founder. INSERT a missing row (active, or suppressed with its reason when the
 * address is unsubscribed / complained / bounced); when a row already exists, the only change
 * ever made is lifting an 'onboarding' suppression — a founder who was on the waitlist form
 * and got backfilled as "has an account" is reactivated on the same schedule. Any other
 * existing row (active, sending, completed, unsubscribed…) is left exactly as it is.
 */
async function enrollFounder(email: string, at: Date, deps: AutostartDeps): Promise<FounderEnrollOutcome> {
  const facts = await deps.founderFacts(email)
  const reason = founderSuppressionReason(facts)
  const rows = await deps.query<{ inserted: boolean }>(
    `INSERT INTO waitlist_sequence
       (email, first_name, submission_id, stage, status, next_send_at, suppression_reason, suppressed_at, unsubscribe_token)
     VALUES ($1, $2, NULL, 0, $3, $4, $5, CASE WHEN $5::text IS NULL THEN NULL ELSE now() END, $6)
     ON CONFLICT (lower(email)) DO UPDATE SET
       status = 'active', suppression_reason = NULL, suppressed_at = NULL,
       next_send_at = COALESCE(waitlist_sequence.next_send_at, EXCLUDED.next_send_at),
       first_name = COALESCE(NULLIF(waitlist_sequence.first_name, ''), EXCLUDED.first_name),
       updated_at = now()
     WHERE waitlist_sequence.status = 'suppressed'
       AND waitlist_sequence.suppression_reason = 'onboarding'
       AND EXCLUDED.suppression_reason IS NULL
     RETURNING (xmax = 0) AS inserted`,
    [
      email,
      founderFirstName(email) || null,
      reason ? 'suppressed' : 'active',
      reason ? null : at.toISOString(),
      reason,
      newUnsubscribeToken(),
    ],
  )
  const r = rows[0]
  if (!r) return { email, outcome: 'exists', reason: null }
  return { email, outcome: r.inserted ? 'inserted' : 'reactivated', reason }
}

/**
 * The autostart pass: founders first (so the backfill's NOT EXISTS skips them), then the
 * existing backfill for real, on the configured date. Never throws — a failure here must
 * not take the drain tick or the scanner boot down with it.
 */
export async function autoEnrollWaitlistDrip(deps: AutostartDeps = defaultDeps): Promise<AutostartResult> {
  const cfg = deps.config()
  const out: AutostartResult = { enabled: cfg.enabled, startDate: cfg.startDate, enrolled: 0, suppressed: {}, founders: [] }
  if (!cfg.enabled || !cfg.startDate) return { ...out, skipped: true }
  if (!deps.dbConfigured()) return { ...out, skipped: true }

  const at = firstSendAt(cfg.startDate)
  try {
    for (const email of cfg.founders) {
      out.founders.push(await enrollFounder(email, at, deps))
    }
    const r = await deps.backfill({ firstSendDate: cfg.startDate, dryRun: false })
    out.enrolled = r.enrolled
    out.suppressed = r.suppressed

    const changedFounders = out.founders.filter((f) => f.outcome !== 'exists')
    const suppressedTotal = Object.values(out.suppressed).reduce((a, b) => a + b, 0)
    if (out.enrolled > 0 || suppressedTotal > 0 || changedFounders.length > 0) {
      const founderNote = changedFounders.map((f) => `${f.email}:${f.outcome}${f.reason ? `(${f.reason})` : ''}`).join(',')
      deps.log(
        `[waitlist-drip] autostart: enrolled=${out.enrolled} suppressed=${suppressedTotal} ` +
          `firstSend=${at.toISOString()} startDate=${cfg.startDate}` +
          (founderNote ? ` founders=${founderNote}` : ''),
      )
    }
  } catch (e) {
    out.error = e instanceof Error ? e.message : String(e)
    console.error(`[waitlist-drip] autostart failed (non-fatal): ${out.error}`)
  }
  return out
}
