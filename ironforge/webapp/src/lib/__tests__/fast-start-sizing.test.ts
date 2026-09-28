/**
 * Unit tests for every branch of the FLAME_FAST_START sizing rule
 * (fast-start-sizing.ts) — the frozen 2x/X=20%/N=8/K=0.25/G rule, live-money
 * sizing for FLAME customer accounts. See fast-start-sizing-parity.test.ts
 * for the day-by-day parity test against the real sim (the key test).
 */
import { describe, it, expect, afterEach } from 'vitest'
import {
  decideFastStartSizing,
  seedFastStartState,
  isFastStartMode,
  sizeFlintGivenEbbOutcome,
  evaluateFastStartTrigger,
  FAST_START_STYLE_MULT,
  FAST_START_X,
  FAST_START_N,
  FAST_START_K,
  type FastStartAccountState,
  type FastStartDayInputs,
} from '../fast-start-sizing'

const ORIG_ENV = process.env.FLAME_FAST_START

afterEach(() => {
  if (ORIG_ENV === undefined) delete process.env.FLAME_FAST_START
  else process.env.FLAME_FAST_START = ORIG_ENV
})

function baseInputs(overrides: Partial<FastStartDayInputs> = {}): FastStartDayInputs {
  return {
    ebbCandidateDay: true,
    flintCandidateDay: true,
    ebbMaxLossPerLot: 170,
    flintMaxLossPerContract: 190,
    normalEbbLadder: 2,
    equity: 4242,
    peakProfit: 0,
    ...overrides,
  }
}

describe('isFastStartMode / FLAME_FAST_START env flag', () => {
  it('unset -> off', () => {
    delete process.env.FLAME_FAST_START
    expect(isFastStartMode()).toBe(false)
  })
  it('"off" -> off', () => {
    process.env.FLAME_FAST_START = 'off'
    expect(isFastStartMode()).toBe(false)
  })
  it('any unrecognized value -> off (fails closed)', () => {
    process.env.FLAME_FAST_START = 'true'
    expect(isFastStartMode()).toBe(false)
    process.env.FLAME_FAST_START = '1'
    expect(isFastStartMode()).toBe(false)
  })
  it('"on" (any case/whitespace) -> on', () => {
    process.env.FLAME_FAST_START = 'ON'
    expect(isFastStartMode()).toBe(true)
    process.env.FLAME_FAST_START = '  on  '
    expect(isFastStartMode()).toBe(true)
  })
})

describe('frozen parameters are pinned (2x / X=20% / N=8 / K=0.25)', () => {
  it('pins the constants', () => {
    expect(FAST_START_STYLE_MULT).toBe(2)
    expect(FAST_START_X).toBe(0.20)
    expect(FAST_START_N).toBe(8)
    expect(FAST_START_K).toBe(0.25)
  })
})

describe('KILL SWITCH: FLAME_FAST_START=off (or unset) returns unchanged normal-ladder sizing on every branch', () => {
  const scenarios: Array<[string, FastStartDayInputs, FastStartAccountState]> = [
    ['phase 1, normal day', baseInputs(), seedFastStartState(4242)],
    ['phase 2, normal day', baseInputs({ peakProfit: 5000 }), { phase: 2, deposit: 4242 }],
    ['new account, no history', baseInputs({ normalEbbLadder: 0 }), seedFastStartState(2000)],
    ['missing max-loss data', baseInputs({ ebbMaxLossPerLot: null, flintMaxLossPerContract: null }), seedFastStartState(4242)],
    ['equity below deposit', baseInputs({ equity: 3000 }), seedFastStartState(4242)],
    ['not an EBB candidate day', baseInputs({ ebbCandidateDay: false }), seedFastStartState(4242)],
  ]

  for (const [label, inputs, state] of scenarios) {
    it(`${label}: off -> ebbContracts === normalEbbLadder (floored), flintContracts === 0, phase unchanged`, () => {
      delete process.env.FLAME_FAST_START
      const { decision, nextState } = decideFastStartSizing(state, inputs)
      const expectedEbb = inputs.ebbCandidateDay ? Math.max(0, Math.floor(inputs.normalEbbLadder)) : 0
      expect(decision.ebbContracts).toBe(expectedEbb)
      expect(decision.flintContracts).toBe(0)
      expect(decision.phase).toBe(state.phase)
      expect(nextState).toEqual(state)
      expect(decision.reason).toContain('off:FLAME_FAST_START')
    })
  }

  it('off never mutates state even across repeated calls', () => {
    delete process.env.FLAME_FAST_START
    let state = seedFastStartState(2000)
    for (let i = 0; i < 10; i++) {
      const { nextState } = decideFastStartSizing(state, baseInputs({ equity: 2000 + i * 1000 }))
      expect(nextState.phase).toBe(1)
      state = nextState
    }
  })
})

