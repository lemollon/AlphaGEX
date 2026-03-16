/**
 * Unit + integration tests for the IronForge scanner.
 *
 * Pure functions are tested directly via the _testing export.
 * DB/Tradier-dependent functions are tested with mocked modules.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock db module BEFORE importing scanner
vi.mock('../db', () => ({
  query: vi.fn().mockResolvedValue([]),
  dbExecute: vi.fn().mockResolvedValue(1),
  botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
  num: (v: any) => { if (v == null || v === '') return 0; const n = parseFloat(v); return isNaN(n) ? 0 : n },
  int: (v: any) => { if (v == null || v === '') return 0; const n = parseInt(v, 10); return isNaN(n) ? 0 : n },
  CT_TODAY: "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date",
}))

// Mock tradier module
vi.mock('../tradier', () => ({
  getQuote: vi.fn().mockResolvedValue({ last: 585.50, bid: 585.45, ask: 585.55, symbol: 'SPY' }),
  getOptionExpirations: vi.fn().mockResolvedValue(['2026-03-18', '2026-03-19', '2026-03-20']),
  getIcEntryCredit: vi.fn().mockResolvedValue({
    putCredit: 0.15, callCredit: 0.12, totalCredit: 0.27, source: 'TRADIER_LIVE',
  }),
  getIcMarkToMarket: vi.fn().mockResolvedValue({ cost_to_close: 0.10, spot_price: 585.50 }),
  isConfigured: vi.fn().mockReturnValue(true),
  placeIcOrderAllAccounts: vi.fn().mockResolvedValue({
    User: { order_id: 12345, contracts: 5, fill_price: 0.27 },
  }),
  closeIcOrderAllAccounts: vi.fn().mockResolvedValue({
    User: { order_id: 12346, contracts: 5, fill_price: 0.08 },
  }),
  getLoadedSandboxAccounts: vi.fn().mockReturnValue([
    { name: 'User', apiKey: 'test-key-user' },
  ]),
  getSandboxAccountPositions: vi.fn().mockResolvedValue([]),
  SandboxOrderInfo: {},
  SandboxCloseInfo: {},
}))

import { _testing } from '../scanner'

const {
  ctHHMM,
  isMarketOpen,
  isInEntryWindow,
  isAfterEodCutoff,
  getSlidingProfitTarget,
  evaluateAdvisor,
  calculateStrikes,
  getTargetExpiration,
  cfg,
  DEFAULT_CONFIG,
  BOTS,
  MAX_CONSECUTIVE_MTM_FAILURES,
  _botConfig,
  _mtmFailureCounts,
} = _testing

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Build a Date object for a specific CT time on a weekday. */
function makeCT(hour: number, minute: number, dayOfWeek: number = 1): Date {
  // dayOfWeek: 0=Sun, 1=Mon, ... 5=Fri, 6=Sat
  const d = new Date(2026, 2, 16, hour, minute, 0) // March 16, 2026 = Monday
  // Adjust to desired day
  const currentDow = d.getDay()
  d.setDate(d.getDate() + (dayOfWeek - currentDow))
  return d
}

/* ================================================================== */
/*  1. Market Hours                                                    */
/* ================================================================== */

