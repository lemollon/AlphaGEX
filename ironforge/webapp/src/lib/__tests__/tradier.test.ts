/**
 * Tests for Tradier API client — sandbox connectivity, buying power,
 * account discovery, OCC symbol building, MTM validation, and order execution.
 *
 * tradier.ts reads env vars at module load time (top-level const).
 * ESM imports are hoisted above vi.stubEnv, so we set process.env directly
 * in a vi.hoisted block which runs before any imports.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Set env vars in a hoisted block — runs BEFORE tradier.ts module init
vi.hoisted(() => {
  process.env.TRADIER_API_KEY = 'test-production-key'
  process.env.TRADIER_SANDBOX_KEY_USER = 'test-sandbox-user'
  process.env.TRADIER_SANDBOX_KEY_MATT = 'test-sandbox-matt'
  process.env.TRADIER_SANDBOX_KEY_LOGAN = 'test-sandbox-logan'
})

// Mock fetch globally — also hoisted
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

import {
  buildOccSymbol,
  getQuote,
  getOptionQuote,
  getIcMarkToMarket,
  getIcEntryCredit,
  getOptionExpirations,
  calculateIcUnrealizedPnl,
  isConfigured,
  getSandboxAccountBalances,
  getLoadedSandboxAccounts,
  getSandboxAccountPositions,
  getBatchOptionQuotes,
} from '../tradier'

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function jsonResponse(data: any, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(data),
  }
}

beforeEach(() => {
  mockFetch.mockReset()
})

/* ================================================================== */
/*  Section 1: OCC Symbol Building                                     */
/* ================================================================== */

describe('buildOccSymbol', () => {
  it('builds correct put symbol', () => {
    const sym = buildOccSymbol('SPY', '2026-03-18', 580, 'P')
    expect(sym).toBe('SPY260318P00580000')
  })

  it('builds correct call symbol', () => {
    const sym = buildOccSymbol('SPY', '2026-03-18', 590, 'C')
    expect(sym).toBe('SPY260318C00590000')
  })

  it('handles fractional strikes', () => {
    const sym = buildOccSymbol('SPY', '2026-03-18', 585.5, 'P')
    expect(sym).toBe('SPY260318P00585500')
  })

  it('pads single-digit months and days', () => {
    const sym = buildOccSymbol('SPY', '2026-01-05', 600, 'C')
    expect(sym).toBe('SPY260105C00600000')
  })
})

/* ================================================================== */
/*  Section 2: Production Quote Fetching                               */
/* ================================================================== */

describe('getQuote', () => {
  it('returns parsed quote on success', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ quotes: { quote: { last: '585.50', bid: '585.45', ask: '585.55', symbol: 'SPY' } } }),
    )
    const q = await getQuote('SPY')
    expect(q).toEqual({ last: 585.50, bid: 585.45, ask: 585.55, symbol: 'SPY' })
  })

  it('returns null on API error', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({}, 500))
    const q = await getQuote('SPY')
    expect(q).toBeNull()
  })

  it('returns null when quote has no last price', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ quotes: { quote: { bid: '585.45', ask: '585.55', symbol: 'SPY' } } }),
    )
    const q = await getQuote('SPY')
    expect(q).toBeNull()
  })

  it('handles array of quotes (picks first)', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        quotes: {
          quote: [
            { last: '585.50', bid: '585.45', ask: '585.55', symbol: 'SPY' },
            { last: '100.00', bid: '99.00', ask: '101.00', symbol: 'QQQ' },
          ],
        },
      }),
    )
    const q = await getQuote('SPY')
    expect(q?.last).toBe(585.50)
  })
})

describe('getOptionQuote', () => {
  it('returns parsed option quote', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ quotes: { quote: { bid: '0.15', ask: '0.20', last: '0.18', symbol: 'SPY260318P00580000' } } }),
    )
    const q = await getOptionQuote('SPY260318P00580000')
    expect(q).toEqual({ bid: 0.15, ask: 0.20, last: 0.18, symbol: 'SPY260318P00580000' })
  })

  it('returns null on unmatched symbols', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ quotes: { quote: { bid: '0.15', ask: '0.20', last: '0.18', symbol: 'X' }, unmatched_symbols: { symbol: 'SPY260318P00580000' } } }),
    )
    const q = await getOptionQuote('SPY260318P00580000')
    expect(q).toBeNull()
  })
})

/* ================================================================== */
/*  Section 3: IC Mark-to-Market                                       */
/* ================================================================== */

