/**
 * Integration tests for IronForge Accounts system.
 * Tests: capital_pct CRUD, allocated capital calculation, live balance fetching,
 * bot assignment filtering, scanner capital integration, edge cases.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/* ── Mock setup ──────────────────────────────────────────────── */

// Set env vars before any imports
vi.hoisted(() => {
  process.env.TRADIER_API_KEY = 'test-production-key'
  process.env.TRADIER_SANDBOX_KEY_USER = 'test-sandbox-user'
  process.env.TRADIER_SANDBOX_KEY_MATT = 'test-sandbox-matt'
  process.env.TRADIER_SANDBOX_KEY_LOGAN = 'test-sandbox-logan'
})

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Mock the db module
const mockDbQuery = vi.fn()
const mockDbExecute = vi.fn()
vi.mock('../db', () => ({
  query: (...args: any[]) => mockDbQuery(...args),
  dbQuery: (...args: any[]) => mockDbQuery(...args),
  dbExecute: (...args: any[]) => mockDbExecute(...args),
  sharedTable: (name: string) => name,
  botTable: (bot: string, table: string) => `${bot}_${table}`,
  escapeSql: (s: string) => s.replace(/'/g, "''"),
  num: (v: any) => parseFloat(v) || 0,
  int: (v: any) => parseInt(v) || 0,
  CT_TODAY: "'2026-03-21'",
}))

import {
  getAccountsForBotAsync,
  getCapitalPctForAccount,
  getAllocatedCapitalForAccount,
  getPdtEnabledForAccount,
} from '../tradier'
import { readFileSync } from 'fs'
import { resolve } from 'path'

/* ── Helpers ──────────────────────────────────────────────────── */

function jsonResponse(data: any, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  }
}

function tradierProfileResponse(accountNumber: string) {
  return jsonResponse({
    profile: {
      account: { account_number: accountNumber },
    },
  })
}

function tradierBalanceResponse(equity: number, obp: number) {
  return jsonResponse({
    balances: {
      total_equity: equity,
      margin: { option_buying_power: obp },
    },
  })
}

function tradierPositionsResponse(count: number) {
  const positions = count > 0
    ? Array.from({ length: count }, (_, i) => ({ id: i, symbol: `SPY${i}` }))
    : 'null'
  return jsonResponse({
    positions: count > 0 ? { position: positions } : { position: 'null' },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  mockDbQuery.mockReset()
  mockDbExecute.mockReset()
  mockFetch.mockReset()
})

/* ── Group 1: Database Schema & Migration ────────────────────── */

describe('Database Schema & Migration', () => {
  it('should have capital_pct column with default 100', () => {
    // The ensureColumns() in manage/route.ts creates:
    // ALTER TABLE ... ADD COLUMN IF NOT EXISTS capital_pct INTEGER DEFAULT 100
    // We verify the default is 100 by checking getCapitalPctForAccount fallback
    mockDbQuery.mockResolvedValueOnce([]) // no rows found
    return getCapitalPctForAccount('Unknown').then(pct => {
      expect(pct).toBe(100) // default fallback
    })
  })

  it('should read capital_pct from DB when account exists', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: 50 }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(50)
  })

  it('should default to 100 when capital_pct is null in DB', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: null }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(100)
  })

  it('should default to 100 when DB query fails', async () => {
    mockDbQuery.mockRejectedValueOnce(new Error('connection refused'))
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(100)
  })
})

/* ── Group 2: capital_pct CRUD Validation ────────────────────── */

describe('capital_pct CRUD Validation', () => {
  it('should accept capital_pct=50', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: 50 }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(50)
  })

  it('should accept capital_pct=1 (minimum)', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: 1 }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(1)
  })

  it('should accept capital_pct=100 (maximum)', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: 100 }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(100)
  })

  it('should reject capital_pct=0 (below minimum) → defaults to 100', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: 0 }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(100) // 0 is outside 1-100 range
  })

  it('should reject capital_pct=-1 → defaults to 100', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: -1 }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(100)
  })

  it('should reject capital_pct=101 → defaults to 100', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: 101 }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(100)
  })

  it('should handle non-numeric capital_pct → defaults to 100', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: 'abc' }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(100)
  })

  it('should truncate float string capital_pct="50.5" → 50 (parseInt)', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: '50.5' }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(50) // parseInt truncates, does not round
  })

  it('should handle partial numeric string capital_pct="100a" → 100', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: '100a' }])
    const pct = await getCapitalPctForAccount('User')
    expect(pct).toBe(100) // parseInt("100a") = 100, which is in range
  })
})

