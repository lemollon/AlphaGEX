/**
 * GET /api/kindle-check  — KINDLE live-trading PREFLIGHT (read-only).
 *
 * Exercises the real production path end-to-end WITHOUT placing any order:
 *   1. Tradier creds: TRADIER_KINDLE_* valid on production + account funded.
 *   2. Pause state: the kill switch (expect paused=TRUE until deliberate go-live).
 *   3. getProductionAccountsForBot('kindle'): the actual loader the scanner uses
 *      (returns [] while paused — that's correct and safe).
 *   4. Production sizing config availability (loadProductionConfigFor).
 * Returns a plain-English readiness verdict. Places NO orders, writes NO rows,
 * leaks no secrets (account id masked).
 */
import { NextResponse } from 'next/server'
import { getProductionPauseState, getProductionAccountsForBot } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const PROD = 'https://api.tradier.com/v1'

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
  const key = process.env.TRADIER_KINDLE_API_KEY || ''
  const acct = process.env.TRADIER_KINDLE_ACCOUNT_ID || ''

  const checks: Record<string, unknown> = { account_id_masked: mask(acct) }
  const blockers: string[] = []

  // 1. Creds + balance
  let equity: number | null = null
  let obp: number | null = null
  if (!key || !acct) {
    blockers.push('TRADIER_KINDLE_API_KEY / TRADIER_KINDLE_ACCOUNT_ID not set on this service')
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
    } else if ((obp ?? 0) < 200) {
      blockers.push(`option_buying_power $${obp} < $200 (need ~$190 for one $2-wide IC)`)
      checks.creds = 'OK_LOW_BP'
    } else {
      checks.creds = 'OK'
    }
  }

  // 2. Pause state (kill switch)
  let paused = true
  try {
    const ps = await getProductionPauseState('kindle')
    paused = ps.paused
    checks.paused = ps.paused
    checks.paused_reason = ps.paused_reason
  } catch (e: unknown) {
    checks.paused = 'unknown'
    blockers.push(`pause-state read failed: ${e instanceof Error ? e.message : String(e)}`)
  }

  // 3. Real production-account loader (the path the scanner uses)
  try {
    const accts = await getProductionAccountsForBot('kindle')
    checks.production_accounts_resolved = accts.length
    checks.production_account_ids = accts.map(a => mask(a.accountId))
  } catch (e: unknown) {
    checks.production_accounts_resolved = 'error'
    blockers.push(`getProductionAccountsForBot threw: ${e instanceof Error ? e.message : String(e)}`)
  }

  // 4. Production sizing config (loadProductionConfigFor — drives order size)
  try {
    const { loadProductionConfigFor } = await import('@/lib/scanner')
    const cfg = await loadProductionConfigFor('kindle')
    checks.production_config = cfg ? { bp_pct: cfg.bp_pct, max_contracts: cfg.max_contracts } : null
    if (!cfg || !(cfg.bp_pct > 0 && cfg.bp_pct <= 1)) {
      blockers.push('no valid KINDLE production config row — order placement would size-drop (need a kindle_config production row)')
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
    verdict = `LIVE-ARMED — creds valid, funded ($${equity}), and UNPAUSED. KINDLE will place real orders on the next signal.`
  }

  return NextResponse.json({ ready_modulo_pause: ready, verdict, blockers, ...checks })
}
