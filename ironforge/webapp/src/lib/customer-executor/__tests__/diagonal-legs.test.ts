/**
 * The two diagonal leg kinds (ANVIL's single diagonal, HEARTH's double
 * diagonal) and their own sizing.
 *
 * Every other structure the customer mirror places stamps ONE expiration on
 * every leg. These are the first that cannot, so the thing most worth asserting
 * is that the SHORT leg carries the front date and the LONG leg the back one —
 * a swap there places a real order on the wrong contract and inverts the margin
 * treatment.
 */
import { describe, it, expect } from 'vitest'
import {
  diagonalOpenLegs,
  diagonalCloseLegs,
  doubleDiagonalOpenLegs,
  doubleDiagonalCloseLegs,
  sizeDiagonalContracts,
  sizeDoubleDiagonalContracts,
} from '../contracts'
import { resolveLegKind } from '../executor'

const FRONT = '2026-10-16'
const BACK = '2026-10-17'

describe('diagonalOpenLegs (ANVIL)', () => {
  it('sells the FRONT expiry and buys the BACK expiry', () => {
    const legs = diagonalOpenLegs(
      { ticker: 'IWM', frontExpiration: FRONT, backExpiration: BACK, short: 281, long: 282, right: 'C' },
      1,
    )
    expect(legs).toHaveLength(2)
    expect(legs[0].action).toBe('SELL_TO_OPEN')
    expect(legs[0].symbol).toContain('261016')
    expect(legs[0].symbol).toContain('C00281000')
    expect(legs[1].action).toBe('BUY_TO_OPEN')
    expect(legs[1].symbol).toContain('261017')
    expect(legs[1].symbol).toContain('C00282000')
  })

  it('reverses both actions on the close, keeping each leg on its own expiry', () => {
    const legs = diagonalCloseLegs(
      { ticker: 'IWM', frontExpiration: FRONT, backExpiration: BACK, short: 281, long: 282, right: 'C' },
      3,
    )
    expect(legs.map((l) => l.action)).toEqual(['BUY_TO_CLOSE', 'SELL_TO_CLOSE'])
    expect(legs[0].symbol).toContain('261016')
    expect(legs[1].symbol).toContain('261017')
    expect(legs.every((l) => l.units === 3)).toBe(true)
  })

  it('carries the contract count onto every leg', () => {
    const legs = diagonalOpenLegs(
      { ticker: 'IWM', frontExpiration: FRONT, backExpiration: BACK, short: 281, long: 282, right: 'C' },
      4,
    )
    expect(legs.every((l) => l.units === 4)).toBe(true)
  })
})

describe('doubleDiagonalOpenLegs (HEARTH)', () => {
  const p = {
    ticker: 'SPY',
    frontExpiration: FRONT,
    backExpiration: BACK,
    putShort: 760,
    putLong: 757,
    callShort: 772,
    callLong: 775,
  }

  it('sells the strangle in the front expiry and buys both wings in the back', () => {
    const legs = doubleDiagonalOpenLegs(p, 1)
    expect(legs).toHaveLength(4)
    const shorts = legs.filter((l) => l.action === 'SELL_TO_OPEN')
    const longs = legs.filter((l) => l.action === 'BUY_TO_OPEN')
    expect(shorts).toHaveLength(2)
    expect(longs).toHaveLength(2)
    // Both shorts on the near date, both longs on the far date.
    expect(shorts.every((l) => l.symbol.includes('261016'))).toBe(true)
    expect(longs.every((l) => l.symbol.includes('261017'))).toBe(true)
  })

  it('puts the long wings BEYOND each short, not inside', () => {
    const legs = doubleDiagonalOpenLegs(p, 1)
    const byStrike = (frag: string) => legs.find((l) => l.symbol.includes(frag))
    expect(byStrike('P00757000')?.action).toBe('BUY_TO_OPEN') // below the 760 short put
    expect(byStrike('P00760000')?.action).toBe('SELL_TO_OPEN')
    expect(byStrike('C00772000')?.action).toBe('SELL_TO_OPEN')
    expect(byStrike('C00775000')?.action).toBe('BUY_TO_OPEN') // above the 772 short call
  })

  it('reverses all four actions on the close', () => {
    const legs = doubleDiagonalCloseLegs(p, 2)
    expect(legs.filter((l) => l.action === 'BUY_TO_CLOSE')).toHaveLength(2)
    expect(legs.filter((l) => l.action === 'SELL_TO_CLOSE')).toHaveLength(2)
    expect(legs.every((l) => l.units === 2)).toBe(true)
  })
})

