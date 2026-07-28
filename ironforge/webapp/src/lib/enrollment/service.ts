import { customerQuery, customerExecute } from '@/lib/customers-db'
import { LEGAL_DOCUMENTS, requiredDocumentsFor, staleDocumentCodes, type AcceptedVersion } from './legal'
import type { EnrollmentState } from './states'

/**
 * Enrollment service (Enrollment spec §3, §6).
 *
 * The enrollment is a SERVER-OWNED, RESUMABLE record. Before this the funnel's position
 * was a single `users.onboarding_step` string, which cannot say which plan was chosen,
 * cannot be resumed from an email deep link with intent intact (§3 DONE-01), and cannot
 * distinguish "abandoned" from "still deciding".
 *
 * Every function here takes the userId and scopes its query by it. That is §8's
 * "Privilege escalation → Server-side ownership checks on every enrollment/account/
 * config ID" — an enrollment id in a URL must never be enough to read or write it.
 */

export interface EnrollmentRow {
  id: string
  user_id: string
  selected_plan: string | null
  status: EnrollmentState
  current_step: string | null
}

/** Idempotent seed of the active document versions. Safe to call on every request. */
export async function ensureLegalDocumentsSeeded(): Promise<void> {
  for (const d of LEGAL_DOCUMENTS) {
    await customerExecute(
      `INSERT INTO legal_documents (code, plan_scope, version, content_uri, active)
       VALUES ($1, $2, $3, $4, TRUE)
       ON CONFLICT (code, version) DO UPDATE SET plan_scope = EXCLUDED.plan_scope,
                                                content_uri = EXCLUDED.content_uri,
                                                active = TRUE`,
      [d.code, d.scope, d.version, d.contentUri],
    )
  }
}

/**
 * Create or RESUME. One open enrollment per user by design — "Create/resume intent"
 * (§6) — so a customer who abandons and returns continues rather than forking a second
 * funnel whose plan and acceptances disagree with the first.
 */
export async function createOrResumeEnrollment(userId: string, source?: string): Promise<EnrollmentRow> {
  const open = await customerQuery<EnrollmentRow>(
    `SELECT id, user_id, selected_plan, status, current_step
       FROM enrollments
      WHERE user_id = $1 AND status NOT IN ('complete', 'abandoned')
      ORDER BY created_at DESC LIMIT 1`,
    [userId],
  )
  if (open[0]) return open[0]

  const created = await customerQuery<EnrollmentRow>(
    `INSERT INTO enrollments (user_id, status, current_step, source)
     VALUES ($1, 'draft', 'plan', $2)
     RETURNING id, user_id, selected_plan, status, current_step`,
    [userId, source ?? null],
  )
  return created[0]
}

/** Ownership-scoped read. Returns null when the id is not this user's — never 403-by-existence. */
export async function getEnrollmentForUser(id: string, userId: string): Promise<EnrollmentRow | null> {
  const rows = await customerQuery<EnrollmentRow>(
    `SELECT id, user_id, selected_plan, status, current_step
       FROM enrollments WHERE id = $1 AND user_id = $2 LIMIT 1`,
    [id, userId],
  )
  return rows[0] ?? null
}

/**
 * Choose a plan. "Recomputes legal requirements" (§6) — which happens implicitly
 * because requiredDocumentsFor() is derived from the plan on every read, never cached
 * onto the enrollment. Changing Community → Automate therefore cannot leave a customer
 * holding a stale "you're done with legal" flag.
 */
export async function setEnrollmentPlan(id: string, userId: string, plan: string): Promise<void> {
  await customerExecute(
    `UPDATE enrollments
        SET selected_plan = $3, status = 'legal_pending', current_step = 'legal', updated_at = now()
      WHERE id = $1 AND user_id = $2`,
    [id, userId, plan],
  )
}

/** Versions this user has ALREADY accepted, for staleness comparison. */
export async function acceptedVersionsFor(userId: string): Promise<AcceptedVersion[]> {
  const rows = await customerQuery<{ code: string; version: string }>(
    `SELECT d.code, d.version
       FROM legal_acceptances a
       JOIN legal_documents d ON d.id = a.document_id
      WHERE a.user_id = $1`,
    [userId],
  )
  return rows
}

export interface LegalRequirement {
  code: string
  title: string
  version: string
  contentUri: string
  accepted: boolean
}

/**
 * What this enrollment still needs. Computed fresh every call — "No stale cached
 * versions" (§6).
 */
export async function legalRequirementsFor(
  plan: string | null,
  userId: string,
): Promise<{ documents: LegalRequirement[]; outstanding: string[] }> {
  const accepted = await acceptedVersionsFor(userId)
  const have = new Set(accepted.map((a) => `${a.code}@${a.version}`))
  const documents = requiredDocumentsFor(plan).map((d) => ({
    code: d.code,
    title: d.title,
    version: d.version,
    contentUri: d.contentUri,
    accepted: have.has(`${d.code}@${d.version}`),
  }))
  return { documents, outstanding: staleDocumentCodes(plan, accepted) }
}

/**
 * Record acceptances ATOMICALLY — "Atomic all-required validation" (§6).
 *
 * Either every required document is present in this submission, or NOTHING is written.
 * A partial write would leave a customer looking accepted-but-not-really, which is the
 * worst possible state for a consent record to be in: it reads as consent in the audit
 * and blocks nothing at activation.
 *
 * Append-only: acceptances are inserted, never updated, so the history of what was
 * agreed and when survives every later version bump (§5).
 */
export async function recordAcceptances(opts: {
  userId: string
  enrollmentId: string
  plan: string | null
  submittedCodes: string[]
  ip: string | null
  userAgent: string | null
}): Promise<{ ok: true } | { ok: false; missing: string[] }> {
  const required = requiredDocumentsFor(opts.plan)
  const submitted = new Set(opts.submittedCodes)
  const missing = required.filter((d) => !submitted.has(d.code)).map((d) => d.code)
  if (missing.length > 0) return { ok: false, missing }

  for (const d of required) {
    await customerExecute(
      `INSERT INTO legal_acceptances (user_id, enrollment_id, document_id, ip, user_agent)
       SELECT $1, $2, id, $4, $5 FROM legal_documents WHERE code = $3 AND version = $6`,
      [opts.userId, opts.enrollmentId, d.code, opts.ip, opts.userAgent, d.version],
    )
  }
  await customerExecute(
    `UPDATE enrollments SET status = 'billing_pending', current_step = 'billing', updated_at = now()
      WHERE id = $1 AND user_id = $2`,
    [opts.enrollmentId, opts.userId],
  )
  return { ok: true }
}

/**
 * The next step a resumable enrollment should land on. Kept here rather than in the
 * client so a deep link from an email cannot disagree with the server (§3 DONE-01).
 */
export function nextStepFor(row: Pick<EnrollmentRow, 'status' | 'selected_plan'>): string {
  switch (row.status) {
    case 'draft': return 'plan'
    case 'legal_pending': return 'legal'
    case 'billing_pending': return 'billing'
    // Community completes at billing; Automate has setup left to do.
    case 'setup_required': return 'setup'
    case 'complete': return 'done'
    default: return 'plan'
  }
}