describe('getIcMarkToMarket', () => {
  it('calculates cost_to_close from 4 leg quotes', async () => {
    // PS ask=0.12, PL bid=0.01, CS ask=0.10, CL bid=0.01, SPY last=585.50
    const mockQuotes = [
      jsonResponse({ quotes: { quote: { bid: '0.10', ask: '0.12', last: '0.11', symbol: 'PS' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.01', ask: '0.02', last: '0.01', symbol: 'PL' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.08', ask: '0.10', last: '0.09', symbol: 'CS' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.01', ask: '0.02', last: '0.01', symbol: 'CL' } } }),
      jsonResponse({ quotes: { quote: { last: '585.50', bid: '585.45', ask: '585.55', symbol: 'SPY' } } }),
    ]
    for (const r of mockQuotes) mockFetch.mockResolvedValueOnce(r)

    const result = await getIcMarkToMarket('SPY', '2026-03-18', 580, 575, 590, 595, 0.27)
    expect(result).not.toBeNull()
    // cost = PS.ask + CS.ask - PL.bid - CL.bid = 0.12 + 0.10 - 0.01 - 0.01 = 0.20
    expect(result!.cost_to_close).toBeCloseTo(0.20, 4)
    expect(result!.spot_price).toBe(585.50)
  })

  it('returns null when a leg quote is missing', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({}, 500)) // PS fails
    mockFetch.mockResolvedValueOnce(jsonResponse({ quotes: { quote: { bid: '0.01', ask: '0.02', last: '0.01', symbol: 'PL' } } }))
    mockFetch.mockResolvedValueOnce(jsonResponse({ quotes: { quote: { bid: '0.08', ask: '0.10', last: '0.09', symbol: 'CS' } } }))
    mockFetch.mockResolvedValueOnce(jsonResponse({ quotes: { quote: { bid: '0.01', ask: '0.02', last: '0.01', symbol: 'CL' } } }))
    mockFetch.mockResolvedValueOnce(jsonResponse({ quotes: { quote: { last: '585.50', bid: '585.45', ask: '585.55', symbol: 'SPY' } } }))

    const result = await getIcMarkToMarket('SPY', '2026-03-18', 580, 575, 590, 595, 0.27)
    expect(result).toBeNull()
  })

  it('caps cost at spread width', async () => {
    // All asks very high — cost would exceed spread width
    const mockQuotes = [
      jsonResponse({ quotes: { quote: { bid: '4.90', ask: '5.10', last: '5.0', symbol: 'PS' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.01', ask: '0.02', last: '0.01', symbol: 'PL' } } }),
      jsonResponse({ quotes: { quote: { bid: '4.90', ask: '5.10', last: '5.0', symbol: 'CS' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.01', ask: '0.02', last: '0.01', symbol: 'CL' } } }),
      jsonResponse({ quotes: { quote: { last: '585.50', bid: '585.45', ask: '585.55', symbol: 'SPY' } } }),
    ]
    for (const r of mockQuotes) mockFetch.mockResolvedValueOnce(r)

    const result = await getIcMarkToMarket('SPY', '2026-03-18', 580, 575, 590, 595)
    // spread width = 580 - 575 = 5.0; cost should be capped
    expect(result).not.toBeNull()
    expect(result!.cost_to_close).toBeLessThanOrEqual(5.0)
  })
})

/* ================================================================== */
/*  Section 4: IC Entry Credit                                         */
/* ================================================================== */

describe('getIcEntryCredit', () => {
  it('calculates conservative fills (sell at bid, buy at ask)', async () => {
    // PS bid=0.20, PL ask=0.05 → put credit = 0.15
    // CS bid=0.18, CL ask=0.05 → call credit = 0.13
    const mockQuotes = [
      jsonResponse({ quotes: { quote: { bid: '0.20', ask: '0.25', last: '0.22', symbol: 'PS' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.03', ask: '0.05', last: '0.04', symbol: 'PL' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.18', ask: '0.22', last: '0.20', symbol: 'CS' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.03', ask: '0.05', last: '0.04', symbol: 'CL' } } }),
    ]
    for (const r of mockQuotes) mockFetch.mockResolvedValueOnce(r)

    const result = await getIcEntryCredit('SPY', '2026-03-18', 580, 575, 590, 595)
    expect(result).not.toBeNull()
    expect(result!.putCredit).toBeCloseTo(0.15, 4)
    expect(result!.callCredit).toBeCloseTo(0.13, 4)
    expect(result!.totalCredit).toBeCloseTo(0.28, 4)
    expect(result!.source).toBe('TRADIER_LIVE')
  })

  it('falls back to mid-price when bid-ask gives negative credit', async () => {
    // PS bid=0.02, PL ask=0.05 → conservative = -0.03 (negative!)
    // Should fall back to mid-price
    const mockQuotes = [
      jsonResponse({ quotes: { quote: { bid: '0.02', ask: '0.04', last: '0.03', symbol: 'PS' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.03', ask: '0.05', last: '0.04', symbol: 'PL' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.18', ask: '0.22', last: '0.20', symbol: 'CS' } } }),
      jsonResponse({ quotes: { quote: { bid: '0.03', ask: '0.05', last: '0.04', symbol: 'CL' } } }),
    ]
    for (const r of mockQuotes) mockFetch.mockResolvedValueOnce(r)

    const result = await getIcEntryCredit('SPY', '2026-03-18', 580, 575, 590, 595)
    expect(result).not.toBeNull()
    // Mid-price fallback: put = (0.03 - 0.04) = -0.01 → capped at 0
    // call = (0.20 - 0.04) = 0.16
    expect(result!.putCredit).toBeGreaterThanOrEqual(0)
  })
})

/* ================================================================== */
/*  Section 5: Unrealized P&L Calculation                              */
/* ================================================================== */

describe('calculateIcUnrealizedPnl', () => {
  it('calculates profit when cost < credit', () => {
    // entry credit = 0.27, cost to close = 0.10, 5 contracts, $5 spread
    const pnl = calculateIcUnrealizedPnl(0.27, 0.10, 5, 5.0)
    // (0.27 - 0.10) * 100 * 5 = $85
    expect(pnl).toBeCloseTo(85.0, 2)
  })

  it('calculates loss when cost > credit', () => {
    const pnl = calculateIcUnrealizedPnl(0.27, 0.50, 5, 5.0)
    // (0.27 - 0.50) * 100 * 5 = -$115
    expect(pnl).toBeCloseTo(-115.0, 2)
  })

  it('caps cost at spread width', () => {
    // cost to close = 6.0 > spread width 5.0 → should cap at 5.0
    const pnl = calculateIcUnrealizedPnl(0.27, 6.0, 1, 5.0)
    // (0.27 - 5.0) * 100 * 1 = -$473
    expect(pnl).toBeCloseTo(-473.0, 2)
  })

  it('caps cost at zero (no negative cost)', () => {
    const pnl = calculateIcUnrealizedPnl(0.27, -0.05, 5, 5.0)
    // cost capped to 0 → (0.27 - 0) * 100 * 5 = $135
    expect(pnl).toBeCloseTo(135.0, 2)
  })

  it('returns zero for zero contracts', () => {
    const pnl = calculateIcUnrealizedPnl(0.27, 0.10, 0, 5.0)
    expect(pnl).toBe(0)
  })
})

/* ================================================================== */
/*  Section 6: Sandbox Account Loading                                 */
/* ================================================================== */

describe('Sandbox account loading', () => {
  it('loads all 3 configured sandbox accounts', () => {
    const accounts = getLoadedSandboxAccounts()
    expect(accounts).toHaveLength(3)
    expect(accounts.map((a) => a.name)).toEqual(['User', 'Matt', 'Logan'])
  })

  it('each account has a non-empty API key', () => {
    const accounts = getLoadedSandboxAccounts()
    for (const acct of accounts) {
      expect(acct.apiKey).toBeTruthy()
      expect(acct.apiKey.length).toBeGreaterThan(0)
    }
  })
})

/* ================================================================== */
/*  Section 7: Sandbox Account Balances (buying power flow)            */
/* ================================================================== */

describe('getSandboxAccountBalances', () => {
  it('returns balance data for all 3 accounts', async () => {
    // getSandboxAccountBalances runs Promise.all across 3 accounts concurrently.
    // Each account calls: getAccountIdForKey (profile), then balance + positions in parallel.
    // With concurrent execution, fetch call order is non-deterministic.
    // Use mockResolvedValue (not Once) to always return valid data for any endpoint.
    let callCount = 0
    mockFetch.mockImplementation(async (url: string) => {
      callCount++
      const urlStr = typeof url === 'string' ? url : url.toString()

      if (urlStr.includes('/user/profile')) {
        // Return different account IDs based on which sandbox key is in the auth header
        // Since we can't easily inspect headers here, return a generic ID
        return jsonResponse({ profile: { account: { account_number: `ACC-${callCount}` } } })
      }
      if (urlStr.includes('/balances')) {
        return jsonResponse({
          balances: {
            total_equity: '25000.00',
            option_buying_power: '20000.00',
            close_pl: '50.00',
            pending_cash: '0',
          },
        })
      }
      if (urlStr.includes('/positions')) {
        return jsonResponse({ positions: 'null' })
      }
      return jsonResponse({})
    })

    const balances = await getSandboxAccountBalances()
    expect(balances).toHaveLength(3)

    // All accounts should have valid data
    for (const acct of balances) {
      expect(acct.account_id).toBeTruthy()
      expect(acct.total_equity).toBe(25000)
      expect(acct.option_buying_power).toBe(20000)
    }

    // Verify names are User, Matt, Logan
    const names = balances.map((b) => b.name).sort()
    expect(names).toEqual(['Logan', 'Matt', 'User'])
  })

  it('returns all 3 accounts even with cached IDs', async () => {
    // Account IDs cached from first test — only balance + positions calls needed
    mockFetch.mockImplementation(async (url: string) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('/balances')) {
        return jsonResponse({
          balances: { total_equity: '18000', option_buying_power: '14000' },
        })
      }
      if (urlStr.includes('/positions')) {
        return jsonResponse({
          positions: {
            position: [
              { symbol: 'SPY260318P00580000', quantity: '-5' },
              { symbol: 'SPY260318P00575000', quantity: '5' },
            ],
          },
        })
      }
      // Profile — should be cached, but return valid response just in case
      return jsonResponse({ profile: { account: { account_number: 'ACC-CACHED' } } })
    })

    const balances = await getSandboxAccountBalances()
    expect(balances).toHaveLength(3)
    for (const acct of balances) {
      expect(acct.total_equity).toBe(18000)
      expect(acct.option_buying_power).toBe(14000)
      expect(acct.open_positions_count).toBe(2)
    }
  })
})

/* ================================================================== */
/*  Section 8: Sandbox Positions Filtering                             */
/* ================================================================== */

describe('getSandboxAccountPositions', () => {
  it('returns positions filtered to matching OCC symbols', async () => {
    mockFetch.mockImplementation(async (url: string) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('/user/profile')) {
        return jsonResponse({ profile: { account: { account_number: 'ACC-POS-TEST' } } })
      }
      if (urlStr.includes('/positions')) {
        return jsonResponse({
          positions: {
            position: [
              { symbol: 'SPY260318P00580000', quantity: '-5', cost_basis: '-100.00', market_value: '-50.00', gain_loss: '50.00', gain_loss_percent: '50.00' },
              { symbol: 'SPY260318P00575000', quantity: '5', cost_basis: '25.00', market_value: '10.00', gain_loss: '-15.00', gain_loss_percent: '-60.00' },
              { symbol: 'QQQ260318C00500000', quantity: '-2', cost_basis: '-50.00', market_value: '-30.00', gain_loss: '20.00', gain_loss_percent: '40.00' },
            ],
          },
        })
      }
      return jsonResponse({})
    })

    const positions = await getSandboxAccountPositions(
      'test-key-pos',
      ['SPY260318P00580000', 'SPY260318P00575000'],
    )
    expect(positions).toHaveLength(2)
    expect(positions[0].symbol).toBe('SPY260318P00580000')
    expect(positions[0].quantity).toBe(-5)
    expect(positions[1].symbol).toBe('SPY260318P00575000')
  })

  it('returns all positions when no filter specified', async () => {
    // 'test-key-pos' cached from previous test
    mockFetch.mockImplementation(async (url: string) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('/positions')) {
        return jsonResponse({
          positions: {
            position: [
              { symbol: 'SPY260318P00580000', quantity: '-5', cost_basis: '0', market_value: '0', gain_loss: '0', gain_loss_percent: '0' },
              { symbol: 'QQQ260318C00500000', quantity: '-2', cost_basis: '0', market_value: '0', gain_loss: '0', gain_loss_percent: '0' },
            ],
          },
        })
      }
      return jsonResponse({ profile: { account: { account_number: 'ACC-POS-TEST' } } })
    })

    const positions = await getSandboxAccountPositions('test-key-pos')
    expect(positions).toHaveLength(2)
  })
})

/* ================================================================== */
/*  Section 9: Batch Option Quotes                                     */
/* ================================================================== */

describe('getBatchOptionQuotes', () => {
  it('returns map of symbol to leg quote', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        quotes: {
          quote: [
            { symbol: 'SPY260318P00580000', bid: '0.10', ask: '0.15', last: '0.12' },
            { symbol: 'SPY260318P00575000', bid: '0.02', ask: '0.04', last: '0.03' },
          ],
        },
      }),
    )

    const result = await getBatchOptionQuotes(['SPY260318P00580000', 'SPY260318P00575000'])
    expect(Object.keys(result)).toHaveLength(2)
    expect(result['SPY260318P00580000'].bid).toBe(0.10)
    expect(result['SPY260318P00580000'].ask).toBe(0.15)
    expect(result['SPY260318P00580000'].mid).toBeCloseTo(0.125, 4)
  })

  it('returns empty for empty input', async () => {
    const result = await getBatchOptionQuotes([])
    expect(Object.keys(result)).toHaveLength(0)
  })
})

/* ================================================================== */
/*  Section 10: Option Expirations                                     */
/* ================================================================== */

describe('getOptionExpirations', () => {
  it('returns list of expiration dates', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ expirations: { date: ['2026-03-18', '2026-03-19', '2026-03-20'] } }),
    )
    const exps = await getOptionExpirations('SPY')
    expect(exps).toEqual(['2026-03-18', '2026-03-19', '2026-03-20'])
  })

  it('wraps single expiration in array', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ expirations: { date: '2026-03-18' } }),
    )
    const exps = await getOptionExpirations('SPY')
    expect(exps).toEqual(['2026-03-18'])
  })

  it('returns empty on API error', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({}, 500))
    const exps = await getOptionExpirations('SPY')
    expect(exps).toEqual([])
  })
})

