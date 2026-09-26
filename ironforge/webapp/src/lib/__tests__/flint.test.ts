/**
 * FLINT — pins strike selection, the (now unconditional) day filter, the
 * credit floor, mode gating (off/paper/live), the assignment-guard trigger
 * math, and the per-account profit gate (rule R1).
 *
 * Ships DISARMED: FLINT_MODE is unset by default and must resolve to 'off'.
 * 'live' additionally requires FLAME's own isFlameLiveArmed() gate in
 * tradier.ts (pinned separately in flame-live-gate.test.ts) — this suite
 * only pins THIS sleeve's own switch.
 */
import { describe, it, expect, afterEach } from 'vitest'
import {
  FLINT_MIN_CREDIT_DEFAULT,
  FLINT_MAX_CONTRACTS_DEFAULT,
  FLINT_GUARD_BUFFER_DEFAULT,
  FLINT_OTM_OFFSET_DEFAULT,
  FLINT_COMMISSION_PER_CONTRACT,
  FLINT_BP_FLOOR_PER_CONTRACT,
  computeFlintStrikes,
  getFlintMode,
  getFlintMaxContracts,
  getFlintGuardBuffer,
  getFlintOtmOffset,
  getFlintMinCredit,
  isFlintDayEligible,
  meetsFlintCreditFloor,
  isFlintGuardTriggered,
  flintMaxLoss,
  evaluateFlintProfitGate,
  buildFlintDailyContextRow,
  UNAVAILABLE_FLINT_GAMMA_CONTEXT,
  type FlintGammaContext,
} from '../flint'

const ENV_KEYS = [
  'FLINT_MODE', 'FLINT_MAX_CONTRACTS', 'FLINT_GUARD_BUFFER', 'FLINT_OTM_OFFSET', 'FLINT_MIN_CREDIT',
] as const

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

describe('FLINT strike selection (short = ceil(spot + offset), long = short + 2)', () => {
  it('spot 768.05, default offset 1 -> short 770, long 772', () => {
    expect(computeFlintStrikes(768.05)).toEqual({ short: 770, long: 772 })
  })
  it('spot 770.00, default offset 1 -> short 771, long 773 (exactly on a whole dollar)', () => {
    expect(computeFlintStrikes(770.00)).toEqual({ short: 771, long: 773 })
  })
  it('honors an explicit non-default offset', () => {
    expect(computeFlintStrikes(768.05, 2)).toEqual({ short: 771, long: 773 })
  })
  it('FLINT_OTM_OFFSET_DEFAULT is 1', () => {
    expect(FLINT_OTM_OFFSET_DEFAULT).toBe(1)
  })
})

describe('FLINT_OTM_OFFSET env resolution', () => {
  it('defaults to 1 when unset', () => {
    delete process.env.FLINT_OTM_OFFSET
    expect(getFlintOtmOffset()).toBe(1)
  })
  it('honors a valid override', () => {
    process.env.FLINT_OTM_OFFSET = '2'
    expect(getFlintOtmOffset()).toBe(2)
  })
  it('falls back to the default on negative or garbage', () => {
    process.env.FLINT_OTM_OFFSET = '-1'
    expect(getFlintOtmOffset()).toBe(1)
    process.env.FLINT_OTM_OFFSET = 'nope'
    expect(getFlintOtmOffset()).toBe(1)
  })
})

describe('FLINT day filter — trades EVERY day now, regardless of FLAME\'s own gate ratio', () => {
  it('ratio 0.79 (FLAME itself is trading) is still eligible', () => {
    expect(isFlintDayEligible(0.79)).toBe(true)
  })
  it('ratio 0.81 (the day FLAME used to skip) is still eligible', () => {
    expect(isFlintDayEligible(0.81)).toBe(true)
  })
  it('a null/unknown ratio is still eligible — the ratio never gates FLINT any more', () => {
    expect(isFlintDayEligible(null)).toBe(true)
  })
})

