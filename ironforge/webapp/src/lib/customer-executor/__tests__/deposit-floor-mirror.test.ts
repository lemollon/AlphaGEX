/**
 * CUSTOMER_DEPOSIT_FLOOR — mocked end-to-end coverage for the main-leg sizing cap
 * (mirrorOneOpen/applyDepositFloor) and its interaction with CUSTOMER_FLINT's own
 * "dropped first" combined check. Pure-function parity against the sim already lives
 * in contracts.test.ts; this file covers the DB/broker wiring: state persistence,
 * the flag-off kill switch, and pre-trigger / triggered-near-floor / zero-contract
 * scenarios end-to-end through mirrorOpenToCustomers.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const ENV_KEYS = ['CUSTOMER_DEPOSIT_FLOOR', 'CUSTOMER_FLINT', 'CUSTOMER_EXECUTOR_ENABLED', 'SNAPTRADE_CLIENT_ID', 'SNAPTRADE_CONSUMER_KEY'] as const

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
    activation_id: 'act-1', activation_status: 'active', config_id: 'cfg-1', user_id: 'user-1',
    config_json: { max_deployment_pct: 20 }, broker_account_id: 'ba-1',
    external_account_ref_ciphertext: 'enc-account-ref',
    buying_power_cents: 200_000, // deposit baseline: $2,000
    connection_status: 'active', provider: 'snaptrade', subscription_status: 'active',
    ...overrides,
  }
}

// FLAME-style put credit spread master open: width $5, credit $1.20 -> collateral/maxLoss
// per contract = (5-1.2)*100 = $380 = 38_000 cents.
const MAIN_MASTER = {
  botName: 'flame', positionId: 'FLAME-SPY-20260928-XYZ', ticker: 'SPY', expiration: '2026-09-28',
  putShort: 630, putLong: 625, callShort: 0, callLong: 0, spreadWidth: 5, credit: 1.2,
}

beforeEach(() => {
  customerExecuteMock.mockClear().mockResolvedValue(1)
  customerQueryMock.mockClear().mockResolvedValue([])
  getUserAccountBalanceMock.mockReset()
  placeMlegOrderMock.mockReset().mockResolvedValue({ data: { brokerage_order_id: 'order-1' } })
  process.env.SNAPTRADE_CLIENT_ID = 'x'
  process.env.SNAPTRADE_CONSUMER_KEY = 'y'
  process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
})

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  vi.resetModules()
})

describe('CUSTOMER_DEPOSIT_FLOOR flag gating — kill switch, ships DISARMED', () => {
  it('off (unset): mirrorOneOpen sizes exactly as sizeContracts computed — no floor-state DB calls at all', async () => {
    delete process.env.CUSTOMER_DEPOSIT_FLOOR
    const customer = makeCustomer({ buying_power_cents: 1_000_000 }) // $10,000 BP -> plenty of room
    customerQueryMock.mockResolvedValueOnce([customer]).mockResolvedValueOnce([{ id: 'row-1' }])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 10000 }] })

    const { mirrorOpenToCustomers } = await import('../executor')
    await mirrorOpenToCustomers(MAIN_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    // No query/execute call ever touches customer_deposit_floor_state.
    const touchedFloorState = [...customerQueryMock.mock.calls, ...customerExecuteMock.mock.calls]
      .some((c) => String(c[0]).includes('customer_deposit_floor_state'))
    expect(touchedFloorState).toBe(false)
  })

  it('any value other than the exact string "on" reads as off (fails closed)', async () => {
    const customer = makeCustomer({ buying_power_cents: 1_000_000 })
    for (const v of ['1', 'true', 'yes', '']) {
      process.env.CUSTOMER_DEPOSIT_FLOOR = v
      customerQueryMock.mockClear().mockResolvedValueOnce([customer]).mockResolvedValueOnce([{ id: 'row-1' }])
      getUserAccountBalanceMock.mockReset().mockResolvedValueOnce({ data: [{ buying_power: 10000 }] })
      placeMlegOrderMock.mockClear()
      const { mirrorOpenToCustomers } = await import('../executor')
      await mirrorOpenToCustomers(MAIN_MASTER)
      const touchedFloorState = [...customerQueryMock.mock.calls, ...customerExecuteMock.mock.calls]
        .some((c) => String(c[0]).includes('customer_deposit_floor_state'))
      expect(touchedFloorState, `value ${JSON.stringify(v)} must stay off`).toBe(false)
    }
  })
})

describe('CUSTOMER_DEPOSIT_FLOOR main-leg sizing — mocked end-to-end', () => {
  beforeEach(() => { process.env.CUSTOMER_DEPOSIT_FLOOR = 'on' })

  it('pre-trigger: cushion far below 3x a normal position — sizes exactly as sizeContracts computed, unmodified', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 }) // deposit $2,000
    customerQueryMock
      .mockResolvedValueOnce([customer]) // eligibleCustomers
      .mockResolvedValueOnce([{ id: 'row-1' }]) // SELECT id after claim
      .mockResolvedValueOnce([]) // SELECT ... customer_deposit_floor_state (no row yet)
    // equity $2,100 -> cushion $100, nowhere near 3x a $380 position
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2100 }] })

    const { mirrorOpenToCustomers } = await import('../executor')
    await mirrorOpenToCustomers(MAIN_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    const preTriggerCall = placeMlegOrderMock.mock.calls[0][0] as { legs: Array<{ units: number }> }
    const legs = preTriggerCall.legs
    expect(legs.every((l) => l.units === 1)).toBe(true) // $2,100 BP / $380 collateral = floor(5.5)=5... capped by max_deployment_pct 20%: floor(2100*0.2/380)=1
    // Insert into customer_deposit_floor_state happened (first-sight row creation).
    const insertedState = customerExecuteMock.mock.calls.some((c) => String(c[0]).includes('INSERT INTO customer_deposit_floor_state'))
    expect(insertedState).toBe(true)
  })

  it('triggered + near the floor: caps contracts DOWN from the normal desired count', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 }) // deposit $2,000
    customerQueryMock
      .mockResolvedValueOnce([customer])
      .mockResolvedValueOnce([{ id: 'row-1' }])
      // Already triggered from a prior day.
      .mockResolvedValueOnce([{ deposit_cents: 200_000, triggered: true }])
    // equity $2,050 -> cushion $50 = 5_000c; budget/(ml+margin) = 5_000/(38_000+5_000) = 0 -> 0 contracts
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2050 }] })

    const { mirrorOpenToCustomers } = await import('../executor')
    await mirrorOpenToCustomers(MAIN_MASTER)

    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    const skipCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes("status = 'skipped'"))
    expect(skipCall?.[1]).toEqual(expect.arrayContaining(['deposit_floor_capped_to_zero']))
  })

  it('ROUND 8 variant G: a ratcheted peak profit raises the floor, but the minimum layer (gated on DEPOSIT, not the floor) still saves 1 contract that variant S would have zeroed out', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 }) // deposit $2,000
    customerQueryMock
      .mockResolvedValueOnce([customer])
      .mockResolvedValueOnce([{ id: 'row-1' }])
      // Persisted state: triggered, with a prior peak equity of $4,000 (a $2,000 peak
      // profit) -> floorLevel = 200_000 + 0.1*200_000 = 220_000. Equity has since fallen
      // to $2,500 -> budgetK (equity-floor) = 30_000 < mlEff(43_000), so the EXTRA layer
      // alone would give 0 — but budgetDep (equity-deposit) = 50_000 >= mlEff, so the
      // minimum layer (nMin) still fires: n=1, not 0.
      .mockResolvedValueOnce([{ deposit_cents: 200_000, triggered: true, peak_equity_cents: 400_000 }])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })

    const { mirrorOpenToCustomers } = await import('../executor')
    await mirrorOpenToCustomers(MAIN_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    const call = placeMlegOrderMock.mock.calls[0][0] as { legs: Array<{ units: number }> }
    expect(call.legs[0].units).toBe(1)
    // The persisted peak ratchet must not move backwards (equity 250_000 < peak 400_000).
    const updateCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('UPDATE customer_deposit_floor_state'))
    expect(updateCall?.[1]).toEqual(expect.arrayContaining([400_000]))
  })

  it('equity <= deposit + max loss (a real drawdown day, post-trigger): exactly 0 contracts, never negative, never sized up', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 })
    customerQueryMock
      .mockResolvedValueOnce([customer])
      .mockResolvedValueOnce([{ id: 'row-1' }])
      .mockResolvedValueOnce([{ deposit_cents: 200_000, triggered: true }])
    // equity == deposit exactly (a bad stretch wiped the profit back to deposit).
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2000 }] })

    const { mirrorOpenToCustomers } = await import('../executor')
    await mirrorOpenToCustomers(MAIN_MASTER)

    expect(placeMlegOrderMock).not.toHaveBeenCalled()
  })

  it('triggered with ample cushion: sizes up to but never above the normal (unfloored) desired count', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 })
    customerQueryMock
      .mockResolvedValueOnce([customer])
      .mockResolvedValueOnce([{ id: 'row-1' }])
      .mockResolvedValueOnce([{ deposit_cents: 200_000, triggered: true }])
    // equity $50,000 -> budget = $48,000 = 4_800_000c, way more than enough for the BP-limited desired count.
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 50000 }] })

    const { mirrorOpenToCustomers } = await import('../executor')
    await mirrorOpenToCustomers(MAIN_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    const ampleCall = placeMlegOrderMock.mock.calls[0][0] as { legs: Array<{ units: number }> }
    // desired = floor(50000*0.2/380) = floor(26.3) = 26 — the floor must not have reduced it.
    expect(ampleCall.legs[0].units).toBe(26)
  })

  it('a read/write failure evaluating the floor FAILS OPEN — today\'s normal sizing still places, and it is logged', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 })
    customerQueryMock
      .mockResolvedValueOnce([customer])
      .mockResolvedValueOnce([{ id: 'row-1' }])
      .mockRejectedValueOnce(new Error('db unavailable')) // the floor-state SELECT throws
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2100 }] })
    const warnSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { mirrorOpenToCustomers } = await import('../executor')
    await mirrorOpenToCustomers(MAIN_MASTER)

    // Trade still placed at the NORMAL (unfloor'ed) size — fails open, not closed.
    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })
})

describe('CUSTOMER_FLINT host-leg netting — "FLINT is dropped first" (ROUND 8, unconditional — independent of CUSTOMER_DEPOSIT_FLOOR)', () => {
  const FLINT_MASTER = {
    botName: 'flame', positionId: 'FLINT-SPY-20260928-ABC', ticker: 'SPY', expiration: '2026-09-28',
    callShort: 770, callLong: 772, spreadWidth: 2, credit: 0.30, tradeDate: '2026-09-28',
  }

  beforeEach(() => {
    process.env.CUSTOMER_FLINT = 'on'
    process.env.CUSTOMER_DEPOSIT_FLOOR = 'on'
  })

  it('main leg already committed most of the cushion today: FLINT is dropped even though its OWN standalone check would pass', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 }) // deposit $2,000
    customerQueryMock
      .mockResolvedValueOnce([customer]) // eligibleCustomers for FLINT
      .mockResolvedValueOnce([{ deposit_cents: 200_000, triggered: false, peak_equity_cents: null }]) // floor-state read (floor on)
      // main-leg lookup: $1,700 already committed today (leaves only $100 of the $200 total cushion)
      .mockResolvedValueOnce([{ total_cents: 170_000 }])
    // equity $2,200 -> cushion $200 = 20_000c. FLINT alone needs maxLoss(17_140)+margin(5_000)=22_140 -- already fails standalone!
    // Use a bigger cushion so the STANDALONE check passes but the NETTED one does not:
    // equity $2,400 -> cushion 40_000c >= 22_140 (standalone eligible), but netted needs
    // 170_000 + 17_140 + 5_000 = 192_140 > 40_000 (netted fails) -> FLINT dropped.
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2400 }] })

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    const decisionCall = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('flint_customer_decisions'))
    expect(decisionCall?.[1]).toEqual(expect.arrayContaining([false, 'cushion_insufficient']))
  })

  it('no main-leg position today: netted check reduces to the standalone check (FLINT trades normally)', async () => {
    const customer = makeCustomer({ buying_power_cents: 200_000 })
    customerQueryMock
      .mockResolvedValueOnce([customer])
      .mockResolvedValueOnce([{ deposit_cents: 200_000, triggered: false, peak_equity_cents: null }]) // floor-state read
      .mockResolvedValueOnce([]) // no main-leg row today
      .mockResolvedValueOnce([{ id: 'row-1' }]) // SELECT id after FLINT's own claim
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] }) // cushion 50_000c >= 17_140+5_000

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
  })

  it('CUSTOMER_DEPOSIT_FLOOR off: protect_level stays raw deposit, but the host-leg netting STILL runs (ROUND 8 — unconditional)', async () => {
    delete process.env.CUSTOMER_DEPOSIT_FLOOR
    const customer = makeCustomer({ buying_power_cents: 200_000 })
    customerQueryMock
      .mockResolvedValueOnce([customer])
      // no floor-state read at all (floor is off) — next call is the host-committed lookup
      .mockResolvedValueOnce([{ total_cents: 170_000 }]) // host leg already committed $1,700 today
      // never reached: netted cushion (40_000-170_000-17_140-5_000 < 0) fails before any claim/SELECT id
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2400 }] })

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    const touchedFloorState = customerQueryMock.mock.calls.some((c) => String(c[0]).includes('customer_deposit_floor_state'))
    expect(touchedFloorState, 'floor is off — must never read floor state').toBe(false)
    const touchedMainLeg = customerQueryMock.mock.calls.some((c) => String(c[0]).includes("strategy = 'main'"))
    expect(touchedMainLeg, 'host-leg netting is unconditional, even with the floor off').toBe(true)
  })

  it('CUSTOMER_DEPOSIT_FLOOR off AND no host commitment today: FLINT trades normally off the ORIGINAL P3 rule', async () => {
    delete process.env.CUSTOMER_DEPOSIT_FLOOR
    const customer = makeCustomer({ buying_power_cents: 200_000 })
    customerQueryMock
      .mockResolvedValueOnce([customer])
      .mockResolvedValueOnce([]) // host-leg lookup: no main-leg position today
      .mockResolvedValueOnce([{ id: 'row-1' }]) // SELECT id after FLINT's own claim
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
  })

  it('a main leg opened YESTERDAY but still status=open (FLAME is 2DTE) is still netted — no opened_at date filter', async () => {
    // Regression: the host-leg lookup used to filter `opened_at::date = $3::date`
    // (today). FLAME's own EBB host leg is a 2DTE hold, opened Friday and still
    // status='open' on Monday/Tuesday -- that date filter returned ZERO rows on
    // every day but the one it opened, silently reading "no host collateral
    // committed" while the position was still holding real buying power on this
    // SAME account. The fix drops the date predicate and sums ALL open 'main'
    // rows regardless of when they opened.
    const customer = makeCustomer({ buying_power_cents: 200_000 })
    customerQueryMock
      .mockResolvedValueOnce([customer]) // eligibleCustomers for FLINT
      .mockResolvedValueOnce([{ deposit_cents: 200_000, triggered: false, peak_equity_cents: null }]) // floor-state read
      // main-leg lookup: $1,700 committed by a position opened a PRIOR day, still open today.
      .mockResolvedValueOnce([{ total_cents: 170_000 }])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2400 }] }) // same numbers as the "already committed" case above

    const { mirrorFlintOpenToCustomers } = await import('../executor')
    await mirrorFlintOpenToCustomers(FLINT_MASTER)

    // The netted check must have seen the $1,700 and dropped FLINT — proving the
    // host-leg lookup reached and used a row, not "no rows because of a date miss".
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    const hostLegCall = customerQueryMock.mock.calls.find((c) => String(c[0]).includes("strategy = 'main'"))
    expect(hostLegCall, 'host-leg lookup must run').toBeDefined()
    const sql = String(hostLegCall?.[0])
    expect(sql).not.toContain('opened_at::date')
    // Only 2 bound params now (user_id, agent_code) -- no 3rd tradeDate param.
    expect(hostLegCall?.[1]).toHaveLength(2)
  })
})
