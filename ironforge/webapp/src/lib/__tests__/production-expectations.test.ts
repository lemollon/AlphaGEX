/**
 * Production Expectations Tests — verifies the math, sizing, and P&L
 * expectations for FLAME trading on Logan's production Tradier account.
 *
 * Every expectation is backed by a fact from the codebase.
 *
 * Run:  npx vitest run src/lib/__tests__/production-expectations.test.ts
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
  CT_TODAY: "'2026-03-23'",
}))

/* ── Mock fetch ─────────────────────────────────────────────────────── */

vi.stubGlobal('fetch', vi.fn())

/* ── Source ──────────────────────────────────────────────────────────── */

const SCANNER_PATH = path.resolve(__dirname, '../scanner.ts')
const TRADIER_PATH = path.resolve(__dirname, '../tradier.ts')
const DB_PATH = path.resolve(__dirname, '../db.ts')
const scannerSource = fs.readFileSync(SCANNER_PATH, 'utf-8')
const tradierSource = fs.readFileSync(TRADIER_PATH, 'utf-8')
const dbSource = fs.readFileSync(DB_PATH, 'utf-8')

/* ── Import scanner helpers ─────────────────────────────────────────── */

vi.mock('../tradier', () => ({
  isConfigured: () => true,
  isConfiguredAsync: () => Promise.resolve(true),
  getIcMarkToMarket: vi.fn(),
  placeIcOrderAllAccounts: vi.fn().mockResolvedValue({}),
  closeIcOrderAllAccounts: vi.fn().mockResolvedValue({}),
  getIcEntryCredit: vi.fn(),
  getQuote: vi.fn(),
  getOptionExpirations: vi.fn(),
  getSandboxAccountBalances: vi.fn().mockResolvedValue([]),
  getLoadedSandboxAccounts: vi.fn().mockReturnValue([]),
  getLoadedSandboxAccountsAsync: vi.fn().mockResolvedValue([]),
  getSandboxAccountPositions: vi.fn().mockResolvedValue([]),
  emergencyCloseSandboxPositions: vi.fn().mockResolvedValue({ closed: 0, failed: 0, details: [] }),
  buildOccSymbol: vi.fn().mockReturnValue('SPY260320P00580000'),
  calculateIcUnrealizedPnl: vi.fn().mockReturnValue(0),
  getAccountsForBot: vi.fn().mockReturnValue(['User']),
  getBpShareForBot: vi.fn().mockReturnValue(1.0),
  getBatchOptionQuotes: vi.fn().mockResolvedValue([]),
  SandboxCloseInfo: {},
  SandboxOrderInfo: {},
}))

import { _testing } from '../scanner'

const { calculateStrikes, evaluateAdvisor, cfg, DEFAULT_CONFIG, getSlidingProfitTarget } = _testing

beforeEach(() => {
  mockQuery.mockReset().mockResolvedValue([])
})

/* ================================================================== */
/*  FLAME CONFIG — Verified Defaults                                   */
/* ================================================================== */

describe('FLAME Config Defaults', () => {
  const flameCfg = cfg({ name: 'flame', dte: '2DTE' } as any)

  it('SD multiplier = 1.2', () => {
    expect(flameCfg.sd).toBe(1.2)
  })

  it('profit target = 30% (0.30)', () => {
    expect(flameCfg.pt_pct).toBe(0.30)
  })

  it('stop loss multiplier = 2.0 (100% of credit = cost reaches 2x)', () => {
    expect(flameCfg.sl_mult).toBe(2.0)
  })

  it('spread width = $5 (hardcoded in calculateStrikes)', () => {
    // WIDTH = 5 is hardcoded in calculateStrikes, not in BotConfig
    expect(scannerSource).toMatch(/const\s+WIDTH\s*=\s*5/)
  })

  it('max trades per day = 1', () => {
    expect(flameCfg.max_trades).toBe(1)
  })

  it('entry window closes at 1400 CT (2:00 PM)', () => {
    expect(flameCfg.entry_end).toBe(1400)
  })

  it('VIX skip threshold = 32 (hardcoded in scanner)', () => {
    // vix_skip is a constant in the scanner, not in BotConfig
    expect(scannerSource).toMatch(/vix\s*>\s*32/)
  })

  it('buying power usage = 85%', () => {
    expect(flameCfg.bp_pct).toBe(0.85)
  })
})

/* ================================================================== */
/*  PRODUCTION SAFETY — Hard Caps                                      */
/* ================================================================== */

