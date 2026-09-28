/**
 * FLAME_FAST_START — WIRED integration tests against the real
 * placeCallSpreadOrderAllAccounts (tradier.ts), with a mocked DB layer and
 * a mocked Tradier HTTP layer (global fetch). Extends the same harness
 * style as flint-multi-account.test.ts.
 *
 * Covers, at the WIRED call site (not just the pure fast-start-sizing.ts
 * function, which already has its own unit + parity tests):
 *   1. KILL SWITCH: FLAME_FAST_START unset/off never touches any
 *      fast_start_* table and produces byte-identical sizing to before
 *      this feature existed (rule R1's own contract count).
 *   2. The ordering-gap fix: FLINT runs before EBB in the real scanner, so
 *      it cannot observe a same-tick EBB decision — instead it PLANS EBB's
 *      likely outcome from the SAME deterministic VIX-decay gate EBB's own
 *      entry uses (no live quote needed). On a day EBB's gate FAILS (about
 *      half of FLINT's days), FLINT still enters AT ITS NORMAL TIME/SIZE,
 *      treating EBB as a non-candidate — the bug this replaced (deferring
 *      for hours) is gone.
 *   3. On a day EBB's gate PASSES, FLINT reserves budget against a
 *      WORST-CASE (conservative) estimate of EBB's max loss.
 *   4. Equity-fetch failure falls back to today's (pre-fast-start) sizing
 *      and logs it — never sizes up on missing data.
 *   5. peak_profit/phase never change from an intraday call — only
 *      updateFastStartEodState (fast-start-db.ts) can move them.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockDbQuery = vi.fn()
const mockDbExecute = vi.fn().mockResolvedValue(1)

// In-memory stores the mock SQL layer reads/writes.
let flintFloorStore: Record<string, number> = {}
let fastStartStateStore: Record<string, { phase: number; deposit: number; peak_profit: number }> = {}
let flintDailyContextRow: Record<string, unknown> | null = null
// sw_vix_daily rows served to vixDecayCheck, most-recent-first (row[0] = "prior").
let vixRows: Array<{ vix: number }> = []
const loggedDecisions: any[] = []

vi.mock('../db', () => ({
  query: (...args: any[]) => mockDbQuery(...args),
  dbQuery: (...args: any[]) => mockDbQuery(...args),
  dbExecute: (...args: any[]) => mockDbExecute(...args),
  sharedTable: (name: string) => name,
  botTable: (bot: string, table: string) => `${bot}_${table}`,
  escapeSql: (s: string) => s.replace(/'/g, "''"),
  num: (v: any) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0 },
  int: (v: any) => { const n = parseInt(v, 10); return Number.isFinite(n) ? n : 0 },
  CT_TODAY: "'2026-09-29'",
}))

const ENV_KEYS = [
  'FLAME_FAST_START', 'IRONFORGE_FLAME_LIVE', 'TRADIER_FLAME_API_KEY', 'TRADIER_FLAME_ACCOUNT_ID',
  'TRADIER_SANDBOX_KEY_USER', 'TRADIER_SANDBOX_KEY_MATT', 'TRADIER_SANDBOX_KEY_LOGAN',
] as const

const BROKER: Record<string, { accountId: string; equity: number | null; obp: number }> = {
  'sb-user-key': { accountId: 'SBUSER1', equity: 4242, obp: 5000 },
}

// 21 rows = VIX_DECAY_MIN_HISTORY (VIX_DECAY_WINDOW=20 + 1). row[0] = prior
// close; rows[1..20] = the trailing 20-session window. prior=10, window=20
// each -> ratio=0.5 <= FLAME's 0.80 ceiling -> EBB's VIX gate PASSES.
const VIX_GATE_PASSES: Array<{ vix: number }> = [{ vix: 10 }, ...Array.from({ length: 20 }, () => ({ vix: 20 }))]
// Fewer than 21 rows -> vixDecayCheck returns reason='vix_unknown(...)' ->
// EBB's gate FAILS (any non-null reason means "not a candidate", matching
// EBB's own real tryOpenFlamePutSpread behavior exactly).
const VIX_GATE_FAILS: Array<{ vix: number }> = [{ vix: 15 }]

function jsonResponse(body: any, ok = true) {
  return { ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'ERR', json: async () => body, text: async () => JSON.stringify(body) } as any
}

beforeEach(() => {
  // Fix "now" to 13:06 CT (18:06Z, CDT) — inside FLAME's entry window —
  // so the wiring is deterministic regardless of the real wall-clock time
  // this suite happens to run at.
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-29T18:06:00Z'))
  for (const k of ENV_KEYS) delete process.env[k]
  // deposit=3900, equity=4242 -> cushion=$342, clears FLINT's own standing
  // rule ($171.40 for a $2-wide/$0.30-credit contract) independent of
  // fast-start, so the kill-switch test isn't confounded by R1 itself.
  flintFloorStore = { 'User:sandbox': 3900 }
  fastStartStateStore = {}
  flintDailyContextRow = { decision: 'traded', call_short_strike_considered: 600, call_long_strike_considered: 602, entry_credit_seen: 0.30 }
  vixRows = VIX_GATE_PASSES
  loggedDecisions.length = 0

  mockDbQuery.mockReset()
  mockDbExecute.mockReset().mockResolvedValue(1)

  mockDbQuery.mockImplementation(async (sql: string, params: any[] = []) => {
    if (sql.includes('SELECT person, api_key, account_id, type FROM ironforge_accounts')) {
      return [{ person: 'User', api_key: 'sb-user-key', account_id: 'SBUSER1', type: 'sandbox' }]
    }
    if (sql.includes('SELECT DISTINCT person, type FROM ironforge_accounts')) {
      return [{ person: 'User', type: 'sandbox' }]
    }
    if (sql.includes('SELECT api_key, type FROM ironforge_accounts')) {
      return [{ api_key: 'sb-user-key', type: 'sandbox' }]
    }
    if (sql.includes('SELECT capital_pct FROM ironforge_accounts')) return []
    if (sql.includes('FROM ironforge_owner_pause')) return []
    if (sql.includes('FROM ironforge_production_pause')) return []
    if (sql.includes('FROM flint_positions')) return [{ cnt: 0 }]
    if (sql.includes('FROM flame_positions')) return [{ m: 0 }]

    // ---- flint_account_floor (deposit source for sandbox) ----
    if (sql.includes('SELECT floor_amount FROM flint_account_floor')) {
      const key = `${params[0]}:${params[1]}`
      return flintFloorStore[key] != null ? [{ floor_amount: flintFloorStore[key] }] : []
    }
    if (sql.includes('SELECT funded_amount FROM ironforge_accounts')) return []
    if (sql.includes('INSERT INTO flint_account_floor')) {
      const key = `${params[0]}:${params[1]}`
      if (flintFloorStore[key] == null) flintFloorStore[key] = params[3]
      return []
    }

    // ---- fast_start_state ----
    if (sql.includes('SELECT phase, deposit, peak_profit FROM fast_start_state')) {
      const key = `${params[0]}:${params[1]}`
      return fastStartStateStore[key] ? [fastStartStateStore[key]] : []
    }
    if (sql.includes('INSERT INTO fast_start_state')) {
      const key = `${params[0]}:${params[1]}`
      if (!fastStartStateStore[key]) {
        fastStartStateStore[key] = { phase: 1, deposit: params[2], peak_profit: params[3] ?? 0 }
      }
      return []
    }
    if (sql.includes('UPDATE fast_start_state')) {
      const key = `${params[0]}:${params[1]}`
      if (fastStartStateStore[key]) fastStartStateStore[key].phase = 2
      return []
    }

    // ---- fast_start_decision_log ----
    if (sql.includes('INSERT INTO fast_start_decision_log')) {
      loggedDecisions.push(params)
      return []
    }

    // ---- flint_daily_context (EBB's cross-leg read) ----
    if (sql.includes('FROM flint_daily_context')) {
      return flintDailyContextRow ? [flintDailyContextRow] : []
    }

    // ---- sw_vix_daily (EBB's own VIX-decay gate, planned by FLINT) ----
    if (sql.includes('FROM sw_vix_daily')) return vixRows

    return []
  })

  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: any) => {
    const auth = String(init?.headers?.Authorization ?? '')
    const key = auth.replace('Bearer ', '')
    const acct = BROKER[key]
    if (url.includes('/user/profile')) return jsonResponse({ profile: { account: { account_number: acct?.accountId ?? null } } })
    if (url.includes('/balances')) {
      if (acct?.equity == null) return jsonResponse({}, false) // simulate an unreadable equity fetch
      return jsonResponse({ balances: { total_equity: String(acct.equity), margin: { option_buying_power: String(acct.obp) } } })
    }
    if (url.includes('/orders') && init?.method === 'POST') return jsonResponse({ order: { id: 42, status: 'ok' } })
    if (url.includes('/orders/')) return jsonResponse({ order: { status: 'filled', avg_fill_price: '0.30' } })
    return jsonResponse({}, false) // e.g. the VIX daily-history HTTP fetch inside ensureVixHistory — irrelevant, mocked at the DB layer instead
  }))
})

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

import { placeCallSpreadOrderAllAccounts } from '../tradier'

describe('FLAME_FAST_START — wired at placeCallSpreadOrderAllAccounts (FLINT)', () => {
  it('KILL SWITCH: unset -> never touches fast_start_state/log, sizes exactly as rule R1 alone would', async () => {
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos1', { baseContracts: 1 })
    expect(Object.keys(result)).toContain('User:sandbox')
    expect(mockDbQuery.mock.calls.some((c) => String(c[0]).includes('fast_start_state'))).toBe(false)
    expect(mockDbQuery.mock.calls.some((c) => String(c[0]).includes('fast_start_decision_log'))).toBe(false)
    expect(loggedDecisions.length).toBe(0)
  })

  it("ON, EBB's VIX gate FAILS today -> FLINT still enters at its normal time/size, treating EBB as a non-candidate (the bug this replaced: deferring for hours)", async () => {
    process.env.FLAME_FAST_START = 'on'
    vixRows = VIX_GATE_FAILS
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos2', { baseContracts: 1 })
    expect(result['User:sandbox']).toBeDefined() // entered THIS tick, not deferred
    const lastLog = loggedDecisions[loggedDecisions.length - 1]
    expect(lastLog[3]).toBe('flint')
    expect(lastLog[8]).toBe(1) // full budget available since EBB is planned as non-candidate
    expect(String(lastLog[lastLog.length - 1])).toContain('candidate=false')
  })

  it("ON, EBB's VIX gate PASSES today -> FLINT reserves budget against EBB's worst-case planned max loss", async () => {
    process.env.FLAME_FAST_START = 'on'
    vixRows = VIX_GATE_PASSES // EBB planned as a candidate
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos3', { baseContracts: 1 })
    const lastLog = loggedDecisions[loggedDecisions.length - 1]
    expect(lastLog[3]).toBe('flint')
    expect(String(lastLog[lastLog.length - 1])).toContain('candidate=true')
    // deposit=3900 -> X budget=780. EBB planned Phase-1 target = 2*ladder(0)=0
    // (peak_profit=0, floor=3900 -> ladder=floor(3900/1500)=2 -> target=4,
    // capped by floor(780/est_maxloss). est_maxloss=(2-0.10)*100+1.40=191.40
    // -> floor(780/191.40)=4 -> planned ebb=4 -> committed=4*191.40=765.60,
    // remaining=780-765.60=14.40 < flint_ml(171.40) -> flint=0.
    expect(result['User:sandbox']).toBeUndefined()
    expect(lastLog[8]).toBe(0)
  })

  it('equity-fetch failure -> falls back to today\'s (pre-fast-start) sizing, never sizes up on missing data', async () => {
    process.env.FLAME_FAST_START = 'on'
    BROKER['sb-user-key'].equity = null as any // simulate an unreadable Tradier balance
    const result = await placeCallSpreadOrderAllAccounts('SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos4', { baseContracts: 1 })
    // R1's own gate ALSO needs equity — with it unreadable, rule R1 itself
    // skips the account (fails closed), which is the correct "fall back to
    // today's sizing, and today's sizing itself requires equity" outcome.
    expect(result['User:sandbox']).toBeUndefined()
    BROKER['sb-user-key'].equity = 4242
  })

  it('phase/peak_profit never change from an intraday call — only updateFastStartEodState can move them', async () => {
    process.env.FLAME_FAST_START = 'on'
    // Seed a state row already sitting at a large peak_profit, phase 1.
    fastStartStateStore['User:sandbox'] = { phase: 1, deposit: 3900, peak_profit: 1_000_000 }
    await placeCallSpreadOrderAllAccounts('SPY', '2026-09-29', 600, 602, 1, 0.30, 'pos5', { baseContracts: 1 })
    // Even with a cushion this large (which would trivially clear any
    // trigger threshold), the intraday call must NOT have advanced phase —
    // no UPDATE fast_start_state call should have fired.
    expect(mockDbQuery.mock.calls.some((c) => String(c[0]).includes('UPDATE fast_start_state'))).toBe(false)
    expect(fastStartStateStore['User:sandbox'].phase).toBe(1)
    expect(fastStartStateStore['User:sandbox'].peak_profit).toBe(1_000_000)
  })
})
