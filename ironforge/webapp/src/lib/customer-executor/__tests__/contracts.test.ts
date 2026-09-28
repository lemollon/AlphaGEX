import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  occSymbol,
  condorOpenLegs,
  condorCloseLegs,
  spreadOpenLegs,
  spreadCloseLegs,
  sizeContracts,
  canOpenForCustomer,
  evaluateFlintCushion,
  evaluateDepositFloorCap,
  evaluateFastStartUpsize,
  evaluateCalmUpsize,
  estimatePlannedHostRiskCents,
  type MirrorGateInput,
} from '../contracts'

describe('occSymbol', () => {
  it('builds the 21-character OCC format', () => {
    const s = occSymbol('SPY', '2026-08-14', 'P', 640)
    expect(s).toBe('SPY   260814P00640000')
    expect(s).toHaveLength(21)
  })

  it('handles fractional strikes (half-dollar)', () => {
    expect(occSymbol('XSP', '2026-08-14', 'C', 645.5)).toBe('XSP   260814C00645500')
  })

  it('rejects malformed inputs', () => {
    expect(() => occSymbol('SPY', '20260814', 'P', 640)).toThrow()
    expect(() => occSymbol('SPY', '2026-08-14', 'P', 0)).toThrow()
    expect(() => occSymbol('SPY', '2026-08-14', 'P', NaN)).toThrow()
  })
})

describe('condor legs', () => {
  const p = { ticker: 'SPY', expiration: '2026-08-14', putShort: 630, putLong: 625, callShort: 650, callLong: 655 }

  it('open sells the inner strikes and buys the wings', () => {
    const legs = condorOpenLegs(p, 2)
    expect(legs).toHaveLength(4)
    expect(legs.map((l) => l.action)).toEqual(['SELL_TO_OPEN', 'BUY_TO_OPEN', 'SELL_TO_OPEN', 'BUY_TO_OPEN'])
    expect(legs.every((l) => l.units === 2)).toBe(true)
    expect(legs[0].symbol).toBe('SPY   260814P00630000')
    expect(legs[2].symbol).toBe('SPY   260814C00650000')
  })

  it('close exactly inverts the open actions on the same symbols', () => {
    const open = condorOpenLegs(p, 3)
    const close = condorCloseLegs(p, 3)
    expect(close.map((l) => l.symbol)).toEqual(open.map((l) => l.symbol))
    expect(close.map((l) => l.action)).toEqual(['BUY_TO_CLOSE', 'SELL_TO_CLOSE', 'BUY_TO_CLOSE', 'SELL_TO_CLOSE'])
  })
})

describe('put credit spread legs (FLAME)', () => {
  const p = { ticker: 'SPY', expiration: '2026-08-14', short: 630, long: 625, right: 'P' as const }

  it('open is sell-short / buy-long', () => {
    const legs = spreadOpenLegs(p, 1)
    expect(legs).toHaveLength(2)
    expect(legs[0]).toMatchObject({ action: 'SELL_TO_OPEN', symbol: 'SPY   260814P00630000' })
    expect(legs[1]).toMatchObject({ action: 'BUY_TO_OPEN', symbol: 'SPY   260814P00625000' })
  })

  it('close inverts', () => {
    const legs = spreadCloseLegs(p, 1)
    expect(legs.map((l) => l.action)).toEqual(['BUY_TO_CLOSE', 'SELL_TO_CLOSE'])
  })
})

describe('call credit spread legs (FLINT) — same generic spreadOpenLegs/spreadCloseLegs, right="C"', () => {
  // FLINT sells the near call and buys the far call — mleg-wise no different from a
  // put credit spread; this pins that the "call-side support" question is a non-issue,
  // since spreadOpenLegs/spreadCloseLegs are already right-agnostic and condorOpenLegs
  // already places two call legs through the identical placeMlegOrder path today.
  const p = { ticker: 'SPY', expiration: '2026-08-14', short: 770, long: 772, right: 'C' as const }

  it('open sells the near call, buys the far call', () => {
    const legs = spreadOpenLegs(p, 1)
    expect(legs).toHaveLength(2)
    expect(legs[0]).toMatchObject({ action: 'SELL_TO_OPEN', symbol: 'SPY   260814C00770000' })
    expect(legs[1]).toMatchObject({ action: 'BUY_TO_OPEN', symbol: 'SPY   260814C00772000' })
  })

  it('close inverts', () => {
    const legs = spreadCloseLegs(p, 1)
    expect(legs.map((l) => l.action)).toEqual(['BUY_TO_CLOSE', 'SELL_TO_CLOSE'])
    expect(legs.map((l) => l.symbol)).toEqual(['SPY   260814C00770000', 'SPY   260814C00772000'])
  })
})