describe('Phase 1 sizing (on)', () => {
  it('new account, no history: seeds phase 1, deposit fixed', () => {
    const state = seedFastStartState(4242)
    expect(state.phase).toBe(1)
    expect(state.deposit).toBe(4242)
  })

  it('2x the normal ladder, capped by X=20% of deposit (EBB allocated first)', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(4242)
    // normalLadder=2 -> target 4 lots. X budget = 0.20*4242=848.4. ebb_ml=170 -> floor(848.4/170)=4.
    const { decision } = decideFastStartSizing(state, baseInputs({ normalEbbLadder: 2, ebbMaxLossPerLot: 170 }))
    expect(decision.phase).toBe(1)
    expect(decision.ebbContracts).toBe(4)
    expect(decision.floor).toBe(4242)
  })

  it('Phase 1 cap smaller than 1 lot -> 0 EBB contracts, logged', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(500) // X budget = 100, ebb_ml way above it
    const { decision } = decideFastStartSizing(
      state,
      baseInputs({ equity: 500, normalEbbLadder: 1, ebbMaxLossPerLot: 500 }),
    )
    expect(decision.ebbContracts).toBe(0)
    expect(decision.reason).toContain('ebb=0')
  })

  it('FLINT never multiplied — always <= 1, gated by its own standing cushion rule AND the shared X budget', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(4242)
    // cushion is 0 on a brand-new account -> flint standing rule fails (cushion < flint_ml)
    const { decision } = decideFastStartSizing(state, baseInputs({ equity: 4242 }))
    expect(decision.flintContracts).toBe(0)
  })

  it('FLINT trades when cushion covers it AND budget remains after EBB', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(2000)
    // cushion = 300 >= flint_ml(190). X budget = 400. ebb target=2*1=2, ebb_ml=170 -> ebb=min(2,floor(400/170)=2)=2.
    // remaining = 400-2*170=60 < 190 -> flint should be 0 (budget exhausted by EBB first).
    const { decision } = decideFastStartSizing(
      state,
      baseInputs({ equity: 2300, normalEbbLadder: 1, ebbMaxLossPerLot: 170, flintMaxLossPerContract: 190 }),
    )
    expect(decision.ebbContracts).toBe(2)
    expect(decision.flintContracts).toBe(0)
  })

  it('missing EBB max-loss data on an EBB-candidate day -> 0 EBB contracts, logged, never guesses', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(4242)
    const { decision } = decideFastStartSizing(state, baseInputs({ ebbMaxLossPerLot: null }))
    expect(decision.ebbContracts).toBe(0)
    expect(decision.reason).toContain('unreadable')
  })

  it('missing FLINT max-loss data on a FLINT-candidate day -> 0 FLINT contracts, logged', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(4242)
    const { decision } = decideFastStartSizing(
      state,
      baseInputs({ equity: 6000, flintMaxLossPerContract: null }),
    )
    expect(decision.flintContracts).toBe(0)
    expect(decision.reason).toContain('flint max-loss unreadable')
  })

  it('not an EBB-candidate day -> 0 EBB contracts even with room in the budget', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(4242)
    const { decision } = decideFastStartSizing(state, baseInputs({ ebbCandidateDay: false }))
    expect(decision.ebbContracts).toBe(0)
  })

  it('trigger fires mid-day: an account that already has enough cushion transitions to Phase 2 THE SAME DAY (existing account with pre-existing profit)', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(2000)
    // ladder=1, ebb_ml=170, flint_ml=190 (both candidates) -> combined_ml_ladder = 1*170+190=360. trigger=8*360=2880.
    // cushion must be >= 2880 -> equity >= 4880.
    const { decision, nextState } = decideFastStartSizing(
      state,
      baseInputs({ equity: 5000, normalEbbLadder: 1, ebbMaxLossPerLot: 170, flintMaxLossPerContract: 190, peakProfit: 3000 }),
    )
    expect(decision.triggeredToday).toBe(true)
    expect(decision.phase).toBe(2) // sized under Phase 2 THIS SAME call, not starting tomorrow
    expect(nextState.phase).toBe(2)
  })

  it('an account below deposit stays in Phase 1 at 2x (cushion insufficient for the trigger)', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(4242)
    const { decision, nextState } = decideFastStartSizing(state, baseInputs({ equity: 3000, peakProfit: 0 }))
    expect(decision.phase).toBe(1)
    expect(nextState.phase).toBe(1)
  })

  it('trigger evaluated on a FLINT-only candidate day too (EBB not a candidate that day)', () => {
    process.env.FLAME_FAST_START = 'on'
    const state = seedFastStartState(2000)
    // ebb not candidate -> combined_ml_ladder = flint_ml alone = 190. trigger = 8*190=1520. cushion=equity-2000.
    const { decision } = decideFastStartSizing(
      state,
      baseInputs({ ebbCandidateDay: false, flintCandidateDay: true, flintMaxLossPerContract: 190, equity: 3600 }),
    )
    expect(decision.triggerLevel).toBe(8 * 190)
    expect(decision.triggeredToday).toBe(true)
  })
})

