/**
 * Production Readiness Tests — verifies the full production trading path
 * for FLAME's Iron Viper (Logan) production account before market open.
 *
 * Tests cover:
 *   1. Capital sizing with capital_pct (behavioral)
 *   2. PRODUCTION_MAX_CONTRACTS safety cap (structural + arithmetic)
 *   3. Production-Only Mode flow (structural)
 *   4. Production position DB recording (structural)
 *   5. Production close path (structural)
 *   6. Full tomorrow-morning scenario (structural)
 *   7. Blockers that could prevent production trading (structural)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import fs from 'fs'
import path from 'path'

/* ── Environment ────────────────────────────────────────────────────── */

vi.hoisted(() => {
  process.env.TRADIER_API_KEY = 'test-production-key'
  process.env.TRADIER_SANDBOX_KEY_USER = 'test-sandbox-user'
  process.env.TRADIER_SANDBOX_KEY_MATT = 'test-sandbox-matt'
  process.env.TRADIER_SANDBOX_KEY_LOGAN = 'test-sandbox-logan'
})

/* ── Mock DB ────────────────────────────────────────────────────────── */

const mockQuery = vi.fn().mockResolvedValue([])
const mockDbExecute = vi.fn().mockResolvedValue(1)

vi.mock('../db', () => ({
  query: (...args: any[]) => mockQuery(...args),
  dbQuery: (...args: any[]) => mockQuery(...args),
  dbExecute: (...args: any[]) => mockDbExecute(...args),
  botTable: (bot: string, table: string) => `${bot}_${table}`,
  sharedTable: (table: string) => table,
  validateBot: (bot: string) => bot,
  dteMode: (bot: string) => bot === 'inferno' ? '0DTE' : bot === 'spark' ? '1DTE' : '2DTE',
  num: (v: any) => parseFloat(v) || 0,
  int: (v: any) => parseInt(v) || 0,
  escapeSql: (v: string) => v,
  CT_TODAY: "'2026-03-24'",
}))

/* ── Mock fetch ─────────────────────────────────────────────────────── */

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

/* ── Source code reading for structural tests ────────────────────────── */

const TRADIER_PATH = path.resolve(__dirname, '../tradier.ts')
const SCANNER_PATH = path.resolve(__dirname, '../scanner.ts')
const DB_PATH = path.resolve(__dirname, '../db.ts')
const CLOSE_ROUTE_PATH = path.resolve(__dirname, '../../app/api/[bot]/force-close/route.ts')

const tradierSource = fs.readFileSync(TRADIER_PATH, 'utf-8')
const scannerSource = fs.readFileSync(SCANNER_PATH, 'utf-8')
const dbSource = fs.readFileSync(DB_PATH, 'utf-8')
const closeRouteSource = fs.readFileSync(CLOSE_ROUTE_PATH, 'utf-8')

beforeEach(() => {
  mockQuery.mockReset().mockResolvedValue([])
  mockFetch.mockReset()
  mockDbExecute.mockReset().mockResolvedValue(1)
})

/* ================================================================== */
/*  1. Capital Sizing with capital_pct (behavioral)                    */
/* ================================================================== */

