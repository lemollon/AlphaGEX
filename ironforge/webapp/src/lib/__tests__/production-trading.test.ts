/**
 * Production Trading Tests — verifies the production trading code paths
 * for FLAME's Iron Viper (Logan) production account.
 *
 * Tests cover:
 *   1. getCapitalPctForAccount — sandbox vs production behavior
 *   2. placeIcOrderAllAccounts — production account separation (structural)
 *   3. Scanner production position recording (structural)
 *   4. _productionOnlyMode flow (structural)
 *   5. Force-trade production support (structural)
 *   6. Close position production support (structural)
 *   7. DB schema production columns (structural)
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

vi.mock('../db', () => ({
  query: (...args: any[]) => mockQuery(...args),
  dbQuery: (...args: any[]) => mockQuery(...args),
  dbExecute: vi.fn().mockResolvedValue(1),
  botTable: (bot: string, table: string) => `${bot}_${table}`,
  sharedTable: (table: string) => table,
  validateBot: (bot: string) => bot,
  dteMode: (bot: string) => bot === 'inferno' ? '0DTE' : bot === 'spark' ? '1DTE' : '2DTE',
  num: (v: any) => parseFloat(v) || 0,
  int: (v: any) => parseInt(v) || 0,
  escapeSql: (v: string) => v,
  CT_TODAY: "'2026-03-21'",
}))

/* ── Mock fetch (for Tradier API calls) ─────────────────────────────── */

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

/* ── Source code reading for structural tests ────────────────────────── */

const TRADIER_PATH = path.resolve(__dirname, '../tradier.ts')
const SCANNER_PATH = path.resolve(__dirname, '../scanner.ts')
const DB_PATH = path.resolve(__dirname, '../db.ts')
const FORCE_TRADE_PATH = path.resolve(__dirname, '../../app/api/[bot]/force-trade/route.ts')

const tradierSource = fs.readFileSync(TRADIER_PATH, 'utf-8')
const scannerSource = fs.readFileSync(SCANNER_PATH, 'utf-8')
const dbSource = fs.readFileSync(DB_PATH, 'utf-8')
const forceTradeSource = fs.readFileSync(FORCE_TRADE_PATH, 'utf-8')

beforeEach(() => {
  mockQuery.mockReset().mockResolvedValue([])
  mockFetch.mockReset()
})

/* ================================================================== */
/*  1. getCapitalPctForAccount — Production vs Sandbox                 */
/* ================================================================== */

describe('getCapitalPctForAccount', () => {
  // Dynamic import to use mocked db
  let getCapitalPctForAccount: (person: string, accountType?: 'sandbox' | 'production') => Promise<number>

  beforeEach(async () => {
    const mod = await import('../tradier')
    getCapitalPctForAccount = mod.getCapitalPctForAccount
  })

  it('sandbox always returns 100% (never reads DB)', async () => {
    const result = await getCapitalPctForAccount('User', 'sandbox')
    expect(result).toBe(100)
    // DB should NOT be called for sandbox
    expect(mockQuery).not.toHaveBeenCalled()
  })

  it('undefined accountType returns 100% (treated as sandbox)', async () => {
    const result = await getCapitalPctForAccount('User')
    expect(result).toBe(100)
    expect(mockQuery).not.toHaveBeenCalled()
  })

  it('production reads capital_pct from DB', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 15 }])
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(15)
    expect(mockQuery).toHaveBeenCalledWith(
      expect.stringContaining('capital_pct'),
    )
  })

  it('production with capital_pct=50 returns 50', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 50 }])
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(50)
  })

  it('production with NULL capital_pct defaults to 100', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: null }])
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(100)
  })

  it('production with no DB rows defaults to 100', async () => {
    mockQuery.mockResolvedValueOnce([])
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(100)
  })

  it('production with out-of-range value (0) defaults to 100', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 0 }])
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(100)
  })

  it('production with out-of-range value (101) defaults to 100', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 101 }])
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(100)
  })

  it('production with DB error defaults to 100', async () => {
    mockQuery.mockRejectedValueOnce(new Error('DB connection failed'))
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(100)
  })

  it('production boundary: capital_pct=1 is valid (minimum)', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 1 }])
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(1)
  })

  it('production boundary: capital_pct=100 is valid (maximum)', async () => {
    mockQuery.mockResolvedValueOnce([{ capital_pct: 100 }])
    const result = await getCapitalPctForAccount('Logan', 'production')
    expect(result).toBe(100)
  })
})

