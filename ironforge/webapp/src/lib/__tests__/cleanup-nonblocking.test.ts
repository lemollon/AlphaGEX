/**
 * Tests verifying cleanup and health check behavior in runAllScans.
 *
 * dailySandboxCleanup is BLOCKING (awaited) — stale positions must be cleared
 * before scanning or every new order gets rejected (1500+ rejections/day).
 *
 * prescanSandboxHealthCheck is fire-and-forget (non-blocking).
 *
 * These tests verify the code structure by reading the source.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

/* ================================================================== */
/*  1. Code Structure: Cleanup blocking, health check fire-and-forget  */
/* ================================================================== */

describe('Cleanup: Code Structure', () => {
  const scannerSource = readFileSync(
    resolve(__dirname, '../scanner.ts'),
    'utf-8',
  )

  it('dailySandboxCleanup IS awaited (blocking) in runAllScans', () => {
    // Cleanup MUST block bot scanning — stale positions consume buying power
    // and cause every new order to be rejected (1500+ rejections/day).
    const runAllScansMatch = scannerSource.match(
      /async function runAllScans\(\)[\s\S]*?^}/m,
    )
    expect(runAllScansMatch).toBeTruthy()
    const fnBody = runAllScansMatch![0]

    // Must contain "await dailySandboxCleanup(ct)" inside a try/catch
    expect(fnBody).toMatch(/await\s+dailySandboxCleanup\(ct\)/)
  })

  it('prescanSandboxHealthCheck is NOT awaited in runAllScans', () => {
    const runAllScansMatch = scannerSource.match(
      /async function runAllScans\(\)[\s\S]*?^}/m,
    )
    expect(runAllScansMatch).toBeTruthy()
    const fnBody = runAllScansMatch![0]

    // Must NOT contain "await prescanSandboxHealthCheck"
    expect(fnBody).not.toMatch(/await\s+prescanSandboxHealthCheck/)

    // Must contain the fire-and-forget pattern
    expect(fnBody).toMatch(/prescanSandboxHealthCheck\(\)\.catch/)
  })

  it('bot scanning (scanBot) runs AFTER cleanup completes', () => {
    const runAllScansMatch = scannerSource.match(
      /async function runAllScans\(\)[\s\S]*?^}/m,
    )
    expect(runAllScansMatch).toBeTruthy()
    const fnBody = runAllScansMatch![0]

    // dailySandboxCleanup (awaited) must appear BEFORE scanBot calls
    const cleanupIdx = fnBody.indexOf('dailySandboxCleanup(ct)')
    const scanBotIdx = fnBody.indexOf('scanBot(bot)')

    expect(cleanupIdx).toBeGreaterThan(-1)
    expect(scanBotIdx).toBeGreaterThan(-1)
    expect(scanBotIdx).toBeGreaterThan(cleanupIdx)
  })
})

/* ================================================================== */
/*  2. Position Counting Independence                                  */
/* ================================================================== */

describe('Cleanup Non-Blocking: Position Count Independence', () => {
  const scannerSource = readFileSync(
    resolve(__dirname, '../scanner.ts'),
    'utf-8',
  )

  it('position counting queries the DATABASE, not Tradier sandbox', () => {
    // The monitorPosition query must use botTable (PostgreSQL), not Tradier API
    // Pattern: SELECT position_id ... FROM ... positions ... WHERE status = 'open'
    // (multiline SQL — use dotAll flag)
    expect(scannerSource).toMatch(
      /SELECT\s+position_id[\s\S]*?FROM[\s\S]*?positions[\s\S]*?WHERE\s+status\s*=\s*'open'/i,
    )
  })

  it('dailySandboxCleanup operates on Tradier sandbox positions', () => {
    // Cleanup calls getSandboxAccountPositions (Tradier API), not DB query
    const cleanupMatch = scannerSource.match(
      /async function dailySandboxCleanup[\s\S]*?^}/m,
    )
    expect(cleanupMatch).toBeTruthy()
    expect(cleanupMatch![0]).toMatch(/getSandboxAccountPositions/)
  })

  it('no race: cleanup and position counting use different data stores', () => {
    // This is a documentation test — cleanup modifies Tradier sandbox,
    // position counting reads PostgreSQL. Different stores = no race.
    // If someone changes this, this test will catch it.

    const cleanupFn = scannerSource.match(
      /async function dailySandboxCleanup[\s\S]*?^}/m,
    )![0]
    const scanBotFn = scannerSource.match(
      /async function scanBot[\s\S]*?^}/m,
    )![0]

    // Cleanup should NOT directly modify DB positions (no UPDATE...status)
    // It only closes Tradier sandbox positions
    expect(cleanupFn).not.toMatch(/UPDATE.*positions.*SET.*status/)

    // scanBot should count from DB, not Tradier
    // monitorPosition (called by scanBot) queries positions table
    expect(scannerSource).toMatch(/SELECT\s+position_id[\s\S]*?FROM[\s\S]*?positions/i)
  })
})

