import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { createOrResumeEnrollment, recordAcceptedDocuments } from '@/lib/enrollment/service'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Backfill versioned legal acceptances for customers who completed the LEGACY funnel.
 *
 * They accepted the three disclosures — the proof is a `LEGAL_ACCEPTED` audit row with
 * the acknowledgment flags — but that row records no document version and nothing joins
 * to it. `acceptedVersionsFor()` reads `legal_acceptances`, which only the v1 chain ever
 * wrote, so every pre-existing customer reads as having signed nothing and would be
 * blocked at activation forever, with no screen on which to re-accept.
 *
 * This translates the evidence that already exists into the versioned shape. It does NOT
 * invent consent: a user is only backfilled if they have an actual LEGAL_ACCEPTED audit
 * row, and only the flags set to true in that row are converted.
 *
 * GET  — dry run. Who would be backfilled and with what.
 * POST — apply. Idempotent: the unique index makes a re-run a no-op.
 *
 * Deliberately manual rather than a startup migration. It writes consent records on a
 * production table; that should be a decision someone makes, at a time they choose, with
 * the dry run in front of them.
 */

interface AuditRow {
  user_id: string
  metadata: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
}

/** The legacy checkbox → registry code mapping (see lib/enrollment/legal.ts). */
function codesFromAcks(meta: Record<string, unknown> | null): string[] {
  if (!meta) return []
  const codes: string[] = []
  if (meta.termsAccepted === true) codes.push('TERMS')
  if (meta.riskDisclosure === true) codes.push('RISK')
  if (meta.automatedExecution === true) codes.push('TRADING_AUTH')
  return codes
}

/** Latest LEGAL_ACCEPTED per user who has no versioned acceptance rows yet. */
async function loadCandidates(): Promise<AuditRow[]> {
  return customerQuery<AuditRow>(
    `SELECT DISTINCT ON (a.user_id) a.user_id, a.metadata, a.ip_address, a.user_agent
       FROM audit_events a
      WHERE a.event_type = 'LEGAL_ACCEPTED'
        AND NOT EXISTS (SELECT 1 FROM legal_acceptances la WHERE la.user_id = a.user_id)
      ORDER BY a.user_id, a.created_at DESC`,
  )
}

async function gate() {
  if (isPublicMode()) return null
  const ops = await getSession()
  if (!ops.userId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Operator session required.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  return null
}

export async function GET() {
  const blocked = await gate()
  if (blocked) return blocked
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Customers DB not configured.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  const candidates = await loadCandidates()
  const withCodes = candidates.map((c) => ({ user_id: c.user_id, codes: codesFromAcks(c.metadata) }))
  return NextResponse.json({
    dryRun: true,
    candidates: withCodes.length,
    // A candidate with no true flags is reported, never silently skipped — it means the
    // audit row exists but records no affirmative consent, which someone should look at.
    would_write: withCodes.filter((c) => c.codes.length > 0).length,
    no_affirmative_flags: withCodes.filter((c) => c.codes.length === 0).map((c) => c.user_id),
    sample: withCodes.slice(0, 10),
  })
}

export async function POST() {
  const blocked = await gate()
  if (blocked) return blocked
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Customers DB not configured.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  try {
    const candidates = await loadCandidates()
    let written = 0
    let skipped = 0
    for (const c of candidates) {
      const codes = codesFromAcks(c.metadata)
      if (codes.length === 0) {
        skipped++
        continue
      }
      const enrollment = await createOrResumeEnrollment(c.user_id, 'backfill')
      await recordAcceptedDocuments({
        userId: c.user_id,
        enrollmentId: enrollment.id,
        codes,
        ip: c.ip_address,
        userAgent: c.user_agent,
      })
      written++
    }
    return NextResponse.json({
      ok: true,
      users_backfilled: written,
      skipped_no_affirmative_flags: skipped,
      summary: `${written} customer(s) now have versioned acceptances.`,
    })
  } catch (e) {
    const env = redactProviderError('backfill-legal', e, 'INTERNAL', 'Backfill failed.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