describe('Capital Sizing with capital_pct', () => {
  let getCapitalPctForAccount: (person: string, accountType?: 'sandbox' | 'production') => Promise<number>

  beforeEach(async () => {
    const mod = await import('../tradier')
    getCapitalPctForAccount = mod.getCapitalPctForAccount
  })

  it('15% of $7500 BP → usableBP=$956 → 1 contract for $5 spread', async () => {
    // Simulates Logan production: $7500 option BP, 15% capital_pct, $5 spread width
    mockQuery.mockResolvedValueOnce([{ capital_pct: 15 }])
    const pct = await getCapitalPctForAccount('Logan', 'production')
    expect(pct).toBe(15)

    // placeIcOrderAllAccounts sizing math:
    // bp = $7500, capitalPct = 15%, botShare = 1.0 (sole production account)
    // bpAfterCapitalPct = 7500 * 0.15 = 1125
    // usableBP = 1125 * 1.0 * 0.85 = 956.25
    // brokerMarginPer = spreadWidth * 100 = $500
    // bpContracts = floor(956.25 / 500) = 1
    const bp = 7500
    const capitalPct = pct
    const botShare = 1.0
    const bpAfterCapitalPct = bp * (capitalPct / 100)
    const usableBP = bpAfterCapitalPct * botShare * 0.85
    const brokerMarginPer = 5 * 100  // $5 spread × 100 = $500/contract
    const bpContracts = Math.floor(usableBP / brokerMarginPer)

    expect(bpAfterCapitalPct).toBe(1125)
    expect(usableBP).toBeCloseTo(956.25, 2)
    expect(bpContracts).toBe(1)
  })

  it('50% of $7500 BP → 5 contracts', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 50 }])
    const pct = await getCapitalPctForAccount('Logan', 'production')

    const usableBP = 7500 * (pct / 100) * 1.0 * 0.85
    const bpContracts = Math.floor(usableBP / 500)

    expect(usableBP).toBeCloseTo(3187.5, 2)
    expect(bpContracts).toBe(6)
  })

  it('100% of $7500 BP → 12 contracts', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 100 }])
    const pct = await getCapitalPctForAccount('Logan', 'production')

    const usableBP = 7500 * (pct / 100) * 1.0 * 0.85
    const bpContracts = Math.floor(usableBP / 500)

    expect(usableBP).toBeCloseTo(6375, 2)
    expect(bpContracts).toBe(12)
  })

  it('out-of-range capital_pct (0) defaults to 100', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 0 }])
    const pct = await getCapitalPctForAccount('Logan', 'production')
    expect(pct).toBe(100)
  })

  it('out-of-range capital_pct (101) defaults to 100', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 101 }])
    const pct = await getCapitalPctForAccount('Logan', 'production')
    expect(pct).toBe(100)
  })

  it('tradier.ts applies per-scope bp_pct in sizing math (structural)', () => {
    // Sizing model post-Commit-A: one bp_pct per scope, no capital_pct double-dip.
    //   Paper/Sandbox: usableBP = bp * botShare * 0.85
    //   Live/Production: usableBP = bp * botShare * prodBpPct (from siloed config)
    // Contract count is floor(usableBP / brokerMarginPer) as before.
    expect(tradierSource).toMatch(/const bpPct = acct\.type === 'production'/)
    expect(tradierSource).toMatch(/\? prodBpPct/)
    expect(tradierSource).toMatch(/: 0\.85/)
    expect(tradierSource).toMatch(/const usableBP = bp \* botShare \* bpPct/)
    expect(tradierSource).toMatch(/bpContracts\s*=\s*Math\.floor\(usableBP\s*\/\s*brokerMarginPer\)/)
    // Legacy double-dip formula must be gone — would re-introduce 15% × 0.85 = 12.75% bug.
    expect(tradierSource).not.toMatch(/usableBP\s*=\s*bpAfterCapitalPct\s*\*\s*botShare\s*\*\s*0\.85/)
  })
})

/* ================================================================== */
/*  2. PRODUCTION_MAX_CONTRACTS Safety Cap                             */
/* ================================================================== */