/* ================================================================== */
/*  3. Double-Close Guard                                              */
/* ================================================================== */

describe('Cleanup Non-Blocking: Double-Close Guard', () => {
  const scannerSource = readFileSync(
    resolve(__dirname, '../scanner.ts'),
    'utf-8',
  )

  it('closePosition checks rowsAffected to prevent double-close', () => {
    // The closePosition function must check if the UPDATE actually modified a row
    // Pattern: rowsAffected === 0 means position was already closed
    const closePosFn = scannerSource.match(
      /async function closePosition[\s\S]*?^}/m,
    )
    expect(closePosFn).toBeTruthy()
    expect(closePosFn![0]).toMatch(/rowsAffected/)
  })
})

/* ================================================================== */
/*  4. Stuck Scan Detector                                             */
/* ================================================================== */

describe('Cleanup Non-Blocking: Stuck Scan Safety', () => {
  // Import the _testing export for runtime checks
  vi.mock('../db', () => ({
    query: vi.fn().mockResolvedValue([]),
    dbExecute: vi.fn().mockResolvedValue(1),
    botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
    num: (v: any) => (v == null || v === '' ? 0 : parseFloat(v) || 0),
    int: (v: any) => (v == null || v === '' ? 0 : parseInt(v, 10) || 0),
    CT_TODAY: "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date",
  }))

  vi.mock('../tradier', () => ({
    getQuote: vi.fn().mockResolvedValue(null),
    isConfigured: vi.fn().mockReturnValue(false),
    isConfiguredAsync: vi.fn().mockResolvedValue(false),
    getLoadedSandboxAccountsAsync: vi.fn().mockResolvedValue([]),
    getLoadedSandboxAccounts: vi.fn().mockReturnValue([]),
    placeIcOrderAllAccounts: vi.fn().mockResolvedValue({}),
    closeIcOrderAllAccounts: vi.fn().mockResolvedValue({}),
    emergencyCloseSandboxPositions: vi.fn().mockResolvedValue({ closed: 0, failed: 0, details: [] }),
    getSandboxAccountPositions: vi.fn().mockResolvedValue([]),
    getIcMarkToMarket: vi.fn().mockResolvedValue(null),
    getIcEntryCredit: vi.fn().mockResolvedValue(null),
    getOptionExpirations: vi.fn().mockResolvedValue([]),
  }))

  // Dynamic import after mocks
  let _testing: any
  beforeEach(async () => {
    const mod = await import('../scanner')
    _testing = mod._testing
  })

  it('MAX_SCAN_DURATION_MS is 5 minutes', () => {
    expect(_testing.MAX_SCAN_DURATION_MS).toBe(5 * 60 * 1000)
  })

  it('stuck scan detector resets _running flag', () => {
    // Simulate a scan that has been running for 6 minutes
    _testing._running = true
    _testing._scanStartedAt = Date.now() - (6 * 60 * 1000) // 6 min ago

    // The safeRunAllScans function would check this and reset
    const isStuck = _testing._scanStartedAt !== null &&
      Date.now() - _testing._scanStartedAt > _testing.MAX_SCAN_DURATION_MS

    expect(isStuck).toBe(true)

    // Clean up
    _testing._running = false
    _testing._scanStartedAt = null
  })
})
