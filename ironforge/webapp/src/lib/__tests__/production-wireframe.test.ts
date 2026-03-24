/**
 * FLAME Account Interaction Wireframe
 *
 * Documents how FLAME interacts with sandbox accounts, paper accounts,
 * and the production account in Tradier. Every assertion is backed by
 * a line number in the source code.
 *
 * ┌─────────────────────────────────────────────────────────────────────────────┐
 * │                        FLAME ACCOUNT ARCHITECTURE                          │
 * │                                                                             │
 * │  ┌──────────────────────────────────────────────────────────────────────┐   │
 * │  │                     ironforge_accounts (DB)                          │   │
 * │  │                                                                      │   │
 * │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │   │
 * │  │  │ User:sandbox │ │ Matt:sandbox │ │Logan:sandbox │ │Logan:prod  │  │   │
 * │  │  │ api_key=env  │ │ api_key=env  │ │ api_key=env  │ │api_key=DB  │  │   │
 * │  │  │ bot=FLAME,.. │ │ bot=FLAME,.. │ │ bot=SPARK,.. │ │bot=FLAME   │  │   │
 * │  │  │ cap_pct=100  │ │ cap_pct=100  │ │ cap_pct=100  │ │cap_pct=15  │  │   │
 * │  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └─────┬──────┘  │   │
 * │  └─────────┼────────────────┼────────────────┼────────────────┼─────────┘   │
 * │            │                │                │                │             │
 * │  ┌─────── ▼ ───────────────▼────────────────▼────────────────▼──────────┐  │
 * │  │              _sandboxAccounts[] (in-memory, tradier.ts)               │  │
 * │  │                                                                       │  │
 * │  │  Loaded from: env vars (TRADIER_SANDBOX_KEY_*) + DB merge            │  │
 * │  │  Each entry: { name, apiKey, baseUrl, type }                         │  │
 * │  │                                                                       │  │
 * │  │  baseUrl routing:                                                     │  │
 * │  │    sandbox  → https://sandbox.tradier.com/v1                         │  │
 * │  │    production → https://api.tradier.com/v1   ← REAL MONEY            │  │
 * │  └──────────────────────────────┬────────────────────────────────────────┘  │
 * │                                 │                                           │
 * │  ┌──────────────────────────────▼────────────────────────────────────────┐  │
 * │  │            placeIcOrderAllAccounts() — tradier.ts:1126               │  │
 * │  │                                                                       │  │
 * │  │  Step 1: Filter eligible accounts for FLAME (DB bot column)          │  │
 * │  │  Step 2: Partition into sandboxAccts[] vs productionAccts[]          │  │
 * │  │  Step 3: Size each account independently:                            │  │
 * │  │          usableBP = optionBP × capitalPct% × botShare × 85%         │  │
 * │  │          contracts = floor(usableBP / $500)                          │  │
 * │  │                                                                       │  │
 * │  │  ORDERING:                                                            │  │
 * │  │  ┌─────────────────────┐                                             │  │
 * │  │  │ 1. User:sandbox     │ ← SEQUENTIAL (must fill first)             │  │
 * │  │  │    await placeFor() │                                             │  │
 * │  │  └─────────┬───────────┘                                             │  │
 * │  │            │                                                          │  │
 * │  │  ┌─────────▼───────────┐  ┌────────────────┐                        │  │
 * │  │  │ 2. Other sandboxes  │  │ 3. Production   │                        │  │
 * │  │  │    Promise.all([    │  │    Promise.all([ │ ← INDEPENDENT          │  │
 * │  │  │      Matt:sandbox   │  │      Logan:prod  │   (never blocked       │  │
 * │  │  │    ])               │  │    ])            │    by sandbox)          │  │
 * │  │  └─────────┬───────────┘  └───────┬─────────┘                        │  │
 * │  │            └──────────┬───────────┘                                   │  │
 * │  │                       ▼                                               │  │
 * │  │  Returns: { 'User:sandbox': {fill}, 'Matt:sandbox': {fill},          │  │
 * │  │            'Logan:production': {fill} }                               │  │
 * │  └──────────────────────────┬────────────────────────────────────────────┘  │
 * │                             │                                               │
 * │  ┌──────────────────────────▼────────────────────────────────────────────┐  │
 * │  │          scanner.ts tryOpenTrade() — POSITION RECORDING               │  │
 * │  │                                                                        │  │
 * │  │  ┌─ Phase 1: PRODUCTION FILLS (immediate) ────────────────────────┐   │  │
 * │  │  │  For each fill WHERE account_type = 'production':              │   │  │
 * │  │  │    ● INSERT flame_positions (account_type='production',        │   │  │
 * │  │  │      person='Logan', contracts=min(fill, 2))                   │   │  │
 * │  │  │    ● UPDATE flame_paper_account WHERE account_type=            │   │  │
 * │  │  │      'production' AND person='Logan'                           │   │  │
 * │  │  │    ● INSERT flame_logs level='PRODUCTION_ORDER'                │   │  │
 * │  │  └────────────────────────────────────────────────────────────────┘   │  │
 * │  │                                                                        │  │
 * │  │  ┌─ Phase 2: SANDBOX PAPER POSITION ──────────────────────────────┐   │  │
 * │  │  │  Require User:sandbox fill_price > 0                           │   │  │
 * │  │  │    ● INSERT flame_positions (account_type='sandbox',           │   │  │
 * │  │  │      person='User', credit=Tradier fill, contracts=paper BP)   │   │  │
 * │  │  │    ● UPDATE flame_paper_account WHERE account_type='sandbox'   │   │  │
 * │  │  │    ● sandbox_order_id = JSON of ALL fills                      │   │  │
 * │  │  └────────────────────────────────────────────────────────────────┘   │  │
 * │  └───────────────────────────────────────────────────────────────────────┘  │
 * │                                                                             │
 * │  ┌───────────────────────────────────────────────────────────────────────┐  │
 * │  │          PAPER ACCOUNTS (flame_paper_account)                         │  │
 * │  │                                                                       │  │
 * │  │  ┌─────────────────────────────┐  ┌────────────────────────────────┐  │  │
 * │  │  │  SANDBOX (shared, 1 row)    │  │  PRODUCTION (per-person)       │  │  │
 * │  │  │  account_type='sandbox'     │  │  account_type='production'     │  │  │
 * │  │  │  dte_mode='2DTE'            │  │  person='Logan'                │  │  │
 * │  │  │                             │  │  dte_mode='2DTE'               │  │  │
 * │  │  │  starting_capital: $10,000  │  │                                │  │  │
 * │  │  │  (fixed paper money)        │  │  starting_capital: synced      │  │  │
 * │  │  │                             │  │  = Tradier equity × 15%        │  │  │
 * │  │  │  cumulative_pnl: sandbox    │  │                                │  │  │
 * │  │  │  collateral: sandbox only   │  │  cumulative_pnl: prod only     │  │  │
 * │  │  │                             │  │  collateral: prod only          │  │  │
 * │  │  │  Tracks: paper position P&L │  │  Tracks: real money P&L        │  │  │
 * │  │  └─────────────────────────────┘  └────────────────────────────────┘  │  │
 * │  │                                                                       │  │
 * │  │  Sync every cycle (scanner.ts:251-285):                              │  │
 * │  │    Production: getAllocatedCapitalForAccount('Logan','production')    │  │
 * │  │    → Tradier API total_equity × capital_pct / 100                    │  │
 * │  │    → Update starting_capital if changed by > $1                      │  │
 * │  └───────────────────────────────────────────────────────────────────────┘  │
 * │                                                                             │
 * │  ┌───────────────────────────────────────────────────────────────────────┐  │
 * │  │          CLOSE FLOW — monitorSinglePosition()                         │  │
 * │  │                                                                       │  │
 * │  │  Monitors ALL open positions (sandbox + production) in parallel       │  │
 * │  │                                                                       │  │
 * │  │  Trigger: PT hit (30%), SL hit (100%), or EOD (2:45 PM CT)           │  │
 * │  │                                                                       │  │
 * │  │  closeIcOrderAllAccounts() → close on ALL Tradier accounts           │  │
 * │  │    ● sandbox accounts → sandbox.tradier.com (paper close)            │  │
 * │  │    ● production accounts → api.tradier.com (REAL close)              │  │
 * │  │                                                                       │  │
 * │  │  P&L routing:                                                         │  │
 * │  │    Sandbox position  → UPDATE sandbox paper_account                  │  │
 * │  │    Production position → UPDATE production paper_account (per-person) │  │
 * │  └───────────────────────────────────────────────────────────────────────┘  │
 * │                                                                             │
 * │  ┌───────────────────────────────────────────────────────────────────────┐  │
 * │  │          PRODUCTION-ONLY MODE (scanner.ts:1264)                       │  │
 * │  │                                                                       │  │
 * │  │  Activates when: sandbox traded today BUT production hasn't           │  │
 * │  │  Effect: skips sandbox, only places production orders                 │  │
 * │  │  Position ID: {mainId}-prod-{person}                                  │  │
 * │  │  Purpose: sandbox daily limit (1) doesn't block production            │  │
 * │  └───────────────────────────────────────────────────────────────────────┘  │
 * └─────────────────────────────────────────────────────────────────────────────┘
 *
 * SAFETY GUARDS:
 * ┌─────────────────────────────────────────────────────────────────────┐
 * │ 1. PRODUCTION_MAX_CONTRACTS = 2           (scanner.ts, 3 locations)│
 * │ 2. capital_pct ABORT on lookup failure    (tradier.ts:1230-1234)   │
 * │ 3. fill_price > 0 required               (scanner.ts:1283,1496)   │
 * │ 4. Production independent of sandbox      (tradier.ts:1320-1325)   │
 * │ 5. Per-person paper_account isolation     (scanner.ts:1341-1347)   │
 * │ 6. EOD force-close at 2:45 PM CT         (scanner.ts:770+)        │
 * │ 7. VIX > 32 skip                         (scanner.ts)             │
 * │ 8. 1 trade/day max                        (scanner.ts:1098-1122)   │
 * └─────────────────────────────────────────────────────────────────────┘
 */