/* ================================================================== */
/*  2. placeIcOrderAllAccounts — Production Account Separation         */
/* ================================================================== */

describe('placeIcOrderAllAccounts — Production Account Handling (Structural)', () => {
  it('separates production accounts from sandbox accounts', () => {
    // The function should filter accounts by type
    expect(tradierSource).toMatch(/\.filter\(.*\.type\s*===\s*'production'/)
    expect(tradierSource).toMatch(/\.filter\(.*\.type\s*!==\s*'production'/)
  })

  it('places production orders INDEPENDENTLY of sandbox', () => {
    // Comment or code confirming production runs independently
    expect(tradierSource).toMatch(/production.*independent/i)
  })

  it('uses api.tradier.com for production accounts', () => {
    expect(tradierSource).toContain('api.tradier.com')
  })

  it('uses sandbox.tradier.com for sandbox accounts', () => {
    expect(tradierSource).toContain('sandbox.tradier.com')
  })

  it('skips production account when capital_pct lookup fails', () => {
    // The ABORT guard for production
    expect(tradierSource).toMatch(/PRODUCTION.*capital_pct.*SKIP/i)
  })

  it('calls getCapitalPctForAccount for each account', () => {
    expect(tradierSource).toMatch(/getCapitalPctForAccount/)
  })

  it('returns results keyed by person:account_type', () => {
    // Results use format like "Logan:production"
    expect(tradierSource).toMatch(/`\$\{.*\.name\}:\$\{.*\.type/)
  })
})

/* ================================================================== */
/*  3. Scanner — Production Position Recording                         */
/* ================================================================== */

describe('Scanner Production Position Recording (Structural)', () => {
  it('defines PRODUCTION_MAX_CONTRACTS safety cap', () => {
    expect(scannerSource).toMatch(/PRODUCTION_MAX_CONTRACTS\s*=\s*2/)
  })

  it('filters production fills by account_type', () => {
    expect(scannerSource).toMatch(/account_type\s*!==\s*'production'/)
  })

  it('inserts production positions with account_type = production', () => {
    // The INSERT should include 'production' for account_type
    expect(scannerSource).toMatch(/open.*NOW\(\).*production/s)
  })

  it('records person on production positions', () => {
    // Production positions track which person they belong to
    expect(scannerSource).toMatch(/prodPerson/)
  })

  it('caps production contracts at PRODUCTION_MAX_CONTRACTS', () => {
    expect(scannerSource).toMatch(/Math\.min\(.*PRODUCTION_MAX_CONTRACTS\)/)
  })

  it('deducts collateral from production paper_account', () => {
    // UPDATE paper_account WHERE account_type = 'production' AND person = ...
    expect(scannerSource).toMatch(/account_type\s*=\s*'production'\s*AND\s*person/)
  })

  it('logs production orders with PRODUCTION_ORDER level', () => {
    expect(scannerSource).toContain("'PRODUCTION_ORDER'")
  })
})

/* ================================================================== */
/*  4. _productionOnlyMode Flow                                        */
/* ================================================================== */

describe('_productionOnlyMode (Structural)', () => {
  it('defines _productionOnlyMode variable', () => {
    expect(scannerSource).toMatch(/let\s+_productionOnlyMode\s*=\s*false/)
  })

  it('checks if production traded today before enabling production-only mode', () => {
    expect(scannerSource).toMatch(/account_type\s*=\s*'production'/)
    expect(scannerSource).toMatch(/prodTradedToday/)
  })

  it('sets _productionOnlyMode = true when sandbox traded but production has not', () => {
    expect(scannerSource).toMatch(/_productionOnlyMode\s*=\s*true/)
  })

  it('logs entry into production-only mode', () => {
    expect(scannerSource).toMatch(/production-only mode/i)
  })

  it('creates production position IDs with -prod- suffix', () => {
    expect(scannerSource).toMatch(/-prod-/)
  })

  it('calls placeIcOrderAllAccounts in production-only mode', () => {
    // Inside the _productionOnlyMode block
    const prodOnlyBlock = scannerSource.match(/if\s*\(_productionOnlyMode\)\s*\{[\s\S]*?(?=\n  \} else |\/\/ ── )/)?.[0] ?? ''
    expect(prodOnlyBlock).toContain('placeIcOrderAllAccounts')
  })

  it('only records production fills in production-only mode (skips sandbox)', () => {
    const prodOnlyBlock = scannerSource.match(/if\s*\(_productionOnlyMode\)\s*\{[\s\S]*?(?=\n  \} else |\/\/ ── )/)?.[0] ?? ''
    expect(prodOnlyBlock).toMatch(/account_type\s*!==\s*'production'.*continue/s)
  })
})

/* ================================================================== */
/*  5. Force-Trade Production Support                                  */
/* ================================================================== */

describe('Force-Trade Production Support (Structural)', () => {
  it('reads account_type from query parameters', () => {
    expect(forceTradeSource).toMatch(/searchParams\.get\(\s*'account_type'\s*\)/)
  })

  it('filters paper_account by account_type', () => {
    expect(forceTradeSource).toMatch(/account_type\s*=\s*'production'/)
  })

  it('inserts position with account_type value', () => {
    // The INSERT should use the accountType variable
    expect(forceTradeSource).toMatch(/account_type/)
    expect(forceTradeSource).toMatch(/accountType/)
  })

  it('calls placeIcOrderAllAccounts to mirror orders', () => {
    expect(forceTradeSource).toContain('placeIcOrderAllAccounts')
  })
})

/* ================================================================== */
/*  6. Close Position — Production Support                             */
/* ================================================================== */

describe('Close Position Production Support (Structural)', () => {
  it('closeIcOrderAllAccounts function exists', () => {
    expect(tradierSource).toMatch(/export\s+async\s+function\s+closeIcOrderAllAccounts/)
  })

  it('close logic iterates over all loaded accounts including production', () => {
    // The close function should iterate _sandboxAccounts (which includes production)
    expect(tradierSource).toMatch(/closeIcOrderAllAccounts[\s\S]*?_sandboxAccounts\.map/)
  })

  it('close results include account type in key', () => {
    // Results keyed like "Logan:production"
    expect(tradierSource).toMatch(/`\$\{.*\.name\}:\$\{.*\.type/)
  })
})

/* ================================================================== */
/*  7. DB Schema — Production Columns                                  */
/* ================================================================== */

describe('DB Schema Production Columns (Structural)', () => {
  it('adds capital_pct column to ironforge_accounts', () => {
    expect(dbSource).toMatch(/ALTER TABLE.*ironforge_accounts.*ADD COLUMN.*capital_pct/s)
  })

  it('adds pdt_enabled column to ironforge_accounts', () => {
    expect(dbSource).toMatch(/ALTER TABLE.*ironforge_accounts.*ADD COLUMN.*pdt_enabled/s)
  })

  it('adds account_type column to bot tables (positions, paper_account, etc.)', () => {
    // The migration iterates over bot tables dynamically: `${bot}_positions`, `${bot}_paper_account`, etc.
    // The for-loop lists these tables and adds account_type to each
    expect(dbSource).toMatch(/positions.*paper_account.*ADD COLUMN IF NOT EXISTS account_type/s)
  })

  it('adds person column to paper_account tables', () => {
    expect(dbSource).toMatch(/paper_account.*ADD COLUMN.*person/)
  })

  it('seeds production paper_account for Logan', () => {
    expect(dbSource).toMatch(/production.*Logan/s)
    expect(dbSource).toMatch(/flame_paper_account/)
  })

  it('ensures FLAME is assigned to Logan production account', () => {
    expect(dbSource).toMatch(/FLAME.*Logan.*production/s)
  })

  it('defaults account_type to sandbox', () => {
    expect(dbSource).toMatch(/account_type.*DEFAULT\s*'sandbox'/)
  })

  it('defaults capital_pct to 100', () => {
    expect(dbSource).toMatch(/capital_pct.*DEFAULT\s*100/)
  })
})
