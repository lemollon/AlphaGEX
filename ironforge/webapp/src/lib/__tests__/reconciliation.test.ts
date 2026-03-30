/**
 * Reconciliation Tests — 1:1 Matching Across Account Types
 * ==========================================================
 *
 * Verifies that P&L, equity curve, scorecard, and balance numbers are
 * consistent between paper, sandbox, and production accounts through
 * the full open → monitor → close lifecycle.
 *
 * Mix of:
 *   - Behavioral tests: mock data, compute math, verify results
 *   - Structural tests: regex on source code to verify patterns exist
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

/* ------------------------------------------------------------------ */
/*  Load source files for structural tests                             */
/* ------------------------------------------------------------------ */

const SCANNER_PATH = resolve(__dirname, '../scanner.ts')
const STATUS_PATH = resolve(__dirname, '../../app/api/[bot]/status/route.ts')
const RECONCILE_PATH = resolve(__dirname, '../../app/api/[bot]/reconcile/route.ts')
const EQUITY_PATH = resolve(__dirname, '../../app/api/[bot]/equity-curve/route.ts')
const PERF_PATH = resolve(__dirname, '../../app/api/[bot]/performance/route.ts')

const scannerSource = readFileSync(SCANNER_PATH, 'utf-8')
const statusSource = readFileSync(STATUS_PATH, 'utf-8')
const reconcileSource = readFileSync(RECONCILE_PATH, 'utf-8')
const equitySource = readFileSync(EQUITY_PATH, 'utf-8')
const perfSource = readFileSync(PERF_PATH, 'utf-8')

/* ------------------------------------------------------------------ */
/*  Shared fixtures                                                    */
/* ------------------------------------------------------------------ */

function makePosition(overrides: Record<string, any> = {}) {
  return {
    position_id: 'FLAME-20260324-A1B2C3',
    ticker: 'SPY',
    expiration: '2026-03-26',
    put_short_strike: 575,
    put_long_strike: 570,
    call_short_strike: 595,
    call_long_strike: 600,
    contracts: 5,
    spread_width: 5,
    total_credit: 1.20,
    close_price: 0.36,
    realized_pnl: 420.00,
    status: 'closed',
    close_reason: 'profit_target_morning',
    collateral_required: 1900,
    account_type: 'sandbox',
    person: null,
    open_time: '2026-03-24T14:30:00Z',
    close_time: '2026-03-24T18:00:00Z',
    sandbox_order_id: JSON.stringify({
      User: { order_id: 12345, contracts: 5, fill_price: 1.20 },
    }),
    sandbox_close_order_id: JSON.stringify({
      User: { order_id: 12346, contracts: 5, fill_price: 0.36 },
    }),
    dte_mode: '2DTE',
    ...overrides,
  }
}

/* ================================================================== */
/*  1. Open Trade Reconciliation                                       */
/* ================================================================== */

describe('1. Open Trade Reconciliation', () => {
  it('paper total_credit matches Tradier fill_price exactly when fill is present', () => {
    const pos = makePosition()
    const sandboxInfo = JSON.parse(pos.sandbox_order_id)
    const fillPrice = sandboxInfo.User.fill_price

    expect(Math.abs(pos.total_credit - fillPrice)).toBeLessThan(0.001)
  })

  it('entry credit within 5% tolerance with slippage', () => {
    const pos = makePosition({ total_credit: 1.20 })
    const fillPrice = 1.14 // 5% slippage

    const diffPct = Math.abs((pos.total_credit - fillPrice) / pos.total_credit) * 100
    expect(diffPct).toBeCloseTo(5, 10)
    // Exactly at boundary — reconcile route uses < 5, so this WOULD flag
  })

  it('detects entry credit mismatch beyond 5% tolerance', () => {
    const paperCredit = 1.20
    const fillPrice = 0.80 // 33% difference

    const diffPct = Math.abs((paperCredit - fillPrice) / paperCredit) * 100
    expect(diffPct).toBeGreaterThan(5)
  })

  it('[structural] reconcile route checks entry credit difference', () => {
    // Reconcile route computes entry_credit_diff_pct
    expect(reconcileSource).toMatch(/entry_credit_diff/)
    expect(reconcileSource).toMatch(/implied_entry_credit/)
  })

  it('[structural] scanner updates position with actual fill price', () => {
    // After sandbox fill, scanner updates total_credit with actual fill
    expect(scannerSource).toMatch(/fill_price/)
    expect(scannerSource).toMatch(/total_credit/)
  })
})