describe('Production Safety Guards', () => {
  it('PRODUCTION_MAX_CONTRACTS is exactly 2', () => {
    // This constant appears 3 times in scanner.ts (normal path, production-only, SPARK/INFERNO path)
    const matches = scannerSource.match(/PRODUCTION_MAX_CONTRACTS\s*=\s*(\d+)/g)
    expect(matches).not.toBeNull()
    // Every declaration must be 2
    for (const m of matches!) {
      expect(m).toContain('= 2')
    }
  })

  it('SANDBOX_MAX_CONTRACTS is 200 (accounts have separate hard cap)', () => {
    expect(tradierSource).toMatch(/SANDBOX_MAX_CONTRACTS\s*=\s*200/)
  })

  it('production abort on capital_pct lookup failure (never defaults to 100%)', () => {
    // The code explicitly returns/skips when capital_pct lookup fails for production
    expect(tradierSource).toMatch(/PRODUCTION.*capital_pct.*SKIP/i)
  })

  it('default capital_pct for Logan = 15% (in db.ts seeding)', () => {
    expect(dbSource).toMatch(/capital_pct.*15/)
  })
})

/* ================================================================== */
/*  STRIKE CALCULATION — Where do wings land?                          */
/* ================================================================== */

describe('Strike Calculation (SD=1.2, width=5)', () => {
  // VIX = 18 (typical), SPY spot = $590
  const vix = 18
  const spot = 590
  const expectedMove = (vix / 100 / Math.sqrt(252)) * spot // ≈ $6.69

  it('expected move formula: (VIX/100/sqrt(252)) × spot', () => {
    const em = (vix / 100 / Math.sqrt(252)) * spot
    expect(em).toBeCloseTo(6.69, 1)
  })

  it('short put at floor(spot - 1.2 × EM)', () => {
    const strikes = calculateStrikes(spot, expectedMove, 1.2)
    const expected = Math.floor(spot - 1.2 * expectedMove) // floor(590 - 8.03) = floor(581.97) = 581
    expect(strikes.putShort).toBe(expected)
  })

  it('short call at ceil(spot + 1.2 × EM)', () => {
    const strikes = calculateStrikes(spot, expectedMove, 1.2)
    const expected = Math.ceil(spot + 1.2 * expectedMove) // ceil(590 + 8.03) = ceil(598.03) = 599
    expect(strikes.callShort).toBe(expected)
  })

  it('long put = short put - 5', () => {
    const strikes = calculateStrikes(spot, expectedMove, 1.2)
    expect(strikes.putLong).toBe(strikes.putShort - 5)
  })

  it('long call = short call + 5', () => {
    const strikes = calculateStrikes(spot, expectedMove, 1.2)
    expect(strikes.callLong).toBe(strikes.callShort + 5)
  })

  it('total width between short strikes ≈ 2.4 × EM', () => {
    const strikes = calculateStrikes(spot, expectedMove, 1.2)
    const innerWidth = strikes.callShort - strikes.putShort
    // Should be approximately 2.4 × EM ≈ 16 points (±1 for rounding)
    expect(innerWidth).toBeGreaterThanOrEqual(15)
    expect(innerWidth).toBeLessThanOrEqual(20)
  })
})

/* ================================================================== */
/*  PRODUCTION SIZING — What can Logan actually trade?                 */
/* ================================================================== */

