import { NextRequest, NextResponse } from 'next/server'
import { query, t } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

const TABLE = t('ironforge_sandbox_accounts')
const SANDBOX_URL = 'https://sandbox.tradier.com/v1'

/**
 * POST /api/accounts/[accountId]/test
 * Tests a sandbox API key by calling Tradier sandbox profile endpoint.
 */
export async function POST(
  _req: NextRequest,
  { params }: { params: { accountId: string } },
) {
  const accountId = params.accountId
  if (!accountId) {
    return NextResponse.json({ error: 'Missing accountId' }, { status: 400 })
  }

  try {
    // Fetch the API key from the database
    const rows = await query(
      `SELECT api_key FROM ${TABLE}
       WHERE account_id = '${accountId.replace(/'/g, "''")}'
       LIMIT 1`,
    )
    if (rows.length === 0) {
      return NextResponse.json({ valid: false, message: 'Account not found' }, { status: 404 })
    }

    const apiKey = (rows[0] as any).api_key
    if (!apiKey) {
      return NextResponse.json({ valid: false, message: 'No API key stored' })
    }

    // Test against Tradier sandbox
    const res = await fetch(`${SANDBOX_URL}/user/profile`, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
      },
      cache: 'no-store',
    })

    if (!res.ok) {
      return NextResponse.json({
        valid: false,
        message: `Tradier returned ${res.status}: ${res.statusText}`,
      })
    }

    const data = await res.json()
    const profile = data.profile
    if (!profile) {
      return NextResponse.json({ valid: false, message: 'No profile returned' })
    }

    let account = profile.account
    if (Array.isArray(account)) account = account[0]
    const acctNumber = account?.account_number || 'unknown'

    return NextResponse.json({
      valid: true,
      message: `Connected — account ${acctNumber}`,
      account_number: acctNumber,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ valid: false, message }, { status: 500 })
  }
}