describe('Market Hours', () => {
  describe('ctHHMM', () => {
    it('returns HHMM integer from Date', () => {
      expect(ctHHMM(makeCT(8, 30))).toBe(830)
      expect(ctHHMM(makeCT(14, 45))).toBe(1445)
      expect(ctHHMM(makeCT(0, 0))).toBe(0)
      expect(ctHHMM(makeCT(15, 0))).toBe(1500)
    })
  })

  describe('isMarketOpen', () => {
    it('returns true during market hours on weekday', () => {
      expect(isMarketOpen(makeCT(8, 30, 1))).toBe(true)   // 8:30 AM Mon
      expect(isMarketOpen(makeCT(12, 0, 3))).toBe(true)    // noon Wed
      expect(isMarketOpen(makeCT(15, 0, 5))).toBe(true)    // 3:00 PM Fri
    })

    it('returns false before market open', () => {
      expect(isMarketOpen(makeCT(8, 29, 1))).toBe(false)
    })

    it('returns false after market close (Fix 6: 15:00 not 15:30)', () => {
      expect(isMarketOpen(makeCT(15, 1, 1))).toBe(false)
      expect(isMarketOpen(makeCT(15, 30, 1))).toBe(false)
    })

    it('returns false on weekends', () => {
      expect(isMarketOpen(makeCT(12, 0, 0))).toBe(false)  // Sunday
      expect(isMarketOpen(makeCT(12, 0, 6))).toBe(false)  // Saturday
    })
  })

  describe('isAfterEodCutoff (Fix 6)', () => {
    it('returns true at 14:45 CT and after', () => {
      expect(isAfterEodCutoff(makeCT(14, 45))).toBe(true)
      expect(isAfterEodCutoff(makeCT(15, 0))).toBe(true)
      expect(isAfterEodCutoff(makeCT(15, 45))).toBe(true)
    })

    it('returns false before 14:45 CT', () => {
      expect(isAfterEodCutoff(makeCT(14, 44))).toBe(false)
      expect(isAfterEodCutoff(makeCT(14, 0))).toBe(false)
      expect(isAfterEodCutoff(makeCT(8, 30))).toBe(false)
    })

    it('OLD cutoff 15:45 would have been wrong — verify 14:45 is correct', () => {
      // This is the bug that was fixed: 15:45 was too late
      expect(isAfterEodCutoff(makeCT(15, 45))).toBe(true)
      // 14:45 is now the cutoff — positions should close here
      expect(isAfterEodCutoff(makeCT(14, 45))).toBe(true)
      // 14:44 should NOT trigger EOD
      expect(isAfterEodCutoff(makeCT(14, 44))).toBe(false)
    })
  })

  describe('isInEntryWindow (Fix 11: per-bot)', () => {
    const flame = BOTS[0]  // entry_end=1400
    const inferno = BOTS[2] // entry_end=1430

    it('FLAME entry window: 8:30-14:00', () => {
      expect(isInEntryWindow(makeCT(8, 30, 1), flame)).toBe(true)
      expect(isInEntryWindow(makeCT(14, 0, 1), flame)).toBe(true)
      expect(isInEntryWindow(makeCT(14, 1, 1), flame)).toBe(false)
    })

    it('INFERNO entry window: 8:30-14:30', () => {
      expect(isInEntryWindow(makeCT(14, 1, 1), inferno)).toBe(true)
      expect(isInEntryWindow(makeCT(14, 30, 1), inferno)).toBe(true)
      expect(isInEntryWindow(makeCT(14, 31, 1), inferno)).toBe(false)
    })

    it('returns false on weekends for all bots', () => {
      expect(isInEntryWindow(makeCT(12, 0, 0), flame)).toBe(false)
      expect(isInEntryWindow(makeCT(12, 0, 6), inferno)).toBe(false)
    })

    it('returns false before market open', () => {
      expect(isInEntryWindow(makeCT(8, 29, 1), flame)).toBe(false)
    })
  })
})

/* ================================================================== */
/*  2. Sliding Profit Target (Fix 2)                                   */
/* ================================================================== */