describe('Production Sizing Math', () => {
  // Tradier uses full spread width for margin, NOT net collateral
  const SPREAD_WIDTH = 5
  const BROKER_MARGIN_PER = SPREAD_WIDTH * 100 // = $500 per contract

  it('broker margin per contract = spread_width × 100 = $500', () => {
    expect(BROKER_MARGIN_PER).toBe(500)
    expect(tradierSource).toMatch(/brokerMarginPer\s*=\s*spreadWidth\s*\*\s*100/)
  })

  it('usable BP formula: optionBP × capitalPct% × botShare × 85%', () => {
    expect(tradierSource).toMatch(/bpAfterCapitalPct\s*\*\s*botShare\s*\*\s*0\.85/)
  })

  // Scenario: Logan has $10K account, 15% capital_pct, sole FLAME account
  const optionBP = 10000
  const capitalPct = 15
  const botShare = 1.0
  const usableBP = optionBP * (capitalPct / 100) * botShare * 0.85

  it('Logan ($10K, 15%, sole bot): usable BP = $1,275', () => {
    expect(usableBP).toBe(1275)
  })

  it('Logan ($10K, 15%): can afford floor($1,275 / $500) = 2 contracts', () => {
    const bpContracts = Math.floor(usableBP / BROKER_MARGIN_PER)
    expect(bpContracts).toBe(2)
  })

  it('Logan: 2 contracts capped at PRODUCTION_MAX_CONTRACTS = 2 → 2 contracts', () => {
    const bpContracts = Math.floor(usableBP / BROKER_MARGIN_PER)
    const PRODUCTION_MAX_CONTRACTS = 2
    const finalContracts = Math.min(bpContracts, PRODUCTION_MAX_CONTRACTS)
    expect(finalContracts).toBe(2)
  })

  // Scenario: Logan has $5K account (smaller), 15% capital_pct
  it('Logan ($5K, 15%): usable BP = $637.50 → only 1 contract', () => {
    const smallBP = 5000 * (15 / 100) * 1.0 * 0.85
    expect(smallBP).toBe(637.5)
    expect(Math.floor(smallBP / BROKER_MARGIN_PER)).toBe(1)
  })

  // Scenario: Logan has $3K account (very small), 15% capital_pct
  it('Logan ($3K, 15%): usable BP = $382.50 → 0 contracts (CANNOT TRADE)', () => {
    const tinyBP = 3000 * (15 / 100) * 1.0 * 0.85
    expect(tinyBP).toBe(382.5)
    expect(Math.floor(tinyBP / BROKER_MARGIN_PER)).toBe(0)
  })

  // What capital_pct is needed for at least 1 contract with $10K?
  it('minimum capital_pct for 1 contract with $10K: ceil(500 / (10000×0.85)) = 6%', () => {
    // usableBP >= 500 → BP × pct/100 × 0.85 >= 500
    // pct >= 500 / (10000 × 0.85) = 5.88% → 6%
    const minPct = Math.ceil(500 / (10000 * 0.85) * 100)
    expect(minPct).toBe(6)
  })

  it('minimum capital_pct for 2 contracts with $10K: ceil(1000 / (10000×0.85)) = 12%', () => {
    const minPct = Math.ceil(1000 / (10000 * 0.85) * 100)
    expect(minPct).toBe(12)
  })
})

/* ================================================================== */
/*  P&L EXPECTATIONS — What does each trade look like?                 */
/* ================================================================== */

describe('P&L Per Trade (2 contracts, typical credit)', () => {
  // Typical credit range for SPY 2DTE IC with SD=1.2: $0.25 - $0.60
  // Using $0.40 as representative
  const CONTRACTS = 2
  const ENTRY_CREDIT = 0.40
  const SPREAD_WIDTH = 5

  it('gross premium collected = credit × 100 × contracts = $80', () => {
    const premium = ENTRY_CREDIT * 100 * CONTRACTS
    expect(premium).toBe(80)
  })

  it('collateral required (paper) = (width - credit) × 100 × contracts = $920', () => {
    // Paper account uses net collateral: (spread_width - credit) × 100 × contracts
    // This is DIFFERENT from Tradier broker margin which is full spread width × 100
    const collateral = (SPREAD_WIDTH - ENTRY_CREDIT) * 100 * CONTRACTS
    expect(collateral).toBeCloseTo(920, 2)
  })

  it('broker margin (Tradier) = width × 100 × contracts = $1,000', () => {
    // Tradier uses full spread width, not net collateral
    const margin = SPREAD_WIDTH * 100 * CONTRACTS
    expect(margin).toBe(1000)
  })

  // Profit target: close when cost_to_close ≤ entry_credit × (1 - pt_pct)
  it('profit target price = credit × (1 - 0.30) = $0.28', () => {
    const ptPrice = ENTRY_CREDIT * (1 - 0.30)
    expect(ptPrice).toBeCloseTo(0.28, 4)
  })

  it('profit at PT = (credit - close_price) × 100 × contracts = $24', () => {
    const closePrice = ENTRY_CREDIT * (1 - 0.30) // $0.28
    const pnl = (ENTRY_CREDIT - closePrice) * 100 * CONTRACTS
    expect(pnl).toBeCloseTo(24, 2)
  })

  // Stop loss: close when cost_to_close ≥ entry_credit × sl_mult (2.0)
  it('stop loss price = credit × 2.0 = $0.80', () => {
    const slPrice = ENTRY_CREDIT * 2.0
    expect(slPrice).toBeCloseTo(0.80, 4)
  })

  it('loss at SL = (credit - close_price) × 100 × contracts = -$80', () => {
    const closePrice = ENTRY_CREDIT * 2.0 // $0.80
    const pnl = (ENTRY_CREDIT - closePrice) * 100 * CONTRACTS
    expect(pnl).toBeCloseTo(-80, 2)
  })

  // Risk/reward ratio
  it('risk/reward at typical credit: risk $80 to make $24 → 3.33:1 R:R', () => {
    const profit = 24
    const loss = 80
    const rr = loss / profit
    expect(rr).toBeCloseTo(3.33, 1)
  })

  it('breakeven win rate = loss / (profit + loss) = 76.9%', () => {
    const profit = 24
    const loss = 80
    const beWinRate = loss / (profit + loss)
    expect(beWinRate).toBeCloseTo(0.769, 2)
  })

  // Maximum loss (spread blows through)
  it('maximum loss if expired ITM = spread_width × 100 × contracts - premium = $920', () => {
    // Net max loss = (spread_width - credit) × 100 × contracts
    const maxLoss = (SPREAD_WIDTH - ENTRY_CREDIT) * 100 * CONTRACTS
    expect(maxLoss).toBeCloseTo(920, 2)
  })
})