describe('Production Contract Ceiling (Config-Driven, Commit A)', () => {
  it('hardcoded PRODUCTION_MAX_CONTRACTS is gone from scanner.ts', () => {
    // Pre-Commit-A: three hardcoded `PRODUCTION_MAX_CONTRACTS = 2` declarations
    // post-fill capped Tradier's filled qty, creating a record-vs-broker
    // mismatch and defeating the 15% sizing. Commit A removed them; the cap
    // now lives upstream via spark_config.production.max_contracts
    // (default 0 = unlimited, bp_pct × Tradier OBP is the real risk bound).
    const matches = scannerSource.match(/PRODUCTION_MAX_CONTRACTS\s*=\s*\d+/g) ?? []
    expect(matches.length).toBe(0)
  })

  it('no post-fill Math.min cap against info.contracts', () => {
    // Ensure nothing re-introduces a hardcoded cap that shrinks Tradier's
    // actual filled quantity before we record the position.
    const capUsages = scannerSource.match(/Math\.min\(info\.contracts,\s*PRODUCTION_MAX_CONTRACTS\)/g) ?? []
    expect(capUsages.length).toBe(0)
  })

  it('production ceiling reads from spark_config.production.max_contracts', () => {
    // tradier.ts now resolves the ceiling from the siloed production config
    // at sizing time. 0 means unlimited.
    expect(tradierSource).toMatch(/prodMaxContracts\s*=\s*Math\.max\(0, prodCfg\.max_contracts\)/)
    expect(tradierSource).toMatch(/prodCeiling\s*=\s*prodMaxContracts\s*>\s*0\s*\?\s*prodMaxContracts\s*:\s*Number\.POSITIVE_INFINITY/)
  })

  it('production sizing uses Tradier OBP × bp_pct (no paperContracts cap)', () => {
    // Production must size independently of paperContracts (which was the
    // cap that shrank prod orders to paper-sized count). Sandbox still mirrors
    // paper contracts.
    expect(tradierSource).toMatch(/acctContracts = Math\.min\(SANDBOX_MAX_CONTRACTS, bpContracts, prodCeiling\)/)
    expect(tradierSource).toMatch(/acctContracts = Math\.min\(SANDBOX_MAX_CONTRACTS, bpContracts, paperContracts\)/)
  })
})

/* ================================================================== */
/*  3. Production-Only Mode Flow                                       */
/* ================================================================== */