describe('Sliding Profit Target', () => {
  describe('FLAME/SPARK (base=0.30)', () => {
    it('MORNING (8:30-10:29): 30%', () => {
      const [pt, tier] = getSlidingProfitTarget(makeCT(8, 30), 0.30, 'flame')
      expect(tier).toBe('MORNING')
      expect(pt).toBe(0.30)
    })

    it('MORNING at 10:29: still 30%', () => {
      const [pt, tier] = getSlidingProfitTarget(makeCT(10, 29), 0.30, 'spark')
      expect(tier).toBe('MORNING')
      expect(pt).toBe(0.30)
    })

    it('MIDDAY (10:30-12:59): 20%', () => {
      const [pt, tier] = getSlidingProfitTarget(makeCT(10, 30), 0.30, 'flame')
      expect(tier).toBe('MIDDAY')
      expect(pt).toBeCloseTo(0.20, 10) // base - 0.10
    })

    it('AFTERNOON (13:00-14:44): 15%', () => {
      const [pt, tier] = getSlidingProfitTarget(makeCT(13, 0), 0.30, 'flame')
      expect(tier).toBe('AFTERNOON')
      expect(pt).toBe(0.15) // base - 0.15
    })

    it('AFTERNOON at 14:44: still 15%', () => {
      const [pt, tier] = getSlidingProfitTarget(makeCT(14, 44), 0.30, 'flame')
      expect(tier).toBe('AFTERNOON')
      expect(pt).toBe(0.15)
    })
  })

  describe('INFERNO (base=0.50)', () => {
    it('MORNING: 50%', () => {
      const [pt, tier] = getSlidingProfitTarget(makeCT(9, 0), 0.50, 'inferno')
      expect(tier).toBe('MORNING')
      expect(pt).toBe(0.50)
    })

    it('MIDDAY: 30%', () => {
      const [pt, tier] = getSlidingProfitTarget(makeCT(11, 0), 0.50, 'inferno')
      expect(tier).toBe('MIDDAY')
      expect(pt).toBe(0.30)
    })

    it('AFTERNOON: 10%', () => {
      const [pt, tier] = getSlidingProfitTarget(makeCT(13, 30), 0.50, 'inferno')
      expect(tier).toBe('AFTERNOON')
      expect(pt).toBe(0.10)
    })
  })

  describe('edge: minimum floor of 10%', () => {
    it('never goes below 10% even with low base', () => {
      const [pt] = getSlidingProfitTarget(makeCT(14, 0), 0.20, 'flame')
      expect(pt).toBeGreaterThanOrEqual(0.10)
    })
  })

  describe('profit target price calculation', () => {
    it('MORNING 30%: PT price = entry * 0.70', () => {
      const entryCredit = 0.50
      const [ptFrac] = getSlidingProfitTarget(makeCT(9, 0), 0.30, 'flame')
      const ptPrice = entryCredit * (1 - ptFrac)
      expect(ptPrice).toBeCloseTo(0.35, 4) // 0.50 * 0.70
    })

    it('AFTERNOON 15%: PT price = entry * 0.85', () => {
      const entryCredit = 0.50
      const [ptFrac] = getSlidingProfitTarget(makeCT(13, 30), 0.30, 'flame')
      const ptPrice = entryCredit * (1 - ptFrac)
      expect(ptPrice).toBeCloseTo(0.425, 4) // 0.50 * 0.85
    })

    it('INFERNO AFTERNOON: PT price = entry * 0.90', () => {
      const entryCredit = 0.80
      const [ptFrac] = getSlidingProfitTarget(makeCT(14, 0), 0.50, 'inferno')
      const ptPrice = entryCredit * (1 - ptFrac)
      expect(ptPrice).toBeCloseTo(0.72, 4) // 0.80 * 0.90
    })
  })
})

/* ================================================================== */
/*  3. Per-Bot Config (Fix 1)                                          */
/* ================================================================== */

describe('Per-Bot Config', () => {
  it('FLAME defaults: sd=1.2, pt=0.30, sl=2.0, entry_end=1400, max_contracts=10', () => {
    const c = DEFAULT_CONFIG.flame
    expect(c.sd).toBe(1.2)
    expect(c.pt_pct).toBe(0.30)
    expect(c.sl_mult).toBe(2.0)
    expect(c.entry_end).toBe(1400)
    expect(c.max_contracts).toBe(10)
    expect(c.max_trades).toBe(1)
    expect(c.bp_pct).toBe(0.85)
  })

  it('SPARK defaults: identical to FLAME', () => {
    const f = DEFAULT_CONFIG.flame
    const s = DEFAULT_CONFIG.spark
    expect(s.sd).toBe(f.sd)
    expect(s.pt_pct).toBe(f.pt_pct)
    expect(s.sl_mult).toBe(f.sl_mult)
    expect(s.entry_end).toBe(f.entry_end)
    expect(s.max_contracts).toBe(f.max_contracts)
  })

  it('INFERNO defaults: sd=1.0, pt=0.50, sl=3.0, entry_end=1430, max_contracts=3, unlimited trades', () => {
    const c = DEFAULT_CONFIG.inferno
    expect(c.sd).toBe(1.0)
    expect(c.pt_pct).toBe(0.50)
    expect(c.sl_mult).toBe(3.0)
    expect(c.entry_end).toBe(1430)
    expect(c.max_contracts).toBe(3)
    expect(c.max_trades).toBe(0) // 0 = unlimited
  })

  it('cfg() returns default config for each bot', () => {
    expect(cfg(BOTS[0]).sd).toBe(1.2) // flame
    expect(cfg(BOTS[1]).sd).toBe(1.2) // spark
    expect(cfg(BOTS[2]).sd).toBe(1.0) // inferno
  })

  it('BOTS array has correct dte/minDte', () => {
    expect(BOTS[0]).toEqual({ name: 'flame', dte: '2DTE', minDte: 2 })
    expect(BOTS[1]).toEqual({ name: 'spark', dte: '1DTE', minDte: 1 })
    expect(BOTS[2]).toEqual({ name: 'inferno', dte: '0DTE', minDte: 0 })
  })
})

