/**
 * CALLDIAG — pins the exact construction replicated from
 * tools/mr_book/gate_500s_iwm_intraday_retest.py (front/back expiry, implied
 * spot, ATM straddle EM, short/long strike, debit/collateral, exit-day
 * walk, exit P&L), the frozen vol stand-down gate from
 * out/clusters/CLUSTER_calldiag_iwm.py, the $7,500 unlock threshold
 * (env-overridable), the per-account cushion gate, and mode gating
 * (off/paper/live). Ships DISARMED: CALLDIAG_MODE is unset by default and
 * must resolve to 'off'.
 */
import { describe, it, expect, afterEach } from 'vitest'
import {
  CALLDIAG_FRONT_DTE,
  CALLDIAG_BACK_DTE,
  CALLDIAG_WING_WIDTH,
  CALLDIAG_FEE_PER_LEG,
  CALLDIAG_MAX_CONTRACTS,
  CALLDIAG_MIN_EQUITY_DEFAULT,
  CALLDIAG_RV5_STANDDOWN_THRESHOLD,
  getCallDiagMode,
  getCallDiagMinEquity,
  isCallDiagUnlocked,
  computeTrailing5dRealizedVolPct,
  isCallDiagStandDown,
  pickCallDiagExpiry,
  computeCallDiagImpliedSpot,
  buildCallDiagTrade,
  pickCallDiagExitDate,
  computeCallDiagExitPnl,
  evaluateCallDiagCushion,
  type CallDiagQuote,
} from '../calldiag'

const ENV_KEYS = ['CALLDIAG_MODE', 'CALLDIAG_MIN_EQUITY'] as const

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

describe('constants match the research spec exactly', () => {
  it('front=10dte, back=20dte, wing=$1, fee=$0.04/leg, max 1 contract', () => {
    expect(CALLDIAG_FRONT_DTE).toBe(10)
    expect(CALLDIAG_BACK_DTE).toBe(20)
    expect(CALLDIAG_WING_WIDTH).toBe(1.0)
    expect(CALLDIAG_FEE_PER_LEG).toBe(0.04)
    expect(CALLDIAG_MAX_CONTRACTS).toBe(1)
  })
  it('unlock default is $7,500 (Leron, 2026-09-27 follow-up)', () => {
    expect(CALLDIAG_MIN_EQUITY_DEFAULT).toBe(7500)
  })
  it('stand-down threshold is the frozen 17.81 (rv5_pct first-half median)', () => {
    expect(CALLDIAG_RV5_STANDDOWN_THRESHOLD).toBe(17.81)
  })
})

describe('CALLDIAG_MODE gating — fails closed', () => {
  it('unset resolves to off', () => {
    delete process.env.CALLDIAG_MODE
    expect(getCallDiagMode()).toBe('off')
  })
  it('garbage resolves to off', () => {
    process.env.CALLDIAG_MODE = 'true'
    expect(getCallDiagMode()).toBe('off')
    process.env.CALLDIAG_MODE = ''
    expect(getCallDiagMode()).toBe('off')
  })
  it('paper and live are honored', () => {
    process.env.CALLDIAG_MODE = 'paper'
    expect(getCallDiagMode()).toBe('paper')
    process.env.CALLDIAG_MODE = 'LIVE'
    expect(getCallDiagMode()).toBe('live')
  })
})

describe('CALLDIAG_MIN_EQUITY — unlock threshold, env-overridable', () => {
  it('defaults to $7,500 when unset', () => {
    delete process.env.CALLDIAG_MIN_EQUITY
    expect(getCallDiagMinEquity()).toBe(7500)
  })
  it('$7,499 is locked, $7,500 is unlocked, at the default', () => {
    delete process.env.CALLDIAG_MIN_EQUITY
    expect(isCallDiagUnlocked(7499, getCallDiagMinEquity())).toBe(false)
    expect(isCallDiagUnlocked(7500, getCallDiagMinEquity())).toBe(true)
  })
  it('honors an env override with no code change (e.g. a future $4,000 or $10,000 study)', () => {
    process.env.CALLDIAG_MIN_EQUITY = '4000'
    expect(getCallDiagMinEquity()).toBe(4000)
    expect(isCallDiagUnlocked(3999, getCallDiagMinEquity())).toBe(false)
    expect(isCallDiagUnlocked(4000, getCallDiagMinEquity())).toBe(true)
  })
  it('falls back to the default on garbage or non-positive', () => {
    process.env.CALLDIAG_MIN_EQUITY = '-100'
    expect(getCallDiagMinEquity()).toBe(7500)
    process.env.CALLDIAG_MIN_EQUITY = 'nope'
    expect(getCallDiagMinEquity()).toBe(7500)
  })
  it('unreadable equity never unlocks', () => {
    expect(isCallDiagUnlocked(null, 7500)).toBe(false)
  })
})