describe('Phase 2 sizing (G / grandfather, on)', () => {
  const phase2State: FastStartAccountState = { phase: 2, deposit: 4242 }

  it('floor = deposit + K x peak_profit, only ratchets up (derived directly from monotonic peak_profit)', () => {
    process.env.FLAME_FAST_START = 'on'
    const { decision } = decideFastStartSizing(phase2State, baseInputs({ peakProfit: 4000, equity: 8000 }))
    expect(decision.floor).toBeCloseTo(4242 + 0.25 * 4000, 2)
  })

  it('equity <= floor -> 0 EBB contracts (budget exhausted, minimum layer also fails if it would breach deposit)', () => {
    process.env.FLAME_FAST_START = 'on'
    // floor = 4242 + 0.25*8000 = 6242; equity = 6000 <= floor -> budget negative.
    // but the MINIMUM layer is gated on deposit, not floor, so it may still fire if cushion (equity-deposit) covers it.
    const { decision } = decideFastStartSizing(
      phase2State,
      baseInputs({ peakProfit: 8000, equity: 6000, normalEbbLadder: 5, ebbMaxLossPerLot: 170 }),
    )
    // cushion = 6000-4242 = 1758 >= 170 -> minimum layer of 1 still fires (proven-safe by construction),
    // but the EXTRA layer (budget_K = equity-floor = -242) must be 0.
    expect(decision.ebbContracts).toBe(1)
    expect(decision.budget).toBeLessThan(0)
  })

  it('equity below deposit itself -> minimum layer also fails closed (0 contracts, never breaches deposit further)', () => {
    process.env.FLAME_FAST_START = 'on'
    const { decision } = decideFastStartSizing(
      phase2State,
      baseInputs({ peakProfit: 0, equity: 4000, ebbMaxLossPerLot: 170, flintMaxLossPerContract: 190 }),
    )
    expect(decision.ebbContracts).toBe(0)
    expect(decision.flintContracts).toBe(0)
  })

  it('never sizes EBB above the normal (un-multiplied) ladder in Phase 2', () => {
    process.env.FLAME_FAST_START = 'on'
    const { decision } = decideFastStartSizing(
      phase2State,
      baseInputs({ peakProfit: 100000, equity: 150000, normalEbbLadder: 7, ebbMaxLossPerLot: 170 }),
    )
    expect(decision.ebbContracts).toBeLessThanOrEqual(7)
  })

  it('FLINT never gets an extra layer beyond its 1-contract minimum', () => {
    process.env.FLAME_FAST_START = 'on'
    const { decision } = decideFastStartSizing(
      phase2State,
      baseInputs({ peakProfit: 100000, equity: 150000, flintMaxLossPerContract: 190 }),
    )
    expect(decision.flintContracts).toBeLessThanOrEqual(1)
  })

  it('missing EBB max-loss data in Phase 2 -> 0 EBB, logged', () => {
    process.env.FLAME_FAST_START = 'on'
    const { decision } = decideFastStartSizing(
      phase2State,
      baseInputs({ peakProfit: 5000, equity: 10000, ebbMaxLossPerLot: null }),
    )
    expect(decision.ebbContracts).toBe(0)
    expect(decision.reason).toContain('ebb max-loss unreadable')
  })

  it('missing FLINT max-loss data in Phase 2 -> 0 FLINT, logged', () => {
    process.env.FLAME_FAST_START = 'on'
    const { decision } = decideFastStartSizing(
      phase2State,
      baseInputs({ peakProfit: 5000, equity: 10000, flintMaxLossPerContract: null }),
    )
    expect(decision.flintContracts).toBe(0)
    expect(decision.reason).toContain('flint max-loss unreadable')
  })

  it('phase never reverts to 1 once in Phase 2, even on a bad day', () => {
    process.env.FLAME_FAST_START = 'on'
    const { nextState } = decideFastStartSizing(
      phase2State,
      baseInputs({ peakProfit: 0, equity: 100, normalEbbLadder: 0 }),
    )
    expect(nextState.phase).toBe(2)
  })

  it('not a candidate day -> 0 for that leg regardless of budget', () => {
    process.env.FLAME_FAST_START = 'on'
    const { decision } = decideFastStartSizing(
      phase2State,
      baseInputs({ peakProfit: 5000, equity: 10000, ebbCandidateDay: false, flintCandidateDay: false }),
    )
    expect(decision.ebbContracts).toBe(0)
    expect(decision.flintContracts).toBe(0)
  })
})