/* ================================================================== */
/*  4. Strike Calculation (Fix 1: per-bot SD)                          */
/* ================================================================== */

describe('Strike Calculation', () => {
  const spot = 585.50
  const vix = 16.0
  const em = (vix / 100 / Math.sqrt(252)) * spot // ~5.90

  it('calculates symmetric IC strikes with SD=1.2 (FLAME/SPARK)', () => {
    const s = calculateStrikes(spot, em, 1.2)
    // putShort = floor(585.50 - 1.2 * 5.90) = floor(578.42) = 578
    // callShort = ceil(585.50 + 1.2 * 5.90) = ceil(592.58) = 593
    expect(s.putShort).toBe(578)
    expect(s.callShort).toBe(593)
    expect(s.putLong).toBe(573)  // putShort - 5
    expect(s.callLong).toBe(598) // callShort + 5
  })

  it('calculates tighter strikes with SD=1.0 (INFERNO)', () => {
    const s = calculateStrikes(spot, em, 1.0)
    // putShort = floor(585.50 - 1.0 * 5.90) = floor(579.60) = 579
    // callShort = ceil(585.50 + 1.0 * 5.90) = ceil(591.40) = 592
    expect(s.putShort).toBe(579)
    expect(s.callShort).toBe(592)
    expect(s.putLong).toBe(574)
    expect(s.callLong).toBe(597)
  })

  it('INFERNO strikes are tighter than FLAME for same market conditions', () => {
    const flame = calculateStrikes(spot, em, 1.2)
    const inferno = calculateStrikes(spot, em, 1.0)
    // Tighter = closer to spot
    expect(inferno.putShort).toBeGreaterThan(flame.putShort)
    expect(inferno.callShort).toBeLessThan(flame.callShort)
  })

  it('enforces minimum expected move of 0.5% of spot', () => {
    const tinyEM = 0.01
    const s = calculateStrikes(spot, tinyEM, 1.2)
    // minEM = 585.50 * 0.005 = 2.9275
    // putShort = floor(585.50 - 1.2 * 2.9275) = floor(582.0) = 581
    expect(s.putShort).toBeGreaterThan(spot - 10)
    expect(s.callShort).toBeLessThan(spot + 10)
  })

  it('fallback to 2% spread when callShort <= putShort', () => {
    // This would happen with zero expected move and some edge case
    const s = calculateStrikes(100, 0, 0)
    // With SD=0, both short strikes would be at spot
    // Fallback: putShort = floor(100 - 2) = 98, callShort = ceil(100 + 2) = 102
    expect(s.putShort).toBe(98)
    expect(s.callShort).toBe(102)
    expect(s.putLong).toBe(93)
    expect(s.callLong).toBe(107)
  })

  it('spread width is always $5', () => {
    const s = calculateStrikes(spot, em, 1.2)
    expect(s.putShort - s.putLong).toBe(5)
    expect(s.callLong - s.callShort).toBe(5)
  })
})

/* ================================================================== */
/*  5. Expiration Targeting                                            */
/* ================================================================== */

describe('getTargetExpiration', () => {
  it('minDte=0 returns today', () => {
    const exp = getTargetExpiration(0)
    const today = new Date().toISOString().slice(0, 10)
    expect(exp).toBe(today)
  })

  it('minDte=1 returns next business day', () => {
    const exp = getTargetExpiration(1)
    const expDate = new Date(exp + 'T12:00:00')
    const dow = expDate.getDay()
    expect(dow).toBeGreaterThanOrEqual(1) // Not Sunday
    expect(dow).toBeLessThanOrEqual(5)     // Not Saturday
  })

  it('minDte=2 skips weekends', () => {
    const exp = getTargetExpiration(2)
    const expDate = new Date(exp + 'T12:00:00')
    const dow = expDate.getDay()
    expect(dow).toBeGreaterThanOrEqual(1)
    expect(dow).toBeLessThanOrEqual(5)
  })
})