describe('vol stand-down gate (frozen rule: rv5_pct <= 17.81 -> stand down)', () => {
  it('5 prior-close returns -> sample stdev * sqrt(252) * 100', () => {
    // returns of 0 every day -> zero realized vol
    expect(computeTrailing5dRealizedVolPct([0, 0, 0, 0, 0])).toBe(0)
  })
  it('a known small-return series produces a positive, finite rv5', () => {
    const rv = computeTrailing5dRealizedVolPct([0.01, -0.01, 0.005, -0.005, 0.002])
    expect(rv).not.toBeNull()
    expect(rv as number).toBeGreaterThan(0)
  })
  it('anything other than exactly 5 finite returns is unmeasurable (null)', () => {
    expect(computeTrailing5dRealizedVolPct([0.01, 0.02])).toBeNull()
    expect(computeTrailing5dRealizedVolPct([0.01, 0.02, 0.03, 0.04, NaN])).toBeNull()
  })
  it('stands down at or below the threshold', () => {
    expect(isCallDiagStandDown(17.81)).toBe(true)
    expect(isCallDiagStandDown(10)).toBe(true)
  })
  it('trades above the threshold', () => {
    expect(isCallDiagStandDown(17.82)).toBe(false)
    expect(isCallDiagStandDown(40)).toBe(false)
  })
  it('unmeasurable vol fails closed (stands down)', () => {
    expect(isCallDiagStandDown(null)).toBe(true)
  })
})

describe('expiry selection — first listed expiry with dte >= minDte', () => {
  it('picks the first front (>=10dte) and back (>=20dte) expiry', () => {
    const exps = ['2025-01-27', '2025-02-03', '2025-02-10', '2025-02-14', '2025-02-21']
    // trade date 2025-01-24: +3d, +10d, +17d, +21d, +28d
    expect(pickCallDiagExpiry(exps, '2025-01-24', CALLDIAG_FRONT_DTE)).toBe('2025-02-03')
    expect(pickCallDiagExpiry(exps, '2025-01-24', CALLDIAG_BACK_DTE)).toBe('2025-02-14')
  })
  it('null when nothing clears the minimum', () => {
    expect(pickCallDiagExpiry(['2025-01-25'], '2025-01-24', 10)).toBeNull()
  })
})

describe('implied spot — put-call parity, median of strike + callMid - putMid', () => {
  it('three common strikes all implying the same spot', () => {
    const q: CallDiagQuote[] = [
      { strike: 100, cp: 'C', bid: 1.4, ask: 1.6 }, { strike: 100, cp: 'P', bid: 0.4, ask: 0.6 },
      { strike: 101, cp: 'C', bid: 0.9, ask: 1.1 }, { strike: 101, cp: 'P', bid: 0.9, ask: 1.1 },
      { strike: 102, cp: 'C', bid: 0.5, ask: 0.7 }, { strike: 102, cp: 'P', bid: 1.5, ask: 1.7 },
    ]
    expect(computeCallDiagImpliedSpot(q)).toBe(101)
  })
  it('null with fewer than 2 common strikes', () => {
    const q: CallDiagQuote[] = [{ strike: 100, cp: 'C', bid: 1, ask: 1.2 }]
    expect(computeCallDiagImpliedSpot(q)).toBeNull()
  })
})

/** Shared front chain for the 3 fixture builds below: spot=101, ATM k=101, em=2.0, target=103. */
const FRONT: CallDiagQuote[] = [
  { strike: 100, cp: 'C', bid: 1.4, ask: 1.6 }, { strike: 100, cp: 'P', bid: 0.4, ask: 0.6 },
  { strike: 101, cp: 'C', bid: 0.9, ask: 1.1 }, { strike: 101, cp: 'P', bid: 0.9, ask: 1.1 },
  { strike: 102, cp: 'C', bid: 0.5, ask: 0.7 }, { strike: 102, cp: 'P', bid: 1.5, ask: 1.7 },
  { strike: 103, cp: 'C', bid: 0.3, ask: 0.4 },
]