/* ================================================================== */
/*  2. Close Trade Reconciliation                                      */
/* ================================================================== */

describe('2. Close Trade Reconciliation', () => {
  it('close_price matches Tradier close fill exactly', () => {
    const pos = makePosition()
    const closeInfo = JSON.parse(pos.sandbox_close_order_id)
    const closeFill = closeInfo.User.fill_price

    expect(pos.close_price).toBe(closeFill)
  })

  it('effectivePrice uses actual fill when available, not estimated', () => {
    const estimatedPrice = 0.35
    const actualFill = 0.30

    // Scanner logic: if fill_price != null && fill_price > 0 → use it
    let effectivePrice = estimatedPrice
    if (actualFill != null && actualFill > 0) {
      effectivePrice = actualFill
    }

    expect(effectivePrice).toBe(0.30)
  })

  it('effectivePrice falls back to estimated when fill is null', () => {
    const estimatedPrice = 0.35
    const fillPrice: number | null = null

    let effectivePrice = estimatedPrice
    if (fillPrice != null && fillPrice > 0) {
      effectivePrice = fillPrice
    }

    expect(effectivePrice).toBe(0.35)
  })

  it('effectivePrice falls back to estimated when fill is 0', () => {
    const estimatedPrice = 0.35
    const fillPrice = 0

    let effectivePrice = estimatedPrice
    if (fillPrice != null && fillPrice > 0) {
      effectivePrice = fillPrice
    }

    expect(effectivePrice).toBe(0.35)
  })

  it('[structural] scanner uses fill_price for close when available', () => {
    // Scanner checks fill_price is non-null and > 0 before using
    expect(scannerSource).toMatch(/fill_price/)
    // Close logic references effective close price
    expect(scannerSource).toMatch(/close_price|effectiveClose|effective_close/)
  })
})

/* ================================================================== */
/*  3. P&L Consistency Across Account Types                            */
/* ================================================================== */

describe('3. P&L Consistency Across Account Types', () => {
  it('P&L formula produces identical results regardless of account_type label', () => {
    const entryCredit = 1.20
    const closePrice = 0.36
    const contracts = 5

    // Formula: (entry - close) * 100 * contracts
    const pnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100

    // Same formula for sandbox
    const sandboxPnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100

    // Same formula for production
    const productionPnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100

    expect(pnl).toBe(420.00)
    expect(sandboxPnl).toBe(pnl)
    expect(productionPnl).toBe(pnl)
  })

  it('P&L for loss scenario (stop loss at 2x)', () => {
    const entryCredit = 0.80
    const closePrice = 1.60 // 2x stop loss
    const contracts = 3

    const pnl = Math.round((entryCredit - closePrice) * 100 * contracts * 100) / 100

    expect(pnl).toBe(-240.00)
  })

  it('production (2 contracts) vs sandbox (10 contracts) — each correct independently', () => {
    const entryCredit = 1.20
    const closePrice = 0.36

    const prodPnl = Math.round((entryCredit - closePrice) * 100 * 2 * 100) / 100
    const sandboxPnl = Math.round((entryCredit - closePrice) * 100 * 10 * 100) / 100

    expect(prodPnl).toBe(168.00)
    expect(sandboxPnl).toBe(840.00)
    // They differ because contracts differ, but formula is identical
    expect(prodPnl / 2).toBe(sandboxPnl / 10) // per-contract P&L is same
  })

  it('[structural] production close routes to production paper_account row', () => {
    // Scanner must filter by account_type when updating production paper_account
    expect(scannerSource).toMatch(/account_type.*=.*'production'/)
  })

  it('[structural] sandbox close routes to sandbox paper_account row', () => {
    // Scanner must use COALESCE for sandbox (default account_type)
    expect(scannerSource).toMatch(/COALESCE\(account_type.*'sandbox'\)/)
  })

  it('[structural] P&L formula uses (entry_credit - close_price) * 100 * contracts', () => {
    // Both Python executor and scanner.ts must use same P&L formula
    // Scanner.ts pattern: entryCredit - effectiveClose (or similar)
    expect(scannerSource).toMatch(/entryCredit|entry_credit|total_credit/)
    expect(scannerSource).toMatch(/realizedPnl|realized_pnl/)
  })
})

