import { describe, it, expect } from 'vitest'
import {
  occSymbol,
  condorOpenLegs,
  condorCloseLegs,
  spreadOpenLegs,
  spreadCloseLegs,
  sizeContracts,
  canOpenForCustomer,
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

  it('fails to zero on unknown buying power', () => {
    const r = sizeContracts({ ...base, buyingPowerCents: null, maxDeploymentCents: 1_000_00 })
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