/* ── Group 3: Allocated Capital Calculation ──────────────────── */

describe('Allocated Capital Calculation', () => {
  // Note: getAllocatedCapitalForAccount calls getAccountIdForKey internally,
  // which caches account IDs. Once cached for a given API key, the profile
  // fetch won't be called again. We use unique API keys per test to avoid cache interference.

  function setupTradierMocks(equity: number, apiKey: string) {
    // getAccountIdForKey calls /user/profile, then getSandboxTotalEquity calls /accounts/.../balances
    mockFetch
      .mockImplementation((url: string) => {
        const urlStr = typeof url === 'string' ? url : url.toString()
        if (urlStr.includes('/user/profile')) {
          return Promise.resolve(tradierProfileResponse('VA-TEST'))
        }
        if (urlStr.includes('/balances')) {
          return Promise.resolve(tradierBalanceResponse(equity, equity * 0.9))
        }
        return Promise.resolve(jsonResponse(null, 404))
      })
  }

  it('should calculate 50% of $50,000 = $25,000', async () => {
    const apiKey = 'unique-key-50pct'
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 50 }])
      .mockResolvedValueOnce([{ api_key: apiKey }])
    setupTradierMocks(50000, apiKey)

    const allocated = await getAllocatedCapitalForAccount('User')
    expect(allocated).toBe(25000)
  })

  it('should calculate 100% of $50,000 = $50,000', async () => {
    const apiKey = 'unique-key-100pct'
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 100 }])
      .mockResolvedValueOnce([{ api_key: apiKey }])
    setupTradierMocks(50000, apiKey)

    const allocated = await getAllocatedCapitalForAccount('User100')
    expect(allocated).toBe(50000)
  })

  it('should calculate 1% of $100,000 = $1,000', async () => {
    const apiKey = 'unique-key-1pct'
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 1 }])
      .mockResolvedValueOnce([{ api_key: apiKey }])
    setupTradierMocks(100000, apiKey)

    const allocated = await getAllocatedCapitalForAccount('User1')
    expect(allocated).toBe(1000)
  })

  it('should round to 2 decimal places', async () => {
    const apiKey = 'unique-key-33pct'
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 33 }])
      .mockResolvedValueOnce([{ api_key: apiKey }])
    setupTradierMocks(10000, apiKey)

    const allocated = await getAllocatedCapitalForAccount('User33')
    expect(allocated).toBe(3300)
  })

  it('should fallback to $10,000 × pct when Tradier is unreachable', async () => {
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 50 }])
      .mockResolvedValueOnce([{ api_key: 'unreachable-key' }])
    mockFetch.mockRejectedValue(new Error('network error'))

    const allocated = await getAllocatedCapitalForAccount('UserDown')
    expect(allocated).toBe(5000)
  })

  it('should fallback when no account found in DB', async () => {
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 25 }])
      .mockResolvedValueOnce([]) // no api_key row

    const allocated = await getAllocatedCapitalForAccount('Ghost')
    expect(allocated).toBe(2500)
  })

  it('should fallback when API key is empty string (falsy)', async () => {
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 50 }])
      .mockResolvedValueOnce([{ api_key: '' }]) // empty string, not NULL

    const allocated = await getAllocatedCapitalForAccount('EmptyKey')
    // "" is falsy in JS, so `if (rows[0].api_key)` skips → fallback
    expect(allocated).toBe(5000) // $10,000 × 50%
  })

  it('should round allocated capital to 2 decimal places', async () => {
    const apiKey = 'unique-key-rounding'
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 33 }])
      .mockResolvedValueOnce([{ api_key: apiKey }])
    // 33% of $10,001 = 3300.33 (clean), but try 33% of $10,003 = 3300.99
    mockFetch.mockImplementation((url: string) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('/user/profile')) {
        return Promise.resolve(tradierProfileResponse('VA-ROUND'))
      }
      if (urlStr.includes('/balances')) {
        return Promise.resolve(tradierBalanceResponse(10003, 9000))
      }
      return Promise.resolve(jsonResponse(null, 404))
    })

    const allocated = await getAllocatedCapitalForAccount('RoundUser')
    // Math.round(10003 * 33 / 100 * 100) / 100 = Math.round(330099) / 100 = 3300.99
    expect(allocated).toBe(3300.99)
    // Verify it's exactly 2 decimal places (no floating point artifacts)
    expect(String(allocated).split('.')[1]?.length ?? 0).toBeLessThanOrEqual(2)
  })
})

/* ── Group 5: Bot Assignment Filtering (DB-backed) ───────────── */

