import { customerQuery, customerExecute } from '@/lib/customers-db'
import { LEGAL_DOCUMENTS, requiredDocumentsFor, staleDocumentCodes, isAutomatePlan, type AcceptedVersion } from './legal'
import { isStripeConfigured, hasUsablePaymentMethod, findLiveSubscriptionForPrice, findPriceIdByLookupKey } from '@/lib/billing/stripe'
import { COMMUNITY_PLAN } from '@/lib/billing/plans'
import type { EnrollmentState } from './states'
import { isUuid } from './ids'

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
 * The user's OPEN enrollment, if any — a read that never creates. The /enroll door
 * uses this to decide between "resume the funnel" and "this person is done, route to
 * their product" without minting a fresh draft for every returning customer.
 */
export async function getOpenEnrollment(userId: string): Promise<EnrollmentRow | null> {
  const open = await customerQuery<EnrollmentRow>(
    `SELECT id, user_id, selected_plan, status, current_step
       FROM enrollments
      WHERE user_id = $1 AND status NOT IN ('complete', 'abandoned')
      ORDER BY created_at DESC LIMIT 1`,
    [userId],
  )
  return open[0] ?? null
}

/**
 * Create or RESUME. One open enrollment per user by design — "Create/resume intent"
 * (§6) — so a customer who abandons and returns continues rather than forking a second
 * funnel whose plan and acceptances disagree with the first.
 */
