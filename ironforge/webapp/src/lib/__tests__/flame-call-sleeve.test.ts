/**
 * FLAME-CALL sleeve — pins strike selection, the day filter, the credit
 * floor, mode gating (off/paper/live), and the assignment-guard trigger math.
 *
 * Ships DISARMED: FLAME_CALL_SLEEVE_MODE is unset by default and must
 * resolve to 'off'. 'live' additionally requires FLAME's own
 * isFlameLiveArmed() gate in tradier.ts (pinned separately in
 * flame-live-gate.test.ts) — this suite only pins THIS sleeve's own switch.
 */
import { describe, it, expect, afterEach } from 'vitest'
import {
  CALL_SLEEVE_MIN_CREDIT,
  CALL_SLEEVE_DEFAULT_MAX_CONTRACTS,
  CALL_SLEEVE_DEFAULT_GUARD_BUFFER,
  computeCallStrikes,
  getCallSleeveMode,
  getCallSleeveMaxContracts,
  getCallSleeveGuardBuffer,
  isCallSleeveDayEligible,
  meetsCallCreditFloor,
  isCallGuardTriggered,
} from '../flame-call-sleeve'

const ENV_KEYS = ['FLAME_CALL_SLEEVE_MODE', 'CALL_SLEEVE_MAX_CONTRACTS', 'CALL_SLEEVE_GUARD_BUFFER'] as const

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

describe('FLAME-CALL strike selection (ceil(spot + 2), long = short + 2)', () => {
  it('spot 768.05 -> short 771, long 773', () => {
    expect(computeCallStrikes(768.05)).toEqual({ short: 771, long: 773 })
  })
  it('spot 770.00 -> short 772, long 774 (exactly on a whole dollar)', () => {
    expect(computeCallStrikes(770.00)).toEqual({ short: 772, long: 774 })
  })
  it('spot 769.99 -> short 772, long 774 (ceil of 771.99)', () => {
    expect(computeCallStrikes(769.99)).toEqual({ short: 772, long: 774 })
  })
})

describe('FLAME-CALL day filter (trade only when FLAME\'s own gate ratio > 0.80)', () => {
  const CEILING = 0.80
  it('ratio 0.80 (== ceiling) does NOT trade — FLAME itself still trades at 0.80', () => {
    expect(isCallSleeveDayEligible(0.80, CEILING)).toBe(false)
  })
  it('ratio 0.81 (> ceiling) trades — the day FLAME skips', () => {
    expect(isCallSleeveDayEligible(0.81, CEILING)).toBe(true)
  })
  it('ratio 0.79 (< ceiling) does not trade — FLAME is trading today', () => {
    expect(isCallSleeveDayEligible(0.79, CEILING)).toBe(false)
  })
  it('null ratio (unknown/unavailable history) never trades — fails closed', () => {
    expect(isCallSleeveDayEligible(null, CEILING)).toBe(false)
  })
  it('NaN never trades', () => {
    expect(isCallSleeveDayEligible(Number.NaN, CEILING)).toBe(false)
  })
})

describe('FLAME-CALL credit floor ($0.10/share)', () => {
  it('exactly $0.10 clears (inclusive floor)', () => {
    expect(CALL_SLEEVE_MIN_CREDIT).toBe(0.10)
    expect(meetsCallCreditFloor(0.10)).toBe(true)
  })
  it('$0.09 does not clear', () => {
    expect(meetsCallCreditFloor(0.09)).toBe(false)
  })
  it('$0.15 clears', () => {
    expect(meetsCallCreditFloor(0.15)).toBe(true)
  })
  it('0 or negative never clears', () => {
    expect(meetsCallCreditFloor(0)).toBe(false)
    expect(meetsCallCreditFloor(-0.05)).toBe(false)
  })
})