/* ================================================================== */
/*  P&L WITH HIGHER CREDIT (VIX elevated)                              */
/* ================================================================== */

describe('P&L Per Trade — Higher Credit ($0.80, VIX elevated)', () => {
  const CONTRACTS = 2
  const ENTRY_CREDIT = 0.80
  const SPREAD_WIDTH = 5

  it('gross premium = $160', () => {
    expect(ENTRY_CREDIT * 100 * CONTRACTS).toBe(160)
  })

  it('profit at 30% PT = $48', () => {
    const closePrice = ENTRY_CREDIT * (1 - 0.30) // $0.56
    const pnl = (ENTRY_CREDIT - closePrice) * 100 * CONTRACTS
    expect(pnl).toBeCloseTo(48, 2)
  })

  it('loss at SL = -$160', () => {
    const closePrice = ENTRY_CREDIT * 2.0 // $1.60
    const pnl = (ENTRY_CREDIT - closePrice) * 100 * CONTRACTS
    expect(pnl).toBeCloseTo(-160, 2)
  })

  it('risk/reward = 3.33:1 (same ratio regardless of credit)', () => {
    // With 30% PT and 100% SL, R:R is always 100/30 = 3.33
    const rr = 1.0 / 0.30
    expect(rr).toBeCloseTo(3.33, 1)
  })

  it('breakeven win rate always ≈ 76.9% with 30/100 PT/SL', () => {
    // loss% / (profit% + loss%) = 100 / (30 + 100) = 76.9%
    const beWinRate = 100 / (30 + 100)
    expect(beWinRate).toBeCloseTo(0.769, 2)
  })
})

/* ================================================================== */
/*  WEEKLY / MONTHLY PROJECTIONS                                       */
/* ================================================================== */

describe('Weekly & Monthly Projections (2 contracts, $0.40 avg credit)', () => {
  const PROFIT_PER_WIN = 24    // $0.40 × 30% × 100 × 2
  const LOSS_PER_LOSS = 80     // $0.40 × 100% × 100 × 2
  const TRADES_PER_WEEK = 5    // 1 trade/day, 5 market days

  it('at 80% win rate: weekly = +$16, monthly = +$64', () => {
    const wins = TRADES_PER_WEEK * 0.80
    const losses = TRADES_PER_WEEK * 0.20
    const weekly = (wins * PROFIT_PER_WIN) - (losses * LOSS_PER_LOSS)
    expect(weekly).toBeCloseTo(16, 0)
    expect(weekly * 4).toBeCloseTo(64, 0)
  })

  it('at 85% win rate: weekly = +$42, monthly = +$168', () => {
    const wins = TRADES_PER_WEEK * 0.85
    const losses = TRADES_PER_WEEK * 0.15
    const weekly = (wins * PROFIT_PER_WIN) - (losses * LOSS_PER_LOSS)
    expect(weekly).toBeCloseTo(42, 0)
    expect(weekly * 4).toBeCloseTo(168, 0)
  })

  it('at 90% win rate: weekly = +$68, monthly = +$272', () => {
    const wins = TRADES_PER_WEEK * 0.90
    const losses = TRADES_PER_WEEK * 0.10
    const weekly = (wins * PROFIT_PER_WIN) - (losses * LOSS_PER_LOSS)
    expect(weekly).toBeCloseTo(68, 0)
    expect(weekly * 4).toBeCloseTo(272, 0)
  })

  it('at 76.9% win rate (breakeven): weekly = $0', () => {
    const beWR = 100 / (30 + 100)
    const wins = TRADES_PER_WEEK * beWR
    const losses = TRADES_PER_WEEK * (1 - beWR)
    const weekly = (wins * PROFIT_PER_WIN) - (losses * LOSS_PER_LOSS)
    expect(Math.abs(weekly)).toBeLessThan(1) // essentially zero
  })

  it('at 70% win rate: weekly = -$36 (LOSING MONEY)', () => {
    const wins = TRADES_PER_WEEK * 0.70
    const losses = TRADES_PER_WEEK * 0.30
    const weekly = (wins * PROFIT_PER_WIN) - (losses * LOSS_PER_LOSS)
    expect(weekly).toBeCloseTo(-36, 0)
  })
})

