/**
 * STOKE — pins strike selection (nearest-to-spot+2, NOT FLINT's ceil-to-
 * spot+1), the two entry gates (EBB's own VIX-skip ratio + prior-day-SPY-
 * down), the credit floor, mode gating (off/paper/live), the assignment-
 * guard trigger math, and STOKE's own profit gate (the R1-equivalent).
 *
 * Ships DISARMED: STOKE_MODE is unset by default and must resolve to 'off'.
 * 'live' additionally requires FLAME's own isFlameLiveArmed() gate in
 * tradier.ts (pinned separately for FLINT in flame-live-gate.test.ts;
 * STOKE reuses the exact same gate) — this suite only pins THIS sleeve's
 * own switch.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  STOKE_MIN_CREDIT_DEFAULT,
  STOKE_MAX_CONTRACTS_DEFAULT,
  STOKE_GUARD_BUFFER_DEFAULT,
  STOKE_OTM_OFFSET_DEFAULT,
  STOKE_COMMISSION_PER_CONTRACT,
  STOKE_BP_FLOOR_PER_CONTRACT,
  STOKE_FLOOR_AMOUNT_DEFAULT,
  computeStokeStrikes,
  getStokeMode,
  getStokeMaxContracts,
  getStokeGuardBuffer,
  getStokeOtmOffset,
  getStokeMinCredit,
  getStokeFloorAmount,
  meetsStokeCreditFloor,
  isStokeVixGateEligible,
  isStokeGuardTriggered,
  stokeMaxLoss,
  evaluateStokeProfitGate,
  decideStokeContractsForCushion,
} from '../stoke'

const ENV_KEYS = [
  'STOKE_MODE', 'STOKE_MAX_CONTRACTS', 'STOKE_GUARD_BUFFER', 'STOKE_OTM_OFFSET', 'STOKE_MIN_CREDIT',
  'STOKE_FLOOR_AMOUNT',
] as const

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

describe('STOKE strike selection (short = round(spot + offset), long = short + 2)', () => {
  it('spot 768.05, default offset 2 -> short 770, long 772', () => {
    expect(computeStokeStrikes(768.05)).toEqual({ short: 770, long: 772 })
  })
  it('spot 768.60, default offset 2 -> short 771, long 773 (rounds up at .5+)', () => {
    expect(computeStokeStrikes(768.60)).toEqual({ short: 771, long: 773 })
  })
  it('spot 770.00, default offset 2 -> short 772, long 774 (exactly on a whole dollar)', () => {
    expect(computeStokeStrikes(770.00)).toEqual({ short: 772, long: 774 })
  })
  it('honors an explicit non-default offset', () => {
    expect(computeStokeStrikes(768.05, 1)).toEqual({ short: 769, long: 771 })
  })
  it('STOKE_OTM_OFFSET_DEFAULT is 2 — different from FLINT\'s 1', () => {
    expect(STOKE_OTM_OFFSET_DEFAULT).toBe(2)
  })
  it('uses Math.round, not Math.ceil — a spot exactly .5 below the next dollar still rounds UP at offset boundary', () => {
    // spot + 2 = 769.50 exactly -> JS Math.round rounds .5 up -> 770
    expect(computeStokeStrikes(767.50)).toEqual({ short: 770, long: 772 })
  })
})

describe('STOKE_OTM_OFFSET env resolution', () => {
  it('defaults to 2 when unset', () => {
    delete process.env.STOKE_OTM_OFFSET
    expect(getStokeOtmOffset()).toBe(2)
  })
  it('honors a valid override', () => {
    process.env.STOKE_OTM_OFFSET = '3'
    expect(getStokeOtmOffset()).toBe(3)
  })
  it('falls back to the default on negative or garbage', () => {
    process.env.STOKE_OTM_OFFSET = '-1'
    expect(getStokeOtmOffset()).toBe(2)
    process.env.STOKE_OTM_OFFSET = 'nope'
    expect(getStokeOtmOffset()).toBe(2)
  })
})

describe('STOKE credit floor (default $0.10/share, configurable via STOKE_MIN_CREDIT)', () => {
  it('exactly $0.10 clears (inclusive floor)', () => {
    expect(STOKE_MIN_CREDIT_DEFAULT).toBe(0.10)
    expect(meetsStokeCreditFloor(0.10)).toBe(true)
  })
  it('$0.09 does not clear', () => {
    expect(meetsStokeCreditFloor(0.09)).toBe(false)
  })
  it('0 or negative never clears', () => {
    expect(meetsStokeCreditFloor(0)).toBe(false)
    expect(meetsStokeCreditFloor(-0.05)).toBe(false)
  })
  it('honors a custom floor', () => {
    expect(meetsStokeCreditFloor(0.20, 0.25)).toBe(false)
    expect(meetsStokeCreditFloor(0.25, 0.25)).toBe(true)
  })
})

describe('STOKE_MIN_CREDIT env resolution', () => {
  it('defaults to 0.10 when unset', () => {
    delete process.env.STOKE_MIN_CREDIT
    expect(getStokeMinCredit()).toBe(0.10)
  })
  it('honors a valid override', () => {
    process.env.STOKE_MIN_CREDIT = '0.20'
    expect(getStokeMinCredit()).toBe(0.20)
  })
  it('falls back to the default on negative or garbage', () => {
    process.env.STOKE_MIN_CREDIT = '-1'
    expect(getStokeMinCredit()).toBe(0.10)
    process.env.STOKE_MIN_CREDIT = 'nope'
    expect(getStokeMinCredit()).toBe(0.10)
  })
})

describe('STOKE_FLOOR_AMOUNT env resolution (STOKE\'s own dedicated profit-gate floor, default $500)', () => {
  it('defaults to 500 when unset', () => {
    delete process.env.STOKE_FLOOR_AMOUNT
    expect(STOKE_FLOOR_AMOUNT_DEFAULT).toBe(500)
    expect(getStokeFloorAmount()).toBe(500)
  })
  it('honors a valid override', () => {
    process.env.STOKE_FLOOR_AMOUNT = '700'
    expect(getStokeFloorAmount()).toBe(700)
  })
  it('falls back to the default on negative or garbage', () => {
    process.env.STOKE_FLOOR_AMOUNT = '-1'
    expect(getStokeFloorAmount()).toBe(500)
    process.env.STOKE_FLOOR_AMOUNT = 'nope'
    expect(getStokeFloorAmount()).toBe(500)
  })
})

describe('STOKE mode gating (off / paper / live) — shipped DISARMED', () => {
  it('defaults to off with nothing set — the shipped default', () => {
    delete process.env.STOKE_MODE
    expect(getStokeMode()).toBe('off')
  })
  it('is off for any unrecognized value — fails closed, never guesses armed', () => {
    for (const v of ['1', 'true', 'on', '']) {
      process.env.STOKE_MODE = v
      expect(getStokeMode(), `value ${JSON.stringify(v)} must stay off`).toBe('off')
    }
  })
  it('resolves to paper only on the exact string "paper"', () => {
    process.env.STOKE_MODE = 'paper'
    expect(getStokeMode()).toBe('paper')
  })
  it('resolves to live only on the exact string "live"', () => {
    process.env.STOKE_MODE = 'live'
    expect(getStokeMode()).toBe('live')
  })
  it('is case/whitespace tolerant only via trim+lowercase, not fuzzy matching', () => {
    process.env.STOKE_MODE = '  LIVE  '
    expect(getStokeMode()).toBe('live')
    process.env.STOKE_MODE = 'PAPER'
    expect(getStokeMode()).toBe('paper')
  })
})

describe('STOKE max contracts (fixed size, no upsize feature)', () => {
  it('defaults to 1', () => {
    delete process.env.STOKE_MAX_CONTRACTS
    expect(STOKE_MAX_CONTRACTS_DEFAULT).toBe(1)
    expect(getStokeMaxContracts()).toBe(1)
  })
  it('reads a valid override and floors it', () => {
    process.env.STOKE_MAX_CONTRACTS = '3.7'
    expect(getStokeMaxContracts()).toBe(3)
  })
  it('falls back to 1 on zero, negative, or garbage', () => {
    for (const v of ['0', '-2', 'abc', '']) {
      process.env.STOKE_MAX_CONTRACTS = v
      expect(getStokeMaxContracts(), `value ${JSON.stringify(v)}`).toBe(1)
    }
  })
})

describe('STOKE assignment guard buffer (default $0.25, same as FLINT)', () => {
  it('defaults to 0.25 when unset', () => {
    delete process.env.STOKE_GUARD_BUFFER
    expect(STOKE_GUARD_BUFFER_DEFAULT).toBe(0.25)
    expect(getStokeGuardBuffer()).toBe(0.25)
  })
  it('empty string disables the guard (returns 0)', () => {
    process.env.STOKE_GUARD_BUFFER = ''
    expect(getStokeGuardBuffer()).toBe(0)
  })
  it('"0" disables the guard', () => {
    process.env.STOKE_GUARD_BUFFER = '0'
    expect(getStokeGuardBuffer()).toBe(0)
  })
  it('a valid positive override is honored', () => {
    process.env.STOKE_GUARD_BUFFER = '0.40'
    expect(getStokeGuardBuffer()).toBe(0.40)
  })
  it('unparsable/negative falls back to the default rather than silently disabling', () => {
    process.env.STOKE_GUARD_BUFFER = '-1'
    expect(getStokeGuardBuffer()).toBe(0.25)
    process.env.STOKE_GUARD_BUFFER = 'nope'
    expect(getStokeGuardBuffer()).toBe(0.25)
  })
})

describe('STOKE guard trigger math (byte-for-byte the same shape as isFlintGuardTriggered)', () => {
  const SHORT = 770
  it('clear well below the short strike', () => {
    expect(isStokeGuardTriggered(767, SHORT, 0.25)).toBe(false)
  })
  it('triggers just inside the buffer below the strike', () => {
    expect(isStokeGuardTriggered(769.80, SHORT, 0.25)).toBe(true)
  })
  it('does not trigger just outside the buffer', () => {
    expect(isStokeGuardTriggered(769.70, SHORT, 0.25)).toBe(false)
  })
  it('triggers exactly at the buffer boundary (inclusive)', () => {
    expect(isStokeGuardTriggered(769.75, SHORT, 0.25)).toBe(true)
  })
  it('triggers when spot is above the short strike', () => {
    expect(isStokeGuardTriggered(771, SHORT, 0.25)).toBe(true)
  })
  it('buffer of 0 (disabled) never triggers, regardless of spot', () => {
    expect(isStokeGuardTriggered(9999, SHORT, 0)).toBe(false)
  })
  it('negative buffer never triggers (treated as disabled)', () => {
    expect(isStokeGuardTriggered(9999, SHORT, -1)).toBe(false)
  })
})

describe('STOKE max loss — worst case, includes commission (byte-for-byte the same formula as flintMaxLoss)', () => {
  it('short 770, long 772, credit 0.22, 1 contract', () => {
    expect(stokeMaxLoss(770, 772, 0.22, 1)).toBeCloseTo(179.40, 2)
  })
  it('scales with contracts', () => {
    expect(stokeMaxLoss(770, 772, 0.22, 2)).toBeCloseTo(358.80, 2)
  })
  it('STOKE_COMMISSION_PER_CONTRACT is $1.40 (two legs at $0.70 each)', () => {
    expect(STOKE_COMMISSION_PER_CONTRACT).toBe(1.40)
  })
  it('STOKE_BP_FLOOR_PER_CONTRACT is $200', () => {
    expect(STOKE_BP_FLOOR_PER_CONTRACT).toBe(200)
  })
})

describe('Gate 1 — EBB-skip VIX ratio (fires only when EBB itself would skip, ratio > 0.80)', () => {
  it('ratio 0.79 (EBB itself is trading) is NOT eligible for STOKE', () => {
    expect(isStokeVixGateEligible(0.79)).toBe(false)
  })
  it('ratio exactly 0.80 (the ceiling itself) is NOT eligible — strictly above, not >=', () => {
    expect(isStokeVixGateEligible(0.80)).toBe(false)
  })
  it('ratio 0.81 (the day EBB skips) IS eligible', () => {
    expect(isStokeVixGateEligible(0.81)).toBe(true)
  })
  it('a null/unreadable ratio fails CLOSED, never trades on a guess', () => {
    expect(isStokeVixGateEligible(null)).toBe(false)
  })
  it('a non-finite ratio fails CLOSED', () => {
    expect(isStokeVixGateEligible(NaN)).toBe(false)
  })
  it('honors a custom ceiling', () => {
    expect(isStokeVixGateEligible(0.95, 0.90)).toBe(true)
    expect(isStokeVixGateEligible(0.85, 0.90)).toBe(false)
  })
})

describe('STOKE profit gate — cushion = stokeFloor + stokeRealizedPnl, must clear maxLoss (byte-for-byte the same shape as FLINT\'s rule R1)', () => {
  it('cushion of exactly 0 with any positive maxLoss always skips', () => {
    const result = evaluateStokeProfitGate(0, 0, 190)
    expect(result.cushion).toBe(0)
    expect(result.eligible).toBe(false)
    expect(result.reason).toContain('skip:stoke_profit_cushion')
  })
  it('zero prior STOKE P&L still trades off the floor alone', () => {
    const result = evaluateStokeProfitGate(250, 0, 190)
    expect(result.cushion).toBe(250)
    expect(result.eligible).toBe(true)
  })
  it('cushion 189 vs maxloss 190 -> skip (cushion strictly below maxloss)', () => {
    const result = evaluateStokeProfitGate(250, -61, 190)
    expect(result.cushion).toBe(189)
    expect(result.eligible).toBe(false)
  })
  it('cushion 190 vs maxloss 190 -> trade (inclusive floor, >= not >)', () => {
    const result = evaluateStokeProfitGate(250, -60, 190)
    expect(result.cushion).toBe(190)
    expect(result.eligible).toBe(true)
    expect(result.reason).toBeNull()
  })
  it('null floor fails closed, never guesses', () => {
    const result = evaluateStokeProfitGate(null, 0, 190)
    expect(result.eligible).toBe(false)
    expect(result.cushion).toBeNull()
  })
  it('null realized P&L fails closed, never guesses', () => {
    const result = evaluateStokeProfitGate(250, null, 190)
    expect(result.eligible).toBe(false)
    expect(result.cushion).toBeNull()
  })
  it('per-account independence: one account trades, another skips, same day, same maxLoss', () => {
    const maxLoss = 190
    const accountA = evaluateStokeProfitGate(250, 250, maxLoss)
    const accountB = evaluateStokeProfitGate(250, -200, maxLoss)
    expect(accountA.eligible).toBe(true)
    expect(accountB.eligible).toBe(false)
    expect(evaluateStokeProfitGate(250, 250, maxLoss)).toEqual(accountA)
  })
  it('a same-day FLINT or EBB loss never appears in either input — the gate only ever takes stokeFloor/stokeRealizedPnl', () => {
    // There is no third argument for FLINT's or EBB's own P&L/equity at all —
    // the function signature itself proves the independence.
    expect(evaluateStokeProfitGate.length).toBe(3)
  })
})

describe('decideStokeContractsForCushion — no upsize feature, desired===base is always exactly ONE gate evaluation', () => {
  const short = 770, long = 772, credit = 0.30 // maxLoss @1ct = (2-0.30)*100+1.40 = $171.40

  it('is byte-for-byte evaluateStokeProfitGate when desired === base', () => {
    const loss = stokeMaxLoss(short, long, credit, 1)
    const direct = evaluateStokeProfitGate(250, 0, loss)
    const viaDecision = decideStokeContractsForCushion(1, 1, 250, 0, short, long, credit)
    expect(viaDecision.contracts).toBe(direct.eligible ? 1 : 0)
    expect(viaDecision.gate).toEqual(direct)
  })

  it('cushion clears the 1-contract loss -> contracts is 1', () => {
    const d = decideStokeContractsForCushion(1, 1, 250, 0, short, long, credit)
    expect(d.contracts).toBe(1)
    expect(d.gate.eligible).toBe(true)
  })

  it('cushion does not clear -> contracts is 0, caller must skip entirely', () => {
    const d = decideStokeContractsForCushion(1, 1, 250, -200, short, long, credit)
    expect(d.contracts).toBe(0)
    expect(d.gate.eligible).toBe(false)
  })

  it('unreadable floor/realized P&L fails CLOSED', () => {
    expect(decideStokeContractsForCushion(1, 1, null, 100, short, long, credit).contracts).toBe(0)
    expect(decideStokeContractsForCushion(1, 1, 250, null, short, long, credit).contracts).toBe(0)
  })
})

/**
 * STOKE_MODE unset (-> 'off') must place zero orders ANYWHERE — sandbox or
 * production, entry or guard-close — not just resolve the mode string.
 * tryOpenStoke and closeStokeAtRiskBeforeBell are module-private in
 * scanner.ts: pin the gate structurally, so a future refactor that moves
 * work ABOVE the 'off' check shows up as a diff here.
 */