describe('FLINT credit floor (default $0.10/share, configurable via FLINT_MIN_CREDIT)', () => {
  it('exactly $0.10 clears (inclusive floor)', () => {
    expect(FLINT_MIN_CREDIT_DEFAULT).toBe(0.10)
    expect(meetsFlintCreditFloor(0.10)).toBe(true)
  })
  it('$0.09 does not clear', () => {
    expect(meetsFlintCreditFloor(0.09)).toBe(false)
  })
  it('$0.15 clears', () => {
    expect(meetsFlintCreditFloor(0.15)).toBe(true)
  })
  it('0 or negative never clears', () => {
    expect(meetsFlintCreditFloor(0)).toBe(false)
    expect(meetsFlintCreditFloor(-0.05)).toBe(false)
  })
  it('honors a custom floor', () => {
    expect(meetsFlintCreditFloor(0.20, 0.25)).toBe(false)
    expect(meetsFlintCreditFloor(0.25, 0.25)).toBe(true)
  })
})

describe('FLINT_MIN_CREDIT env resolution', () => {
  it('defaults to 0.10 when unset', () => {
    delete process.env.FLINT_MIN_CREDIT
    expect(getFlintMinCredit()).toBe(0.10)
  })
  it('honors a valid override', () => {
    process.env.FLINT_MIN_CREDIT = '0.20'
    expect(getFlintMinCredit()).toBe(0.20)
  })
  it('falls back to the default on negative or garbage', () => {
    process.env.FLINT_MIN_CREDIT = '-1'
    expect(getFlintMinCredit()).toBe(0.10)
    process.env.FLINT_MIN_CREDIT = 'nope'
    expect(getFlintMinCredit()).toBe(0.10)
  })
})

describe('FLINT mode gating (off / paper / live) — shipped DISARMED', () => {
  it('defaults to off with nothing set — the shipped default', () => {
    delete process.env.FLINT_MODE
    expect(getFlintMode()).toBe('off')
  })
  it('is off for any unrecognized value — fails closed, never guesses armed', () => {
    for (const v of ['1', 'true', 'on', '']) {
      process.env.FLINT_MODE = v
      expect(getFlintMode(), `value ${JSON.stringify(v)} must stay off`).toBe('off')
    }
  })
  it('resolves to paper only on the exact string "paper"', () => {
    process.env.FLINT_MODE = 'paper'
    expect(getFlintMode()).toBe('paper')
  })
  it('resolves to live only on the exact string "live"', () => {
    process.env.FLINT_MODE = 'live'
    expect(getFlintMode()).toBe('live')
  })
  it('is case/whitespace tolerant only via trim+lowercase, not fuzzy matching', () => {
    process.env.FLINT_MODE = '  LIVE  '
    expect(getFlintMode()).toBe('live')
    process.env.FLINT_MODE = 'PAPER'
    expect(getFlintMode()).toBe('paper')
  })
})

describe('FLINT max contracts (fixed size, not the ladder)', () => {
  it('defaults to 1', () => {
    delete process.env.FLINT_MAX_CONTRACTS
    expect(FLINT_MAX_CONTRACTS_DEFAULT).toBe(1)
    expect(getFlintMaxContracts()).toBe(1)
  })
  it('reads a valid override and floors it', () => {
    process.env.FLINT_MAX_CONTRACTS = '3.7'
    expect(getFlintMaxContracts()).toBe(3)
  })
  it('falls back to 1 on zero, negative, or garbage', () => {
    for (const v of ['0', '-2', 'abc', '']) {
      process.env.FLINT_MAX_CONTRACTS = v
      expect(getFlintMaxContracts(), `value ${JSON.stringify(v)}`).toBe(1)
    }
  })
})

describe('FLINT assignment guard buffer (default $0.25)', () => {
  it('defaults to 0.25 when unset', () => {
    delete process.env.FLINT_GUARD_BUFFER
    expect(FLINT_GUARD_BUFFER_DEFAULT).toBe(0.25)
    expect(getFlintGuardBuffer()).toBe(0.25)
  })
  it('empty string disables the guard (returns 0)', () => {
    process.env.FLINT_GUARD_BUFFER = ''
    expect(getFlintGuardBuffer()).toBe(0)
  })
  it('"0" disables the guard', () => {
    process.env.FLINT_GUARD_BUFFER = '0'
    expect(getFlintGuardBuffer()).toBe(0)
  })
  it('a valid positive override is honored', () => {
    process.env.FLINT_GUARD_BUFFER = '0.40'
    expect(getFlintGuardBuffer()).toBe(0.40)
  })
  it('unparsable/negative falls back to the default rather than silently disabling', () => {
    process.env.FLINT_GUARD_BUFFER = '-1'
    expect(getFlintGuardBuffer()).toBe(0.25)
    process.env.FLINT_GUARD_BUFFER = 'nope'
    expect(getFlintGuardBuffer()).toBe(0.25)
  })
})