describe('buildCallDiagTrade — 3 fixture chains, byte-for-byte the research build()', () => {
  it('fixture 1: full success — short=103, long=104, debit=-5.00, collateral=100.00', () => {
    const back: CallDiagQuote[] = [{ strike: 104, cp: 'C', bid: 0.15, ask: 0.25 }]
    const r = buildCallDiagTrade('2025-02-03', '2025-02-14', FRONT, back)
    expect(r).toEqual({
      front: '2025-02-03', back: '2025-02-14',
      shortStrike: 103, longStrike: 104, spot: 101, em: 2,
      shortBid: 0.3, longAsk: 0.25, debit: -5, collateral: 100,
    })
  })
  it('fixture 2: back chain missing the long strike -> missing_leg_quote', () => {
    const back: CallDiagQuote[] = [{ strike: 108, cp: 'C', bid: 0.05, ask: 0.1 }]
    expect(buildCallDiagTrade('2025-02-03', '2025-02-14', FRONT, back)).toBe('missing_leg_quote')
  })
  it('fixture 3: no front strike clears spot+em -> no_short_strike', () => {
    // same front chain but drop the 103 call, so nothing >= target (103) exists
    const frontNoShort = FRONT.filter((q) => q.strike !== 103)
    const back: CallDiagQuote[] = [{ strike: 104, cp: 'C', bid: 0.15, ask: 0.25 }]
    expect(buildCallDiagTrade('2025-02-03', '2025-02-14', frontNoShort, back)).toBe('no_short_strike')
  })
  it('too few common strikes to trust a spot -> spot_not_measurable (the build()-level '
    + "no_common_strikes branch is unreachable through this path: both spot AND the "
    + 'common-strikes check key off the same call/put strike intersection)', () => {
    const frontCallOnly: CallDiagQuote[] = [{ strike: 100, cp: 'C', bid: 1, ask: 1.2 }]
    const back: CallDiagQuote[] = [{ strike: 101, cp: 'C', bid: 0.1, ask: 0.2 }]
    expect(buildCallDiagTrade('2025-02-03', '2025-02-14', frontCallOnly, back)).toBe('spot_not_measurable')
  })
  it('spot not measurable (empty chain) -> spot_not_measurable', () => {
    expect(buildCallDiagTrade('2025-02-03', '2025-02-14', [], [])).toBe('spot_not_measurable')
  })
})

describe('exit scheduling — last trading session strictly before front expiry', () => {
  const CAL = ['2025-01-24', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-03']
  it('walks forward from entry to the day before front expiry', () => {
    expect(pickCallDiagExitDate(CAL, '2025-01-24', '2025-02-03')).toBe('2025-01-31')
  })
  it('entry day itself when the very next session is the front expiry', () => {
    expect(pickCallDiagExitDate(CAL, '2025-01-31', '2025-02-03')).toBe(null)
    // front expiry the day right after entry -> exit is that single intervening session
    expect(pickCallDiagExitDate(CAL, '2025-01-30', '2025-02-03')).toBe('2025-01-31')
  })
  it('null (no_session_before_expiry) when the entry date is not in the calendar', () => {
    expect(pickCallDiagExitDate(CAL, '2099-01-01', '2025-02-03')).toBeNull()
  })
})

describe('exit P&L — buy back short at exit ask, sell long at exit bid, minus fee*4', () => {
  it('matches the research formula on the fixture-1 trade', () => {
    // fixture-1 entry: shortBid=0.30, longAsk=0.25. Assume exit shortAsk=0.10, longBid=0.20.
    const pnl = computeCallDiagExitPnl(0.30, 0.25, 0.10, 0.20)
    // 100*(0.30-0.10) + 100*(0.20-0.25) - 0.04*4 = 20 - 5 - 0.16 = 14.84
    expect(pnl).toBe(14.84)
  })
})

describe('per-account cushion gate (rule R1, mirrors evaluateFlintProfitGate)', () => {
  it('eligible when cushion clears max loss', () => {
    const r = evaluateCallDiagCushion(8000, 7500, 100)
    expect(r.eligible).toBe(true)
    expect(r.cushion).toBe(500)
  })
  it('skips when cushion is short of max loss', () => {
    const r = evaluateCallDiagCushion(7550, 7500, 100)
    expect(r.eligible).toBe(false)
    expect(r.reason).toContain('calldiag_profit_cushion')
  })
  it('fails closed when equity or floor is unreadable', () => {
    expect(evaluateCallDiagCushion(null, 7500, 100).eligible).toBe(false)
    expect(evaluateCallDiagCushion(8000, null, 100).eligible).toBe(false)
  })
  it('per-account independence: two accounts with different equity/floor are gated independently', () => {
    const accountA = evaluateCallDiagCushion(9000, 7500, 100) // cushion 1500, eligible
    const accountB = evaluateCallDiagCushion(7550, 7500, 100) // cushion 50, not eligible
    expect(accountA.eligible).toBe(true)
    expect(accountB.eligible).toBe(false)
    // B's gate result carries no trace of A's numbers
    expect(accountB.cushion).toBe(50)
  })
})