describe('STOKE_MODE off places zero orders anywhere (sandbox or production) — structural', () => {
  const scanner = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

  function fnBody(name: string): string {
    const start = scanner.indexOf(`async function ${name}(`)
    expect(start, `${name} must exist`).toBeGreaterThan(-1)
    const rest = scanner.slice(start + 1)
    const end = rest.search(/\n(?:async )?function \w+\(/)
    return end === -1 ? rest : rest.slice(0, end)
  }

  it("tryOpenStoke's very first statement (after reading mode) is the mode==='off' bail, before any table/DB touch or account loop", () => {
    const body = fnBody('tryOpenStoke')
    const modeIdx = body.indexOf("if (mode === 'off') return ''")
    expect(modeIdx, 'the off-gate must exist').toBeGreaterThan(-1)
    expect(body.slice(0, modeIdx)).not.toMatch(/query\(|ensureStokeTable|placeStokeOrderAllAccounts/)
    const placeIdx = body.indexOf('placeStokeOrderAllAccounts(')
    expect(placeIdx).toBeGreaterThan(modeIdx)
  })

  it("closeStokeAtRiskBeforeBell's very first statement is the same mode==='off' bail, before reading flame_stoke_positions", () => {
    const body = fnBody('closeStokeAtRiskBeforeBell')
    const modeIdx = body.indexOf("if (getStokeMode() === 'off') return ''")
    expect(modeIdx, 'the off-gate must exist').toBeGreaterThan(-1)
    expect(body.slice(0, modeIdx)).not.toMatch(/query\(|placeStokeOrderAllAccounts/)
    const selectIdx = body.indexOf('FROM ${STOKE_TABLE}')
    expect(selectIdx).toBeGreaterThan(modeIdx)
  })

  it("settleStokeExpired's very first statement is the same mode==='off' bail", () => {
    const body = fnBody('settleStokeExpired')
    const modeIdx = body.indexOf("if (getStokeMode() === 'off') return ''")
    expect(modeIdx, 'the off-gate must exist').toBeGreaterThan(-1)
    const selectIdx = body.indexOf('FROM ${STOKE_TABLE}')
    expect(selectIdx).toBeGreaterThan(modeIdx)
  })
})

describe('STOKE never reads FLINT\'s or EBB\'s own tables/functions — structural', () => {
  const scanner = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')
  const tradier = readFileSync(join(__dirname, '..', 'tradier.ts'), 'utf8')

  function fnBody(src: string, name: string): string {
    const start = src.indexOf(`async function ${name}(`) >= 0
      ? src.indexOf(`async function ${name}(`)
      : src.indexOf(`export async function ${name}(`)
    expect(start, `${name} must exist`).toBeGreaterThan(-1)
    const rest = src.slice(start + 1)
    const end = rest.search(/\n(?:export )?(?:async )?function \w+\(/)
    return end === -1 ? rest : rest.slice(0, end)
  }

  it('tryOpenStoke never references flint_positions, FLINT_TABLE, or getFlintPaperLedger', () => {
    const body = fnBody(scanner, 'tryOpenStoke')
    expect(body).not.toMatch(/flint_positions|FLINT_TABLE|getFlintPaperLedger|getFlintCumulativeRealizedPnl/)
  })

  it('placeStokeOrderAllAccounts never references flint_account_floor or FLINT_BP_FLOOR_PER_CONTRACT', () => {
    const body = fnBody(tradier, 'placeStokeOrderAllAccounts')
    expect(body).not.toMatch(/flint_account_floor|FLINT_BP_FLOOR_PER_CONTRACT|getFlintSandboxLedger|getOrSeedFlintAccountFloor/)
  })
})