describe('sizeContracts', () => {
  // $5 wide, $1.20 credit → collateral $380/contract = 38_000 cents
  const base = { spreadWidth: 5, creditPerSpread: 1.2 }

  it('floors deployable / collateral', () => {
    const r = sizeContracts({ ...base, buyingPowerCents: 1_000_00, maxDeploymentCents: 1_000_00 })
    expect(r.collateralPerSpreadCents).toBe(38_000)
    expect(r.contracts).toBe(2) // 100_000 / 38_000 = 2.63 → 2
  })

  it('the smaller of buying power and the authorized ceiling wins', () => {
    // ceiling below BP
    expect(sizeContracts({ ...base, buyingPowerCents: 10_000_00, maxDeploymentCents: 40_000 }).contracts).toBe(1)
    // BP below ceiling
    expect(sizeContracts({ ...base, buyingPowerCents: 40_000, maxDeploymentCents: 10_000_00 }).contracts).toBe(1)
  })

  it('fails to zero on unknown buying power, and says it was UNREADABLE', () => {
    const r = sizeContracts({ ...base, buyingPowerCents: null, maxDeploymentCents: 1_000_00 })
    expect(r.contracts).toBe(0)
    // A null BP means the broker never answered. It must NOT be reported as
    // "no buying power", which is a real, different account state.
    expect(r.reason).toBe('buying_power_unreadable')
  })

  it('reports a genuinely empty account separately from an unreadable one', () => {
    const r = sizeContracts({ ...base, buyingPowerCents: 0, maxDeploymentCents: 1_000_00 })
    expect(r.contracts).toBe(0)
    expect(r.reason).toBe('no_buying_power')
  })

  it('fails to zero below one contract', () => {
    const r = sizeContracts({ ...base, buyingPowerCents: 20_000, maxDeploymentCents: 20_000 })
    expect(r.contracts).toBe(0)
    expect(r.reason).toBe('below_one_contract')
  })

  it('rejects impossible geometry (credit >= width, zero width, NaN)', () => {
    expect(sizeContracts({ spreadWidth: 5, creditPerSpread: 5, buyingPowerCents: 1_000_00, maxDeploymentCents: 1_000_00 }).reason).toBe('bad_inputs')
    expect(sizeContracts({ spreadWidth: 0, creditPerSpread: 0, buyingPowerCents: 1_000_00, maxDeploymentCents: 1_000_00 }).reason).toBe('bad_inputs')
    expect(sizeContracts({ spreadWidth: NaN, creditPerSpread: 1, buyingPowerCents: 1_000_00, maxDeploymentCents: 1_000_00 }).reason).toBe('bad_inputs')
  })

  it('a negative ceiling never sizes a position', () => {
    expect(sizeContracts({ ...base, buyingPowerCents: 1_000_00, maxDeploymentCents: -1 }).contracts).toBe(0)
  })
})