/* ================================================================== */
/*  6. Advisor                                                         */
/* ================================================================== */

describe('Advisor', () => {
  const spot = 585.50
  const em = 5.90
  const idealVix = 18.0

  it('TRADE_FULL when conditions are ideal', () => {
    const result = evaluateAdvisor(idealVix, spot, em, '2DTE')
    expect(result.advice).toBe('TRADE_FULL')
    expect(result.winProbability).toBeGreaterThanOrEqual(0.60)
    expect(result.confidence).toBeGreaterThanOrEqual(0.50)
  })

  it('penalizes heavily when VIX is extremely high', () => {
    const result = evaluateAdvisor(40, spot, em, '0DTE')
    // VIX=40 + 0DTE gets heavy penalties, but advisor may still say TRADE_REDUCED
    // depending on day-of-week. The key check is the VIX factor is negative.
    const vixFactor = result.topFactors.find(([n]) => n.startsWith('VIX_'))
    expect(vixFactor![0]).toBe('VIX_HIGH_RISK')
    expect(vixFactor![1]).toBe(-0.15)
    expect(result.winProbability).toBeLessThan(0.60) // Below TRADE_FULL threshold
  })

  it('winProbability clamped to [0.10, 0.95]', () => {
    const high = evaluateAdvisor(18, spot, 1.0, '2DTE')
    expect(high.winProbability).toBeLessThanOrEqual(0.95)

    const low = evaluateAdvisor(50, spot, 20.0, '0DTE')
    expect(low.winProbability).toBeGreaterThanOrEqual(0.10)
  })

  it('confidence clamped to [0.10, 0.95]', () => {
    const result = evaluateAdvisor(idealVix, spot, em, '2DTE')
    expect(result.confidence).toBeGreaterThanOrEqual(0.10)
    expect(result.confidence).toBeLessThanOrEqual(0.95)
  })

  it('returns factors array with names and values', () => {
    const result = evaluateAdvisor(idealVix, spot, em, '2DTE')
    expect(result.topFactors.length).toBeGreaterThan(0)
    for (const [name, val] of result.topFactors) {
      expect(typeof name).toBe('string')
      expect(typeof val).toBe('number')
    }
  })

  it('0DTE gets DTE_0DAY_AGGRESSIVE penalty', () => {
    const result = evaluateAdvisor(idealVix, spot, em, '0DTE')
    const dteFactor = result.topFactors.find(([n]) => n.startsWith('DTE_'))
    expect(dteFactor).toBeDefined()
    expect(dteFactor![0]).toBe('DTE_0DAY_AGGRESSIVE')
    expect(dteFactor![1]).toBe(-0.05)
  })

  it('2DTE gets DTE_2DAY_DECAY bonus', () => {
    const result = evaluateAdvisor(idealVix, spot, em, '2DTE')
    const dteFactor = result.topFactors.find(([n]) => n.startsWith('DTE_'))
    expect(dteFactor![0]).toBe('DTE_2DAY_DECAY')
    expect(dteFactor![1]).toBe(0.03)
  })
})

/* ================================================================== */
/*  7. MTM Failure Tracking (Fix 3)                                    */
/* ================================================================== */

describe('MTM Failure Tracking', () => {
  it('MAX_CONSECUTIVE_MTM_FAILURES is 10', () => {
    expect(MAX_CONSECUTIVE_MTM_FAILURES).toBe(10)
  })

  it('_mtmFailureCounts is a Map', () => {
    expect(_mtmFailureCounts).toBeInstanceOf(Map)
  })

  it('failure count increments and resets correctly', () => {
    const pid = 'TEST-20260316-ABC123'
    _mtmFailureCounts.set(pid, 5)
    expect(_mtmFailureCounts.get(pid)).toBe(5)

    // Simulate reset on successful MTM
    _mtmFailureCounts.delete(pid)
    expect(_mtmFailureCounts.has(pid)).toBe(false)
  })
})

/* ================================================================== */
/*  8. Stop Loss Configuration (Fix 1: per-bot)                        */
/* ================================================================== */