describe('new account with no history', () => {
  it('seeds phase 1 at the given deposit', () => {
    const s = seedFastStartState(7500)
    expect(s).toEqual({ phase: 1, deposit: 7500 })
  })
})

describe('evaluateFastStartTrigger — standalone, shared by intraday (skipped) and EOD (authoritative)', () => {
  it('fires when cushion clears N x combined_ml_ladder', () => {
    // ladder=2, ebb_ml=170 -> combined=340 (ebb candidate, flint not). trigger=8*340=2720.
    const r = evaluateFastStartTrigger(2720, 2, true, 170, false, null)
    expect(r.triggered).toBe(true)
    expect(r.triggerLevel).toBe(2720)
  })
  it('does not fire one dollar short', () => {
    const r = evaluateFastStartTrigger(2719.99, 2, true, 170, false, null)
    expect(r.triggered).toBe(false)
  })
  it('includes FLINT only when it is a candidate today', () => {
    const withFlint = evaluateFastStartTrigger(100000, 2, true, 170, true, 190)
    const withoutFlint = evaluateFastStartTrigger(100000, 2, true, 170, false, 190)
    expect(withFlint.combinedMlLadder).toBe(2 * 170 + 190)
    expect(withoutFlint.combinedMlLadder).toBe(2 * 170)
  })
  it('never fires on a day neither leg is a candidate', () => {
    const r = evaluateFastStartTrigger(1_000_000, 5, false, null, false, null)
    expect(r.triggered).toBe(false)
    expect(r.combinedMlLadder).toBe(0)
  })
})