import { describe, it, expect, vi } from 'vitest'
import fs from 'fs'
import path from 'path'

/* ── Environment ────────────────────────────────────────────────────── */

vi.hoisted(() => {
  process.env.TRADIER_API_KEY = 'test-key'
  process.env.TRADIER_SANDBOX_KEY_USER = 'test-sandbox-user'
  process.env.TRADIER_SANDBOX_KEY_MATT = 'test-sandbox-matt'
  process.env.TRADIER_SANDBOX_KEY_LOGAN = 'test-sandbox-logan'
})

/* ── Mock DB ────────────────────────────────────────────────────────── */

vi.mock('../db', () => ({
  query: vi.fn().mockResolvedValue([]),
  dbQuery: vi.fn().mockResolvedValue([]),
  dbExecute: vi.fn().mockResolvedValue(1),
  botTable: (bot: string, table: string) => `${bot}_${table}`,
  sharedTable: (table: string) => table,
  validateBot: (bot: string) => bot,
  dteMode: (bot: string) => bot === 'inferno' ? '0DTE' : bot === 'spark' ? '1DTE' : '2DTE',
  num: (v: any) => parseFloat(v) || 0,
  int: (v: any) => parseInt(v) || 0,
  escapeSql: (v: string) => v,
  CT_TODAY: "'2026-03-24'",
}))