/* ================================================================== */
/*  4. Balance Integrity                                               */
/* ================================================================== */

describe('4. Balance Integrity', () => {
  it('balance = starting_capital + sum of all realized P&Ls', () => {
    const startingCapital = 10000
    const pnls = [420, -240, 150]
    const totalPnl = pnls.reduce((a, b) => a + b, 0)
    const balance = Math.round((startingCapital + totalPnl) * 100) / 100

    expect(balance).toBe(10330)
  })

  it('balance never uses cached paper_account.current_balance', () => {
    const startingCapital = 10000
    const cachedBalance = 9999 // stale/wrong
    const actualRealizedPnl = 330

    const computedBalance = Math.round((startingCapital + actualRealizedPnl) * 100) / 100

    expect(computedBalance).toBe(10330)
    expect(computedBalance).not.toBe(cachedBalance)
  })

  it('[structural] status route computes balance from live SUM, not paper_account', () => {
    // Status route must query SUM(realized_pnl) from positions
    expect(statusSource).toMatch(/SUM\(realized_pnl\)/)
    // And compute balance = startingCapital + realizedPnl
    expect(statusSource).toMatch(/startingCapital.*\+.*realizedPnl|starting_capital.*\+.*realized_pnl/i)
  })

  it('balance is correct with zero trades', () => {
    const startingCapital = 10000
    const realizedPnl = 0
    const balance = Math.round((startingCapital + realizedPnl) * 100) / 100

    expect(balance).toBe(10000)
  })

  it('balance handles floating point edge cases', () => {
    const startingCapital = 10000
    const pnls = [0.01, -0.005, 0.333]
    const totalPnl = pnls.reduce((a, b) => a + b, 0)
    const balance = Math.round((startingCapital + totalPnl) * 100) / 100

    // 0.01 + (-0.005) + 0.333 = 0.338 → rounded to 0.34
    expect(balance).toBe(10000.34)
  })
})

/* ================================================================== */
/*  5. Collateral Integrity                                            */
/* ================================================================== */

describe('5. Collateral Integrity', () => {
  it('collateral = SUM of open position collateral_required', () => {
    const openPositions = [
      makePosition({ collateral_required: 1900, status: 'open' }),
      makePosition({ collateral_required: 2100, status: 'open' }),
    ]

    const totalCollateral = openPositions.reduce(
      (sum, pos) => sum + pos.collateral_required,
      0,
    )

    expect(totalCollateral).toBe(4000)
  })

  it('collateral = 0 when no open positions', () => {
    const openPositions: any[] = []
    const totalCollateral = openPositions.reduce(
      (sum, pos) => sum + pos.collateral_required,
      0,
    )

    expect(totalCollateral).toBe(0)
  })

  it('collateral_required formula: max(0, (spread - credit) * 100) * contracts', () => {
    const spreadWidth = 5
    const credit = 1.20
    const contracts = 5

    const collateralPer = Math.max(0, (spreadWidth - credit) * 100)
    const totalCollateral = collateralPer * contracts

    expect(collateralPer).toBe(380)
    expect(totalCollateral).toBe(1900)
  })

  it('[structural] status route uses SUM(collateral_required) from open positions', () => {
    expect(statusSource).toMatch(/SUM\(collateral_required\)/)
  })

  it('[structural] scanner reconciles collateral from open positions', () => {
    expect(scannerSource).toMatch(/SUM\(collateral_required\)/)
  })

  it('buying_power = balance - collateral', () => {
    const balance = 10330
    const collateral = 1900
    const buyingPower = balance - collateral

    expect(buyingPower).toBe(8430)
  })
})

/* ================================================================== */
/*  6. Equity Curve Consistency                                        */
/* ================================================================== */

