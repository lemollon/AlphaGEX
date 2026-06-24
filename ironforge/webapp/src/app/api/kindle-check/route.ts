/**
 * GET /api/kindle-check
 *
 * Read-only verification that KINDLE's live Tradier credentials are wired and
 * the account is funded. Reads TRADIER_KINDLE_API_KEY + TRADIER_KINDLE_ACCOUNT_ID
 * from the server environment (the only place they live — never the DB), calls
 * Tradier production /balances, and returns the equity + option buying power.
 *
 * Places NO orders and writes NO rows. The account id is masked in the response.
 * This is the in-system proof that the deployed app can read the KINDLE env creds
 * and reach the real-money account — a building block of the stage-2 preflight.
 */
import { NextResponse } from 'next/server'
import { getTradierBalanceDetail } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const TRADIER_PROD = 'https://api.tradier.com/v1'

function mask(id: string): string {
  return id.length <= 4 ? '***' : `${id.slice(0, 3)}***${id.slice(-2)}`
}

export async function GET() {
  const apiKey = process.env.TRADIER_KINDLE_API_KEY || ''
  const acctId = process.env.TRADIER_KINDLE_ACCOUNT_ID || ''
  const base = {
    env_api_key_set: !!apiKey,
    env_account_id_set: !!acctId,
    account_id_masked: acctId ? mask(acctId) : null,
  }

  if (!apiKey || !acctId) {
    return NextResponse.json({
      ok: false,
      reason:
        'TRADIER_KINDLE_API_KEY and/or TRADIER_KINDLE_ACCOUNT_ID are not set on THIS service. ' +
        'Set both on the "ironforge" (main) Render service, then redeploy.',
      ...base,
    })
  }

  try {
    const bal = await getTradierBalanceDetail(apiKey, acctId, TRADIER_PROD)
    if (!bal) {
      return NextResponse.json({
        ok: false,
        reason:
          'Tradier returned no balance — likely an invalid key, a SANDBOX key used against production, ' +
          'or a wrong account id. Confirm a PRODUCTION key against api.tradier.com.',
        ...base,
      })
    }
    return NextResponse.json({
      ok: (bal.total_equity ?? 0) > 0,
      ...base,
      account_number: bal.account_number,
      total_equity: bal.total_equity,
      total_cash: bal.total_cash,
      option_buying_power: bal.option_buying_power,
    })
  } catch (e: unknown) {
    return NextResponse.json({
      ok: false,
      reason: `Tradier request failed: ${e instanceof Error ? e.message : String(e)}`,
      ...base,
    })
  }
}
