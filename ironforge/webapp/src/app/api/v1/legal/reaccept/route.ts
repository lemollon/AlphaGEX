import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { recordAcceptedDocuments } from '@/lib/enrollment/service'
import { signatureMatchesName } from '@/lib/enrollment/legal'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

/**
 * POST /api/v1/legal/reaccept — records an ALREADY-ACTIVE customer's
 * acceptance of a document whose version changed since they last signed,
 * through the SAME append-only path enrollment uses (recordAcceptedDocuments
 * — also shared with the legacy /onboarding/legal funnel). enrollmentId is
 * null here on purpose: this acceptance belongs to no enrollment row, it
 * belongs to the customer directly.
 */
export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  if (!identity?.customerId) {
    return NextResponse.json({ ok: false, error: 'Please sign in to continue.' }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Not available right now.' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as { codes?: unknown; signature_name?: unknown }
  const codes = Array.isArray(body.codes) ? body.codes.filter((c): c is string => typeof c === 'string') : []
  const signatureName = typeof body.signature_name === 'string' ? body.signature_name.trim() : ''

  if (codes.length === 0) {
    return NextResponse.json({ ok: false, error: 'No documents to accept.' }, { status: 400 })
  }
  if (signatureName.length < 2 || !/\s/.test(signatureName)) {
    return NextResponse.json(
      { ok: false, error: 'Type your first and last name.', field: 'signature_name' },
      { status: 422 },
    )
  }

  const user = (
    await customerQuery<{ first_name: string | null; last_name: string | null }>(
      `SELECT first_name, last_name FROM users WHERE id = $1 LIMIT 1`,
      [identity.customerId],
    )
  )[0]
  const fullName = user?.first_name && user?.last_name ? `${user.first_name} ${user.last_name}`.trim() : ''
  if (fullName && !signatureMatchesName(signatureName, user!.first_name!, user!.last_name!)) {
    return NextResponse.json(
      { ok: false, error: `Type your name exactly as ${fullName}.`, field: 'signature_name' },
      { status: 422 },
    )
  }

  try {
    const result = await recordAcceptedDocuments({
      userId: identity.customerId,
      enrollmentId: null,
      codes,
      ip: clientIp(req),
      userAgent: req.headers.get('user-agent'),
      signatureName,
    })
    return NextResponse.json({ ok: true, ...result })
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : 'Could not record your acceptance.' },
      { status: 500 },
    )
  }
}