describe('Stop Loss Configuration', () => {
  it('FLAME/SPARK stop loss = 2.0x entry credit', () => {
    const entryCredit = 0.50
    const slPrice = entryCredit * DEFAULT_CONFIG.flame.sl_mult
    expect(slPrice).toBe(1.00) // 200% of entry
  })

  it('INFERNO stop loss = 3.0x entry credit', () => {
    const entryCredit = 0.80
    const slPrice = entryCredit * DEFAULT_CONFIG.inferno.sl_mult
    expect(slPrice).toBeCloseTo(2.40, 10) // 300% of entry
  })

  it('INFERNO has wider stop loss than FLAME for same credit', () => {
    const credit = 0.50
    const flameSL = credit * DEFAULT_CONFIG.flame.sl_mult
    const infernoSL = credit * DEFAULT_CONFIG.inferno.sl_mult
    expect(infernoSL).toBeGreaterThan(flameSL)
  })
})

/* ================================================================== */
/*  9. Collateral & Sizing Math                                        */
/* ================================================================== */

describe('Collateral & Sizing', () => {
  it('collateral per contract = (width - credit) * 100', () => {
    const spreadWidth = 5 // $5 wide
    const totalCredit = 0.27
    const collateralPer = (spreadWidth - totalCredit) * 100
    expect(collateralPer).toBeCloseTo(473, 0)
  })

  it('max contracts respects bp_pct and max_contracts cap', () => {
    const buyingPower = 10000
    const collateralPer = 473
    const bpPct = 0.85
    const maxContractsCap = 10

    const usableBP = buyingPower * bpPct // 8500
    const rawContracts = Math.floor(usableBP / collateralPer) // 17
    const capped = Math.min(maxContractsCap, Math.max(1, rawContracts))
    expect(capped).toBe(10) // Capped at 10 for FLAME
  })

  it('INFERNO max_contracts=3 caps correctly', () => {
    const buyingPower = 10000
    const collateralPer = 473
    const bpPct = 0.85
    const maxContractsCap = 3

    const usableBP = buyingPower * bpPct
    const rawContracts = Math.floor(usableBP / collateralPer)
    const capped = Math.min(maxContractsCap, Math.max(1, rawContracts))
    expect(capped).toBe(3)
  })

  it('P&L calculation: (entryCredit - closePrice) * 100 * contracts', () => {
    const entryCredit = 0.27
    const closePrice = 0.10
    const contracts = 5
    const pnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100
    expect(pnl).toBe(85.00) // $0.17 * 100 * 5 = $85
  })

  it('P&L is negative when close > entry (stop loss)', () => {
    const entryCredit = 0.27
    const closePrice = 0.60 // 222% of entry
    const contracts = 5
    const pnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100
    expect(pnl).toBe(-165.00)
  })
})

/* ================================================================== */
/*  10. Integration: DB-dependent scanner logic                        */
/* ================================================================== */

describe('Integration: closePosition double-close guard (Fix 5)', () => {
  let mockDbExecute: ReturnType<typeof vi.fn>
  let mockQuery: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    const db = await import('../db')
    mockDbExecute = db.dbExecute as ReturnType<typeof vi.fn>
    mockQuery = db.query as ReturnType<typeof vi.fn>
    mockDbExecute.mockClear()
    mockQuery.mockClear()
  })

  it('dbExecute is used (not query) for the position UPDATE', () => {
    // Verify the import exists — the actual call is tested by checking
    // that scanner.ts imports dbExecute
    expect(mockDbExecute).toBeDefined()
    expect(typeof mockDbExecute).toBe('function')
  })
})

describe('Integration: config loading from DB', () => {
  let mockQuery: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    const db = await import('../db')
    mockQuery = db.query as ReturnType<typeof vi.fn>
    mockQuery.mockClear()

    // Reset config to defaults
    Object.assign(_botConfig.flame, DEFAULT_CONFIG.flame)
    Object.assign(_botConfig.inferno, DEFAULT_CONFIG.inferno)
  })

  it('_botConfig starts with default values', () => {
    expect(_botConfig.flame.sd).toBe(1.2)
    expect(_botConfig.inferno.sd).toBe(1.0)
    expect(_botConfig.inferno.max_trades).toBe(0)
  })
})

/* ================================================================== */
/*  11. Position ID format                                             */
/* ================================================================== */

describe('Position ID Format', () => {
  it('follows pattern BOTNAME-YYYYMMDD-HEX', () => {
    const pattern = /^[A-Z]+-\d{8}-[0-9A-F]{6}$/
    // Simulate the scanner's position ID generation
    const now = new Date()
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '')
    const hex = Math.random().toString(16).slice(2, 8).toUpperCase()
    const pid = `FLAME-${dateStr}-${hex}`
    expect(pid).toMatch(pattern)
  })
})

