/**
 * GET /api/kindle-check
 *
 * Read-only diagnostic for KINDLE's live Tradier credentials. Reads
 * TRADIER_KINDLE_API_KEY + TRADIER_KINDLE_ACCOUNT_ID from the server env (never
 * the DB) and runs three probes to pinpoint any problem WITHOUT guessing:
 *   1. prod  /user/profile  → what accounts does this key actually own?
 *   2. prod  /accounts/{id}/balances → the funded balance (the goal).
 *   3. sbx   /user/profile  → is this key actually a SANDBOX key?
 *
 * Reports HTTP statuses + the (masked) accounts the key owns + a plain-English
 * diagnosis. Places NO orders, writes NO rows, leaks no secrets.
 */
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const PROD = 'https://api.tradier.com/v1'
const SBX = 'https://sandbox.tradier.com/v1'

function mask(id?: string | null): string | null {
  if (!id) return null
  return id.length <= 4 ? '***' : `${id.slice(0, 3)}***${id.slice(-2)}`
}

async function call(base: string, path: string, key: string) {
  try {
    const r = await fetch(`${base}${path}`, {
      headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' },
      cache: 'no-store',
    })
    let body: unknown = null
    try { body = await r.json() } catch { body = null }
    return { status: r.status, ok: r.ok, body: body as Record<string, unknown> | null }
  } catch (e: unknown) {
    return { status: 0, ok: false, body: null, err: e instanceof Error ? e.message : String(e) }
  }
}

function ownedAccounts(profileBody: Record<string, unknown> | null): (string | null)[] {
  const prof = (profileBody as { profile?: { account?: unknown } } | null)?.profile
  const acct = prof?.account
  if (!acct) return []
  const arr = Array.isArray(acct) ? acct : [acct]
  return arr.map((a) => mask((a as { account_number?: string })?.account_number))
}

export async function GET() {
  const key = process.env.TRADIER_KINDLE_API_KEY || ''
  const acct = process.env.TRADIER_KINDLE_ACCOUNT_ID || ''
  if (!key || !acct) {
    return NextResponse.json({
      ok: false,
      diagnosis: 'TRADIER_KINDLE_API_KEY and/or TRADIER_KINDLE_ACCOUNT_ID not set on this service.',
      env_api_key_set: !!key,
      env_account_id_set: !!acct,
    })
  }

  const prodProfile = await call(PROD, '/user/profile', key)
  const prodBal = await call(PROD, `/accounts/${acct}/balances`, key)
  const sbxProfile = await call(SBX, '/user/profile', key)

  const owns = ownedAccounts(prodProfile.body)
  const balances = (prodBal.body as { balances?: Record<string, unknown> } | null)?.balances
  const equity = balances ? (balances.total_equity as number | undefined) ?? null : null
  const margin = (balances?.margin as Record<string, unknown> | undefined) || {}
  const cash = (balances?.cash as Record<string, unknown> | undefined) || {}
  const obp = (margin.option_buying_power as number | undefined)
    ?? (cash.cash_available as number | undefined) ?? null

  let diagnosis: string
  if (equity != null) {
    diagnosis = `LIVE OK — key authorizes account ${mask(acct)} on production.`
  } else if (prodProfile.status === 401 && sbxProfile.status === 200) {
    diagnosis = 'This is a SANDBOX key (works on sandbox.tradier.com, rejected by production). You need a PRODUCTION access token from your live Tradier dashboard.'
  } else if (prodProfile.status === 401) {
    diagnosis = 'Key is INVALID/unauthorized on production (401). Re-copy the production access token (no extra spaces).'
  } else if (prodProfile.ok && owns.length && !owns.includes(mask(acct))) {
    diagnosis = `Key is a valid PRODUCTION key but does NOT own ${mask(acct)}. It owns: ${owns.join(', ')}. Set TRADIER_KINDLE_ACCOUNT_ID to one of those.`
  } else if (prodBal.status === 401 || prodBal.status === 404) {
    diagnosis = `Account ${mask(acct)} not accessible under this key (balances ${prodBal.status}). Confirm the account number matches the key.`
  } else {
    diagnosis = 'Unexpected — see raw statuses below.'
  }

  return NextResponse.json({
    ok: equity != null,
    diagnosis,
    account_id_masked: mask(acct),
    key_owns_accounts: owns,
    total_equity: equity,
    option_buying_power: obp,
    prod_profile_status: prodProfile.status,
    prod_balances_status: prodBal.status,
    sandbox_profile_status: sbxProfile.status,
  })
}
