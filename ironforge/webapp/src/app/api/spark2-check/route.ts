/**
 * GET /api/spark2-check — SPARK2 live-trading PREFLIGHT (read-only).
 *
 * Clone of kindle-check for SPARK2 (which reads TRADIER_SPARK2_* env with
 * fallback to the old TRADIER_KINDLE_* names — same physical account).
 * Exercises the real production path end-to-end WITHOUT placing any order:
 *   1. Tradier creds valid on production + account funded, incl. the SPARK2
 *      sizing reality: under the 30%-BP cap a $5-wing IC (~$475 collateral)
 *      needs option_buying_power ≥ ~$1,600 to size 1 contract.
 *   2. Pause state (expect paused=TRUE until deliberate go-live).
 *   3. getProductionAccountsForBot('spark2') — the loader the scanner uses
 *      (returns [] while paused — correct and safe).
 *   4. Production sizing config availability (loadProductionConfigFor).
 * Places NO orders, writes NO rows, leaks no secrets (account id masked).
 */
import { NextResponse } from 'next/server'
import { getProductionPauseState, getProductionAccountsForBot } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const PROD = 'https://api.tradier.com/v1'
/** Worst-case collateral for one $5-wing SPY IC (wing − credit ≈ $4.75 × 100). */
const COLLATERAL_PER_CONTRACT = 475

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

export async function GET() {
  const key = process.env.TRADIER_SPARK2_API_KEY || process.env.TRADIER_KINDLE_API_KEY || ''
  const acct = process.env.TRADIER_SPARK2_ACCOUNT_ID || process.env.TRADIER_KINDLE_ACCOUNT_ID || ''
  const credsSource = process.env.TRADIER_SPARK2_API_KEY ? 'TRADIER_SPARK2_*' : process.env.TRADIER_KINDLE_API_KEY ? 'TRADIER_KINDLE_* (fallback)' : 'none'

  const checks: Record<string, unknown> = { account_id_masked: mask(acct), creds_source: credsSource }
  const blockers: string[] = []

  // 1. Creds + balance + SPARK2 sizing reality (30%-BP cap, $5 wings)
  let equity: number | null = null
  let obp: number | null = null
  if (!key || !acct) {
    blockers.push('TRADIER_SPARK2_API_KEY / TRADIER_SPARK2_ACCOUNT_ID not set on this service')
    checks.creds = 'MISSING'
  } else {
    const bal = await call(PROD, `/accounts/${acct}/balances`, key)
    const balances = (bal.body as { balances?: Record<string, unknown> } | null)?.balances
    equity = balances ? ((balances.total_equity as number | undefined) ?? null) : null
    const margin = (balances?.margin as Record<string, unknown> | undefined) || {}
    const cash = (balances?.cash as Record<string, unknown> | undefined) || {}
    obp = (margin.option_buying_power as number | undefined) ?? (cash.cash_available as number | undefined) ?? null
    checks.prod_balances_status = bal.status
    checks.total_equity = equity
    checks.option_buying_power = obp
    if (bal.status !== 200 || equity == null) {
      blockers.push(`Tradier production rejected the credentials (status ${bal.status}) — invalid/sandbox key or wrong account`)
      checks.creds = 'INVALID'
    } else {
      const estContracts = Math.floor(((obp ?? 0) * 0.30) / COLLATERAL_PER_CONTRACT)
      checks.est_contracts_at_30pct_bp = estContracts
      if (estContracts < 1) {
        blockers.push(
          `sizes to ZERO contracts: option_buying_power $${obp} × 30% BP cap = $${(((obp ?? 0) * 0.3)).toFixed(0)} ` +
          `< ~$${COLLATERAL_PER_CONTRACT} collateral for one $5-wing IC — fund the account to ≥ ~$1,600 OBP`,
        )
        checks.creds = 'OK_LOW_BP'
      } else {
        checks.creds = 'OK'
      }
    }
  }

  // 2. Pause state (kill switch)
  let paused = true
  try {
    const ps = await getProductionPauseState('spark2')
    paused = ps.paused
    checks.paused = ps.paused
    checks.paused_reason = ps.paused_reason
  } catch (e: unknown) {
    checks.paused = 'unknown'
    blockers.push(`pause-state read failed: ${e instanceof Error ? e.message : String(e)}`)
  }

  // 3. Real production-account loader (the path the scanner uses)
  try {
    const accts = await getProductionAccountsForBot('spark2')
    checks.production_accounts_resolved = accts.length
    checks.production_account_ids = accts.map(a => mask(a.accountId))
  } catch (e: unknown) {
    checks.production_accounts_resolved = 'error'
    blockers.push(`getProductionAccountsForBot threw: ${e instanceof Error ? e.message : String(e)}`)
  }

  // 4. Production sizing config (loadProductionConfigFor — drives order size)
  try {
    const { loadProductionConfigFor } = await import('@/lib/scanner')
    const cfg = await loadProductionConfigFor('spark2')
    checks.production_config = cfg ? { bp_pct: cfg.bp_pct, max_contracts: cfg.max_contracts } : null
    if (!cfg || !(cfg.bp_pct > 0 && cfg.bp_pct <= 1)) {
      blockers.push('no valid SPARK2 production config row — order placement would size-drop (need a spark2_config production row)')
    }
  } catch (e: unknown) {
    checks.production_config = 'error'
    blockers.push(`loadProductionConfigFor threw: ${e instanceof Error ? e.message : String(e)}`)
  }

  // Verdict. "Paused" is NOT a blocker — it's the intended pre-go-live state.
  const credsOk = checks.creds === 'OK'
  const ready = credsOk && blockers.length === 0
  let verdict: string
  if (!credsOk) {
    verdict = 'NOT READY — credentials/balance problem (see blockers).'
  } else if (blockers.length > 0) {
    verdict = `NOT READY — creds OK ($${equity} equity) but ${blockers.length} blocker(s) remain before go-live.`
  } else if (paused) {
    verdict = `READY (PAUSED) — creds valid, account funded ($${equity}, OBP $${obp}), kill switch ON. Deliberate unpause is the last step.`
  } else {
    verdict = `LIVE-ARMED — creds valid, funded ($${equity}), and UNPAUSED. SPARK2 will place real orders on the next signal.`
  }

  return NextResponse.json({ ready_modulo_pause: ready, verdict, blockers, ...checks })
}