describe('front-before-back guard', () => {
  const reversed = { frontExpiration: BACK, backExpiration: FRONT }

  it('THROWS when the short leg expires after the long leg', () => {
    // Reversing them forfeits reduced spread margin: the broker margins the
    // short as naked, so a position sized as defined-risk is not.
    expect(() =>
      diagonalOpenLegs({ ticker: 'IWM', ...reversed, short: 281, long: 282, right: 'C' }, 1),
    ).toThrow(/expires AFTER/)
    expect(() =>
      doubleDiagonalOpenLegs(
        { ticker: 'SPY', ...reversed, putShort: 760, putLong: 757, callShort: 772, callLong: 775 },
        1,
      ),
    ).toThrow(/expires AFTER/)
  })

  it('throws on the close path too, so one side cannot be wired without the other', () => {
    expect(() =>
      diagonalCloseLegs({ ticker: 'IWM', ...reversed, short: 281, long: 282, right: 'C' }, 1),
    ).toThrow(/expires AFTER/)
  })

  it('throws when either expiration is missing rather than defaulting', () => {
    expect(() =>
      diagonalOpenLegs(
        { ticker: 'IWM', frontExpiration: FRONT, backExpiration: '', short: 281, long: 282, right: 'C' },
        1,
      ),
    ).toThrow(/needs both expirations/)
  })

  it('allows front === back (a vertical expressed through this builder is still defined-risk)', () => {
    expect(() =>
      diagonalOpenLegs(
        { ticker: 'IWM', frontExpiration: FRONT, backExpiration: FRONT, short: 281, long: 282, right: 'C' },
        1,
      ),
    ).not.toThrow()
  })
})

describe('sizeDiagonalContracts (ANVIL — a DEBIT structure)', () => {
  it('charges the debit, not width-minus-credit', () => {
    // $1.00 debit = $100/contract = 10_000c. $45_000 deployable -> 4 contracts.
    const r = sizeDiagonalContracts({
      buyingPowerCents: 45_000,
      maxDeploymentCents: 45_000,
      debitPerSpread: 1.0,
    })
    expect(r.collateralPerSpreadCents).toBe(10_000)
    expect(r.contracts).toBe(4)
    expect(r.reason).toBeUndefined()
  })

  it('takes the SMALLER of live buying power and the authorized ceiling', () => {
    const r = sizeDiagonalContracts({
      buyingPowerCents: 100_000,
      maxDeploymentCents: 25_000,
      debitPerSpread: 1.0,
    })
    expect(r.contracts).toBe(2)
  })

  it('distinguishes an unreadable broker from an account with no room', () => {
    expect(
      sizeDiagonalContracts({ buyingPowerCents: null, maxDeploymentCents: 50_000, debitPerSpread: 1 }).reason,
    ).toBe('buying_power_unreadable')
    expect(
      sizeDiagonalContracts({ buyingPowerCents: 0, maxDeploymentCents: 50_000, debitPerSpread: 1 }).reason,
    ).toBe('no_buying_power')
  })

  it('sizes to zero below one contract and on a non-positive debit', () => {
    expect(
      sizeDiagonalContracts({ buyingPowerCents: 5_000, maxDeploymentCents: 5_000, debitPerSpread: 1 }),
    ).toMatchObject({ contracts: 0, reason: 'below_one_contract' })
    expect(
      sizeDiagonalContracts({ buyingPowerCents: 50_000, maxDeploymentCents: 50_000, debitPerSpread: 0 }),
    ).toMatchObject({ contracts: 0, reason: 'bad_inputs' })
  })
})

describe('sizeDoubleDiagonalContracts (HEARTH)', () => {
  it('charges 2 x wing minus credit, i.e. BOTH sides', () => {
    // HEARTH's frozen spec: collat = 2 * W * 100 - credit. W=$3, credit=$1.00
    // -> (6 - 1) * 100 = $500/contract = 50_000c.
    const r = sizeDoubleDiagonalContracts({
      buyingPowerCents: 150_000,
      maxDeploymentCents: 150_000,
      wingWidth: 3,
      creditPerSpread: 1.0,
    })
    expect(r.collateralPerSpreadCents).toBe(50_000)
    expect(r.contracts).toBe(3)
  })

  it('does NOT charge only the wider side — that would double the tested position', () => {
    const r = sizeDoubleDiagonalContracts({
      buyingPowerCents: 150_000,
      maxDeploymentCents: 150_000,
      wingWidth: 3,
      creditPerSpread: 1.0,
    })
    // One-sided would be (3 - 1) * 100 = 20_000c -> 7 contracts.
    expect(r.collateralPerSpreadCents).not.toBe(20_000)
    expect(r.contracts).toBeLessThan(7)
  })

  it('rejects a credit at or above total width instead of clamping it', () => {
    expect(
      sizeDoubleDiagonalContracts({
        buyingPowerCents: 150_000,
        maxDeploymentCents: 150_000,
        wingWidth: 3,
        creditPerSpread: 6,
      }),
    ).toMatchObject({ contracts: 0, reason: 'bad_inputs' })
  })

  it('carries the same unreadable-vs-empty distinction', () => {
    expect(
      sizeDoubleDiagonalContracts({
        buyingPowerCents: null, maxDeploymentCents: 150_000, wingWidth: 3, creditPerSpread: 1,
      }).reason,
    ).toBe('buying_power_unreadable')
  })
})

describe('resolveLegKind never infers a diagonal', () => {
  it('still infers only condor or put_spread from strikes alone', () => {
    expect(resolveLegKind({ callShort: 772 })).toBe('condor')
    expect(resolveLegKind({ callShort: 0 })).toBe('put_spread')
  })

  it('returns a diagonal kind only when the sleeve sets it explicitly', () => {
    expect(resolveLegKind({ legKind: 'diagonal', callShort: 281 })).toBe('diagonal')
    expect(resolveLegKind({ legKind: 'double_diagonal', callShort: 772 })).toBe('double_diagonal')
  })
})
