import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, sharedTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')
const SANDBOX_URL = 'https://sandbox.tradier.com/v1'

interface TestResult {
  account_id: string
  person: string
  success: boolean
  message: string
}

async function testOne(accountId: string, apiKey: string, person: string): Promise<TestResult> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)

  try {
    const res = await fetch(`${SANDBOX_URL}/user/profile`, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
      },
      signal: controller.signal,
    })
    clearTimeout(timeout)

    if (res.ok) {
      return { account_id: accountId, person, success: true, message: 'Connected' }
    }
    return { account_id: accountId, person, success: false, message: `HTTP ${res.status}` }
  } catch (err: unknown) {
    clearTimeout(timeout)
    const msg = err instanceof Error && err.name === 'AbortError'
      ? 'Timeout'
      : err instanceof Error ? err.message : 'Unknown error'
    return { account_id: accountId, person, success: false, message: msg }
  }
}

/**
 * POST /api/accounts/test-all
 * Tests all active accounts by reading real API keys from Databricks
 * and hitting Tradier sandbox /user/profile.
 */
export async function POST(_req: NextRequest) {
  try {
    // Read real (unmasked) API keys from Databricks
    const rows = await dbQuery(`
      SELECT account_id, api_key, person
      FROM ${TABLE}
      WHERE is_active = TRUE
      ORDER BY person
    `)

    // Test all accounts in parallel
    const results = await Promise.all(
      rows.map((row) => testOne(row.account_id, row.api_key, row.person)),
    )

    return NextResponse.json(results)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