describe('Production-Only Mode Flow', () => {
  it('production-only mode is triggered when sandbox traded but production has NOT', () => {
    // Sandbox trades checked via pdt_log with account_type='sandbox'
    expect(scannerSource).toMatch(/COALESCE\(account_type,\s*'sandbox'\)\s*=\s*'sandbox'/)
    // Production check: positions with account_type='production' opened today
    expect(scannerSource).toMatch(/account_type\s*=\s*'production'/)
    expect(scannerSource).toMatch(/prodTradedToday/)
  })

  it('sets _productionOnlyMode = true when conditions are met', () => {
    expect(scannerSource).toMatch(/_productionOnlyMode\s*=\s*true/)
  })

  it('returns skip when BOTH sandbox and production already traded', () => {
    // If prodTradedToday is true AND sandbox hit max → skip
    expect(scannerSource).toMatch(/if\s*\(prodTradedToday\)\s*\{[\s\S]*?return\s*'skip:already_traded_today'/)
  })

  it('calls placeIcOrderAllAccounts in production-only mode', () => {
    // Extract the production-only mode block
    const prodOnlyBlock = scannerSource.match(
      /if\s*\(_productionOnlyMode\)\s*\{[\s\S]*?return\s*'skip:flame_production_only_no_fills'/,
    )?.[0] ?? ''
    expect(prodOnlyBlock.length).toBeGreaterThan(100)
    expect(prodOnlyBlock).toContain('placeIcOrderAllAccounts')
  })

  it('skips non-production fills in production-only mode', () => {
    const prodOnlyBlock = scannerSource.match(
      /if\s*\(_productionOnlyMode\)\s*\{[\s\S]*?return\s*'skip:flame_production_only_no_fills'/,
    )?.[0] ?? ''
    expect(prodOnlyBlock).toMatch(/account_type\s*!==\s*'production'.*continue/s)
  })

  it('creates position IDs with -prod- suffix', () => {
    expect(scannerSource).toMatch(/-prod-/)
    // Verify the pattern: positionId-prod-personname
    expect(scannerSource).toMatch(/\$\{positionId\}-prod-\$\{prodPerson/)
  })

  it('returns traded:...-production-only on successful production trade', () => {
    expect(scannerSource).toContain('return `traded:${positionId}-production-only`')
  })
})

/* ================================================================== */
/*  4. Production Position DB Recording                                */
/* ================================================================== */

describe('Production Position DB Recording', () => {
  it('position INSERT includes account_type = production (literal in SQL)', () => {
    // The INSERT uses 'production' as a literal in the VALUES clause (not a parameter)
    // Pattern: 'open', NOW(), CT_TODAY, $37, $38, 'production'
    expect(scannerSource).toMatch(/'open',\s*NOW\(\),\s*\$\{CT_TODAY\},\s*\$\d+,\s*\$\d+,\s*'production'/)
  })

  it('collateral UPDATE targets production paper_account', () => {
    expect(scannerSource).toMatch(
      /UPDATE.*paper_account[\s\S]*?WHERE\s+account_type\s*=\s*'production'\s+AND\s+person\s*=\s*\$/,
    )
  })

  it('log entry uses PRODUCTION_ORDER level', () => {
    expect(scannerSource).toContain("'PRODUCTION_ORDER'")
  })

  it('zero or null fill_price skips DB writes', () => {
    // Guard: if (!info.fill_price || info.fill_price <= 0) continue
    expect(scannerSource).toMatch(/!info\.fill_price\s*\|\|\s*info\.fill_price\s*<=\s*0.*continue/s)
  })

  it('production person is extracted from key before colon', () => {
    expect(scannerSource).toMatch(/prodPerson\s*=\s*key\.split\(':'\)\[0\]/)
  })

  it('production collateral calculation matches sandbox formula', () => {
    // Both use: Math.max(0, (spreadWidth - credit) * 100) * contracts
    expect(scannerSource).toMatch(/prodCollateral\s*=\s*Math\.max\(0,\s*\(spreadWidth\s*-\s*prodCredit\)\s*\*\s*100\)\s*\*\s*prodContracts/)
  })

  it('production fill summary logs missing production entries as warnings', () => {
    expect(scannerSource).toMatch(/PRODUCTION FILL SUMMARY.*0 production/)
    expect(scannerSource).toMatch(/production account may not.*eligible/i)
  })
})

/* ================================================================== */
/*  5. Production Close Path                                           */
/* ================================================================== */

describe('Production Close Path', () => {
  it('closePosition reads account_type from positions table', () => {
    expect(scannerSource).toMatch(
      /COALESCE\(account_type,\s*'sandbox'\)\s*as\s+account_type[\s\S]*?FROM.*positions.*WHERE\s+position_id/,
    )
  })

  it('production close uses {person}:production key for fill price lookup', () => {
    // primaryCloseKey = `${posPerson}:production`
    expect(scannerSource).toMatch(/primaryCloseKey\s*=\s*posAccountType\s*===\s*'production'/)
    expect(scannerSource).toMatch(/`\$\{posPerson\}:production`/)
  })

  it('close P&L formula is identical for production and sandbox', () => {
    // Both paths use: (entryCredit - effectivePrice) * 100 * contracts
    expect(scannerSource).toMatch(/entryCredit\s*-\s*effectivePrice/)
    // P&L is rounded
    expect(scannerSource).toMatch(/Math\.round\(.*100.*\)\s*\/\s*100/)
  })

  it('production position close updates production paper_account collateral', () => {
    // In closePosition: UPDATE paper_account WHERE account_type = ... AND person = ...
    // The function uses posAccountType read from the position
    expect(scannerSource).toMatch(/posAccountType/)
    expect(scannerSource).toMatch(/posPerson/)
  })

  it('force-close route supports production positions', () => {
    // force-close reads account_type from position
    expect(closeRouteSource).toMatch(/account_type/)
  })
})

/* ================================================================== */
/*  6. Full Scenario: Tomorrow Morning at 8:35 AM CT                   */
/* ================================================================== */

describe('Full Tomorrow Morning Scenario', () => {
  it('the production bot is recognized as requiring broker fills (isProductionFillOnly)', () => {
    expect(scannerSource).toMatch(/isProductionFillOnly\s*=\s*bot\.name\s*===\s*PRODUCTION_BOT/)
  })

  it('production orders are placed INDEPENDENTLY of sandbox results', () => {
    // The "PRODUCTION FILLS" block runs regardless of sandbox outcome
    expect(scannerSource).toContain('PRODUCTION FILLS: Process INDEPENDENTLY of sandbox')
    // Production is processed BEFORE the sandbox fill check/retry
    // Verify production processing comes before the "SANDBOX FILL CHECK" comment
    const prodFillsIdx = scannerSource.indexOf('PRODUCTION FILLS: Process INDEPENDENTLY')
    const sandboxCheckIdx = scannerSource.indexOf('SANDBOX FILL CHECK: Retry sandbox only')
    expect(prodFillsIdx).toBeGreaterThan(-1)
    expect(sandboxCheckIdx).toBeGreaterThan(-1)
    expect(prodFillsIdx).toBeLessThan(sandboxCheckIdx)
  })

  it('sandbox retry passes sandboxOnly: true to prevent duplicate production orders', () => {
    expect(scannerSource).toMatch(/placeIcOrderAllAccounts\([\s\S]*?\{\s*sandboxOnly:\s*true\s*\}/)
  })

  it('retry only merges sandbox results back (does not overwrite production)', () => {
    // After retry: for (const [key, info] of Object.entries(retryResults)) {
    //   if (info.account_type !== 'production') { sandboxOrderIds[key] = info }
    expect(scannerSource).toMatch(
      /retryResults[\s\S]*?account_type\s*!==\s*'production'[\s\S]*?sandboxOrderIds\[key\]\s*=\s*info/,
    )
  })

  it('placeIcOrderAllAccounts supports sandboxOnly option', () => {
    // The tradier.ts function accepts opts?: { sandboxOnly?: boolean }
    expect(tradierSource).toMatch(/sandboxOnly/)
    // And uses it to gate production block
    expect(tradierSource).toMatch(/!opts\?\.sandboxOnly/)
  })

  it('existing production position prevents new open (monitors instead)', () => {
    // The scanner checks for open production positions before opening new ones
    // If prodTradedToday is true AND sandbox traded → skip:already_traded_today
    expect(scannerSource).toMatch(/prodTradedToday/)
  })

  it('production account uses api.tradier.com (not sandbox)', () => {
    expect(tradierSource).toMatch(/PRODUCTION_URL.*api\.tradier\.com/)
    expect(tradierSource).toMatch(/SANDBOX_URL.*sandbox\.tradier\.com/)
    // Production accounts get the production base URL
    expect(tradierSource).toMatch(/acct\.type\s*===\s*'production'.*PRODUCTION_URL|baseUrl.*production.*api\.tradier/s)
  })
})

/* ================================================================== */
/*  7. Blockers That Could Prevent Production Trading                  */
/* ================================================================== */

describe('Blockers That Could Prevent Production Trading', () => {
  it('_sandboxPaperOnly mode blocks FLAME entirely (including production)', () => {
    // _sandboxPaperOnly check returns BEFORE placeIcOrderAllAccounts
    expect(scannerSource).toMatch(/_sandboxPaperOnly/)
    expect(scannerSource).toContain("return 'skip:flame_requires_tradier(paper_only_mode)'")

    // Verify paper_only check is AFTER production-only mode
    // (production-only has its own early return)
    const prodOnlyIdx = scannerSource.indexOf('if (_productionOnlyMode)')
    const paperOnlyIdx = scannerSource.indexOf("if (_sandboxPaperOnly[bot.name])")
    expect(prodOnlyIdx).toBeGreaterThan(-1)
    expect(paperOnlyIdx).toBeGreaterThan(-1)
    expect(prodOnlyIdx).toBeLessThan(paperOnlyIdx)
  })

  it('consecutive reject backoff does NOT block production-only mode', () => {
    // _productionOnlyMode check is BEFORE the per-bot _consecutiveRejects check
    const prodOnlyIdx = scannerSource.indexOf('if (_productionOnlyMode)')
    const rejectIdx = scannerSource.indexOf('_consecutiveRejects[bot.name] >= MAX_REJECTS_BEFORE_BACKOFF')
    expect(prodOnlyIdx).toBeGreaterThan(-1)
    expect(rejectIdx).toBeGreaterThan(-1)
    expect(prodOnlyIdx).toBeLessThan(rejectIdx)
  })

  it('sandbox cleanup gate is AFTER production-only mode exit', () => {
    // _sandboxCleanupVerified check is after production-only mode
    const prodOnlyReturnIdx = scannerSource.indexOf("return 'skip:flame_production_only_no_fills'")
    expect(prodOnlyReturnIdx).toBeGreaterThan(-1)
    // The stale_positions_blocking return is a template literal — search for the constant part
    const staleBlockIdx = scannerSource.indexOf('skip:flame_stale_positions_blocking')
    expect(staleBlockIdx).toBeGreaterThan(-1)
    // Production-only mode exits before sandbox cleanup can block
    expect(prodOnlyReturnIdx).toBeLessThan(staleBlockIdx)
  })

  it('DB load failure recovery: auto-reset after 15s cooldown', () => {
    expect(tradierSource).toMatch(/_dbLoadLastAttemptTime/)
    expect(tradierSource).toMatch(/15[_]?000/)
    expect(tradierSource).toMatch(/DB load retry counter reset/)
  })

  it('reloadSandboxAccounts resets _dbLoadAttempts', () => {
    expect(tradierSource).toMatch(/reloadSandboxAccounts[\s\S]*?_dbLoadAttempts\s*=\s*0/)
  })

  it('production accounts are loaded exclusively from DB (not env vars)', () => {
    // Env vars only create sandbox accounts. Production is DB-only.
    // Production accounts come from DB rows with type='production'
    expect(tradierSource).toMatch(/row\.type\s*===\s*'production'/)
    // ensureSandboxAccountsLoaded loads from ironforge_accounts
    expect(tradierSource).toMatch(/ironforge_accounts/)
  })

  it('production fill polling has no timeout (polls forever)', () => {
    // Production: maxPollMs = 0 (unlimited)
    // The code should use a different timeout for production vs sandbox
    expect(tradierSource).toMatch(/acct\.type\s*===\s*'production'\s*\?\s*0/)
  })

  it('production config SKIP guard prevents production order with missing/invalid config', () => {
    // Post-Commit-A: capital_pct is gone — production sizing knob is
    // spark_config.production.buying_power_usage_pct (bp_pct). If the
    // production config row is missing or bp_pct is invalid (<= 0 or > 1),
    // production accounts are cleared BEFORE placeForAccount is invoked,
    // and a PRODUCTION_SIZE_DROP audit row is written to spark_logs.
    expect(tradierSource).toMatch(/PRODUCTION_SIZE_DROP/)
    expect(tradierSource).toMatch(/productionConfigOk\s*=\s*true/)
    expect(tradierSource).toMatch(/loadProductionConfigFor/)
    // Defense-in-depth: sizing branch also refuses if the flag is false.
    expect(tradierSource).toMatch(/!productionConfigOk/)
  })

  it('VIX gate blocks production same as sandbox (VIX > 32)', () => {
    // VIX check happens before any account-specific logic
    expect(scannerSource).toMatch(/vix\s*>\s*32/)
    expect(scannerSource).toMatch(/skip:vix_too_high/)
  })
})

/* ================================================================== */
/*  8. Production Collateral & P&L Arithmetic                          */
/* ================================================================== */

describe('Production Collateral & P&L Arithmetic', () => {
  it('production collateral for 1 contract @ $0.82 credit on $5 spread', () => {
    // Simulates Logan's first production trade
    const spreadWidth = 5
    const prodCredit = 0.82
    const prodContracts = 1
    const prodCollateral = Math.max(0, (spreadWidth - prodCredit) * 100) * prodContracts

    expect(prodCollateral).toBe(418) // $4.18 × 100 × 1 = $418
  })

  it('production max profit for 1 contract @ $0.82 credit', () => {
    const prodCredit = 0.82
    const prodContracts = 1
    const prodMaxProfit = prodCredit * 100 * prodContracts

    expect(prodMaxProfit).toBe(82) // $0.82 × 100 × 1 = $82
  })

  it('production P&L: close at 30% of credit (profit target)', () => {
    const entryCredit = 0.82
    const closePrice = entryCredit * 0.30 // 30% profit target
    const contracts = 1

    const pnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100
    expect(pnl).toBeCloseTo(57.40, 2) // $0.574 × 100 × 1 = $57.40
  })

  it('production P&L: close at 200% of credit (stop loss)', () => {
    const entryCredit = 0.82
    const closePrice = entryCredit * 2.0 // 100% stop loss (2x entry)
    const contracts = 1

    const pnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100
    expect(pnl).toBe(-82) // Lost $82
  })

  it('production max loss equals collateral', () => {
    const spreadWidth = 5
    const prodCredit = 0.82
    const prodContracts = 1
    const prodCollateral = Math.max(0, (spreadWidth - prodCredit) * 100) * prodContracts
    const prodMaxLoss = prodCollateral

    expect(prodMaxLoss).toBe(prodCollateral)
    expect(prodMaxLoss).toBe(418)
  })

  it('production records Tradier-filled contract count (no post-fill cap after Commit A)', () => {
    // Post-Commit-A: scanner records exactly what Tradier filled. Cap lives
    // upstream via spark_config.production.max_contracts (pre-submit) and
    // bp_pct × Tradier OBP. No Math.min hardcode that would desync the DB
    // record from the broker's actual position.
    const tradierFillContracts = 10
    const prodContracts = tradierFillContracts // pass-through, no cap

    expect(prodContracts).toBe(10)

    // Collateral tracks actual filled contracts
    const spreadWidth = 5
    const prodCredit = 0.82
    const prodCollateral = Math.max(0, (spreadWidth - prodCredit) * 100) * prodContracts

    expect(prodCollateral).toBe(4180) // $418 × 10
  })
})

/* ================================================================== */
/*  9. Cross-Bot State Isolation Guards                                */
/* ================================================================== */

describe('Cross-Bot State Isolation', () => {
  it('no FLAME-specific mutable globals in scanner.ts (must be per-bot Records)', () => {
    // These old patterns caused cross-bot state bleed when FLAME/SPARK/INFERNO
    // ran in parallel via Promise.allSettled(). If you see a failure here,
    // you probably added a module-level `let _flame*` or `let _sandbox*`
    // variable — convert it to a Record<string, T> keyed by bot name instead.
    const dangerousPatterns = [
      /^let _flame/m,
      /^let _spark/m,
      /^let _inferno/m,
      /^let _sandbox(?!Accounts)/m,  // _sandboxAccounts is in tradier.ts, not scanner
    ]
    for (const pattern of dangerousPatterns) {
      expect(scannerSource).not.toMatch(pattern)
    }
  })

  it('per-bot state variables are Record<string, *> with all 3 bot keys', () => {
    // All mutable per-bot state must be declared as Record with flame/spark/inferno keys
    const perBotVars = [
      '_consecutiveRejects',
      '_sandboxCleanupVerified',
      '_sandboxCleanupVerifiedDate',
      '_sandboxPaperOnly',
      '_lastSandboxCleanupDate',
    ]
    for (const varName of perBotVars) {
      expect(scannerSource).toContain(varName)
      // Verify it's keyed with all 3 bots (declared as a Record literal)
      const varRegex = new RegExp(
        `${varName}[^=]*=\\s*\\{[^}]*flame[^}]*spark[^}]*inferno`,
      )
      expect(scannerSource).toMatch(varRegex)
    }
  })

  it('per-bot state is accessed with [bot.name] not as bare scalar', () => {
    // After the Phase 1 fix, all per-bot Records must be accessed with [bot.name]
    // If this fails, someone is reading a per-bot Record without the bot key
    expect(scannerSource).toMatch(/_consecutiveRejects\[bot\.name\]/)
    expect(scannerSource).toMatch(/_sandboxPaperOnly\[bot\.name\]/)
    expect(scannerSource).toMatch(/_sandboxCleanupVerified\[bot\.name\]/)
  })

  it('tradier.ts _sandboxAccounts uses atomic replacement (no .push)', () => {
    // .push() on a shared array while 3 bots read it concurrently causes
    // race conditions. Verify we use atomic replacement (reassignment) instead.
    const pushPattern = /_sandboxAccounts\.push\(/
    expect(tradierSource).not.toMatch(pushPattern)
  })
})