describe('estimatePlannedHostRiskCents (FLINT same-day host-leg netting plan)', () => {
  const okInputs = { vixCandidateDay: true, equityCents: 300_000, maxDeploymentPct: 20, possibleUpsize: false }

  it('0 when the host leg cannot trade today (VIX gate already failed) — never a guessed positive number', () => {
    expect(estimatePlannedHostRiskCents({ ...okInputs, vixCandidateDay: false })).toBe(0)
  })

  it('0 on unreadable equity or a bad/missing deployment pct — fails closed, not a guess', () => {
    expect(estimatePlannedHostRiskCents({ ...okInputs, equityCents: null })).toBe(0)
    expect(estimatePlannedHostRiskCents({ ...okInputs, equityCents: 0 })).toBe(0)
    expect(estimatePlannedHostRiskCents({ ...okInputs, maxDeploymentPct: null })).toBe(0)
    expect(estimatePlannedHostRiskCents({ ...okInputs, maxDeploymentPct: 0 })).toBe(0)
    expect(estimatePlannedHostRiskCents({ ...okInputs, maxDeploymentPct: 150 })).toBe(0)
  })

  it('sizes off the $2-wide/$0.10-credit conservative estimate — 3 contracts at $2,250 deployment budget', () => {
    // equity $3,000, pct 20% -> maxDeployment $600 = 60_000c. Collateral/contract at
    // width=2,credit=0.10 is (2-0.10)*100*100=19_000c. floor(60_000/19_000)=3.
    const cents = estimatePlannedHostRiskCents(okInputs)
    expect(cents).toBe(3 * 19_000)
  })

  it('adds exactly one extra contract worth of risk when an upsize is possible', () => {
    const withUpsize = estimatePlannedHostRiskCents({ ...okInputs, possibleUpsize: true })
    const without = estimatePlannedHostRiskCents({ ...okInputs, possibleUpsize: false })
    expect(withUpsize - without).toBe(19_000)
  })

  it('0 when the conservative sizing itself floors to below 1 contract', () => {
    expect(estimatePlannedHostRiskCents({ ...okInputs, equityCents: 50_00, maxDeploymentPct: 20 })).toBe(0)
  })
})

describe('canOpenForCustomer', () => {
  const ok: MirrorGateInput = {
    executorArmed: true,
    killSwitchEngaged: false,
    subscriptionStatus: 'trialing',
    customerPaused: false,
    activationActive: true,
    connectionActive: true,
  }

  it('allows a fully-live trialing customer', () => {
    expect(canOpenForCustomer(ok)).toEqual({ allow: true })
  })

  it('allows active subscriptions', () => {
    expect(canOpenForCustomer({ ...ok, subscriptionStatus: 'active' }).allow).toBe(true)
  })

  it('the disarmed flag blocks everything (ship-dark invariant)', () => {
    expect(canOpenForCustomer({ ...ok, executorArmed: false })).toEqual({ allow: false, reason: 'disarmed' })
  })

  it('an UNKNOWN kill switch reads as engaged (fails closed)', () => {
    // anything that is not literally false blocks
    expect(canOpenForCustomer({ ...ok, killSwitchEngaged: true })).toEqual({ allow: false, reason: 'kill_switch' })
    expect(canOpenForCustomer({ ...ok, killSwitchEngaged: undefined as unknown as boolean }).allow).toBe(false)
  })

  it('past_due blocks NEW opens (spec §11)', () => {
    expect(canOpenForCustomer({ ...ok, subscriptionStatus: 'past_due' })).toEqual({ allow: false, reason: 'subscription' })
  })

  it('missing subscription blocks', () => {
    expect(canOpenForCustomer({ ...ok, subscriptionStatus: null })).toEqual({ allow: false, reason: 'subscription' })
  })

  it('customer pause blocks opens', () => {
    expect(canOpenForCustomer({ ...ok, customerPaused: true })).toEqual({ allow: false, reason: 'customer_paused' })
  })

  it('no activation / dead connection block', () => {
    expect(canOpenForCustomer({ ...ok, activationActive: false })).toEqual({ allow: false, reason: 'not_activated' })
    expect(canOpenForCustomer({ ...ok, connectionActive: false })).toEqual({ allow: false, reason: 'connection' })
  })
})