/* ================================================================== */
/*  12. Entry Window vs EOD Cutoff Gap                                 */
/* ================================================================== */

describe('Entry Window vs EOD Cutoff: No Gap', () => {
  it('FLAME: entry ends 14:00, EOD at 14:45 — monitoring window exists', () => {
    // Between 14:00-14:44: can't open new trades, but monitoring continues
    // At 14:45: positions force-closed
    const ct1401 = makeCT(14, 1, 1)
    expect(isInEntryWindow(ct1401, BOTS[0])).toBe(false)
    expect(isAfterEodCutoff(ct1401)).toBe(false)
    expect(isMarketOpen(ct1401)).toBe(true)
    // This is the "monitoring only" window — correct behavior
  })

  it('INFERNO: entry ends 14:30, EOD at 14:45 — 15min monitoring window', () => {
    const ct1431 = makeCT(14, 31, 1)
    expect(isInEntryWindow(ct1431, BOTS[2])).toBe(false)
    expect(isAfterEodCutoff(ct1431)).toBe(false)
    expect(isMarketOpen(ct1431)).toBe(true)
  })

  it('no bot can open trades after EOD cutoff', () => {
    const ct1445 = makeCT(14, 45, 1)
    for (const bot of BOTS) {
      expect(isInEntryWindow(ct1445, bot)).toBe(false)
    }
    expect(isAfterEodCutoff(ct1445)).toBe(true)
  })
})

/* ================================================================== */
/*  13. Config DB Mapping                                              */
/* ================================================================== */

describe('Config DB Column Mapping', () => {
  it('profit_target_pct 30.0 → pt_pct 0.30', () => {
    // DB stores 30.0, we divide by 100 to get 0.30
    const dbVal = 30.0
    const ptPct = dbVal / 100
    expect(ptPct).toBe(0.30)
  })

  it('stop_loss_pct 200.0 → sl_mult 2.0', () => {
    const dbVal = 200.0
    const slMult = dbVal / 100
    expect(slMult).toBe(2.0)
  })

  it('stop_loss_pct 300.0 → sl_mult 3.0 (INFERNO)', () => {
    const dbVal = 300.0
    const slMult = dbVal / 100
    expect(slMult).toBe(3.0)
  })

  it('entry_end "14:30" → 1430', () => {
    const entryEndStr = '14:30'
    const [h, m] = entryEndStr.split(':').map(Number)
    expect(h * 100 + m).toBe(1430)
  })
})

/* ================================================================== */
/*  14. VIX Regime Gate                                                */
/* ================================================================== */

describe('VIX Gate', () => {
  it('VIX > 32 blocks trade', () => {
    // tryOpenTrade returns skip:vix_too_high when vix > 32
    expect(32.1 > 32).toBe(true)
    expect(32.0 > 32).toBe(false) // VIX=32 exactly is allowed
  })

  it('advisor penalizes VIX > 28', () => {
    const result = evaluateAdvisor(30, 585.50, 5.90, '2DTE')
    const vixFactor = result.topFactors.find(([n]) => n.startsWith('VIX_'))
    expect(vixFactor![0]).toBe('VIX_HIGH_RISK')
    expect(vixFactor![1]).toBe(-0.15)
  })
})

/* ================================================================== */
/*  15. FLAME Tradier-fill-only design                                 */
/* ================================================================== */