describe('FLAME-CALL mode gating (off / paper / live) — shipped DISARMED', () => {
  it('defaults to off with nothing set — the shipped default', () => {
    delete process.env.FLAME_CALL_SLEEVE_MODE
    expect(getCallSleeveMode()).toBe('off')
  })
  it('is off for any unrecognized value — fails closed, never guesses armed', () => {
    for (const v of ['1', 'true', 'on', '']) {
      process.env.FLAME_CALL_SLEEVE_MODE = v
      expect(getCallSleeveMode(), `value ${JSON.stringify(v)} must stay off`).toBe('off')
    }
  })
  it('resolves to paper only on the exact string "paper"', () => {
    process.env.FLAME_CALL_SLEEVE_MODE = 'paper'
    expect(getCallSleeveMode()).toBe('paper')
  })
  it('resolves to live only on the exact string "live"', () => {
    process.env.FLAME_CALL_SLEEVE_MODE = 'live'
    expect(getCallSleeveMode()).toBe('live')
  })
  it('is case/whitespace tolerant only via trim+lowercase, not fuzzy matching', () => {
    process.env.FLAME_CALL_SLEEVE_MODE = '  LIVE  '
    expect(getCallSleeveMode()).toBe('live')
    process.env.FLAME_CALL_SLEEVE_MODE = 'PAPER'
    expect(getCallSleeveMode()).toBe('paper')
  })
})

describe('FLAME-CALL max contracts (fixed size, not the ladder)', () => {
  it('defaults to 1', () => {
    delete process.env.CALL_SLEEVE_MAX_CONTRACTS
    expect(CALL_SLEEVE_DEFAULT_MAX_CONTRACTS).toBe(1)
    expect(getCallSleeveMaxContracts()).toBe(1)
  })
  it('reads a valid override and floors it', () => {
    process.env.CALL_SLEEVE_MAX_CONTRACTS = '3.7'
    expect(getCallSleeveMaxContracts()).toBe(3)
  })
  it('falls back to 1 on zero, negative, or garbage', () => {
    for (const v of ['0', '-2', 'abc', '']) {
      process.env.CALL_SLEEVE_MAX_CONTRACTS = v
      expect(getCallSleeveMaxContracts(), `value ${JSON.stringify(v)}`).toBe(1)
    }
  })
})

describe('FLAME-CALL assignment guard buffer (default $0.25, distinct from FLAME put-side $0.50)', () => {
  it('defaults to 0.25 when unset', () => {
    delete process.env.CALL_SLEEVE_GUARD_BUFFER
    expect(CALL_SLEEVE_DEFAULT_GUARD_BUFFER).toBe(0.25)
    expect(getCallSleeveGuardBuffer()).toBe(0.25)
  })
  it('empty string disables the guard (returns 0)', () => {
    process.env.CALL_SLEEVE_GUARD_BUFFER = ''
    expect(getCallSleeveGuardBuffer()).toBe(0)
  })
  it('"0" disables the guard', () => {
    process.env.CALL_SLEEVE_GUARD_BUFFER = '0'
    expect(getCallSleeveGuardBuffer()).toBe(0)
  })
  it('a valid positive override is honored', () => {
    process.env.CALL_SLEEVE_GUARD_BUFFER = '0.40'
    expect(getCallSleeveGuardBuffer()).toBe(0.40)
  })
  it('unparsable/negative falls back to the default rather than silently disabling', () => {
    process.env.CALL_SLEEVE_GUARD_BUFFER = '-1'
    expect(getCallSleeveGuardBuffer()).toBe(0.25)
    process.env.CALL_SLEEVE_GUARD_BUFFER = 'nope'
    expect(getCallSleeveGuardBuffer()).toBe(0.25)
  })
})

describe('FLAME-CALL guard trigger math', () => {
  const SHORT = 771
  it('clear well below the short strike', () => {
    expect(isCallGuardTriggered(768, SHORT, 0.25)).toBe(false)
  })
  it('triggers just inside the buffer below the strike', () => {
    expect(isCallGuardTriggered(770.80, SHORT, 0.25)).toBe(true) // 771 - 0.25 = 770.75
  })
  it('does not trigger just outside the buffer', () => {
    expect(isCallGuardTriggered(770.70, SHORT, 0.25)).toBe(false)
  })
  it('triggers exactly at the buffer boundary (inclusive)', () => {
    expect(isCallGuardTriggered(770.75, SHORT, 0.25)).toBe(true)
  })
  it('triggers when spot is above the short strike', () => {
    expect(isCallGuardTriggered(772, SHORT, 0.25)).toBe(true)
  })
  it('buffer of 0 (disabled) never triggers, regardless of spot', () => {
    expect(isCallGuardTriggered(9999, SHORT, 0)).toBe(false)
  })
  it('negative buffer never triggers (treated as disabled)', () => {
    expect(isCallGuardTriggered(9999, SHORT, -1)).toBe(false)
  })
})
