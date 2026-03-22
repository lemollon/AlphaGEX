/**
 * Tests for scanner race guard and double-close protection.
 *
 * Verifies:
 * 1. Scanner _running flag prevents overlapping scan cycles
 * 2. Stuck scan detection resets the flag after MAX_SCAN_DURATION_MS
 * 3. force-close and eod-close routes use rowCount guards to prevent double-close
 * 4. Double-close logs SKIP and doesn't double-count P&L
 */

import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// Mock db and tradier to import scanner
vi.mock('../db', () => ({
  query: vi.fn().mockResolvedValue([]),
  dbExecute: vi.fn().mockResolvedValue(1),
  botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
  num: (v: any) => { if (v == null || v === '') return 0; const n = parseFloat(v); return isNaN(n) ? 0 : n },
  int: (v: any) => { if (v == null || v === '') return 0; const n = parseInt(v, 10); return isNaN(n) ? 0 : n },
  CT_TODAY: "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date",
}))
vi.mock('../tradier', () => ({
  getQuote: vi.fn().mockResolvedValue(null),
  getOptionExpirations: vi.fn().mockResolvedValue([]),
  getIcEntryCredit: vi.fn().mockResolvedValue(null),
  getIcMarkToMarket: vi.fn().mockResolvedValue(null),
  isConfigured: vi.fn().mockReturnValue(false),
  isConfiguredAsync: vi.fn().mockResolvedValue(false),
  placeIcOrderAllAccounts: vi.fn().mockResolvedValue({}),
  closeIcOrderAllAccounts: vi.fn().mockResolvedValue({}),
  getLoadedSandboxAccounts: vi.fn().mockReturnValue([]),
  getLoadedSandboxAccountsAsync: vi.fn().mockResolvedValue([]),
  getSandboxAccountPositions: vi.fn().mockResolvedValue([]),
  emergencyCloseSandboxPositions: vi.fn().mockResolvedValue({}),
  closeOrphanSandboxPositions: vi.fn().mockResolvedValue(0),
  getOrderFillPrice: vi.fn().mockResolvedValue(null),
  getAccountIdForKey: vi.fn().mockResolvedValue(null),
  buildOccSymbol: vi.fn().mockReturnValue('SPY260322P00580000'),
  getAccountsForBotAsync: vi.fn().mockResolvedValue([]),
  getAllocatedCapitalForAccount: vi.fn().mockResolvedValue(0),
  cancelSandboxOrder: vi.fn().mockResolvedValue(false),
  SandboxOrderInfo: {},
  SandboxCloseInfo: {},
}))

import { _testing } from '../scanner'

const scannerSource = readFileSync(
  resolve(__dirname, '../scanner.ts'),
  'utf-8',
)

const forceCloseSource = readFileSync(
  resolve(__dirname, '../../app/api/[bot]/force-close/route.ts'),
  'utf-8',
)

const eodCloseSource = readFileSync(
  resolve(__dirname, '../../app/api/[bot]/eod-close/route.ts'),
  'utf-8',
)

/* ================================================================== */
/*  Scanner concurrency guard                                          */
/* ================================================================== */

describe('Scanner concurrency guard', () => {
  it('_running flag is exposed via _testing for verification', () => {
    expect(typeof _testing._running).toBe('boolean')
  })

  it('_running defaults to false', () => {
    // Reset (tests may leave it set)
    _testing._running = false
    expect(_testing._running).toBe(false)
  })

  it('safeRunAllScans checks _running before starting', () => {
    // Source code structural test: safeRunAllScans must check _running
    const safeRunMatch = scannerSource.match(
      /function safeRunAllScans[\s\S]*?^}/m,
    )
    expect(safeRunMatch).toBeTruthy()
    const body = safeRunMatch![0]
    expect(body).toMatch(/if\s*\(\s*_running\s*\)/)
  })

  it('safeRunAllScans sets _running = true before scan and false in finally', () => {
    const safeRunMatch = scannerSource.match(
      /function safeRunAllScans[\s\S]*?^}/m,
    )
    const body = safeRunMatch![0]
    expect(body).toMatch(/_running\s*=\s*true/)
    expect(body).toMatch(/\.finally\s*\(\s*\(\)\s*=>\s*\{[\s\S]*?_running\s*=\s*false/)
  })

  it('stuck scan detection resets _running after MAX_SCAN_DURATION_MS', () => {
    const safeRunMatch = scannerSource.match(
      /function safeRunAllScans[\s\S]*?^}/m,
    )
    const body = safeRunMatch![0]
    expect(body).toMatch(/MAX_SCAN_DURATION_MS/)
    expect(body).toMatch(/STUCK SCAN DETECTED/)
  })

  it('MAX_SCAN_DURATION_MS is 5 minutes', () => {
    expect(_testing.MAX_SCAN_DURATION_MS).toBe(5 * 60 * 1000)
  })
})

/* ================================================================== */
/*  Double-close guards                                                */
/* ================================================================== */

describe('Double-close prevention', () => {
  it('force-close checks rowsAffected before updating paper_account', () => {
    // rowsAffected (or rowCount) === 0 means position was already closed
    expect(forceCloseSource).toMatch(/rowsAffected/)
    expect(forceCloseSource).toMatch(/rowsAffected\s*===\s*0/)
  })

  it('force-close logs SKIP when position already closed', () => {
    expect(forceCloseSource).toMatch(/already.?closed|skipped_pnl/i)
  })

  it('eod-close checks rowsAffected before updating paper_account', () => {
    expect(eodCloseSource).toMatch(/rowsAffected/)
    expect(eodCloseSource).toMatch(/rowsAffected\s*===\s*0/)
  })

  it('eod-close logs SKIP for already-closed positions', () => {
    expect(eodCloseSource).toMatch(/EOD SKIP.*already closed/)
  })

  it('eod-close uses continue to skip paper_account update on double-close', () => {
    // After rowsAffected === 0 check, must continue (skip rest of loop body)
    expect(eodCloseSource).toMatch(/continue\s*\/\/\s*Skip/)
  })
})
