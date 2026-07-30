import { NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/brokerage/connections — what this customer has actually linked.
 *
 * There was no way to ASK this. `/onboarding/brokerage` only ever fetched the list of
 * brokerages you could connect to, never the ones you already had, which is why it
 * greeted a connected customer with an empty "Connect your brokerage" form. Disconnect
 * existed (DELETE /api/brokerage/connection) but nothing could enumerate what to
 * disconnect.
 *
 * Reads local rows only — no provider round-trip — so the settings page renders at the
 * speed of a query and cannot fail because a broker's API is slow.
 *
 * Account numbers never leave the encrypted column; only `display_mask` is returned.
 */

interface ConnectionRow {
  id: string
  provider: string
  status: string
  created_at: string
  last_synced_at: string | null
}

interface AccountRow {
  id: string
  connection_id: string
  display_mask: string | null
  eligibility: string | null
  ineligible_reason: string | null
  buying_power_cents: string | null
}

export async function GET() {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, connections: [], configured: false })
  }

  try {
    const conns = await customerQuery<ConnectionRow>(
      `SELECT id, provider, status,
              to_char(created_at, 'YYYY-MM-DD') AS created_at,
              to_char(last_synced_at, 'YYYY-MM-DD"T"HH24:MI:SSZ') AS last_synced_at
         FROM brokerage_connections
        WHERE user_id = $1 AND status <> 'removed'
        ORDER BY created_at DESC`,
      [session.customerId],
    )

    // Ownership through the connection join, never the account id alone.
    const accounts = conns.length
      ? await customerQuery<AccountRow>(
          `SELECT ba.id, ba.connection_id, ba.display_mask, ba.eligibility, ba.ineligible_reason,
                  ba.buying_power_cents
             FROM broker_accounts ba
             JOIN brokerage_connections bc ON bc.id = ba.connection_id
            WHERE bc.user_id = $1 AND bc.status <> 'removed'
            ORDER BY ba.created_at`,
          [session.customerId],
        )
      : []

    return NextResponse.json({
      ok: true,
      configured: true,
      connections: conns.map((c) => ({
        id: c.id,
        provider: c.provider,
        status: c.status,
        connected_on: c.created_at,
        last_synced_at: c.last_synced_at,
        accounts: accounts
          .filter((a) => a.connection_id === c.id)
          .map((a) => ({
            // broker_accounts.id — what PUT /v1/enrollments/{id}/broker-account selects
            // by (ownership still re-checked server-side through the connection join).
            id: a.id,
            mask: a.display_mask,
            eligibility: a.eligibility,
            ineligible_reason: a.ineligible_reason,
            buying_power_cents: a.buying_power_cents == null ? null : Number(a.buying_power_cents),
          })),
      })),
    })
  } catch (e) {
    console.error('[brokerage/connections] failed:', e)
    return NextResponse.json({ ok: false, error: 'Could not load your connections.' }, { status: 500 })
  }
}