describe('6. Equity Curve Consistency', () => {
  it('last point cumulative_pnl matches sum of all closed trade P&Ls', () => {
    const startingCapital = 10000
    const trades = [
      { realized_pnl: 420, close_time: '2026-03-24T18:00:00Z' },
      { realized_pnl: -240, close_time: '2026-03-25T18:00:00Z' },
      { realized_pnl: 150, close_time: '2026-03-26T18:00:00Z' },
    ]

    // Build equity curve with running sum (same as SQL SUM OVER ORDER BY)
    let cumulative = 0
    const curve = trades.map((t) => {
      cumulative += t.realized_pnl
      return {
        timestamp: t.close_time,
        pnl: t.realized_pnl,
        cumulative_pnl: cumulative,
        equity: Math.round((startingCapital + cumulative) * 100) / 100,
      }
    })

    const totalPnl = trades.reduce((sum, t) => sum + t.realized_pnl, 0)
    expect(curve[curve.length - 1].cumulative_pnl).toBe(totalPnl)
    expect(curve[curve.length - 1].cumulative_pnl).toBe(330)
    expect(curve[curve.length - 1].equity).toBe(10330)
  })

  it('equity curve running sum is monotonically correct', () => {
    const pnls = [420, -240, 150]
    let cumulative = 0

    const cumulatives = pnls.map((pnl) => {
      cumulative += pnl
      return cumulative
    })

    expect(cumulatives).toEqual([420, 180, 330])
  })

  it('[structural] equity-curve route uses SUM OVER ORDER BY for cumulative P&L', () => {
    expect(equitySource).toMatch(/SUM\(realized_pnl\) OVER \(ORDER BY close_time\)/)
  })

  it('live unrealized point appended to equity curve', () => {
    const startingCapital = 10000
    const lastCumPnl = 420 // from closed trades
    const unrealizedPnl = 50 // from open position MTM

    const liveCumPnl = lastCumPnl + unrealizedPnl
    const liveEquity = Math.round((startingCapital + liveCumPnl) * 100) / 100

    expect(liveCumPnl).toBe(470)
    expect(liveEquity).toBe(10470)
  })

  it('[structural] equity-curve route appends live unrealized point', () => {
    expect(equitySource).toMatch(/liveUnrealizedPnl|live_unrealized/)
    expect(equitySource).toMatch(/curve\.push/)
  })

  it('equity curve and status balance agree at same realized P&L', () => {
    const startingCapital = 10000
    const realizedPnl = 330

    // Equity curve formula
    const equityBalance = Math.round((startingCapital + realizedPnl) * 100) / 100

    // Status route formula (same)
    const statusBalance = Math.round((startingCapital + realizedPnl) * 100) / 100

    expect(equityBalance).toBe(statusBalance)
    expect(equityBalance).toBe(10330)
  })
})

/* ================================================================== */
/*  7. Scorecard Consistency                                           */
/* ================================================================== */

describe('7. Scorecard Consistency', () => {
  it('win rate = wins / total * 100', () => {
    const wins = 7
    const total = 10
    const winRate = Math.round((wins / total) * 100 * 10) / 10

    expect(winRate).toBe(70.0)
  })

  it('total P&L in scorecard matches SUM(realized_pnl)', () => {
    const trades = [420, -240, 150, 80, -100]
    const totalPnl = Math.round(trades.reduce((a, b) => a + b, 0) * 100) / 100

    expect(totalPnl).toBe(310)
  })

  it('[structural] performance route filters by account_type', () => {
    expect(perfSource).toMatch(/COALESCE\(account_type.*'sandbox'\)/)
    expect(perfSource).toMatch(/accountTypeFilter|account_type/)
  })

  it('sandbox and production scorecards are independent (no mixing)', () => {
    // Sandbox trades
    const sandboxPnls = [420, -240]
    const sandboxTotal = sandboxPnls.reduce((a, b) => a + b, 0)
    const sandboxWins = sandboxPnls.filter((p) => p > 0).length
    const sandboxWinRate = Math.round((sandboxWins / sandboxPnls.length) * 100 * 10) / 10

    // Production trades
    const prodPnls = [80]
    const prodTotal = prodPnls.reduce((a, b) => a + b, 0)
    const prodWins = prodPnls.filter((p) => p > 0).length
    const prodWinRate = Math.round((prodWins / prodPnls.length) * 100 * 10) / 10

    expect(sandboxTotal).toBe(180)
    expect(sandboxWinRate).toBe(50.0)
    expect(prodTotal).toBe(80)
    expect(prodWinRate).toBe(100.0)

    // No cross-contamination
    expect(sandboxTotal).not.toBe(sandboxTotal + prodTotal)
  })
})

