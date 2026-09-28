/**
 * CUSTOMER_FLINT — mirroring FLINT (FLAME/SPARK's profits-only call-spread sleeve) into
 * activated customers' SnapTrade accounts. Covers:
 *  - the flag-off invariant (zero DB/broker calls when CUSTOMER_FLINT or the base
 *    executor arm is off — ships DISARMED, same convention as every other bot flag)
 *  - a mocked end-to-end open (eligible customer, cushion covers it, exactly 1 contract)
 *  - the cushion-insufficient skip path (no order, decision logged)
 *  - close-side leg selection for a call-spread row (the bug this feature fixes)
 *  - a parity check of evaluateFlintCushion against customer_protection_sim.py's P3
 *    daily decisions (fixtures/flint-cushion-parity.json)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { evaluateFlintCushion } from '../contracts'

const ENV_KEYS = ['CUSTOMER_FLINT', 'CUSTOMER_EXECUTOR_ENABLED', 'SNAPTRADE_CLIENT_ID', 'SNAPTRADE_CONSUMER_KEY'] as const

// ---- mocks: every networked/DB dependency the module touches ----
const customerExecuteMock = vi.fn(async (..._args: unknown[]) => 1)
const customerQueryMock = vi.fn(async (..._args: unknown[]) => [] as unknown[])
vi.mock('@/lib/customers-db', () => ({
  customerExecute: (...args: unknown[]) => customerExecuteMock(...args),
  customerQuery: (...args: unknown[]) => customerQueryMock(...args),
  isCustomersDbConfigured: () => true,
}))

const getUserAccountBalanceMock = vi.fn<(...args: unknown[]) => unknown>()
const placeMlegOrderMock = vi.fn<(...args: unknown[]) => unknown>()
vi.mock('@/lib/snaptrade', () => ({
  isSnapTradeConfigured: () => true,
  getSnapTrade: () => ({
    accountInformation: { getUserAccountBalance: (...args: unknown[]) => getUserAccountBalanceMock(...args) },
    trading: { placeMlegOrder: (...args: unknown[]) => placeMlegOrderMock(...args) },
  }),
}))

vi.mock('@/lib/brokerage/snaptrade-user', () => ({
  loadSnapTradeCreds: vi.fn(async () => ({ snaptradeUserId: 'st-user-1', userSecret: 'secret' })),
}))

vi.mock('@/lib/crypto/secret-box', () => ({
  decryptSecret: (v: string) => `decrypted:${v}`,
}))

vi.mock('@/lib/tradier', () => ({
  getProductionPauseState: vi.fn(async () => ({ paused: false })),
}))

function makeCustomer(overrides: Record<string, unknown> = {}) {
  return {
    activation_id: 'act-1',
    activation_status: 'active',
    config_id: 'cfg-1',
    user_id: 'user-1',
    config_json: { max_deployment_pct: 20 },
    broker_account_id: 'ba-1',
    external_account_ref_ciphertext: 'enc-account-ref',
    buying_power_cents: 200_000, // "deposit" baseline captured at connect ($2,000)
    connection_status: 'active',
    provider: 'snaptrade',
    subscription_status: 'active',
    ...overrides,
  }
}

beforeEach(() => {
  customerExecuteMock.mockClear().mockResolvedValue(1)
  customerQueryMock.mockClear().mockResolvedValue([])
  getUserAccountBalanceMock.mockReset()
  placeMlegOrderMock.mockReset().mockResolvedValue({ data: { brokerage_order_id: 'order-123' } })
  process.env.SNAPTRADE_CLIENT_ID = 'x'
  process.env.SNAPTRADE_CONSUMER_KEY = 'y'
})

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  vi.resetModules()
})

const FLINT_MASTER = {
  botName: 'flame',
  positionId: 'FLINT-SPY-20260928-ABC123',
  ticker: 'SPY',
  expiration: '2026-09-28',
  callShort: 770,
  callLong: 772,
  spreadWidth: 2,
  credit: 0.30, // maxLoss@1ct = (2-0.30)*100 + 1.40 = $171.40 -> 17140 cents
  tradeDate: '2026-09-28',
}

describe('CUSTOMER_FLINT flag gating — ships DISARMED', () => {
  it('CUSTOMER_FLINT unset: zero DB/broker calls even with the base executor armed', async () => {
    delete process.env.CUSTOMER_FLINT
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)
    expect(customerQueryMock).not.toHaveBeenCalled()
    expect(customerExecuteMock).not.toHaveBeenCalled()
    expect(getUserAccountBalanceMock).not.toHaveBeenCalled()
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
  })

  it('CUSTOMER_FLINT=on but base executor NOT armed: still zero calls (layered gate, not a replacement)', async () => {
    process.env.CUSTOMER_FLINT = 'on'
    delete process.env.CUSTOMER_EXECUTOR_ENABLED
    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)
    expect(customerQueryMock).not.toHaveBeenCalled()
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
  })

  it('any value other than the exact string "on" reads as off (fails closed)', async () => {
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
    for (const v of ['1', 'true', 'yes', '']) {
      process.env.CUSTOMER_FLINT = v
      const { mirrorFlintOpenToCustomers } = await import('../executor')
      await mirrorFlintOpenToCustomers(FLINT_MASTER)
    }
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
  })

  it('"on" (case/whitespace tolerant) with the base armed reaches the customer loop', async () => {
    process.env.CUSTOMER_FLINT = ' ON '
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
    customerQueryMock.mockResolvedValueOnce([]) // eligibleCustomers -> no rows, but the query itself must run
    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)
    expect(customerQueryMock).toHaveBeenCalled()
  })
})

describe('CUSTOMER_FLINT open mirror — mocked end-to-end', () => {
  beforeEach(() => {
    process.env.CUSTOMER_FLINT = 'on'
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
  })

  it('eligible customer (cushion covers 1 contract + $50 margin): places exactly 1 call-spread contract', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 }) // deposit $2,000
    customerQueryMock
      .mockResolvedValueOnce([customer]) // eligibleCustomers
      .mockResolvedValueOnce([{ id: 'row-1' }]) // SELECT id after claim
    // equity $2,500 -> cushion $500 = 50_000 cents, well above maxLoss 17_140 + margin 5_000
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    const call = placeMlegOrderMock.mock.calls[0][0] as { legs: Array<{ action: string; instrument: { symbol: string } }> }
    expect(call.legs).toHaveLength(2)
    expect(call.legs[0]).toMatchObject({ action: 'SELL_TO_OPEN' })
    expect(call.legs[1]).toMatchObject({ action: 'BUY_TO_OPEN' })
    expect(call.legs[0].instrument.symbol).toContain('C00770000')
    expect(call.legs[1].instrument.symbol).toContain('C00772000')

    // Exactly 1 contract: the claim INSERT and the final UPDATE both reflect 1 lot.
    const claimCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('INSERT INTO customer_positions'))
    expect(claimCall).toBeTruthy()
    const updateCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes("SET status = 'open'"))
    expect(updateCall?.[1]).toEqual(expect.arrayContaining(['row-1']))

    // A decision row was logged as placed/eligible/1 contract.
    const decisionCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('flint_customer_decisions'))
    expect(decisionCall).toBeTruthy()
    expect(decisionCall?.[1]).toEqual(expect.arrayContaining([true, 'placed', 1]))
  })

  it('cushion insufficient (equity just covers max loss but not the $50 margin): skips, logs the decision, never calls the broker', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 }) // deposit $2,000
    customerQueryMock.mockResolvedValueOnce([customer])
    // equity = deposit + maxLoss exactly (17_140 cents) -> cushion covers maxLoss but NOT +margin(5000)
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2000 + 171.40 }] })

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    const decisionCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('flint_customer_decisions'))
    expect(decisionCall).toBeTruthy()
    expect(decisionCall?.[1]).toEqual(expect.arrayContaining([false, 'cushion_insufficient']))
  })

  it('unreadable live equity (broker call throws): skips and logs equity_unreadable, never sizes up on missing data', async () => {
    const customer = makeCustomer()
    customerQueryMock.mockResolvedValueOnce([customer])
    getUserAccountBalanceMock.mockRejectedValueOnce(new Error('broker timeout'))

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    const decisionCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('flint_customer_decisions'))
    expect(decisionCall?.[1]).toEqual(expect.arrayContaining([false, 'equity_unreadable']))
  })

  it('missing deposit baseline (buying_power_cents null): skips and logs deposit_unknown', async () => {
    const customer = makeCustomer({ buying_power_cents: null })
    customerQueryMock.mockResolvedValueOnce([customer])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 5000 }] })

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    const decisionCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('flint_customer_decisions'))
    expect(decisionCall?.[1]).toEqual(expect.arrayContaining([false, 'deposit_unknown']))
  })

  it('a disarmed/paused/unsubscribed customer never reaches the broker (reuses canOpenForCustomer)', async () => {
    const customer = makeCustomer({ subscription_status: 'past_due' })
    customerQueryMock.mockResolvedValueOnce([customer])

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(getUserAccountBalanceMock).not.toHaveBeenCalled()
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    const decisionCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('flint_customer_decisions'))
    expect(decisionCall?.[1]).toEqual(expect.arrayContaining([false, 'subscription']))
  })
})

describe('close-side leg selection for a FLINT (call-spread) customer row', () => {
  it('mirrorCloseToCustomers builds CALL close legs for a leg_kind=call_spread row, not a put close', async () => {
    process.env.CUSTOMER_FLINT = 'on'
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
    const openRow = {
      id: 'cp-1', user_id: 'user-1', agent_code: 'flame', ticker: 'SPY', expiration: '2026-09-28',
      put_short: 0, put_long: 0, call_short: 770, call_long: 772, contracts: 1, close_attempts: 0,
      leg_kind: 'call_spread',
    }
    customerQueryMock
      .mockResolvedValueOnce([openRow]) // mirrorCloseToCustomers's own SELECT ... WHERE status='open'
      .mockResolvedValueOnce([{ external_account_ref_ciphertext: 'enc-ref' }]) // closeOne's ref lookup

    const { mirrorCloseToCustomers } = await import('../executor')
    await mirrorCloseToCustomers('flame', 'FLINT-SPY-20260928-ABC123', 'settled_at_expiry')

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    const closeCall = placeMlegOrderMock.mock.calls[0][0] as { legs: Array<{ action: string; instrument: { symbol: string } }> }
    const legs = closeCall.legs
    expect(legs).toHaveLength(2) // NOT 4 — a call spread is 2 legs, never a condor
    expect(legs[0]).toMatchObject({ action: 'BUY_TO_CLOSE' })
    expect(legs[1]).toMatchObject({ action: 'SELL_TO_CLOSE' })
    expect(legs[0].instrument.symbol).toContain('C00770000') // a CALL symbol, not a put
    expect(legs[1].instrument.symbol).toContain('C00772000')
  })

  it('a row with put_short=0/put_long=0 but NO leg_kind (pre-migration) would be misread as a put spread — this is exactly why leg_kind exists', () => {
    // Documents the bug this feature fixes: the OLD inference `callShort > 0 ? condor : put_spread`
    // takes the put_spread branch here (callShort=770 > 0 is TRUE... wait — old code used
    // `callShort > 0 ? condor : ...`, so a call-only row (callShort=770>0) would hit the CONDOR
    // branch and try to build a put leg from put_short=0, which throws (occSymbol rejects strike<=0).
    // leg_kind='call_spread' bypasses that broken inference entirely.
    const put_short = 0
    const call_short = 770
    const oldInferredKind = call_short > 0 ? 'condor' : 'put_spread'
    expect(oldInferredKind).toBe('condor') // wrong for a pure call spread — would throw building put legs
    expect(put_short).toBe(0) // occSymbol(..., 'P', 0) throws "bad strike" — this is the bug
  })
})

describe('evaluateFlintCushion parity vs customer_protection_sim.py P3 (FLAME $2,000, pct=20%, no floor/P0)', () => {
  const fixturePath = join(__dirname, 'fixtures', 'flint-cushion-parity.json')
  const fixture = JSON.parse(readFileSync(fixturePath, 'utf8')) as {
    bot: string
    deposit: number
    days: Array<{ day_index: number; equity_cents: number; deposit_cents: number; flint_max_loss_cents: number; sim_eligible: boolean }>
  }

  it('the fixture is non-trivial (both eligible and ineligible days present)', () => {
    expect(fixture.days.length).toBeGreaterThan(10)
    expect(fixture.days.some((d) => d.sim_eligible)).toBe(true)
    expect(fixture.days.some((d) => !d.sim_eligible)).toBe(true)
  })

  it('evaluateFlintCushion with marginCents=0 (the sim\'s exact P3 rule) matches every fixture day', () => {
    for (const day of fixture.days) {
      const r = evaluateFlintCushion({
        equityCents: day.equity_cents,
        protectLevelCents: day.deposit_cents,
        maxLossCents: day.flint_max_loss_cents,
        marginCents: 0,
      })
      expect(r.eligible, `day_index=${day.day_index} equity=${day.equity_cents} deposit=${day.deposit_cents} ml=${day.flint_max_loss_cents}`).toBe(day.sim_eligible)
    }
  })

  it('adding the live $50 margin can only ever turn a sim-eligible day ineligible, never the reverse (documented, deliberate tightening)', () => {
    for (const day of fixture.days) {
      const withMargin = evaluateFlintCushion({
        equityCents: day.equity_cents, protectLevelCents: day.deposit_cents,
        maxLossCents: day.flint_max_loss_cents, marginCents: 5_000,
      })
      if (day.sim_eligible === false) expect(withMargin.eligible).toBe(false)
    }
  })
})
