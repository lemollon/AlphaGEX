/**
 * Pins the EBB contract-count ladder (2026-09-04, ADR 0012 + ADR 0013).
 *
 * Leron: "the ladder should not be width, it should be count of contracts",
 * "need to round because contract price is not going to be a round number",
 * "the app is live, the time for 5 max is over", "we are expecting to get
 * 100k accounts maybe more".
 *
 * These tests fail if anyone moves a rung, the static cap, the liquidity
 * share, the rounding direction, lets the high-water ratchet move DOWN, sizes
 * either money path from current_balance, or writes a balance without
 * ratcheting high_water_balance.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import {
  EBB_LADDER_CAP,
  EBB_LIQUIDITY_SHARE,
  FLAME_RUNG_USD,
  SPARK_RUNG_USD,
  ebbLadderCapital,
  ebbLadderContracts,
  ebbRungUsd,
  formatEbbSizingLine,
  isEbbLadderBot,
  liquidityCappedLots,
} from '../ebb-sizing'

describe('EBB count ladder — rungs (2026-08-27 survivor rule, unchanged by ADR 0013)', () => {
  it('FLAME is 1 lot per $1,500', () => {
    expect(FLAME_RUNG_USD).toBe(1500)
    expect(ebbRungUsd('flame')).toBe(1500)
  })
  it('SPARK is 1 lot per $5,000', () => {
    expect(SPARK_RUNG_USD).toBe(5000)
    expect(ebbRungUsd('spark')).toBe(5000)
  })
  it('static cap is 100 — a safety ceiling, not the working limit (9/4 backtest: no cap ever breached 35% DD)', () => {
    expect(EBB_LADDER_CAP).toBe(100)
    expect(ebbLadderContracts('flame', 1_000_000)).toBe(100)
    expect(ebbLadderContracts('spark', 1_000_000)).toBe(100)
  })
  it('$100k accounts: SPARK 20 lots, FLAME 66 lots (ADR 0013)', () => {
    expect(ebbLadderContracts('spark', 100_000)).toBe(20)
    expect(ebbLadderContracts('flame', 100_000)).toBe(66)
  })
  it('only SPARK and FLAME are on the ladder', () => {
    expect(isEbbLadderBot('spark')).toBe(true)
    expect(isEbbLadderBot('flame')).toBe(true)
    expect(isEbbLadderBot('inferno')).toBe(false)
    expect(isEbbLadderBot('forge')).toBe(false)
    expect(isEbbLadderBot(undefined)).toBe(false)
  })
})

describe('EBB count ladder — rounding is ALWAYS down', () => {
  it('SPARK: $8,000 is 1 lot, not 2', () => {
    expect(ebbLadderContracts('spark', 8000)).toBe(1)
  })
  it('SPARK: $9,999 is 1, $10,000 is 2, $25,000 is 5', () => {
    expect(ebbLadderContracts('spark', 9999)).toBe(1)
    expect(ebbLadderContracts('spark', 10000)).toBe(2)
    expect(ebbLadderContracts('spark', 25000)).toBe(5)
  })
  it('FLAME: $9,900 is 6 lots (no longer capped to 5); $2,999 is 1; $3,000 is 2', () => {
    expect(ebbLadderContracts('flame', 9900)).toBe(6)
    expect(ebbLadderContracts('flame', 2999)).toBe(1)
    expect(ebbLadderContracts('flame', 3000)).toBe(2)
  })
  it('FLAME at $2,000 is 1 lot (the small-tier floor)', () => {
    expect(ebbLadderContracts('flame', 2000)).toBe(1)
  })
})

describe('EBB count ladder — below one rung is ZERO, never 1', () => {
  it('SPARK under $5,000 gets no lots (SPARK 2 lots at $5k breached 40% DD; 1 lot needs the full rung)', () => {
    expect(ebbLadderContracts('spark', 4999)).toBe(0)
    expect(ebbLadderContracts('spark', 2000)).toBe(0)
  })
  it('FLAME under $1,500 gets no lots', () => {
    expect(ebbLadderContracts('flame', 1499)).toBe(0)
  })
  it('missing / invalid ladder capital is 0, never a guess', () => {
    expect(ebbLadderContracts('spark', null)).toBe(0)
    expect(ebbLadderContracts('flame', undefined)).toBe(0)
    expect(ebbLadderContracts('flame', NaN)).toBe(0)
    expect(ebbLadderContracts('flame', -5000)).toBe(0)
    expect(ebbLadderContracts('flame', 0)).toBe(0)
  })
})

describe('EBB high-water ratchet — ebbLadderCapital(starting, highWater)', () => {
  it('keys on the larger of funded and high-water', () => {
    expect(ebbLadderCapital(10_000, 12_000)).toBe(12_000)
    expect(ebbLadderCapital(12_000, 10_000)).toBe(12_000)
  })
  it('starting wins when the high-water is missing or invalid (pre-migration row)', () => {
    expect(ebbLadderCapital(10_000, null)).toBe(10_000)
    expect(ebbLadderCapital(10_000, undefined)).toBe(10_000)
    expect(ebbLadderCapital(10_000, 0)).toBe(10_000)
    expect(ebbLadderCapital(10_000, NaN)).toBe(10_000)
    expect(ebbLadderCapital(10_000, -1)).toBe(10_000)
  })
  it('a high-water below starting never drags the ladder under the funded seed', () => {
    expect(ebbLadderCapital(10_000, 7_000)).toBe(10_000)
    expect(ebbLadderContracts('spark', ebbLadderCapital(10_000, 7_000))).toBe(2)
  })
  it('high-water alone carries the ladder when starting is missing', () => {
    expect(ebbLadderCapital(null, 12_000)).toBe(12_000)
    expect(ebbLadderCapital(0, 12_000)).toBe(12_000)
  })
  it('neither valid is null — the caller must skip', () => {
    expect(ebbLadderCapital(null, null)).toBeNull()
    expect(ebbLadderCapital(0, 0)).toBeNull()
    expect(ebbLadderCapital(NaN, undefined)).toBeNull()
    expect(ebbLadderContracts('flame', ebbLadderCapital(null, null))).toBe(0)
  })
  it('lots never decrease through a drawdown when the high-water is the running peak', () => {
    // A $10k SPARK account: balance rides to $15k, then falls to $7k.
    const balances = [10_000, 12_000, 9_000, 15_000, 7_000, 11_000, 16_000]
    let hw = 10_000
    let lastLots = 0
    for (const bal of balances) {
      hw = Math.max(hw, bal)           // what every balance write does with GREATEST()
      const lots = ebbLadderContracts('spark', ebbLadderCapital(10_000, hw))
      expect(lots).toBeGreaterThanOrEqual(lastLots)
      lastLots = lots
    }
    expect(lastLots).toBe(3)           // $16k peak -> 3 lots, held through the $7k trough
    // Sizing from the balance itself would have dropped to 1 lot at $7k (the
    // de-lever rule: $258/yr at 54% DD). The ratchet must never do that.
    expect(ebbLadderContracts('spark', 7_000)).toBe(1)
  })
})

describe('EBB liquidity check — liquidityCappedLots(ladderLots, displayedSize, share)', () => {
  it('share is 25% of the displayed bid size at the short strike', () => {
    expect(EBB_LIQUIDITY_SHARE).toBe(0.25)
  })
  it('passes the ladder through when it fits inside the share', () => {
    const r = liquidityCappedLots(20, 100)
    expect(r).toEqual({ lots: 20, liquidity: 'ok', maxLots: 25, displayedSize: 100 })
  })
  it('caps to floor(25% × size) when the book is thinner than the ladder', () => {
    expect(liquidityCappedLots(20, 60)).toEqual({ lots: 15, liquidity: 'capped', maxLots: 15, displayedSize: 60 })
    expect(liquidityCappedLots(66, 100)).toEqual({ lots: 25, liquidity: 'capped', maxLots: 25, displayedSize: 100 })
    expect(liquidityCappedLots(66, 107).lots).toBe(26)   // floor(26.75)
  })
  it('unknown size (null / undefined / NaN / negative) passes the ladder through and says UNKNOWN', () => {
    for (const size of [null, undefined, NaN, -5]) {
      expect(liquidityCappedLots(20, size)).toEqual({ lots: 20, liquidity: 'unknown', maxLots: null, displayedSize: null })
    }
  })
  it('ZERO displayed size is UNKNOWN, not "no book": falls back to the ladder lots, never to 0', () => {
    expect(liquidityCappedLots(20, 0)).toEqual({ lots: 20, liquidity: 'unknown', maxLots: null, displayedSize: null })
  })
  it('a real but tiny size floors to 0 lots — the rule binding, the caller skips', () => {
    expect(liquidityCappedLots(5, 3)).toEqual({ lots: 0, liquidity: 'capped', maxLots: 0, displayedSize: 3 })
    expect(liquidityCappedLots(1, 4).lots).toBe(1)       // floor(1.0) = 1
  })
  it('the UNKNOWN fallback is still under the static cap', () => {
    expect(liquidityCappedLots(500, null).lots).toBe(EBB_LADDER_CAP)
    expect(liquidityCappedLots(500, 10_000).lots).toBe(EBB_LADDER_CAP)
  })
  it('ladder 0 stays 0 whatever the book shows', () => {
    expect(liquidityCappedLots(0, 1_000).lots).toBe(0)
    expect(liquidityCappedLots(-3, 1_000).lots).toBe(0)
    expect(liquidityCappedLots(NaN, 1_000).lots).toBe(0)
  })
  it('share is a parameter (default 25%)', () => {
    expect(liquidityCappedLots(20, 100, 0.5).lots).toBe(20)
    expect(liquidityCappedLots(20, 100, 0.1).lots).toBe(10)
    expect(liquidityCappedLots(20, 100, 0).liquidity).toBe('unknown')
  })
})

describe('EBB entry log line', () => {
  it('shows funded, high-water, ladder lots, displayed size, liquidity-capped lots and final lots in one line', () => {
    const liq = liquidityCappedLots(20, 60)
    const line = formatEbbSizingLine({ funded: 100_000, highWater: 104_000, rung: 5000, ladderLots: 20, liq, finalLots: 12 })
    expect(line).toBe(
      'funded=$100000 high_water=$104000 ladder_capital=$104000 rung=$5000 ' +
      'ladder_lots=20 displayed_size=60 liquidity=CAPPED liquidity_capped_lots=15 final_lots=12',
    )
    expect(line).not.toMatch(/\n/)
  })
  it('prints UNKNOWN when the quote carried no size and NONE for a missing field', () => {
    const line = formatEbbSizingLine({ funded: 6000, highWater: null, rung: 1500, ladderLots: 4, liq: liquidityCappedLots(4, null), finalLots: 4 })
    expect(line).toContain('high_water=NONE')
    expect(line).toContain('displayed_size=UNKNOWN liquidity=UNKNOWN liquidity_capped_lots=4 final_lots=4')
  })
})

describe('EBB count ladder — both money paths are wired to the ratchet and the liquidity check', () => {
  const lib = join(__dirname, '..')
  const scanner = readFileSync(join(lib, 'scanner.ts'), 'utf8')
  const tradier = readFileSync(join(lib, 'tradier.ts'), 'utf8')
  const db = readFileSync(join(lib, 'db.ts'), 'utf8')

  it('paper path reads high_water_balance, sizes via ebbLadderCapital, skips at 0, and runs the liquidity check on the short-put bid size', () => {
    expect(scanner).toMatch(/SELECT id, current_balance, starting_capital, high_water_balance FROM \$\{botTable\(bot\.name, 'paper_account'\)\}/)
    expect(scanner).toMatch(/const perTrade = flameContracts\(bot\.name, ebbLadderCapital\(funded, highWater\)\)/)
    expect(scanner).toMatch(/if \(perTrade < 1\) \{\s*return `skip:below_ladder_rung/)
    expect(scanner).toMatch(/liquidityCappedLots\(perTrade, c\.shortBidSize\)/)
    expect(scanner).toMatch(/const contracts = liq \? liq\.lots : perTrade/)
    expect(scanner).toMatch(/if \(contracts < 1\) \{[\s\S]*?return `skip:liquidity\(/)
    expect(scanner).toMatch(/sizing: \$\{sizingLine\}/)
    const start = scanner.indexOf('function flameContracts(')
    const fn = scanner.slice(start, start + scanner.slice(start).indexOf('\n}') + 2)
    expect(fn).toMatch(/return ebbLadderContracts\(botName, ladderCapital\)/)
    // The only `return 1` allowed is the non-EBB guard, never a bare flat line.
    expect(fn).not.toMatch(/^\s*return 1\s*$/m)
    expect(fn).toMatch(/if \(!isEbbLadderBot\(botName\)\) return 1/)
    // Never the floating balance.
    expect(scanner).not.toMatch(/flameContracts\(bot\.name, balance\)/)
    expect(scanner).not.toMatch(/ebbLadderCapital\([^)]*balance\b[^)]*current_balance/)
  })

  it('production path reads starting_capital + high_water_balance, sizes via ebbLadderCapital, liquidity-caps on the short-put bid size, skips at 0, and never exceeds broker BP', () => {
    expect(tradier).toMatch(/export async function getProductionLadderCapital\(/)
    expect(tradier).toMatch(/SELECT starting_capital, high_water_balance FROM \$\{botTable\(botName, 'paper_account'\)\}\s+WHERE account_type = 'production' AND person = \$1 AND is_active = TRUE/)
    expect(tradier).toMatch(/const cap = await getProductionLadderCapital\(botName, acct\.name\)/)
    expect(tradier).toMatch(/const ladder = ebbSizing\.ebbLadderContracts\(botName, ebbSizing\.ebbLadderCapital\(funded, highWater\)\)/)
    expect(tradier).toMatch(/if \(ladder < 1\) \{[\s\S]*?return\s*\n\s*\}/)
    expect(tradier).toMatch(/const psQ = await getOptionQuote\(occPs\)/)
    expect(tradier).toMatch(/const liq = ebbSizing\.liquidityCappedLots\(ladder, shortPutBidSize\)/)
    expect(tradier).toMatch(/if \(liq\.lots < 1\) \{[\s\S]*?return\s*\n\s*\}/)
    // ADR 0013: spark_config.max_contracts is INERT on the ladder path. FLAME's
    // production row still says max_contracts=1 (pre-ladder), and minning it in
    // here pinned every FLAME account to 1 lot after PR #2960 shipped.
    expect(tradier).toMatch(/acctContracts = Math\.min\(SANDBOX_MAX_CONTRACTS, liq\.lots\)/)
    expect(tradier).not.toMatch(/Math\.min\(SANDBOX_MAX_CONTRACTS, liq\.lots, prodCeiling\)/)
    expect(tradier).toMatch(/if \(acctContracts > bpContracts\) \{[\s\S]*?acctContracts = bpContracts/)
    expect(tradier).toMatch(/ebbSizing\.formatEbbSizingLine\(\{[\s\S]*?finalLots: acctContracts/)
    // The old funded-only reader is gone; nothing sizes from it any more.
    expect(tradier).not.toMatch(/getProductionFundedCapital/)
  })

  it('Tradier option quotes carry the displayed bid size the liquidity check needs', () => {
    expect(tradier).toMatch(/bidsize: parseQuoteSize\(quote\.bidsize\)/)
    expect(tradier).toMatch(/shortBidSize: psQ\.bidsize \?\? null/)
  })

  it('high_water_balance is added idempotently and backfilled to GREATEST(starting_capital, current_balance)', () => {
    expect(db).toMatch(/ALTER TABLE \$\{bot\}_paper_account ADD COLUMN IF NOT EXISTS high_water_balance NUMERIC\(12,2\)/)
    expect(db).toMatch(/SET high_water_balance = GREATEST\(starting_capital, current_balance\)\s+WHERE high_water_balance IS NULL/)
    expect(db).toMatch(/high_water_balance NUMERIC\(12,2\),/)
  })

  it('EVERY current_balance write in src ratchets high_water_balance in the same statement', () => {
    const src = join(lib, '..')
    const files: string[] = []
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name)
        if (statSync(p).isDirectory()) { if (name !== '__tests__' && name !== 'node_modules') walk(p) }
        else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) files.push(p)
      }
    }
    walk(src)
    const misses: string[] = []
    let writes = 0
    for (const p of files) {
      const text = readFileSync(p, 'utf8')
      const re = /current_balance\s*=\s*(?!=)/g
      let m: RegExpExecArray | null
      while ((m = re.exec(text)) !== null) {
        const lineStart = text.lastIndexOf('\n', m.index) + 1
        const line = text.slice(lineStart, text.indexOf('\n', m.index)).trim()
        // Comments and doc blocks describe writes; they are not writes.
        if (line.startsWith('*') || line.startsWith('//') || line.startsWith('/*')) continue
        // Only SQL SET clauses are writes (a `WHERE current_balance = ...` would be a read).
        const before = text.slice(Math.max(0, m.index - 400), m.index)
        if (!/\bSET\b/.test(before) || /\bWHERE\b[^;`]*$/.test(before)) continue
        writes++
        const stmt = text.slice(m.index, m.index + 900)
        if (!/high_water_balance\s*=/.test(stmt)) {
          misses.push(`${p.replace(src, 'src')}: ${line}`)
        }
      }
    }
    expect(writes).toBeGreaterThanOrEqual(25)
    expect(misses).toEqual([])
  })
})