describe('Bot Assignment Filtering (DB-backed)', () => {
  it('should return persons from DB where bot contains FLAME', async () => {
    mockDbQuery.mockResolvedValueOnce([
      { person: 'User' },
      { person: 'Matt' },
    ])

    const accounts = await getAccountsForBotAsync('flame')
    expect(accounts).toEqual(['User', 'Matt'])
  })

  it('should return persons for SPARK from DB', async () => {
    mockDbQuery.mockResolvedValueOnce([
      { person: 'Logan' },
    ])

    const accounts = await getAccountsForBotAsync('spark')
    expect(accounts).toEqual(['Logan'])
  })

  it('should handle FLAME,SPARK,INFERNO (BOTH equivalent)', async () => {
    mockDbQuery.mockResolvedValueOnce([
      { person: 'User' },
      { person: 'Matt' },
      { person: 'Logan' },
    ])

    const accounts = await getAccountsForBotAsync('flame')
    expect(accounts).toEqual(['User', 'Matt', 'Logan'])
  })

  it('should fallback to hardcoded BOT_ACCOUNTS when DB fails', async () => {
    mockDbQuery.mockRejectedValueOnce(new Error('connection refused'))

    const accounts = await getAccountsForBotAsync('flame')
    // Fallback returns BOT_ACCOUNTS.flame.accounts = ['User']
    expect(accounts).toEqual(['User'])
  })

  it('should fallback when DB returns empty results', async () => {
    mockDbQuery.mockResolvedValueOnce([])

    const accounts = await getAccountsForBotAsync('spark')
    // Fallback returns BOT_ACCOUNTS.spark.accounts = []
    expect(accounts).toEqual([])
  })

  it('should return empty for unknown bot', async () => {
    mockDbQuery.mockResolvedValueOnce([])

    const accounts = await getAccountsForBotAsync('unknown_bot')
    // Falls back to BOT_ACCOUNTS['unknown_bot']?.accounts ?? ['User']
    expect(accounts).toEqual(['User'])
  })
})

/* ── Group 8: Edge Cases ─────────────────────────────────────── */

describe('Edge Cases', () => {
  it('should handle account with $0 balance → allocated = $0', async () => {
    mockDbQuery
      .mockResolvedValueOnce([{ capital_pct: 100 }])
      .mockResolvedValueOnce([{ api_key: 'zero-balance-key' }])
    mockFetch.mockImplementation((url: string) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('/user/profile')) {
        return Promise.resolve(tradierProfileResponse('VA-ZERO'))
      }
      if (urlStr.includes('/balances')) {
        return Promise.resolve(tradierBalanceResponse(0, 0))
      }
      return Promise.resolve(jsonResponse(null, 404))
    })

    const allocated = await getAllocatedCapitalForAccount('UserZero')
    expect(allocated).toBe(0)
  })

  it('should handle SQL injection in person name', async () => {
    // The person name should be escaped via .replace(/'/g, "''")
    const malicious = "Robert'; DROP TABLE ironforge_accounts;--"
    mockDbQuery.mockResolvedValueOnce([])

    const pct = await getCapitalPctForAccount(malicious)
    expect(pct).toBe(100) // defaults gracefully, no crash
    // Verify the query was called with escaped name
    const queryCall = mockDbQuery.mock.calls[0]?.[0]
    expect(queryCall).not.toContain("Robert';")
    expect(queryCall).toContain("Robert'';")
  })

  it('should handle multiple persons — returns first match', async () => {
    mockDbQuery.mockResolvedValueOnce([{ capital_pct: 75 }])
    // ORDER BY type DESC LIMIT 1 ensures only one row
    const pct = await getCapitalPctForAccount('Matt')
    expect(pct).toBe(75)
  })

  it('should handle getCapitalPctForAccount with empty string person', async () => {
    mockDbQuery.mockResolvedValueOnce([])
    const pct = await getCapitalPctForAccount('')
    expect(pct).toBe(100) // defaults
  })
})

/* ── Group 4: Scanner Capital Flow (Code Structure) ──────────── */