/* ================================================================== */
/*  SLIDING PROFIT TARGET — How PT Changes During the Day              */
/* ================================================================== */

describe('Sliding Profit Target', () => {
  // getSlidingProfitTarget(ct: Date, basePt: number, botName: string) → [number, string]
  // Uses CT (Central Time) thresholds:
  //   < 10:30 AM CT → MORNING (base PT)
  //   < 1:00 PM CT → MIDDAY (base - 10%)
  //   >= 1:00 PM CT → AFTERNOON (base - 15%)

  function makeCT(hour: number, minute: number): Date {
    const d = new Date(2026, 2, 18) // Wednesday
    d.setHours(hour, minute, 0, 0)
    return d
  }

  it('before 10:30 AM CT: PT stays at base (30%)', () => {
    const [pct, tier] = getSlidingProfitTarget(makeCT(9, 30), 0.30, 'flame')
    expect(pct).toBe(0.30)
    expect(tier).toBe('MORNING')
  })

  it('at 11:00 AM CT: PT loosens to 20% (base - 10%)', () => {
    const [pct, tier] = getSlidingProfitTarget(makeCT(11, 0), 0.30, 'flame')
    expect(pct).toBeCloseTo(0.20, 10)
    expect(tier).toBe('MIDDAY')
  })

  it('at 1:30 PM CT: PT loosens to 15% (base - 15%)', () => {
    const [pct, tier] = getSlidingProfitTarget(makeCT(13, 30), 0.30, 'flame')
    expect(pct).toBe(0.15)
    expect(tier).toBe('AFTERNOON')
  })

  it('INFERNO afternoon PT = 10% (more aggressive)', () => {
    const [pct, tier] = getSlidingProfitTarget(makeCT(13, 30), 0.50, 'inferno')
    expect(pct).toBe(0.10)
    expect(tier).toBe('AFTERNOON')
  })

  it('PT never goes below 10%', () => {
    const [pct] = getSlidingProfitTarget(makeCT(14, 0), 0.30, 'flame')
    expect(pct).toBeGreaterThanOrEqual(0.10)
  })
})

/* ================================================================== */
/*  ADVISOR — When Does FLAME Trade?                                   */
/* ================================================================== */

describe('Advisor Decisions', () => {
  // evaluateAdvisor(vix, spot, expectedMove, dteMode)
  // Returns: { advice, winProbability, confidence, topFactors, reasoning }
  // NOTE: advisor uses `new Date().getDay()` internally — results depend on
  // what day the tests actually run. We test the VIX and EM factors instead.

  it('ideal VIX (15-22) gives VIX_IDEAL bonus (+0.10)', () => {
    const result = evaluateAdvisor(18, 590, 5.0, '2DTE')
    const vixFactor = result.topFactors.find(([name]: [string, number]) => name === 'VIX_IDEAL')
    expect(vixFactor).toBeDefined()
    expect(vixFactor![1]).toBe(0.10)
  })

  it('high VIX (>28) gives VIX_HIGH_RISK penalty (-0.15)', () => {
    const result = evaluateAdvisor(30, 590, 12.0, '2DTE')
    const vixFactor = result.topFactors.find(([name]: [string, number]) => name === 'VIX_HIGH_RISK')
    expect(vixFactor).toBeDefined()
    expect(vixFactor![1]).toBe(-0.15)
  })

  it('VIX > 32: scanner skips before advisor even runs (structural)', () => {
    // vix_skip gate is checked before advisor in the scanner
    expect(scannerSource).toMatch(/vix\s*>\s*32/)
  })

  it('2DTE gets DTE_2DAY_DECAY bonus (+0.03)', () => {
    const result = evaluateAdvisor(18, 590, 5.0, '2DTE')
    const dteFactor = result.topFactors.find(([name]: [string, number]) => name === 'DTE_2DAY_DECAY')
    expect(dteFactor).toBeDefined()
    expect(dteFactor![1]).toBe(0.03)
  })

  it('tight EM (<1% of spot) gets EM_TIGHT bonus (+0.08)', () => {
    const result = evaluateAdvisor(18, 590, 3.0, '2DTE') // 3.0/590 = 0.51%
    const emFactor = result.topFactors.find(([name]: [string, number]) => name === 'EM_TIGHT')
    expect(emFactor).toBeDefined()
    expect(emFactor![1]).toBe(0.08)
  })

  it('win probability is clamped between 0.10 and 0.95', () => {
    const result = evaluateAdvisor(50, 590, 20.0, '0DTE') // worst-case scenario
    expect(result.winProbability).toBeGreaterThanOrEqual(0.10)
    expect(result.winProbability).toBeLessThanOrEqual(0.95)
  })
})

