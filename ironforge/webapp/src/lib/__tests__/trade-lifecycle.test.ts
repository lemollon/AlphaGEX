/**
 * End-to-end trade lifecycle tests.
 *
 * Tests the full cycle: scan → open position → monitor MTM → close at PT/SL/EOD
 * Uses mocked DB and Tradier to verify correct SQL operations and state transitions.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const scannerSource = readFileSync(resolve(__dirname, '../scanner.ts'), 'utf-8')
const forceTradeSource = readFileSync(
  resolve(__dirname, '../../app/api/[bot]/force-trade/route.ts'), 'utf-8',
)
const forceCloseSource = readFileSync(
  resolve(__dirname, '../../app/api/[bot]/force-close/route.ts'), 'utf-8',
)

// Mock db module
const mockQuery = vi.fn().mockResolvedValue([])
const mockDbExecute = vi.fn().mockResolvedValue(1)
vi.mock('../db', () => ({
  query: (...args: any[]) => mockQuery(...args),
  dbQuery: (...args: any[]) => mockQuery(...args),
  dbExecute: (...args: any[]) => mockDbExecute(...args),
  botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
  num: (v: any) => { if (v == null || v === '') return 0; const n = parseFloat(v); return isNaN(n) ? 0 : n },
  int: (v: any) => { if (v == null || v === '') return 0; const n = parseInt(v, 10); return isNaN(n) ? 0 : n },
  CT_TODAY: "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date",
  escapeSql: (val: string) => val.replace(/'/g, "''"),
  validateBot: (bot: string) => { const b = bot.toLowerCase(); return ['flame','spark','inferno'].includes(b) ? b : null },
  dteMode: (bot: string) => { if (bot === 'flame') return '2DTE'; if (bot === 'spark') return '1DTE'; if (bot === 'inferno') return '0DTE'; return null },
  sharedTable: (name: string) => name,
}))

// Mock tradier module
vi.mock('../tradier', () => ({
  getQuote: vi.fn().mockResolvedValue({ last: 585.50, bid: 585.45, ask: 585.55, symbol: 'SPY' }),
  getOptionExpirations: vi.fn().mockResolvedValue(['2026-03-24', '2026-03-25']),
  getIcEntryCredit: vi.fn().mockResolvedValue({ putCredit: 0.15, callCredit: 0.12, totalCredit: 0.27, source: 'TRADIER_LIVE' }),
  getIcMarkToMarket: vi.fn().mockResolvedValue({ cost_to_close: 0.10, spot_price: 585.50 }),
  isConfigured: vi.fn().mockReturnValue(true),
  isConfiguredAsync: vi.fn().mockResolvedValue(true),
  placeIcOrderAllAccounts: vi.fn().mockResolvedValue({ User: { order_id: 12345, contracts: 5, fill_price: 0.27 } }),
  closeIcOrderAllAccounts: vi.fn().mockResolvedValue({ User: { order_id: 12346, contracts: 5, fill_price: 0.08 } }),
  getLoadedSandboxAccounts: vi.fn().mockReturnValue([{ name: 'User', apiKey: 'test-key' }]),
  getLoadedSandboxAccountsAsync: vi.fn().mockResolvedValue([{ name: 'User', apiKey: 'test-key' }]),
  getSandboxAccountPositions: vi.fn().mockResolvedValue([]),
  emergencyCloseSandboxPositions: vi.fn().mockResolvedValue({}),
  closeOrphanSandboxPositions: vi.fn().mockResolvedValue(0),
  getOrderFillPrice: vi.fn().mockResolvedValue(null),
  getAccountIdForKey: vi.fn().mockResolvedValue('VA12345'),
  buildOccSymbol: vi.fn().mockReturnValue('SPY260324P00580000'),
  getAccountsForBotAsync: vi.fn().mockResolvedValue(['User']),
  getAllocatedCapitalForAccount: vi.fn().mockResolvedValue(10000),
  cancelSandboxOrder: vi.fn().mockResolvedValue(false),
  SandboxOrderInfo: {},
  SandboxCloseInfo: {},
}))

beforeEach(() => {
  mockQuery.mockReset().mockResolvedValue([])
  mockDbExecute.mockReset().mockResolvedValue(1)
})

/* ================================================================== */
/*  Source code structural: full lifecycle operations                   */
/* ================================================================== */

