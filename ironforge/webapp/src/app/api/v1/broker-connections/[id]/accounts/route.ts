import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { evaluateAccountEligibility, maskAccountNumber } from '@/lib/enrollment/eligibility'
import { encryptSecret } from '@/lib/crypto/secret-box'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/v1/broker-connections/{id}/accounts — refresh eligible accounts (§6).
 *
 * "Masked response only." The external account reference is stored ENCRYPTED and the
 * display mask separately (§3 BROKER-02, §5); NOTHING in this response contains a full
 * account number, and none is logged (§8 "Redact ... account identifiers ... from
 * logs/APM").
 *
 * Ineligible accounts are RETURNED, not hidden — with their reason. Hiding them makes
 * the screen look broken to a customer who can see the account in their broker; showing
 * it disabled with "Options approval level 3 is required" tells them what to do.
 *
 * Reads what the connection last synced. Live re-fetch happens on the broker callback,
 * and eligibility is re-checked again immediately before activation (§4) because
 * buying power moves.
 */
export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getCustomerSession()
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Brokerage setup is temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  try {
    // Ownership: the connection must belong to THIS customer (§8).
    const conn = await customerQuery<{ id: string }>(
      `SELECT id FROM brokerage_connections WHERE id = $1 AND user_id = $2 LIMIT 1`,
      [params.id, session.customerId],
    )
    if (!conn[0]) {
      const e = errorEnvelope('FORBIDDEN', 'That brokerage connection is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    const rows = await customerQuery<{
      id: string; display_mask: string; account_type: string | null
      options_level: number | null; eligibility: string; ineligible_reason: string | null
    }>(
      `SELECT id, display_mask, account_type, options_level, eligibility, ineligible_reason
         FROM broker_accounts WHERE connection_id = $1 ORDER BY created_at ASC`,
      [params.id],
    )

    const accounts = rows.map((r) => ({
      id: r.id,
      display_mask: r.display_mask,
      account_type: r.account_type,
      options_level: r.options_level,
      eligible: r.eligibility === 'eligible',
      ineligible_reason: r.ineligible_reason,
    }))

    return NextResponse.json(
      {
        accounts,
        // §11: "No eligible accounts → explain requirements; allow different broker".
        has_eligible: accounts.some((a) => a.eligible),
      },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  } catch (e) {
    const env = redactProviderError('v1/broker-accounts', e, 'INTERNAL', 'Could not load your accounts. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}

/**
 * POST — record accounts returned by the authenticated broker API, with eligibility.
 * Called by the OAuth callback. Encrypts the reference, stores the mask separately.
 */
export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getCustomerSession()
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  try {
    const conn = await customerQuery<{ id: string }>(
      `SELECT id FROM brokerage_connections WHERE id = $1 AND user_id = $2 LIMIT 1`,
      [params.id, session.customerId],
    )
    if (!conn[0]) {
      const e = errorEnvelope('FORBIDDEN', 'That brokerage connection is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    const body = (await req.json().catch(() => ({}))) as { accounts?: unknown }
    const list = Array.isArray(body.accounts) ? body.accounts : []

    for (const raw of list) {
      const a = raw as Record<string, unknown>
      const externalRef = String(a.external_ref ?? '')
      if (!externalRef) continue
      const verdict = evaluateAccountEligibility({
        externalRef,
        accountType: a.account_type as string | null,
        optionsLevel: typeof a.options_level === 'number' ? a.options_level : null,
        status: a.status as string | null,
        buyingPower: typeof a.buying_power === 'number' ? a.buying_power : null,
        brokerBlocked: a.broker_blocked === true,
      })
      await customerExecute(
        `INSERT INTO broker_accounts
           (connection_id, external_account_ref_ciphertext, display_mask, account_type,
            options_level, eligibility, ineligible_reason, buying_power_cents, checked_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())`,
        [
          params.id,
          encryptSecret(externalRef),
          maskAccountNumber(externalRef),
          (a.account_type as string) ?? null,
          typeof a.options_level === 'number' ? a.options_level : null,
          verdict.eligible ? 'eligible' : 'ineligible',
          verdict.reason ?? null,
          typeof a.buying_power === 'number' ? Math.round(a.buying_power * 100) : null,
        ],
      )
    }
    return NextResponse.json({ ok: true, stored: list.length })
  } catch (e) {
    const env = redactProviderError('v1/broker-accounts', e, 'INTERNAL', 'Could not save your accounts. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
