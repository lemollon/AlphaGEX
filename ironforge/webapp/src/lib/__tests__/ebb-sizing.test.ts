/**
 * Pins the EBB contract-count ladder (2026-09-04).
 *
 * Leron: "the ladder should not be width, it should be count of contracts" and
 * "need to round because contract price is not going to be a round number".
 * These tests fail if anyone moves a rung, the cap, the rounding direction, or
 * wires either money path back to buying power / live equity.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  EBB_LADDER_CAP,
  FLAME_RUNG_USD,
  SPARK_RUNG_USD,
  ebbLadderContracts,
  ebbRungUsd,
  isEbbLadderBot,
} from '../ebb-sizing'

describe('EBB count ladder — rungs (2026-08-27 survivor rule)', () => {
  it('FLAME is 1 lot per $1,500 funded', () => {
    expect(FLAME_RUNG_USD).toBe(1500)
    expect(ebbRungUsd('flame')).toBe(1500)
  })
  it('SPARK is 1 lot per $5,000 funded', () => {
    expect(SPARK_RUNG_USD).toBe(5000)
    expect(ebbRungUsd('spark')).toBe(5000)
  })
  it('caps at 5 lots', () => {
    expect(EBB_LADDER_CAP).toBe(5)
    expect(ebbLadderContracts('flame', 1_000_000)).toBe(5)
    expect(ebbLadderContracts('spark', 1_000_000)).toBe(5)
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
  it('FLAME: $9,900 is 7 lots but capped to 5; $2,999 is 1; $3,000 is 2', () => {
    expect(ebbLadderContracts('flame', 9900)).toBe(5)
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
  it('missing / invalid funded capital is 0, never a guess', () => {
    expect(ebbLadderContracts('spark', null)).toBe(0)
    expect(ebbLadderContracts('flame', undefined)).toBe(0)
    expect(ebbLadderContracts('flame', NaN)).toBe(0)
    expect(ebbLadderContracts('flame', -5000)).toBe(0)
    expect(ebbLadderContracts('flame', 0)).toBe(0)
  })
})

describe('EBB count ladder — both money paths are wired to it', () => {
  const lib = join(__dirname, '..')
  const scanner = readFileSync(join(lib, 'scanner.ts'), 'utf8')
  const tradier = readFileSync(join(lib, 'tradier.ts'), 'utf8')

  it('paper path sizes from the ledger starting_capital via the ladder and skips at 0', () => {
    expect(scanner).toMatch(/SELECT id, current_balance, starting_capital FROM \$\{botTable\(bot\.name, 'paper_account'\)\}/)
    expect(scanner).toMatch(/const perTrade = flameContracts\(bot\.name, funded\)/)
    expect(scanner).toMatch(/if \(perTrade < 1\) return `skip:below_ladder_rung/)
    const start = scanner.indexOf('function flameContracts(')
    const fn = scanner.slice(start, start + scanner.slice(start).indexOf('\n}') + 2)
    expect(fn).toMatch(/return ebbLadderContracts\(botName, fundedCapital\)/)
    // The only `return 1` allowed is the non-EBB guard, never a bare flat line.
    expect(fn).not.toMatch(/^\s*return 1\s*$/m)
    expect(fn).toMatch(/if \(!isEbbLadderBot\(botName\)\) return 1/)
  })

  it('production path sizes SPARK/FLAME from funded capital, skips at 0, and never exceeds broker BP', () => {
    expect(tradier).toMatch(/export async function getProductionFundedCapital\(/)
    expect(tradier).toMatch(/SELECT starting_capital FROM \$\{botTable\(botName, 'paper_account'\)\}\s+WHERE account_type = 'production' AND person = \$1 AND is_active = TRUE/)
    expect(tradier).toMatch(/const funded = await getProductionFundedCapital\(botName, acct\.name\)/)
    expect(tradier).toMatch(/const ladder = ebbLadderContracts\(botName, funded\)/)
    expect(tradier).toMatch(/if \(ladder < 1\) \{[\s\S]*?return\s*\n\s*\}/)
    expect(tradier).toMatch(/acctContracts = Math\.min\(SANDBOX_MAX_CONTRACTS, ladder, prodCeiling\)/)
    expect(tradier).toMatch(/if \(acctContracts > bpContracts\) \{[\s\S]*?acctContracts = bpContracts/)
  })
})