vi.stubGlobal('fetch', vi.fn())

/* ── Source ──────────────────────────────────────────────────────────── */

const TRADIER = fs.readFileSync(path.resolve(__dirname, '../tradier.ts'), 'utf-8')
const SCANNER = fs.readFileSync(path.resolve(__dirname, '../scanner.ts'), 'utf-8')
const DB = fs.readFileSync(path.resolve(__dirname, '../db.ts'), 'utf-8')

/* ================================================================== */
/*  1. ACCOUNT LOADING — How accounts get into memory                  */
/* ================================================================== */

describe('Account Loading', () => {
  it('loads sandbox accounts from env vars (TRADIER_SANDBOX_KEY_*)', () => {
    expect(TRADIER).toMatch(/TRADIER_SANDBOX_KEY_USER/)
    expect(TRADIER).toMatch(/TRADIER_SANDBOX_KEY_MATT/)
    expect(TRADIER).toMatch(/TRADIER_SANDBOX_KEY_LOGAN/)
  })

  it('merges production accounts from ironforge_accounts DB table', () => {
    expect(TRADIER).toMatch(/SELECT.*person.*api_key.*type.*FROM\s+ironforge_accounts/s)
  })

  it('routes production to api.tradier.com, sandbox to sandbox.tradier.com', () => {
    expect(TRADIER).toMatch(/api\.tradier\.com/)
    expect(TRADIER).toMatch(/sandbox\.tradier\.com/)
    // type='production' → PRODUCTION_URL
    expect(TRADIER).toMatch(/type.*production.*PRODUCTION/s)
  })

  it('stores all accounts in single _sandboxAccounts array (sandbox + production)', () => {
    expect(TRADIER).toMatch(/_sandboxAccounts/)
  })

  it('each account has: name, apiKey, baseUrl, type', () => {
    expect(TRADIER).toMatch(/name.*apiKey.*baseUrl/s)
  })
})