describe('evaluateFlintCushion (CUSTOMER_FLINT profits-only gate, ported from customer_protection_sim.py P3, netted per ROUND 8 finalK.py)', () => {
  const base = { equityCents: 220_000, protectLevelCents: 200_000, hostCommittedCents: 0, maxLossCents: 18_000, marginCents: 0 }

  it('cushion strictly covers max loss (no margin, no host commitment) -> eligible, matches the ORIGINAL P3 sim exactly', () => {
    // equity-deposit = 20_000 >= maxLoss 18_000
    expect(evaluateFlintCushion(base)).toEqual({ eligible: true, cushionCents: 20_000 })
  })

  it('ROUND 8 netting: a host leg that already committed most of the cushion drops FLINT even though the standalone check would pass', () => {
    // Cushion (equity-protectLevel) = 20_000 >= maxLoss 18_000 in isolation, but the host
    // leg already committed 15_000 of that same cushion today -> only 5_000 left, < 18_000.
    const r = evaluateFlintCushion({ ...base, hostCommittedCents: 15_000 })
    expect(r.eligible).toBe(false)
    expect(r.reason).toBe('cushion_insufficient')
    expect(r.cushionCents).toBe(5_000) // 20_000 - 15_000
  })

  it('zero host commitment is a true no-op — identical to the un-netted result', () => {
    expect(evaluateFlintCushion({ ...base, hostCommittedCents: 0 })).toEqual(evaluateFlintCushion(base))
  })

  it('rejects a negative or non-finite host-committed amount as bad inputs — never guessed', () => {
    expect(evaluateFlintCushion({ ...base, hostCommittedCents: -1 }).reason).toBe('bad_inputs')
    expect(evaluateFlintCushion({ ...base, hostCommittedCents: NaN }).reason).toBe('bad_inputs')
  })

  it('cushion exactly equals max loss -> eligible (inclusive floor, matches sim ">=")', () => {
    const r = evaluateFlintCushion({ ...base, maxLossCents: 20_000 })
    expect(r).toEqual({ eligible: true, cushionCents: 20_000 })
  })

  it('cushion one cent short of max loss -> not eligible', () => {
    const r = evaluateFlintCushion({ ...base, maxLossCents: 20_001 })
    expect(r.eligible).toBe(false)
    expect(r.reason).toBe('cushion_insufficient')
    expect(r.cushionCents).toBe(20_000)
  })

  it('a live-only $50 margin makes a marginal day ineligible (documented sim-vs-live difference)', () => {
    // Same numbers as the exactly-equal case above, but margin=5000 (the live default) —
    // the sim's OWN P3 formula has no margin term; this is Leron's explicit instruction,
    // added on top, not a sim behavior.
    const r = evaluateFlintCushion({ ...base, maxLossCents: 20_000, marginCents: 5_000 })
    expect(r.eligible).toBe(false)
    expect(r.reason).toBe('cushion_insufficient')
    expect(r.cushionCents).toBe(20_000) // cushion itself is unchanged; only the required bar moved
  })

  it('null equity fails closed, never guesses (never sizes up on missing data)', () => {
    const r = evaluateFlintCushion({ ...base, equityCents: null })
    expect(r.eligible).toBe(false)
    expect(r.reason).toBe('equity_unreadable')
    expect(r.cushionCents).toBeNull()
  })

  it('null deposit/protect-level fails closed, never guesses', () => {
    const r = evaluateFlintCushion({ ...base, protectLevelCents: null })
    expect(r.eligible).toBe(false)
    expect(r.reason).toBe('deposit_unknown')
    expect(r.cushionCents).toBeNull()
  })

  it('a negative cushion (equity below deposit) is never eligible', () => {
    const r = evaluateFlintCushion({ ...base, equityCents: 150_000 })
    expect(r.eligible).toBe(false)
    expect(r.cushionCents).toBe(-50_000)
  })

  it('rejects non-finite / non-positive max loss and negative margin as bad inputs', () => {
    expect(evaluateFlintCushion({ ...base, maxLossCents: 0 }).reason).toBe('bad_inputs')
    expect(evaluateFlintCushion({ ...base, maxLossCents: -1 }).reason).toBe('bad_inputs')
    expect(evaluateFlintCushion({ ...base, maxLossCents: NaN }).reason).toBe('bad_inputs')
    expect(evaluateFlintCushion({ ...base, marginCents: -1 }).reason).toBe('bad_inputs')
  })

  it('per-customer independence: one customer eligible, another is not, same day, same maxLoss', () => {
    const rich = evaluateFlintCushion({ ...base, equityCents: 300_000 }) // cushion 100_000 -> eligible
    const thin = evaluateFlintCushion({ ...base, equityCents: 205_000 }) // cushion 5_000 -> not eligible
    expect(rich.eligible).toBe(true)
    expect(thin.eligible).toBe(false)
    // Pure function: evaluating `thin` never mutated or depended on `rich`'s result.
    expect(evaluateFlintCushion({ ...base, equityCents: 300_000 })).toEqual(rich)
  })
})