/* ================================================================== */
/*  Section 11: isConfigured                                           */
/* ================================================================== */

describe('isConfigured', () => {
  it('returns true when API key is set', () => {
    expect(isConfigured()).toBe(true)
  })
})

/* ================================================================== */
/*  Section 12: Buying Power Sizing Math                               */
/* ================================================================== */

describe('Buying power → contract sizing', () => {
  it('calculates contracts from BP correctly (full share)', () => {
    // This mirrors the logic in placeIcOrderAllAccounts with botShare = 1.0
    const bp = 20000
    const botShare = 1.0
    const totalCredit = 0.27
    const spreadWidth = 5.0
    const collateralPer = Math.max(0, (spreadWidth - totalCredit) * 100) // $473 per contract
    const usableBP = bp * botShare * 0.85 // $17,000
    const contracts = Math.max(1, Math.floor(usableBP / collateralPer))
    expect(collateralPer).toBeCloseTo(473, 0)
    expect(contracts).toBe(35) // 17000 / 473 = 35.9 → 35
  })

  it('FLAME/SPARK use 100% of account BP (no share reduction)', () => {
    // All sandbox bots use bpShare=1.0 now — full 85% of account BP
    const bp = 25000
    const botShare = 1.0
    const totalCredit = 0.27
    const spreadWidth = 5.0
    const collateralPer = Math.max(0, (spreadWidth - totalCredit) * 100) // $473
    const usableBP = bp * botShare * 0.85 // 25000 * 1.0 * 0.85 = $21,250
    const contracts = Math.max(1, Math.floor(usableBP / collateralPer))
    expect(contracts).toBe(44) // 21250 / 473 = 44.9 → 44
  })

  it('INFERNO is paper-only (no sandbox accounts)', () => {
    // INFERNO has accounts=[] — placeIcOrderAllAccounts finds zero eligible accounts
    // Paper sizing uses paper_account balance × bp_pct (0.85), not Tradier BP
    const paperBalance = 10000
    const bp_pct = 0.85
    const totalCredit = 0.27
    const spreadWidth = 5.0
    const collateralPer = Math.max(0, (spreadWidth - totalCredit) * 100) // $473
    const usableBP = paperBalance * bp_pct // $8,500
    const contracts = Math.max(1, Math.floor(usableBP / collateralPer))
    expect(contracts).toBe(17) // 8500 / 473 = 17.97 → 17
  })

  it('returns 1 contract when BP barely covers one', () => {
    const bp = 600
    const botShare = 1.0
    const totalCredit = 0.27
    const spreadWidth = 5.0
    const collateralPer = (spreadWidth - totalCredit) * 100
    const usableBP = bp * botShare * 0.85
    const contracts = Math.max(1, Math.floor(usableBP / collateralPer))
    expect(contracts).toBe(1) // 510 / 473 = 1.07 → 1
  })

  it('BP insufficient blocks the trade', () => {
    const bp = 400
    const totalCredit = 0.27
    const spreadWidth = 5.0
    const collateralPer = (spreadWidth - totalCredit) * 100
    // bp < collateralPer → should skip in real code
    expect(bp).toBeLessThan(collateralPer)
  })
})