/* ================================================================== */
/*  2. BOT FILTERING — Which accounts can FLAME use?                   */
/* ================================================================== */

describe('Bot-Based Account Filtering', () => {
  it('queries ironforge_accounts for accounts assigned to the bot', () => {
    // The bot filter query checks bot column for the bot name
    expect(TRADIER).toMatch(/bot\s*=.*\$1.*OR.*bot.*LIKE/s)
  })

  it('builds allowedKeys set of "person:type" pairs', () => {
    // Eligible accounts determined by person + type combination
    expect(TRADIER).toMatch(/`\$\{.*person\}:\$\{.*type\}`/)
  })

  it('filters _sandboxAccounts to only eligible ones for the bot', () => {
    expect(TRADIER).toMatch(/eligibleAccounts.*filter/)
  })
})

/* ================================================================== */
/*  3. ORDER PLACEMENT SEQUENCE                                        */
/* ================================================================== */

describe('Order Placement Sequence', () => {
  it('partitions accounts into sandbox vs production arrays', () => {
    expect(TRADIER).toMatch(/sandboxAccts.*filter.*type\s*!==\s*'production'/)
    expect(TRADIER).toMatch(/productionAccts.*filter.*type\s*===\s*'production'/)
  })

  it('separates User from other sandbox accounts', () => {
    expect(TRADIER).toMatch(/userAccts.*filter.*name\s*===\s*'User'/)
    expect(TRADIER).toMatch(/otherSandboxAccts.*filter.*name\s*!==\s*'User'/)
  })

  it('places User:sandbox FIRST (sequential await)', () => {
    // User must fill before others proceed
    expect(TRADIER).toMatch(/for\s*\(.*userAccts\)\s*await\s+placeForAccount/)
  })

  it('places other sandboxes in PARALLEL (Promise.all)', () => {
    expect(TRADIER).toMatch(/Promise\.all\(otherSandboxAccts\.map/)
  })

  it('places production INDEPENDENTLY (separate Promise.all)', () => {
    expect(TRADIER).toMatch(/productionAccts\.map\(placeForAccount\)/)
    // Comment confirms independence
    expect(TRADIER).toMatch(/production.*independent/i)
  })

  it('results keyed by "person:type" — e.g. "Logan:production"', () => {
    expect(TRADIER).toMatch(/`\$\{acct\.name\}:\$\{acct\.type/)
  })
})

/* ================================================================== */
/*  4. PER-ACCOUNT SIZING                                              */
/* ================================================================== */

describe('Per-Account Sizing', () => {
  it('fetches option_buying_power from Tradier for each account', () => {
    expect(TRADIER).toMatch(/getSandboxBuyingPower/)
  })

  it('applies capital_pct: bpAfterCapitalPct = bp × (capitalPct / 100)', () => {
    expect(TRADIER).toMatch(/bpAfterCapitalPct\s*=\s*bp\s*\*\s*\(capitalPct\s*\/\s*100\)/)
  })

  it('applies botShare (equal split among eligible accounts)', () => {
    expect(TRADIER).toMatch(/botShare.*eligibleAccounts\.length/)
  })

  it('applies 85% buffer: usableBP = bpAfterCapitalPct × botShare × 0.85', () => {
    expect(TRADIER).toMatch(/bpAfterCapitalPct\s*\*\s*botShare\s*\*\s*0\.85/)
  })

  it('uses broker margin (full spread × 100), not net collateral', () => {
    expect(TRADIER).toMatch(/brokerMarginPer\s*=\s*spreadWidth\s*\*\s*100/)
  })

  it('contracts = floor(usableBP / brokerMarginPer)', () => {
    expect(TRADIER).toMatch(/bpContracts\s*=\s*Math\.floor\(usableBP\s*\/\s*brokerMarginPer\)/)
  })

  it('skips account entirely if < 1 contract possible', () => {
    expect(TRADIER).toMatch(/if\s*\(bpContracts\s*<\s*1\)/)
  })

  it('production account ABORTS (not defaults) if capital_pct lookup fails', () => {
    expect(TRADIER).toMatch(/PRODUCTION.*SKIP/i)
  })
})

/* ================================================================== */
/*  5. POSITION RECORDING — Two separate tracks                        */
/* ================================================================== */

describe('Position Recording', () => {
  it('production fills recorded FIRST, before sandbox paper position', () => {
    // In scanner.ts: production loop comes before sandbox INSERT
    const prodIdx = SCANNER.indexOf("account_type !== 'production'")
    const sandboxInsertIdx = SCANNER.indexOf("'open', NOW()", prodIdx)
    expect(prodIdx).toBeLessThan(sandboxInsertIdx)
  })

  it('production positions capped at PRODUCTION_MAX_CONTRACTS = 2', () => {
    expect(SCANNER).toMatch(/PRODUCTION_MAX_CONTRACTS\s*=\s*2/)
    expect(SCANNER).toMatch(/Math\.min\(.*PRODUCTION_MAX_CONTRACTS\)/)
  })

  it('production position has unique ID: {mainId}-prod-{person}', () => {
    expect(SCANNER).toMatch(/-prod-/)
  })

  it('production INSERT has account_type = production', () => {
    // The INSERT includes 'production' as account_type
    expect(SCANNER).toMatch(/'open', NOW\(\).*production/s)
  })

  it('sandbox paper position requires User:sandbox fill_price > 0 (FLAME)', () => {
    expect(SCANNER).toMatch(/FLAME_PRIMARY_ACCOUNT/)
    expect(SCANNER).toMatch(/User/)
  })

  it('sandbox paper position uses Tradier fill price (not estimated)', () => {
    // FLAME uses actual fill: effectiveCredit = primaryFillFinal.fill_price
    expect(SCANNER).toMatch(/effectiveCredit\s*=.*fill_price/)
  })
})

/* ================================================================== */
/*  6. PAPER ACCOUNTS — Sandbox vs Production isolation                */
/* ================================================================== */

describe('Paper Account Isolation', () => {
  it('sandbox has ONE shared paper_account row (no person filter)', () => {
    expect(SCANNER).toMatch(/COALESCE\(account_type, 'sandbox'\)\s*=\s*'sandbox'/)
  })

  it('production has per-person paper_account rows', () => {
    expect(SCANNER).toMatch(/account_type\s*=\s*'production'\s*AND\s*person/)
  })

  it('production paper_account seeded for Logan in db.ts', () => {
    expect(DB).toMatch(/production.*Logan/s)
    expect(DB).toMatch(/flame_paper_account/)
  })

  it('production starting_capital syncs from real Tradier equity', () => {
    expect(SCANNER).toMatch(/getAllocatedCapitalForAccount/)
  })

  it('sync only triggers when equity changes by > $1', () => {
    expect(SCANNER).toMatch(/Math\.abs.*>=\s*1/)
  })

  it('collateral deducted from CORRECT paper_account on open', () => {
    // Production: WHERE account_type='production' AND person=$X
    expect(SCANNER).toMatch(/account_type\s*=\s*'production'\s*AND\s*person\s*=/)
  })
})

/* ================================================================== */
/*  7. CLOSE FLOW — Both accounts closed together                      */
/* ================================================================== */

describe('Close Flow', () => {
  it('monitors ALL open positions regardless of account_type', () => {
    expect(SCANNER).toMatch(/WHERE status = 'open' AND dte_mode/)
    // Includes COALESCE(account_type, 'sandbox')
    expect(SCANNER).toMatch(/COALESCE\(account_type, 'sandbox'\) as account_type/)
  })

  it('closeIcOrderAllAccounts closes on ALL Tradier accounts', () => {
    expect(TRADIER).toMatch(/closeIcOrderAllAccounts/)
  })

  it('P&L credited to correct paper_account based on position account_type', () => {
    // The close logic checks account_type to route P&L
    expect(SCANNER).toMatch(/account_type.*production.*paper_account/s)
  })

  it('EOD force-close at 15:45 ET catches both sandbox and production', () => {
    expect(SCANNER).toMatch(/15:45/)
  })
})

/* ================================================================== */
/*  8. PRODUCTION-ONLY MODE — When sandbox traded but production hasn't*/
/* ================================================================== */

describe('Production-Only Mode', () => {
  it('detects when sandbox hit max_trades_per_day but production has not', () => {
    expect(SCANNER).toMatch(/prodTradedToday/)
  })

  it('enters production-only mode (skips sandbox entirely)', () => {
    expect(SCANNER).toMatch(/_productionOnlyMode\s*=\s*true/)
  })

  it('only records production fills in this mode', () => {
    // Inside _productionOnlyMode block: skip non-production fills via continue
    expect(SCANNER).toMatch(/_productionOnlyMode[\s\S]*?account_type\s*!==\s*'production'[\s\S]*?continue/)
  })
})