describe('decideFastStartSizing opts.skipTriggerCheck — the EOD-only phase gate', () => {
  it('intraday (skipTriggerCheck=true): a cushion that WOULD trigger does NOT advance the phase', () => {
    process.env.FLAME_FAST_START = 'on'
    const state: FastStartAccountState = { phase: 1, deposit: 2000 }
    // cushion=100000 trivially clears any trigger threshold.
    const { decision, nextState } = decideFastStartSizing(
      state,
      baseInputs({ equity: 102000, normalEbbLadder: 1, ebbMaxLossPerLot: 170, flintMaxLossPerContract: 190 }),
      { skipTriggerCheck: true },
    )
    expect(decision.phase).toBe(1)
    expect(decision.triggeredToday).toBe(false)
    expect(nextState.phase).toBe(1)
  })

  it('intraday (skipTriggerCheck=true) still sizes Phase 1 normally — only the transition is suppressed', () => {
    process.env.FLAME_FAST_START = 'on'
    const state: FastStartAccountState = { phase: 1, deposit: 4242 }
    const { decision } = decideFastStartSizing(
      state,
      baseInputs({ equity: 4242, normalEbbLadder: 2, ebbMaxLossPerLot: 170 }),
      { skipTriggerCheck: true },
    )
    expect(decision.ebbContracts).toBe(4) // same as the non-opts Phase-1 test above
  })

  it('default (no opts / opts omitted) behaves exactly as before — the parity test relies on this', () => {
    process.env.FLAME_FAST_START = 'on'
    const state: FastStartAccountState = { phase: 1, deposit: 2000 }
    const inputs = baseInputs({ equity: 102000, normalEbbLadder: 1, ebbMaxLossPerLot: 170, flintMaxLossPerContract: 190 })
    const withOpts = decideFastStartSizing(state, inputs, {})
    const withoutOpts = decideFastStartSizing(state, inputs)
    expect(withOpts.decision).toEqual(withoutOpts.decision)
    expect(withoutOpts.decision.triggeredToday).toBe(true) // sanity: this scenario DOES trigger when not skipped
  })
})

describe('sizeFlintGivenEbbOutcome — the ordering-gap helper (FLINT runs before EBB in the live scanner)', () => {
  it('phase 1: FLINT gets the budget EBB left behind, using EBB\'s REAL committed contracts', () => {
    // deposit=4242, X budget=848.4. EBB already committed 4 lots @ $170 = $680. remaining=$168.4 >= flint_ml(150) -> 1.
    const { flintContracts } = sizeFlintGivenEbbOutcome(1, 4242, 4242 + 300, 300, 4, 170, true, 150)
    expect(flintContracts).toBe(1)
  })

  it('phase 1: EBB already used the whole budget -> FLINT gets 0', () => {
    const { flintContracts } = sizeFlintGivenEbbOutcome(1, 4242, 4242 + 300, 300, 5, 170, true, 190)
    expect(flintContracts).toBe(0)
  })

  it('phase 1: FLINT still needs its OWN standing cushion check even if budget remains', () => {
    // cushion=equity-deposit=0 here -> flint fails its own standing rule regardless of remaining budget.
    const { flintContracts } = sizeFlintGivenEbbOutcome(1, 4242, 4242, 0, 0, null, true, 150)
    expect(flintContracts).toBe(0)
  })

  it('phase 2: ebbMin inferred from ebbContractsToday >= 1; flint gated sequentially after it', () => {
    // cushion=equity-deposit=1000. EBB committed >=1 lot @ $170 -> remaining_deposit_cushion=830 >= flint_ml(190) -> 1.
    const { flintContracts } = sizeFlintGivenEbbOutcome(2, 4242, 5242, 1000, 3, 170, true, 190)
    expect(flintContracts).toBe(1)
  })

  it('phase 2: ebbContractsToday=0 -> ebbMin=0, flint gated only by its own cushion', () => {
    const { flintContracts } = sizeFlintGivenEbbOutcome(2, 4242, 4242 + 100, 5000, 0, null, true, 90)
    expect(flintContracts).toBe(1) // cushion=100 >= flint_ml(90)
  })

  it('not a flint candidate day -> 0 regardless of phase or budget', () => {
    const { flintContracts } = sizeFlintGivenEbbOutcome(1, 4242, 10000, 5000, 0, null, false, 150)
    expect(flintContracts).toBe(0)
  })

  it('missing flint max-loss -> 0, never guesses', () => {
    const { flintContracts } = sizeFlintGivenEbbOutcome(2, 4242, 10000, 5000, 1, 170, true, null)
    expect(flintContracts).toBe(0)
  })
})