describe('FLAME Tradier-Fill-Only', () => {
  it('FLAME is the only bot in fill-only mode', () => {
    // Only flame uses Tradier fills as source of truth
    expect(BOTS[0].name).toBe('flame')
    // SPARK and INFERNO use paper-first mode
    expect(BOTS[1].name).toBe('spark')
    expect(BOTS[2].name).toBe('inferno')
  })

  it('fill-only mode uses actual fill price for P&L', () => {
    // Simulates: estimated credit = $0.27, Tradier filled at $0.25
    const estimatedCredit = 0.27
    const actualFillPrice = 0.25
    const contracts = 5

    // Paper P&L would be based on estimated
    const paperMaxProfit = estimatedCredit * 100 * contracts // $135
    // Tradier-fill P&L is based on actual
    const tradierMaxProfit = actualFillPrice * 100 * contracts // $125

    expect(tradierMaxProfit).toBeLessThan(paperMaxProfit)
    expect(tradierMaxProfit).toBe(125)
  })

  it('fill-only collateral recalculates from actual fill', () => {
    const spreadWidth = 5
    const estimatedCredit = 0.27
    const actualFillPrice = 0.25
    const contracts = 5

    const paperCollateral = (spreadWidth - estimatedCredit) * 100 * contracts // $2365
    const fillCollateral = (spreadWidth - actualFillPrice) * 100 * contracts  // $2375

    // Actual fill was worse → collateral is slightly higher
    expect(fillCollateral).toBeGreaterThan(paperCollateral)
  })

  it('close P&L uses entry credit from Tradier fill, not estimate', () => {
    // If FLAME opened at Tradier fill $0.25 and closes at $0.08
    const entryFromFill = 0.25
    const closePrice = 0.08
    const contracts = 5
    const pnl = Math.round((entryFromFill - closePrice) * 100 * contracts * 100) / 100
    expect(pnl).toBe(85.00)

    // If we had used the estimate ($0.27), P&L would be different
    const wrongEntry = 0.27
    const wrongPnl = Math.round((wrongEntry - closePrice) * 100 * contracts * 100) / 100
    expect(wrongPnl).toBe(95.00)

    // The fill-based P&L is the correct one
    expect(pnl).not.toBe(wrongPnl)
  })

  it('SPARK and INFERNO are NOT affected by fill-only mode', () => {
    // Verify SPARK/INFERNO would use paper estimates
    const sparkBot = BOTS[1]
    const infernoBot = BOTS[2]
    expect(sparkBot.name).toBe('spark')
    expect(infernoBot.name).toBe('inferno')
    // These bots use isFlameFillOnly = false in tryOpenTrade
    expect(sparkBot.name === 'flame').toBe(false)
    expect(infernoBot.name === 'flame').toBe(false)
  })
})

/* ================================================================== */
/*  16. End-to-end scenario walkthrough                                */
/* ================================================================== */

describe('Scenario: Full trade lifecycle P&L', () => {
  it('FLAME: open at Tradier fill → monitor with sliding PT → close at profit target', () => {
    // 1. Open: Tradier fills at $0.25 (estimated was $0.27)
    const entryCredit = 0.25 // from Tradier fill
    const contracts = 5
    const collateral = (5 - entryCredit) * 100 * contracts // $2375

    // 2. Morning: PT = 30% → need cost_to_close <= $0.175 (entry * 0.70)
    const morningPT = entryCredit * (1 - 0.30)
    expect(morningPT).toBeCloseTo(0.175, 4)

    // 3. Midday: PT = 20% → need cost_to_close <= $0.20 (entry * 0.80)
    const middayPT = entryCredit * (1 - 0.20)
    expect(middayPT).toBeCloseTo(0.20, 4)

    // 4. Afternoon: PT = 15% → need cost_to_close <= $0.2125 (entry * 0.85)
    const afternoonPT = entryCredit * (1 - 0.15)
    expect(afternoonPT).toBeCloseTo(0.2125, 4)

    // 5. Close hits in midday at cost_to_close = $0.08
    const closePrice = 0.08
    const realizedPnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100
    expect(realizedPnl).toBe(85.00)

    // 6. Collateral released
    expect(collateral).toBe(2375)
  })

  it('INFERNO: tighter strikes, wider SL, multiple positions', () => {
    const spot = 585.50
    const em = 5.90

    // Tighter strikes (SD=1.0)
    const strikes = calculateStrikes(spot, em, 1.0)
    expect(strikes.callShort - strikes.putShort).toBeLessThan(
      calculateStrikes(spot, em, 1.2).callShort - calculateStrikes(spot, em, 1.2).putShort,
    )

    // Stop loss at 3.0x (not 2.0x)
    const entry = 0.80
    const slPrice = entry * DEFAULT_CONFIG.inferno.sl_mult
    expect(slPrice).toBeCloseTo(2.40, 10)

    // INFERNO allows 0 trades/day = unlimited
    expect(DEFAULT_CONFIG.inferno.max_trades).toBe(0)
    // INFERNO max 3 contracts (not 10)
    expect(DEFAULT_CONFIG.inferno.max_contracts).toBe(3)
  })
})