export async function createOrResumeEnrollment(userId: string, source?: string): Promise<EnrollmentRow> {
  const open = await getOpenEnrollment(userId)
  if (open) return open

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
  // A malformed id would make Postgres raise on the UUID cast rather than return no
  // rows, turning a client mistake into a 500. Same answer as "not yours": null.
  if (!isUuid(id) || !isUuid(userId)) return null
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
/**
 * Write versioned acceptances for specific document CODES. Idempotent.
 *
 * Extracted so the LEGACY onboarding funnel can record the same rows as the v1 chain.
 * Before this, /onboarding/legal wrote only an `audit_events` row with three booleans —
 * no version, nothing joinable — while `acceptedVersionsFor()` reads `legal_acceptances`
 * alone. So a customer who completed the live funnel had ZERO acceptance rows, and
 * `staleDocumentCodes()` would report every required document as stale, blocking
 * activation permanently with no screen on which to re-accept.
 *
 * Two funnels are bad; two funnels that disagree about whether you have signed anything
 * is worse. They now write one record.
 */
export async function recordAcceptedDocuments(opts: {
  userId: string
  enrollmentId: string | null
  codes: string[]
  ip: string | null
  userAgent: string | null
  /**
   * The member's typed full legal name (LEGAL-AUTO-01 e-signature). Stored on each
   * acceptance row it creates. ON CONFLICT DO NOTHING means an already-present
   * acceptance never gains a signature retroactively — append-only, by design.
   */
  signatureName?: string | null
}): Promise<{ written: number; alreadyPresent: number }> {
  // SEED FIRST. The write below is INSERT ... SELECT FROM legal_documents, so an empty
  // registry table matches zero rows and inserts NOTHING — with no error, because a
  // zero-row INSERT is perfectly valid SQL.
  //
  // Not hypothetical: legal_documents was seeded only by the three /v1/enrollments/*
  // routes, none of which has ever run in production. The table was empty, so both this
  // and the backfill silently wrote nothing while reporting success.
  await ensureLegalDocumentsSeeded()

  const wanted = new Set(opts.codes)
  let written = 0
  let alreadyPresent = 0

  for (const d of LEGAL_DOCUMENTS.filter((x) => wanted.has(x.code))) {
    const rows = await customerExecute(
      `INSERT INTO legal_acceptances (user_id, enrollment_id, document_id, ip, user_agent, signature_name)
       SELECT $1, $2, id, $4, $5, $7 FROM legal_documents WHERE code = $3 AND version = $6
       ON CONFLICT (user_id, document_id) DO NOTHING`,
      [opts.userId, opts.enrollmentId, d.code, opts.ip, opts.userAgent, d.version, opts.signatureName ?? null],
    )
    if (rows > 0) {
      written++
      continue
    }
    // Zero rows means EITHER already accepted (fine) OR the document is missing from the
    // registry (not fine). Only one of those is a silent failure, so distinguish them.
    const present = await customerQuery<{ n: string }>(
      `SELECT count(*)::text AS n
         FROM legal_acceptances la JOIN legal_documents d ON d.id = la.document_id
        WHERE la.user_id = $1 AND d.code = $2 AND d.version = $3`,
      [opts.userId, d.code, d.version],
    )
    if (Number(present[0]?.n ?? 0) > 0) alreadyPresent++
    else throw new Error(`legal document ${d.code}@${d.version} is not in legal_documents`)
  }

  return { written, alreadyPresent }
}

export async function recordAcceptances(opts: {
  userId: string
  enrollmentId: string
  plan: string | null
  submittedCodes: string[]
  ip: string | null
  userAgent: string | null
  signatureName?: string | null
}): Promise<{ ok: true } | { ok: false; missing: string[] }> {
  const required = requiredDocumentsFor(opts.plan)
  const submitted = new Set(opts.submittedCodes)
  const missing = required.filter((d) => !submitted.has(d.code)).map((d) => d.code)
  if (missing.length > 0) return { ok: false, missing }

  await recordAcceptedDocuments({
    userId: opts.userId,
    enrollmentId: opts.enrollmentId,
    codes: required.map((d) => d.code),
    ip: opts.ip,
    userAgent: opts.userAgent,
    signatureName: opts.signatureName ?? null,
  })
  await customerExecute(
    `UPDATE enrollments SET status = 'billing_pending', current_step = 'billing', updated_at = now()
      WHERE id = $1 AND user_id = $2`,
    [opts.enrollmentId, opts.userId],
  )
  return { ok: true }
}

/**
 * Advance a billing_pending enrollment whose billing has ACTUALLY completed.
 *
 * The Stripe webhook is the authority for this transition, but the customer returns
 * from hosted Checkout before the webhook necessarily lands. Called on resume
 * (POST /v1/enrollments), this re-derives the answer from Stripe/subscription state so
 * the funnel is immune to webhook lag: automate advances when a payment method exists
 * on the Stripe customer; community completes when the subscription row is live.
 * Anything not provably done stays billing_pending — fail-closed, same as the webhook.
 */
export async function advanceBillingIfComplete(row: EnrollmentRow): Promise<EnrollmentRow> {
  if (row.status !== 'billing_pending') return row

  if (isAutomatePlan(row.selected_plan)) {
    if (!isStripeConfigured()) return row
    const user = (await customerQuery<{ stripe_customer_id: string | null }>(
      `SELECT stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
      [row.user_id],
    ))[0]
    if (!user?.stripe_customer_id) return row
    if (!(await hasUsablePaymentMethod(user.stripe_customer_id))) return row
    await customerExecute(
      `UPDATE enrollments SET status = 'setup_required', current_step = 'setup', updated_at = now()
        WHERE id = $1 AND user_id = $2 AND status = 'billing_pending'`,
      [row.id, row.user_id],
    )
    return { ...row, status: 'setup_required', current_step: 'setup' }
  }

  if (row.selected_plan === 'community') {
    let sub = (await customerQuery<{ status: string }>(
      `SELECT status FROM customer_bot_subscriptions WHERE user_id = $1 AND bot = 'community' LIMIT 1`,
      [row.user_id],
    ))[0]

    // Webhook-lag immunity (UX audit B2): the local row is written by the Stripe
    // webhook, so a customer bouncing back from a SUCCESSFUL checkout could beat it
    // here and be told to pay again. When the row is missing, ask Stripe directly —
    // same discipline as the automate branch above — and write the row ourselves
    // (the webhook later reconciles the same values idempotently).
    if (!sub && isStripeConfigured()) {
      try {
        const user = (await customerQuery<{ stripe_customer_id: string | null }>(
          `SELECT stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
          [row.user_id],
        ))[0]
        const priceId = user?.stripe_customer_id
          ? await findPriceIdByLookupKey(COMMUNITY_PLAN.lookupKey)
          : null
        const live = user?.stripe_customer_id && priceId
          ? await findLiveSubscriptionForPrice(user.stripe_customer_id, priceId)
          : null
        if (live) {
          await customerExecute(
            `INSERT INTO customer_bot_subscriptions
               (user_id, bot, status, stripe_subscription_id, price_lookup_key, current_period_end, updated_at)
             VALUES ($1, 'community', $2, $3, $4, $5, now())
             ON CONFLICT (user_id, bot) DO UPDATE SET
               status = EXCLUDED.status,
               stripe_subscription_id = EXCLUDED.stripe_subscription_id,
               price_lookup_key = EXCLUDED.price_lookup_key,
               current_period_end = EXCLUDED.current_period_end,
               updated_at = now()`,
            [row.user_id, live.status, live.id, COMMUNITY_PLAN.lookupKey,
             live.current_period_end ? new Date(live.current_period_end * 1000).toISOString() : null],
          )
          sub = { status: live.status }
        }
      } catch (e) {
        // Fail closed: stay billing_pending; the webhook remains the backstop.
        console.error('[enrollment] community Stripe reconciliation failed:', e)
      }
    }

    if (sub && ['trialing', 'active', 'past_due'].includes(sub.status)) {
      await customerExecute(
        `UPDATE enrollments
            SET status = 'complete', current_step = 'done', completed_at = now(), updated_at = now()
          WHERE id = $1 AND user_id = $2 AND status = 'billing_pending'`,
        [row.id, row.user_id],
      )
      return { ...row, status: 'complete', current_step: 'done' }
    }
  }

  return row
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