describe('FLINT guard trigger math', () => {
  const SHORT = 770
  it('clear well below the short strike', () => {
    expect(isFlintGuardTriggered(767, SHORT, 0.25)).toBe(false)
  })
  it('triggers just inside the buffer below the strike', () => {
    expect(isFlintGuardTriggered(769.80, SHORT, 0.25)).toBe(true) // 770 - 0.25 = 769.75
  })
  it('does not trigger just outside the buffer', () => {
    expect(isFlintGuardTriggered(769.70, SHORT, 0.25)).toBe(false)
  })
  it('triggers exactly at the buffer boundary (inclusive)', () => {
    expect(isFlintGuardTriggered(769.75, SHORT, 0.25)).toBe(true)
  })
  it('triggers when spot is above the short strike', () => {
    expect(isFlintGuardTriggered(771, SHORT, 0.25)).toBe(true)
  })
  it('buffer of 0 (disabled) never triggers, regardless of spot', () => {
    expect(isFlintGuardTriggered(9999, SHORT, 0)).toBe(false)
  })
  it('negative buffer never triggers (treated as disabled)', () => {
    expect(isFlintGuardTriggered(9999, SHORT, -1)).toBe(false)
  })
})

describe('FLINT max loss (rule R1 input) — worst case, includes commission', () => {
  it('short 770, long 772, credit 0.22, 1 contract', () => {
    // (772 - 770 - 0.22) * 100 * 1 + 1.40 * 1 = 178 + 1.40 = 179.40
    expect(flintMaxLoss(770, 772, 0.22, 1)).toBeCloseTo(179.40, 2)
  })
  it('scales with contracts', () => {
    expect(flintMaxLoss(770, 772, 0.22, 2)).toBeCloseTo(358.80, 2)
  })
  it('FLINT_COMMISSION_PER_CONTRACT is $1.40 (two legs at $0.70 each)', () => {
    expect(FLINT_COMMISSION_PER_CONTRACT).toBe(1.40)
  })
  it('FLINT_BP_FLOOR_PER_CONTRACT is $200', () => {
    expect(FLINT_BP_FLOOR_PER_CONTRACT).toBe(200)
  })
})

describe('FLINT profit gate (rule R1) — cushion = equity - floor, must clear maxLoss', () => {
  it('cushion of exactly 0 with any positive maxLoss always skips', () => {
    const result = evaluateFlintProfitGate(10000, 10000, 190)
    expect(result.cushion).toBe(0)
    expect(result.eligible).toBe(false)
    expect(result.reason).toContain('skip:flint_profit_cushion')
  })
  it('cushion 189 vs maxloss 190 -> skip (cushion strictly below maxloss)', () => {
    const result = evaluateFlintProfitGate(10189, 10000, 190)
    expect(result.cushion).toBe(189)
    expect(result.eligible).toBe(false)
  })
  it('cushion 190 vs maxloss 190 -> trade (inclusive floor, >= not >)', () => {
    const result = evaluateFlintProfitGate(10190, 10000, 190)
    expect(result.cushion).toBe(190)
    expect(result.eligible).toBe(true)
    expect(result.reason).toBeNull()
  })
  it('null equity fails closed, never guesses', () => {
    const result = evaluateFlintProfitGate(null, 10000, 190)
    expect(result.eligible).toBe(false)
    expect(result.cushion).toBeNull()
  })
  it('null floor fails closed, never guesses', () => {
    const result = evaluateFlintProfitGate(10500, null, 190)
    expect(result.eligible).toBe(false)
    expect(result.cushion).toBeNull()
  })
  it('per-account independence: one account trades, another skips, same day, same maxLoss', () => {
    const maxLoss = 190
    const accountA = evaluateFlintProfitGate(10500, 10000, maxLoss) // cushion 500 -> trades
    const accountB = evaluateFlintProfitGate(10050, 10000, maxLoss) // cushion 50 -> skips
    expect(accountA.eligible).toBe(true)
    expect(accountB.eligible).toBe(false)
    // Evaluating B never mutated or depended on A's result — pure functions, no shared state.
    expect(evaluateFlintProfitGate(10500, 10000, maxLoss)).toEqual(accountA)
  })
})