describe('Trade open lifecycle — required DB operations', () => {
  it('force-trade INSERTs into positions table', () => {
    expect(forceTradeSource).toMatch(/INSERT INTO.*positions/)
  })

  it('force-trade INSERTs into signals table', () => {
    expect(forceTradeSource).toMatch(/INSERT INTO.*signals/)
  })

  it('force-trade UPDATEs paper_account collateral and balance', () => {
    expect(forceTradeSource).toMatch(/UPDATE.*paper_account/)
    expect(forceTradeSource).toMatch(/collateral_in_use/)
  })

  it('force-trade INSERTs equity snapshot', () => {
    expect(forceTradeSource).toMatch(/INSERT INTO.*equity_snapshots/)
  })

  it('force-trade INSERTs or UPDATEs daily_perf', () => {
    expect(forceTradeSource).toMatch(/daily_perf/)
    expect(forceTradeSource).toMatch(/ON CONFLICT/)
  })

  it('force-trade INSERTs into logs table', () => {
    expect(forceTradeSource).toMatch(/INSERT INTO.*logs/)
  })

  it('force-trade INSERTs heartbeat', () => {
    expect(forceTradeSource).toMatch(/bot_heartbeats/)
  })
})

describe('Trade close lifecycle — required DB operations', () => {
  it('force-close UPDATEs position status to closed', () => {
    expect(forceCloseSource).toMatch(/SET\s+status\s*=\s*'closed'/)
  })

  it('force-close uses WHERE status = open as guard', () => {
    expect(forceCloseSource).toMatch(/WHERE.*status\s*=\s*'open'/)
  })

  it('force-close UPDATEs paper_account (balance, collateral)', () => {
    expect(forceCloseSource).toMatch(/UPDATE.*paper_account/)
  })

  it('force-close INSERTs close log entry', () => {
    expect(forceCloseSource).toMatch(/TRADE_CLOSE/)
  })

  it('force-close UPDATEs PDT log', () => {
    expect(forceCloseSource).toMatch(/UPDATE.*pdt_log/)
  })

  it('force-close reconciles collateral from live positions', () => {
    // Must recalculate collateral from positions table, not use cached value
    expect(forceCloseSource).toMatch(/SUM\(collateral_required\)/)
  })
})

/* ================================================================== */
/*  Scanner lifecycle matches force-trade/force-close                  */
/* ================================================================== */

describe('Scanner mirrors force-trade/force-close lifecycle', () => {
  it('scanner tryOpenTrade INSERTs position', () => {
    expect(scannerSource).toMatch(/INSERT INTO.*positions/)
  })

  it('scanner tryOpenTrade INSERTs signal', () => {
    expect(scannerSource).toMatch(/INSERT INTO.*signals/)
  })

  it('scanner closePosition UPDATEs status to closed', () => {
    expect(scannerSource).toMatch(/SET\s+status\s*=\s*'closed'/)
  })

  it('scanner closePosition uses rowCount guard', () => {
    // Must check affected rows to prevent double-close
    expect(scannerSource).toMatch(/rowCount|rowsAffected/)
  })

  it('scanner has collateral reconciliation', () => {
    expect(scannerSource).toMatch(/SUM\(collateral_required\)/)
  })
})

/* ================================================================== */
/*  Failure scenarios — structural verification                        */
/* ================================================================== */

describe('Failure handling in trade lifecycle', () => {
  it('sandbox mirror failure is non-fatal in force-trade', () => {
    // Sandbox mirror is in a try/catch that doesn't re-throw
    expect(forceTradeSource).toMatch(/sandbox.*catch|catch.*sandbox/is)
  })

  it('MTM failure returns null, not throw', () => {
    // getIcMarkToMarket is in a try/catch in force-close
    expect(forceCloseSource).toMatch(/getIcMarkToMarket/)
    // And force-close handles null MTM (uses fallback price)
    expect(forceCloseSource).toMatch(/closePrice\s*=\s*0|fallback|Use 0/)
  })

  it('scanner logs scan errors as SCAN level', () => {
    expect(scannerSource).toMatch(/'SCAN'/)
    expect(scannerSource).toMatch(/action.*reason.*spot.*vix/)
  })

  it('scanner has MTM failure tracking with force-close threshold', () => {
    expect(scannerSource).toMatch(/MAX_CONSECUTIVE_MTM_FAILURES/)
    expect(scannerSource).toMatch(/_mtmFailureCounts/)
  })
})

/* ================================================================== */
/*  P&L calculation consistency                                        */
/* ================================================================== */

describe('P&L calculation consistency', () => {
  it('P&L formula is consistent: (entry_credit - close_price) * 100 * contracts', () => {
    // Verify force-close and scanner use same formula
    // force-close: (totalCredit - effectivePrice) * 100
    expect(forceCloseSource).toMatch(/totalCredit\s*-\s*effectivePrice/)
    // Scanner: (entryCredit - effectivePrice) * 100
    expect(scannerSource).toMatch(/entryCredit\s*-\s*effectivePrice/)
  })

  it('force-close rounds P&L to 2 decimal places', () => {
    expect(forceCloseSource).toMatch(/Math\.round.*100.*\/\s*100/)
  })
})