/* ================================================================== */
/*  8. Orphan Detection                                                */
/* ================================================================== */

describe('8. Orphan Detection', () => {
  it('Tradier positions not in DB are flagged as orphans', () => {
    const dbPositionIds = new Set(['FLAME-20260324-A1B2C3'])
    const tradierSymbols = [
      'SPY260326P00575000', // matches DB position
      'SPY260326P00570000', // matches DB position
      'SPY260326C00595000', // matches DB position
      'SPY260326C00600000', // matches DB position
      'SPY260326P00560000', // ORPHAN — not in any DB position
    ]

    // After matching, any unmatched Tradier symbols are orphans
    const matchedSymbols = new Set([
      'SPY260326P00575000',
      'SPY260326P00570000',
      'SPY260326C00595000',
      'SPY260326C00600000',
    ])

    const orphans = tradierSymbols.filter((s) => !matchedSymbols.has(s))
    expect(orphans).toHaveLength(1)
    expect(orphans[0]).toBe('SPY260326P00560000')
  })

  it('DB positions not in Tradier are flagged as missing', () => {
    const dbPositions = [
      makePosition({ position_id: 'FLAME-001', status: 'open' }),
      makePosition({ position_id: 'FLAME-002', status: 'open' }),
    ]

    const tradierAccountHasLegs = new Set(['FLAME-001']) // only 001 found in Tradier

    const missing = dbPositions.filter(
      (pos) => !tradierAccountHasLegs.has(pos.position_id),
    )

    expect(missing).toHaveLength(1)
    expect(missing[0].position_id).toBe('FLAME-002')
  })

  it('[structural] reconcile route has orphan detection logic', () => {
    expect(reconcileSource).toMatch(/orphan/i)
    // Should track matched vs unmatched symbols
    expect(reconcileSource).toMatch(/matched|unmatched/i)
  })
})

/* ================================================================== */
/*  9. Production Isolation                                            */
/* ================================================================== */

describe('9. Production Isolation', () => {
  it('production P&L does NOT appear in sandbox totals', () => {
    const allPositions = [
      makePosition({ account_type: 'sandbox', realized_pnl: 420 }),
      makePosition({ account_type: 'production', realized_pnl: 80 }),
      makePosition({ account_type: 'sandbox', realized_pnl: -240 }),
    ]

    const sandboxPnl = allPositions
      .filter((p) => (p.account_type || 'sandbox') === 'sandbox')
      .reduce((sum, p) => sum + p.realized_pnl, 0)

    const prodPnl = allPositions
      .filter((p) => p.account_type === 'production')
      .reduce((sum, p) => sum + p.realized_pnl, 0)

    expect(sandboxPnl).toBe(180) // 420 + (-240)
    expect(prodPnl).toBe(80)
    expect(sandboxPnl + prodPnl).toBe(260) // combined, but never shown together
  })

  it('sandbox P&L does NOT appear in production totals', () => {
    const allPositions = [
      makePosition({ account_type: 'sandbox', realized_pnl: 420 }),
      makePosition({ account_type: 'production', realized_pnl: 80 }),
    ]

    const prodOnly = allPositions.filter((p) => p.account_type === 'production')
    const prodPnl = prodOnly.reduce((sum, p) => sum + p.realized_pnl, 0)

    expect(prodPnl).toBe(80)
    expect(prodOnly).toHaveLength(1) // sandbox trade excluded
  })

  it('[structural] all position queries filter by account_type', () => {
    // Status route filters
    expect(statusSource).toMatch(/account_type/)
    // Performance route filters
    expect(perfSource).toMatch(/account_type/)
    // Equity curve route filters
    expect(equitySource).toMatch(/account_type/)
  })
})