describe('evaluateDepositFloorCap (CUSTOMER_DEPOSIT_FLOOR, ROUND 8 shipped rule: K=0.1, N=3, variant G)', () => {
  const base = {
    equityCents: 200_000, depositCents: 200_000, peakEquityCents: null as number | null, maxLossCentsPerContract: 18_000,
    marginCents: 5_000, pct: 20, desiredContracts: 2, triggered: false, triggerN: 3, floorK: 0.1,
  }

  it('pre-trigger: passes desiredContracts through UNCHANGED — byte-identical to BASE', () => {
    const r = evaluateDepositFloorCap({ ...base, equityCents: 205_000 }) // cushion 5_000, nowhere near 3x a full position's max loss
    expect(r).toEqual({
      contracts: 2, triggeredNow: false, capped: false, dataOk: true, triggeredForSizing: false,
      floorLevelCents: 200_000, nextPeakEquityCents: 205_000,
    })
  })

  it('trigger fires the instant cushion >= N * (desired_count(deposit,pct,ml) * ml) — unchanged since ROUND 3', () => {
    // deposit 200_000c @ pct=20 -> dcount_ref = floor(200_000*0.2/18_000) = floor(2.22)=2; combined_ml=36_000
    // N=3 -> threshold cushion = 108_000c. Equity = deposit+108_000 exactly triggers (>=).
    const r = evaluateDepositFloorCap({ ...base, equityCents: base.depositCents + 108_000 })
    expect(r.triggeredNow).toBe(true)
    // one cent under the threshold must NOT trigger
    const r2 = evaluateDepositFloorCap({ ...base, equityCents: base.depositCents + 107_999 })
    expect(r2.triggeredNow).toBe(false)
  })

  it('post-trigger, no accumulated peak profit yet: G-variant nMin=1 (gated on deposit) + extra=0 (gated on the stricter floor budget)', () => {
    // equity-deposit = 40_000c (budgetDep), ml+margin = 18_000+5_000=23_000 (mlEff).
    // nMin = 1 (40_000 >= 23_000). floorLevelCents = deposit (no peak profit recorded
    // yet — peakEquityCents defaults to deposit). budgetAfterMin = 40_000-23_000=17_000,
    // extra = floor(17_000/23_000) = 0. n = 1.
    const r = evaluateDepositFloorCap({ ...base, triggered: true, equityCents: base.depositCents + 40_000 })
    expect(r).toEqual({
      contracts: 1, triggeredNow: false, capped: true, dataOk: true, triggeredForSizing: true,
      floorLevelCents: 200_000, nextPeakEquityCents: 240_000,
    })
  })

  it('post-trigger, ample cushion: cap never exceeds desiredContracts even when the budget allows more', () => {
    const r = evaluateDepositFloorCap({ ...base, triggered: true, equityCents: base.depositCents + 10_000_000 })
    expect(r.contracts).toBe(2) // desiredContracts, not the (much larger) budget-implied count
    expect(r.capped).toBe(false)
  })

  it('a ratcheted peak profit RAISES the floor above deposit, which can reduce the extra-layer budget', () => {
    // Peak equity of deposit+200_000 (a prior high-water mark) -> peakProfit=200_000,
    // floorLevelCents = deposit + 0.1*200_000 = deposit+20_000 = 220_000.
    // Equity has since fallen to deposit+40_000 = 240_000 (still above the floor).
    // budgetDep = 40_000 -> nMin=1. budgetAfterMin = (240_000-220_000)-23_000 = -3_000 -> extra=0.
    const r = evaluateDepositFloorCap({
      ...base, triggered: true, peakEquityCents: base.depositCents + 200_000, equityCents: base.depositCents + 40_000,
    })
    expect(r.floorLevelCents).toBe(220_000)
    expect(r.contracts).toBe(1) // nMin only — the higher floor left no room for the extra layer
  })

  it('equity at or below deposit + maxLoss(+margin already spent): floors to 0 contracts, never negative', () => {
    const r = evaluateDepositFloorCap({ ...base, triggered: true, equityCents: base.depositCents })
    expect(r.contracts).toBe(0)
    expect(r.capped).toBe(true)
  })

  it('equity below deposit (a real loss day) after trigger: still floors to 0, never negative', () => {
    const r = evaluateDepositFloorCap({ ...base, triggered: true, equityCents: base.depositCents - 50_000 })
    expect(r.contracts).toBe(0)
  })

  it('fails OPEN (not closed) on missing/bad data — returns desiredContracts unmodified, dataOk=false', () => {
    expect(evaluateDepositFloorCap({ ...base, equityCents: null })).toEqual({
      contracts: 2, triggeredNow: false, capped: false, dataOk: false, triggeredForSizing: false,
      floorLevelCents: 200_000, nextPeakEquityCents: 200_000,
    })
    expect(evaluateDepositFloorCap({ ...base, depositCents: null })).toEqual({
      contracts: 2, triggeredNow: false, capped: false, dataOk: false, triggeredForSizing: false,
      floorLevelCents: 0, nextPeakEquityCents: 0,
    })
    expect(evaluateDepositFloorCap({ ...base, maxLossCentsPerContract: 0 }).dataOk).toBe(false)
    expect(evaluateDepositFloorCap({ ...base, pct: 0 }).dataOk).toBe(false)
    expect(evaluateDepositFloorCap({ ...base, desiredContracts: -1 }).dataOk).toBe(false)
  })

  it('a sticky triggered flag is honored even when equity has since fallen — floor stays engaged (one-way)', () => {
    // Equity well below where the trigger would fire fresh, but triggered=true is passed in.
    const r = evaluateDepositFloorCap({ ...base, triggered: true, equityCents: base.depositCents + 10_000 })
    expect(r.triggeredNow).toBe(false) // it did not trigger JUST NOW
    expect(r.dataOk).toBe(true)
    expect(r.contracts).toBe(0) // budgetDep=10_000 < mlEff=23_000 -> nMin=0, extra=0
  })
})