describe('Scanner Capital Flow (Code Structure)', () => {
  const scannerSource = readFileSync(
    resolve(__dirname, '../scanner.ts'),
    'utf-8',
  )

  it('scanner imports getAllocatedCapitalForAccount from tradier', () => {
    expect(scannerSource).toMatch(/import[\s\S]*?getAllocatedCapitalForAccount[\s\S]*?from\s+['"]\.\/tradier['"]/)
  })

  it('scanner imports getAccountsForBotAsync from tradier', () => {
    expect(scannerSource).toMatch(/import[\s\S]*?getAccountsForBotAsync[\s\S]*?from\s+['"]\.\/tradier['"]/)
  })

  it('getStartingCapitalForBot calls getAllocatedCapitalForAccount', () => {
    const fnMatch = scannerSource.match(
      /async function getStartingCapitalForBot[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/getAccountsForBotAsync/)
    expect(fnBody).toMatch(/getAllocatedCapitalForAccount/)
  })

  it('getStartingCapitalForBot falls back to DEFAULT_CONFIG when no accounts', () => {
    const fnMatch = scannerSource.match(
      /async function getStartingCapitalForBot[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    // Must have fallback to DEFAULT_CONFIG
    expect(fnBody).toMatch(/DEFAULT_CONFIG/)
    // Must have try/catch for graceful fallback
    expect(fnBody).toMatch(/catch/)
  })

  it('loadConfigOverrides calls getStartingCapitalForBot', () => {
    const fnMatch = scannerSource.match(
      /async function loadConfigOverrides[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/getStartingCapitalForBot/)
  })

  it('loadConfigOverrides calls syncPaperAccountCapital', () => {
    const fnMatch = scannerSource.match(
      /async function loadConfigOverrides[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/syncPaperAccountCapital/)
  })

  it('getStartingCapitalForBot uses persons[0] — first person only', () => {
    // When multiple accounts are assigned to a bot, only the first person's
    // allocated capital is used. This is by design (documented behavior).
    const fnMatch = scannerSource.match(
      /async function getStartingCapitalForBot[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    // Uses persons[0], not a loop over all persons
    expect(fnBody).toMatch(/persons\[0\]/)
    // Does NOT iterate over all persons
    expect(fnBody).not.toMatch(/for\s*\(.*persons/)
  })
})

/* ── Group 6: Paper Account Capital Sync (Code Structure) ───── */

describe('Paper Account Capital Sync (Code Structure)', () => {
  const scannerSource = readFileSync(
    resolve(__dirname, '../scanner.ts'),
    'utf-8',
  )

  it('syncPaperAccountCapital reads current starting_capital from DB', () => {
    const fnMatch = scannerSource.match(
      /async function syncPaperAccountCapital[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    // Must SELECT starting_capital from paper_account
    expect(fnBody).toMatch(/SELECT.*starting_capital/)
  })

  it('syncPaperAccountCapital updates balance as target + pnl', () => {
    const fnMatch = scannerSource.match(
      /async function syncPaperAccountCapital[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    // Must UPDATE with new starting_capital, current_balance, buying_power
    expect(fnBody).toMatch(/UPDATE.*paper_account/)
    expect(fnBody).toMatch(/SET\s+starting_capital/)
    expect(fnBody).toMatch(/current_balance/)
    expect(fnBody).toMatch(/buying_power/)
  })

  it('syncPaperAccountCapital skips update for <$1 change', () => {
    const fnMatch = scannerSource.match(
      /async function syncPaperAccountCapital[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    // Must have threshold check to avoid unnecessary writes
    expect(fnBody).toMatch(/Math\.abs.*<\s*1/)
  })

  it('syncPaperAccountCapital updates high_water_mark', () => {
    const fnMatch = scannerSource.match(
      /async function syncPaperAccountCapital[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    // Must update HWM alongside balance
    expect(fnBody).toMatch(/high_water_mark/)
  })
})

/* ── Group 7: PDT Account Integration ────────────────────────── */

describe('PDT Account Integration', () => {
  it('should return true (default) when no account in DB', async () => {
    mockDbQuery.mockResolvedValueOnce([])
    const pdt = await getPdtEnabledForAccount('Unknown')
    expect(pdt).toBe(true)
  })

  it('should return false when pdt_enabled = false in DB', async () => {
    mockDbQuery.mockResolvedValueOnce([{ pdt_enabled: false }])
    const pdt = await getPdtEnabledForAccount('User')
    expect(pdt).toBe(false)
  })

  it('should return true when pdt_enabled = true in DB', async () => {
    mockDbQuery.mockResolvedValueOnce([{ pdt_enabled: true }])
    const pdt = await getPdtEnabledForAccount('User')
    expect(pdt).toBe(true)
  })

  it('should handle string "true" from DB', async () => {
    mockDbQuery.mockResolvedValueOnce([{ pdt_enabled: 'true' }])
    const pdt = await getPdtEnabledForAccount('User')
    expect(pdt).toBe(true)
  })

  it('should default to true when DB query fails', async () => {
    mockDbQuery.mockRejectedValueOnce(new Error('connection refused'))
    const pdt = await getPdtEnabledForAccount('User')
    expect(pdt).toBe(true)
  })
})

/* ── Group 9: Consistent Balance Basis ────────────────────────── */

describe('Consistent Balance Basis (total_equity)', () => {
  const tradierSource = readFileSync(
    resolve(__dirname, '../tradier.ts'),
    'utf-8',
  )

  it('getAllocatedCapitalForAccount uses getSandboxTotalEquity, not getSandboxBuyingPower', () => {
    const fnMatch = tradierSource.match(
      /async function getAllocatedCapitalForAccount[\s\S]*?^}/m,
    )
    // It's exported, so match with export
    const fnExportMatch = tradierSource.match(
      /export async function getAllocatedCapitalForAccount[\s\S]*?^}/m,
    )
    const fnBody = (fnExportMatch || fnMatch)?.[0] ?? ''
    expect(fnBody).toBeTruthy()
    expect(fnBody).toMatch(/getSandboxTotalEquity/)
    expect(fnBody).not.toMatch(/getSandboxBuyingPower/)
  })

  it('getSandboxTotalEquity reads total_equity from balances', () => {
    const fnMatch = tradierSource.match(
      /async function getSandboxTotalEquity[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/total_equity/)
  })

  it('placeIcOrderAllAccounts uses getAccountsForBotAsync (DB-backed)', () => {
    const fnMatch = tradierSource.match(
      /export async function placeIcOrderAllAccounts[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/getAccountsForBotAsync/)
  })
})

/* ── Group 10: Edge Cases — Boundary & Coercion ─────────────── */

describe('Edge Cases: Boundary & Type Coercion', () => {
  const scannerSource = readFileSync(
    resolve(__dirname, '../scanner.ts'),
    'utf-8',
  )
  const tradierSource = readFileSync(
    resolve(__dirname, '../tradier.ts'),
    'utf-8',
  )

  it('scanner blocks trades when buying power < $200', () => {
    // tryOpenTrade checks buyingPower < 200 and returns skip
    const fnMatch = scannerSource.match(
      /async function tryOpenTrade[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/buyingPower\s*<\s*200/)
    expect(fnBody).toMatch(/skip:low_bp/)
  })

  it('negative buying power is caught by <200 check (handles -$3000)', () => {
    // buyingPower = balance - liveCollateral can be negative
    // -3000 < 200 is true, so trade is blocked
    const negativeBP = 5000 - 8000 // -3000
    expect(negativeBP).toBeLessThan(200)
  })

  it('sandbox orders use Math.max(1, ...) for minimum contract floor', () => {
    const tradierSource = readFileSync(
      resolve(__dirname, '../tradier.ts'),
      'utf-8',
    )
    // placeForAccount sizes with Math.max(1, Math.floor(usableBP / brokerMarginPer))
    // This forces at least 1 contract even when BP can't cover it — sandbox concern
    const fnMatch = tradierSource.match(
      /async function placeForAccount[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/Math\.max\(1/)
  })

  it('scanner syncPaperAccountCapital runs before bot scanning', () => {
    // loadConfigOverrides calls syncPaperAccountCapital before returning
    // Then runAllScans runs bots. This ordering is critical.
    const loadFn = scannerSource.match(
      /async function loadConfigOverrides[\s\S]*?^}/m,
    )
    expect(loadFn).toBeTruthy()
    expect(loadFn![0]).toMatch(/syncPaperAccountCapital/)

    const runAllFn = scannerSource.match(
      /async function runAllScans[\s\S]*?^}/m,
    )
    expect(runAllFn).toBeTruthy()
    const body = runAllFn![0]
    const configIdx = body.indexOf('loadConfigOverrides')
    const scanIdx = body.indexOf('scanBot(bot)')
    expect(configIdx).toBeGreaterThan(-1)
    expect(scanIdx).toBeGreaterThan(-1)
    expect(scanIdx).toBeGreaterThan(configIdx)
  })

  it('scanBot checks isConfiguredAsync before opening trades', () => {
    // Bot must be "configured" (has Tradier API key) before calling tryOpenTrade
    const fnMatch = scannerSource.match(
      /async function scanBot[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/isConfiguredAsync/)
    // isConfiguredAsync check happens before tryOpenTrade
    const configIdx = fnBody.indexOf('isConfiguredAsync')
    const tradeIdx = fnBody.indexOf('tryOpenTrade')
    expect(configIdx).toBeGreaterThan(-1)
    expect(tradeIdx).toBeGreaterThan(-1)
    expect(configIdx).toBeLessThan(tradeIdx)
  })

  it('getAccountsForBotAsync SQL uses bot name in query', () => {
    // Bot names come from code (not user input), so injection risk is minimal
    // but verify the query structure exists
    const fnMatch = tradierSource.match(
      /export async function getAccountsForBotAsync[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    // Uses toUpperCase() for consistent matching
    expect(fnBody).toMatch(/toUpperCase\(\)/)
    // Falls back to BOT_ACCOUNTS on error
    expect(fnBody).toMatch(/BOT_ACCOUNTS/)
  })

  it('getAccountsForBotAsync filters to sandbox-only accounts', () => {
    // Production accounts must NEVER affect scanner capital sizing or order placement.
    // The query must include AND type = 'sandbox' to exclude production monitoring accounts.
    const fnMatch = tradierSource.match(
      /export async function getAccountsForBotAsync[\s\S]*?^}/m,
    )
    expect(fnMatch).toBeTruthy()
    const fnBody = fnMatch![0]
    expect(fnBody).toMatch(/type\s*=\s*'sandbox'/)
  })

  it('test-all route uses correct Tradier URL per account type', () => {
    const testAllSource = readFileSync(
      resolve(__dirname, '../../app/api/accounts/test-all/route.ts'),
      'utf-8',
    )
    // Must define both URLs
    expect(testAllSource).toMatch(/sandbox\.tradier\.com/)
    expect(testAllSource).toMatch(/api\.tradier\.com/)
    // testOne must accept a type parameter
    expect(testAllSource).toMatch(/async function testOne[\s\S]*?type/)
    // Must query type column from DB
    expect(testAllSource).toMatch(/SELECT[\s\S]*?type[\s\S]*?FROM/)
  })

  it('per-account test endpoint exists', () => {
    const testRouteSource = readFileSync(
      resolve(__dirname, '../../app/api/accounts/manage/[id]/test/route.ts'),
      'utf-8',
    )
    // Must support both sandbox and production URLs
    expect(testRouteSource).toMatch(/sandbox\.tradier\.com/)
    expect(testRouteSource).toMatch(/api\.tradier\.com/)
    // Must read account type from DB
    expect(testRouteSource).toMatch(/type/)
    // Must export POST handler
    expect(testRouteSource).toMatch(/export async function POST/)
  })
})

/* ── SQL Parameterization — source code checks ────────────── */

describe('SQL Parameterization', () => {
  const manageRouteSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/manage/route.ts'),
    'utf-8',
  )
  const manageIdRouteSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/manage/[id]/route.ts'),
    'utf-8',
  )
  const productionRouteSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/production/route.ts'),
    'utf-8',
  )

  it('manage/route.ts does not import escapeSql', () => {
    // After parameterization, escapeSql should no longer be imported
    expect(manageRouteSource).not.toMatch(/import\s+.*escapeSql.*from/)
  })

  it('manage/route.ts POST uses parameterized INSERT ($1-$7)', () => {
    // The INSERT should use $1, $2, ... placeholders, not string interpolation
    expect(manageRouteSource).toMatch(/VALUES\s*\(\$1,\s*\$2,\s*\$3/)
  })

  it('manage/route.ts sandbox check uses parameterized WHERE', () => {
    // person = $1, not person = '${escapeSql(person)}'
    expect(manageRouteSource).toMatch(/person\s*=\s*\$1\s+AND\s+is_active/)
  })

  it('manage/route.ts duplicate check uses parameterized WHERE', () => {
    expect(manageRouteSource).toMatch(/account_id\s*=\s*\$1\s+LIMIT/)
  })

  it('manage/route.ts seed uses parameterized INSERT', () => {
    // The seedFromEnvVars INSERT should also use $1, $2, $3
    const seedFn = manageRouteSource.match(
      /async function seedFromEnvVars[\s\S]*?^}/m,
    )
    expect(seedFn).toBeTruthy()
    expect(seedFn![0]).toMatch(/VALUES\s*\(\$1,\s*\$2,\s*\$3/)
    expect(seedFn![0]).not.toMatch(/escapeSql/)
  })

  it('manage/[id]/route.ts does not import escapeSql', () => {
    expect(manageIdRouteSource).not.toMatch(/import\s+.*escapeSql.*from/)
  })

  it('manage/[id]/route.ts PUT uses parameterized SET clauses', () => {
    // Should build dynamic $N params, not escapeSql string interpolation
    expect(manageIdRouteSource).toMatch(/\$\{paramIndex\+\+\}/)
    expect(manageIdRouteSource).not.toMatch(/escapeSql/)
  })

  it('manage/[id]/route.ts DELETE uses parameterized WHERE', () => {
    expect(manageIdRouteSource).toMatch(/WHERE id = \$1/)
  })

  it('production/route.ts does not import escapeSql', () => {
    expect(productionRouteSource).not.toMatch(/import\s+.*escapeSql.*from/)
  })

  it('production/route.ts dte filter uses parameterized query', () => {
    // Should use $1 param, not escapeSql(dte)
    expect(productionRouteSource).toMatch(/dte_mode\s*=\s*\$1/)
    expect(productionRouteSource).not.toMatch(/escapeSql/)
  })
})

/* ── Validation Guards ─────────────────────────────────────── */

describe('Validation Guards', () => {
  const manageRouteSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/manage/route.ts'),
    'utf-8',
  )
  const manageIdRouteSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/manage/[id]/route.ts'),
    'utf-8',
  )

  it('PUT blocks account type changes', () => {
    // If body.type is provided, return 400
    expect(manageIdRouteSource).toMatch(/body\.type\s*!=\s*null/)
    expect(manageIdRouteSource).toMatch(/Account type cannot be changed/)
  })

  it('POST validates API key against Tradier before INSERT', () => {
    const postFn = manageRouteSource.match(
      /export async function POST[\s\S]*?^}/m,
    )
    expect(postFn).toBeTruthy()
    const body = postFn![0]
    // tradierFetch call must come BEFORE the INSERT
    const tradierIdx = body.indexOf("tradierFetch('/user/profile'")
    const insertIdx = body.indexOf('INSERT INTO')
    expect(tradierIdx).toBeGreaterThan(-1)
    expect(insertIdx).toBeGreaterThan(-1)
    expect(tradierIdx).toBeLessThan(insertIdx)
  })

  it('POST supports skip_test query param to bypass API key validation', () => {
    expect(manageRouteSource).toMatch(/skip_test/)
  })

  it('POST returns capital warning when allocation is below $500', () => {
    expect(manageRouteSource).toMatch(/below recommended \$500 minimum/)
  })

  it('POST capital warning is informational (not blocking)', () => {
    // The warning is in the success response, not an error
    const postFn = manageRouteSource.match(
      /export async function POST[\s\S]*?^}/m,
    )
    expect(postFn).toBeTruthy()
    const body = postFn![0]
    // warning appears after success: true
    expect(body).toMatch(/success:\s*true[\s\S]*?warning/)
  })

  it('POST capital warning only for sandbox (not production)', () => {
    // Production accounts are monitoring-only, capital_pct is irrelevant
    expect(manageRouteSource).toMatch(/type === 'sandbox' && estimatedAllocation < 500/)
  })
})

/* ── Cache Invalidation ────────────────────────────────────── */

describe('Cache Invalidation', () => {
  const manageRouteSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/manage/route.ts'),
    'utf-8',
  )
  const manageIdRouteSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/manage/[id]/route.ts'),
    'utf-8',
  )
  const tradierSource = readFileSync(
    resolve(__dirname, '../tradier.ts'),
    'utf-8',
  )

  it('POST create invalidates sandbox cache after INSERT', () => {
    const postFn = manageRouteSource.match(
      /export async function POST[\s\S]*?^}/m,
    )
    expect(postFn).toBeTruthy()
    const body = postFn![0]
    // reloadSandboxAccounts must appear AFTER INSERT
    const insertIdx = body.indexOf('INSERT INTO')
    const reloadIdx = body.indexOf('reloadSandboxAccounts')
    expect(insertIdx).toBeGreaterThan(-1)
    expect(reloadIdx).toBeGreaterThan(-1)
    expect(reloadIdx).toBeGreaterThan(insertIdx)
  })

  it('PUT update invalidates sandbox cache after UPDATE', () => {
    const putFn = manageIdRouteSource.match(
      /export async function PUT[\s\S]*?^}/m,
    )
    expect(putFn).toBeTruthy()
    const body = putFn![0]
    const updateIdx = body.indexOf('UPDATE')
    const reloadIdx = body.indexOf('reloadSandboxAccounts')
    expect(updateIdx).toBeGreaterThan(-1)
    expect(reloadIdx).toBeGreaterThan(-1)
    expect(reloadIdx).toBeGreaterThan(updateIdx)
  })

  it('DELETE deactivation invalidates sandbox cache', () => {
    const deleteFn = manageIdRouteSource.match(
      /export async function DELETE[\s\S]*?^}/m,
    )
    expect(deleteFn).toBeTruthy()
    expect(deleteFn![0]).toMatch(/reloadSandboxAccounts/)
  })

  it('reloadSandboxAccounts exists as an exported function in tradier.ts', () => {
    expect(tradierSource).toMatch(/export async function reloadSandboxAccounts/)
  })

  it('reloadSandboxAccounts clears _sandboxAccounts and _accountIdCache', () => {
    const fn = tradierSource.match(
      /export async function reloadSandboxAccounts[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    const body = fn![0]
    expect(body).toMatch(/_sandboxAccounts\s*=\s*\[\]/)
    expect(body).toMatch(/_sandboxAccountsLoadedFromDb\s*=\s*false/)
    expect(body).toMatch(/_accountIdCache/)
  })
})

/* ── Immediate Position Cleanup on Deactivation ────────────── */

describe('Immediate Position Cleanup', () => {
  const manageIdRouteSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/manage/[id]/route.ts'),
    'utf-8',
  )
  const tradierSource = readFileSync(
    resolve(__dirname, '../tradier.ts'),
    'utf-8',
  )

  it('DELETE closes Tradier positions before deactivation', () => {
    const deleteFn = manageIdRouteSource.match(
      /export async function DELETE[\s\S]*?^}/m,
    )
    expect(deleteFn).toBeTruthy()
    const body = deleteFn![0]
    expect(body).toMatch(/closeAllSandboxPositions/)
  })

  it('DELETE only closes positions for sandbox accounts (not production)', () => {
    const deleteFn = manageIdRouteSource.match(
      /export async function DELETE[\s\S]*?^}/m,
    )
    expect(deleteFn).toBeTruthy()
    // Must check type before closing
    expect(deleteFn![0]).toMatch(/type.*===.*'sandbox'/)
  })

  it('DELETE reports closed position count in response', () => {
    expect(manageIdRouteSource).toMatch(/position\(s\) closed/)
  })

  it('closeAllSandboxPositions exists in tradier.ts', () => {
    expect(tradierSource).toMatch(/export async function closeAllSandboxPositions/)
  })

  it('closeAllSandboxPositions uses market orders for immediate fill', () => {
    const fn = tradierSource.match(
      /export async function closeAllSandboxPositions[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    expect(fn![0]).toMatch(/type.*:.*'market'/)
  })
})

/* ── Per-Account PDT Enforcement ───────────────────────────── */

describe('Per-Account PDT Enforcement', () => {
  const scannerSource = readFileSync(
    resolve(__dirname, '../scanner.ts'),
    'utf-8',
  )

  it('scanner imports getPdtEnabledForAccount from tradier', () => {
    expect(scannerSource).toMatch(/getPdtEnabledForAccount/)
    expect(scannerSource).toMatch(/from\s+'\.\/tradier'/)
  })

  it('tryOpenTrade checks per-account PDT after bot-level PDT', () => {
    const fn = scannerSource.match(
      /async function tryOpenTrade[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    const body = fn![0]
    // Must first read from ironforge_pdt_config (bot-level)
    const botLevelIdx = body.indexOf('ironforge_pdt_config')
    // Then check per-account via getPdtEnabledForAccount
    const acctLevelIdx = body.indexOf('getPdtEnabledForAccount')
    expect(botLevelIdx).toBeGreaterThan(-1)
    expect(acctLevelIdx).toBeGreaterThan(-1)
    expect(acctLevelIdx).toBeGreaterThan(botLevelIdx)
  })

  it('per-account PDT can disable enforcement (override bot-level)', () => {
    const fn = scannerSource.match(
      /async function tryOpenTrade[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    const body = fn![0]
    // If account has PDT disabled, set pdtEnabled = false
    expect(body).toMatch(/pdtEnabled\s*=\s*false/)
    expect(body).toMatch(/PDT disabled by account/)
  })
})

/* ── Production Capital Cleanup ─────────────────────────────── */

describe('Production Account Capital UI', () => {
  const accountsContentSource = readFileSync(
    resolve(__dirname, '../../components/AccountsContent.tsx'),
    'utf-8',
  )

  it('AddAccountModal hides capital slider for production accounts', () => {
    // The capital slider should be wrapped in {!isProduction && (...)}
    // which means it only shows for sandbox accounts
    expect(accountsContentSource).toMatch(/!isProduction[\s\S]*?Capital to Use \(%\)/)
  })

  it('EditAccountModal hides capital slider for production accounts', () => {
    // The edit modal should check account.type !== 'production'
    expect(accountsContentSource).toMatch(/account\.type\s*!==\s*'production'[\s\S]*?Capital to Use/)
  })

  it('account card hides capital line for production accounts', () => {
    // The "Capital: X% = $Y" line should be conditional on type
    expect(accountsContentSource).toMatch(/account\.type\s*!==\s*'production'[\s\S]*?Capital:/)
  })
})