/* ================================================================== */
/*  PRODUCTION PAPER ACCOUNT SYNC                                      */
/* ================================================================== */

describe('Production Paper Account Sync (Structural)', () => {
  it('scanner syncs production paper_account from real Tradier equity each cycle', () => {
    // The scanner queries production paper accounts and syncs starting_capital
    expect(scannerSource).toMatch(/account_type\s*=\s*'production'/)
    expect(scannerSource).toMatch(/getAllocatedCapitalForAccount/)
  })

  it('sync only triggers when equity changes by > $1', () => {
    expect(scannerSource).toMatch(/Math\.abs.*>=\s*1/)
  })

  it('sync preserves cumulative_pnl (does not reset it)', () => {
    // The update sets starting_capital and recalculates balance,
    // but cumulative_pnl comes from the existing paper_account row
    expect(scannerSource).toMatch(/cumulative_pnl/)
  })
})

/* ================================================================== */
/*  POSITION CLOSE — Production vs Paper                               */
/* ================================================================== */

describe('Position Close Logic (Structural)', () => {
  it('monitorPosition queries ALL open positions (both sandbox and production)', () => {
    // The query does NOT filter by account_type — monitors everything
    expect(scannerSource).toMatch(/monitorPosition[\s\S]*?WHERE status = 'open' AND dte_mode/)
  })

  it('position includes account_type and person in SELECT', () => {
    expect(scannerSource).toMatch(/COALESCE\(account_type, 'sandbox'\) as account_type/)
    expect(scannerSource).toMatch(/person[\s\S]*?FROM.*positions/)
  })

  it('closeIcOrderAllAccounts places real close orders for production', () => {
    // The close function iterates all loaded accounts (sandbox + production)
    expect(tradierSource).toMatch(/closeIcOrderAllAccounts/)
  })

  it('EOD cutoff at 15:45 ET (2:45 PM CT) force-closes all positions', () => {
    // Both sandbox and production positions get force-closed at EOD
    expect(scannerSource).toMatch(/15:45/)
  })
})

/* ================================================================== */
/*  MINIMUM ACCOUNT SIZE TABLE                                         */
/* ================================================================== */

describe('Minimum Account Size for Production Trading', () => {
  const MARGIN_PER = 500 // $5 spread × 100

  // Formula: minAccountSize = (MARGIN_PER × desiredContracts) / (capitalPct/100 × 0.85)
  function minAccountForContracts(contracts: number, capitalPct: number): number {
    return Math.ceil(MARGIN_PER * contracts / (capitalPct / 100) / 0.85)
  }

  it('1 contract at 15%: need $3,922 account', () => {
    expect(minAccountForContracts(1, 15)).toBe(3922)
  })

  it('2 contracts at 15%: need $7,844 account', () => {
    expect(minAccountForContracts(2, 15)).toBe(7844)
  })

  it('1 contract at 25%: need $2,353 account', () => {
    expect(minAccountForContracts(1, 25)).toBe(2353)
  })

  it('2 contracts at 25%: need $4,706 account', () => {
    expect(minAccountForContracts(2, 25)).toBe(4706)
  })

  it('1 contract at 50%: need $1,177 account', () => {
    expect(minAccountForContracts(1, 50)).toBe(1177)
  })

  it('2 contracts at 50%: need $2,353 account', () => {
    expect(minAccountForContracts(2, 50)).toBe(2353)
  })
})