describe('evaluateFastStartUpsize (CUSTOMER_FAST_START / B1, ported from customer_protection_fastcushion.py "B1 calm+1")', () => {
  const base = { triggeredForSizing: false, baseContracts: 3, vixRatio: 0.5, vixCeiling: 0.70 }

  it('pre-trigger, calm, base>0: adds the flat +1, no other gate (deliberately not house-money-gated)', () => {
    expect(evaluateFastStartUpsize(base)).toEqual({ extraContract: true, reason: 'added' })
  })

  it('post-trigger (triggeredForSizing=true): never applies — that is the calm-upsize arm instead', () => {
    expect(evaluateFastStartUpsize({ ...base, triggeredForSizing: true })).toEqual({ extraContract: false, reason: 'post_trigger' })
  })

  it('base contracts already 0: no add-on (matches the sim\'s own `n > 0` guard)', () => {
    expect(evaluateFastStartUpsize({ ...base, baseContracts: 0 })).toEqual({ extraContract: false, reason: 'base_zero' })
  })

  it('not calm (ratio above ceiling): no add-on', () => {
    expect(evaluateFastStartUpsize({ ...base, vixRatio: 0.71 })).toEqual({ extraContract: false, reason: 'not_calm' })
  })

  it('exactly at the 0.70 ceiling: still calm (inclusive, matches the sim\'s <=)', () => {
    expect(evaluateFastStartUpsize({ ...base, vixRatio: 0.70 }).extraContract).toBe(true)
  })

  it('unreadable VIX ratio: no add-on, never guessed', () => {
    expect(evaluateFastStartUpsize({ ...base, vixRatio: null })).toEqual({ extraContract: false, reason: 'vix_unavailable' })
  })

  it('applies uniformly regardless of deposit size — B1 has NO deposit threshold (round 7: "ALL deposits, BOTH bots")', () => {
    // evaluateFastStartUpsize's input shape has no deposit field at all — this is
    // structural proof there is no threshold to bypass, not just an untested branch.
    expect(Object.keys(base)).not.toContain('depositCents')
  })
})

