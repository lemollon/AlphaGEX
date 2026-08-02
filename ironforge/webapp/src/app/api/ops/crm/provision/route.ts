import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { hasValidServiceToken } from '@/lib/auth/session'
import { isAttioConfigured } from '@/lib/crm/client'
import { provisionCrmSchema } from '@/lib/crm/provision'

/**
 * Provision the Attio CRM schema from the data dictionary.
 *
 * GET  — drift report. Read-only: lists every object, attribute, option, list and seed company
 *        that is missing from the workspace. ALWAYS run this before POST.
 * POST — apply. Creates what is missing. Idempotent; never deletes, renames, or archives.
 *
 * SAFETY — this writes schema to a LIVE workspace holding real customer records:
 *   - Additive only. There is no delete path here, by design (see provision.ts).
 *   - Nothing in the request body can change what gets created — the target is always
 *     src/lib/crm/schema.ts. There are no parameters other than the dry-run/apply verb.
 *   - Operator session OR service token, and no public-mode bypass. ironforge-legacy runs
 *     fully open; a schema write must not be reachable there.
 *   - An api_slug applied by mistake is effectively permanent (renaming a slug breaks every
 *     event mapper that writes to it), which is exactly why GET exists.
 *
 * Saved views are NOT provisioned — Attio has no create-view API. The response's
 * manualFollowUps carries that reminder.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

async function gate(req: NextRequest): Promise<NextResponse | null> {
  const ops = await getSession()
  const viaToken = hasValidServiceToken(req.headers.get('x-ironforge-service'))
  if (!ops.userId && !viaToken) {
    return NextResponse.json(
      { ok: false, error: 'Operator session or service token required.' },
      { status: 401 },
    )
  }
  if (!isAttioConfigured()) {
    return NextResponse.json(
      {
        ok: false,
        error:
          'ATTIO_API_KEY is not set. Provisioning also needs a key with object_configuration ' +
          'read-write scope — the key used for waitlist record writes is not sufficient.',
      },
      { status: 503 },
    )
  }
  return null
}

export async function GET(req: NextRequest) {
  const blocked = await gate(req)
  if (blocked) return blocked

  const report = await provisionCrmSchema(true)
  return NextResponse.json({ ok: true, ...report })
}

export async function POST(req: NextRequest) {
  const blocked = await gate(req)
  if (blocked) return blocked

  const report = await provisionCrmSchema(false)
  // Partial failures are real and worth a non-200 so an operator script notices, but the report
  // still comes back in full so they can see exactly what landed and what didn't.
  const status = report.errors > 0 ? 207 : 200
  return NextResponse.json({ ok: report.errors === 0, ...report }, { status })
}