describe('FLINT daily-context row builder (forward-logging, pure — no DB/network)', () => {
  const EVALUATED_AT = new Date('2026-09-26T13:07:00.000Z')
  const FULL_GAMMA: FlintGammaContext = {
    callGamma: 2.3e10,
    putGamma: 1.7e10,
    netGamma: 6.0e9,
    gammaFlip: 780,
    putWall: null,
    callWall: null,
    gammaSource: 'tradier_chain_dollar_gex_dte0-60',
  }

  it('carries every field through verbatim when a trade is placed', () => {
    const row = buildFlintDailyContextRow({
      tradeDate: '2026-09-26',
      evaluatedAt: EVALUATED_AT,
      spot: 768.05,
      vixRatio: 0.83,
      shortStrike: 770,
      longStrike: 772,
      entryCredit: 0.22,
      decision: 'traded',
      gamma: FULL_GAMMA,
    })
    expect(row).toEqual({
      trade_date: '2026-09-26',
      evaluated_at: EVALUATED_AT.toISOString(),
      spot: 768.05,
      vix_ratio: 0.83,
      call_short_strike_considered: 770,
      call_long_strike_considered: 772,
      entry_credit_seen: 0.22,
      decision: 'traded',
      call_gamma: 2.3e10,
      put_gamma: 1.7e10,
      net_gamma: 6.0e9,
      gamma_flip: 780,
      put_wall: null,
      call_wall: null,
      gamma_source: 'tradier_chain_dollar_gex_dte0-60',
    })
  })

  it('writes every gamma field NULL with gammaSource "unavailable" when gamma is explicitly UNAVAILABLE_FLINT_GAMMA_CONTEXT', () => {
    const row = buildFlintDailyContextRow({
      tradeDate: '2026-09-26',
      evaluatedAt: EVALUATED_AT,
      spot: 768.05,
      vixRatio: 0.83,
      shortStrike: 770,
      longStrike: 772,
      entryCredit: 0.22,
      decision: 'traded',
      gamma: UNAVAILABLE_FLINT_GAMMA_CONTEXT,
    })
    expect(row.call_gamma).toBeNull()
    expect(row.put_gamma).toBeNull()
    expect(row.net_gamma).toBeNull()
    expect(row.gamma_flip).toBeNull()
    expect(row.put_wall).toBeNull()
    expect(row.call_wall).toBeNull()
    expect(row.gamma_source).toBe('unavailable')
  })

  it('never fabricates a gamma reading when `gamma` itself is null — same null+"unavailable" result', () => {
    const row = buildFlintDailyContextRow({
      tradeDate: '2026-09-26',
      evaluatedAt: EVALUATED_AT,
      spot: null,
      vixRatio: 0.83,
      shortStrike: null,
      longStrike: null,
      entryCredit: null,
      decision: 'skip:flint_profit_cushion(cushion=$50.00<maxloss=$190.00)',
      gamma: null,
    })
    expect(row.call_gamma).toBeNull()
    expect(row.put_gamma).toBeNull()
    expect(row.net_gamma).toBeNull()
    expect(row.gamma_source).toBe('unavailable')
    expect(row.spot).toBeNull()
    expect(row.call_short_strike_considered).toBeNull()
    expect(row.entry_credit_seen).toBeNull()
    expect(row.decision).toBe('skip:flint_profit_cushion(cushion=$50.00<maxloss=$190.00)')
  })

  it('a partial gamma read (call/put/net known, flip/walls not) is stored as-is, no backfilling', () => {
    const partial: FlintGammaContext = {
      callGamma: 1.0e10,
      putGamma: 0.9e10,
      netGamma: 1.0e9,
      gammaFlip: null,
      putWall: null,
      callWall: null,
      gammaSource: 'tradier_chain_dollar_gex_dte0-60',
    }
    const row = buildFlintDailyContextRow({
      tradeDate: '2026-09-26',
      evaluatedAt: EVALUATED_AT,
      spot: 768.05,
      vixRatio: 0.90,
      shortStrike: 770,
      longStrike: 772,
      entryCredit: 0.05,
      decision: 'skip:call_credit_too_low',
      gamma: partial,
    })
    expect(row.call_gamma).toBe(1.0e10)
    expect(row.put_gamma).toBe(0.9e10)
    expect(row.net_gamma).toBe(1.0e9)
    expect(row.gamma_flip).toBeNull()
    expect(row.put_wall).toBeNull()
    expect(row.call_wall).toBeNull()
  })
})