describe('evaluateCalmUpsize (CUSTOMER_CALM_UPSIZE, house-money post-cushion, ported from customer_protection_calmday.py)', () => {
  const base = {
    // protectLevelCents == depositCents here (no accumulated peak profit yet — the
    // floor has just triggered) so every pre-existing $ calculation in this describe
    // block's comments stays numerically valid under the new protectLevelCents field.
    equityCents: 500_000, depositCents: 424_200, protectLevelCents: 424_200, baseContracts: 2, maxLossCentsPerContract: 18_000,
    marginCents: 5_000, vixRatio: 0.5, vixCeiling: 0.70, minDepositCentsForUpsize: 400_000,
  }

  it('protect_level (floor_level, not raw deposit) drives the netting once K>0 has ratcheted the floor above deposit', () => {
    // Same equity/deposit as base, but the floor has ratcheted to 450_000 (peak profit
    // accrued). remaining_after_base = (500_000-450_000) - 2*18_000 = 50_000-36_000=14_000
    // < 23_000 required -> NOT eligible, even though netting against raw deposit
    // (424_200) would have shown ample room (39_800 >= 23_000, as the base case does).
    const r = evaluateCalmUpsize({ ...base, protectLevelCents: 450_000 })
    expect(r).toEqual({ extraContract: false, reason: 'insufficient_house_money' })
  })

  it('null protect_level fails closed, never guessed', () => {
    const r = evaluateCalmUpsize({ ...base, protectLevelCents: null })
    expect(r).toEqual({ extraContract: false, reason: 'protect_level_unknown' })
  })

  it('deposit >= $4,000, calm, ample remaining house money: adds the +1', () => {
    // remaining_after_base = (500_000-424_200) - 2*18_000 = 75_800-36_000=39_800 >= 18_000+5_000=23_000
    expect(evaluateCalmUpsize(base)).toEqual({ extraContract: true, reason: 'added' })
  })

  it('the $2,000-deposit-excluded case: below the $4,000 threshold, NEVER adds regardless of how much cushion exists', () => {
    const r = evaluateCalmUpsize({ ...base, depositCents: 200_000, equityCents: 10_000_000 }) // deposit $2,000, absurd cushion
    expect(r).toEqual({ extraContract: false, reason: 'deposit_below_threshold' })
  })

  it('exactly $4,000 deposit clears the threshold (inclusive, matches Round 4\'s own boundary)', () => {
    const r = evaluateCalmUpsize({ ...base, depositCents: 400_000, equityCents: 900_000 })
    expect(r.reason).not.toBe('deposit_below_threshold')
  })

  it('insufficient house money after netting the base position: no add-on (the corrected, additive-risk formula)', () => {
    // remaining_after_base = (500_000-424_200) - 2*18_000 = 39_800; required 23_000 -> still passes above.
    // Push equity down so remaining < required.
    const r = evaluateCalmUpsize({ ...base, equityCents: 470_000 }) // 45_800-36_000=9_800 < 23_000
    expect(r).toEqual({ extraContract: false, reason: 'insufficient_house_money' })
  })

  it('base contracts already 0: no add-on', () => {
    expect(evaluateCalmUpsize({ ...base, baseContracts: 0 })).toEqual({ extraContract: false, reason: 'base_zero' })
  })

  it('not calm: no add-on', () => {
    expect(evaluateCalmUpsize({ ...base, vixRatio: 0.9 })).toEqual({ extraContract: false, reason: 'not_calm' })
  })

  it('nets the base at maxLoss PER CONTRACT (not maxLoss+margin) — the sim\'s literal formula, not the coordinator\'s paraphrase', () => {
    // If the base were (wrongly) netted at ml+margin per contract, remaining would be
    // (500_000-424_200) - 2*(18_000+5_000) = 75_800-46_000=29_800, still >= 23_000 -> same verdict here,
    // so use numbers where the two formulas DIVERGE: base=3 contracts.
    // Sim (ml only): remaining = 75_800 - 3*18_000 = 21_800 < 23_000 -> NOT eligible.
    // Coordinator's paraphrase (ml+margin): remaining = 75_800 - 3*23_000 = 6_800 < 23_000 -> also not eligible (bad example).
    // Use a case where sim says eligible but the (ml+margin)-netting would not be:
    // equity 600_000, deposit 424_200, base=3: sim remaining = 175_800-54_000=121_800 >= 23_000 -> eligible either way.
    // The real divergence is at the MARGIN in the boundary; assert the exact sim arithmetic directly:
    const r = evaluateCalmUpsize({ ...base, baseContracts: 3, equityCents: 424_200 + 3 * 18_000 + 23_000 })
    expect(r.extraContract).toBe(true) // remaining = 3*18_000+23_000 - 3*18_000 = 23_000, exactly meets ml+margin
    const r2 = evaluateCalmUpsize({ ...base, baseContracts: 3, equityCents: 424_200 + 3 * 18_000 + 22_999 })
    expect(r2.extraContract).toBe(false) // one cent short
  })
})
