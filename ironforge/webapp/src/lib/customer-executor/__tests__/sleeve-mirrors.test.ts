/**
 * CUSTOMER_STOKE / CUSTOMER_QUENCH / CUSTOMER_ANVIL — the three sleeve mirrors that
 * follow FLINT's pattern (see flint-mirror.test.ts). Covers, per sleeve:
 *  - the flag-off invariant (zero DB/broker calls when the sleeve switch or the base
 *    executor arm is off — ships DISARMED)
 *  - STOKE: exactly 1 CALL-spread contract, FLAME-only, BP floor, error isolation
 *  - QUENCH: side picks the leg kind (down_call -> call_spread, up_put -> put_spread),
 *    every size clamped to the 1-lot cap
 *  - ANVIL: stays fail-closed — throws the diagonal error, no claim, no order
 *  - ON CONFLICT (source_position_id, user_id) DO NOTHING idempotency on the claim
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const ENV_KEYS = [
  'CUSTOMER_STOKE', 'CUSTOMER_QUENCH', 'CUSTOMER_ANVIL', 'CUSTOMER_EXECUTOR_ENABLED',
  'SNAPTRADE_CLIENT_ID', 'SNAPTRADE_CONSUMER_KEY',
] as const

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

const knownBotAccountsMock = vi.fn<() => string[]>(() => [])
vi.mock('../bot-account-registry', () => ({
  getKnownBotTradedTradierAccountNumbers: () => knownBotAccountsMock(),
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
    display_mask: '••••0000',
    brokerage_slug: 'SNAPTRADE',
    buying_power_cents: 200_000,
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
  knownBotAccountsMock.mockReset().mockReturnValue([])
  process.env.SNAPTRADE_CLIENT_ID = 'x'
  process.env.SNAPTRADE_CONSUMER_KEY = 'y'
})

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
  vi.resetModules()
})

const STOKE_MASTER = {
  botName: 'flame',
  positionId: 'STOKE-SPY-20261019-ABC123',
  ticker: 'SPY',
  expiration: '2026-10-19',
  callShort: 770,
  callLong: 772,
  spreadWidth: 2,
  credit: 0.40, // maxLoss@1ct = (2-0.40)*100 + 1.40 = $161.40
  tradeDate: '2026-10-19',
}

const QUENCH_MASTER = {
  botName: 'flame',
  positionId: 'QUENCH-SPY-20261019-ABC123',
  ticker: 'SPY',
  expiration: '2026-10-19',
  side: 'down_call' as const,
  shortStrike: 770,
  longStrike: 771,
  spreadWidth: 1,
  credit: 0.30, // collateral = (1-0.30)*100 = $70/contract
  tradeDate: '2026-10-19',
}

const ANVIL_MASTER = {
  botName: 'flame',
  positionId: 'ANVIL-IWM-20261019-ABC123',
  ticker: 'IWM',
  expiration: '2026-10-29',
  backExpiration: '2026-11-13',
  callShort: 250,
  callLong: 252,
  debit: 1.50,
  tradeDate: '2026-10-19',
}

type PlacedOrder = { legs: Array<{ action: string; instrument: { symbol: string } }> }

describe('sleeve mirrors ship DISARMED — zero DB and zero broker calls', () => {
  const cases = [
    { name: 'STOKE', flag: 'CUSTOMER_STOKE', fn: 'mirrorStokeOpenToCustomers', master: STOKE_MASTER },
    { name: 'QUENCH', flag: 'CUSTOMER_QUENCH', fn: 'mirrorQuenchOpenToCustomers', master: QUENCH_MASTER },
    { name: 'ANVIL', flag: 'CUSTOMER_ANVIL', fn: 'mirrorAnvilOpenToCustomers', master: ANVIL_MASTER },
  ] as const

  for (const { name, flag, fn, master } of cases) {
    it(`${name}: ${flag} unset with the base executor armed -> no calls`, async () => {
      delete process.env[flag]
      process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
      const mod = await import('../executor')
      await (mod[fn] as (m: unknown) => Promise<void>)(master)
      expect(customerQueryMock).not.toHaveBeenCalled()
      expect(customerExecuteMock).not.toHaveBeenCalled()
      expect(getUserAccountBalanceMock).not.toHaveBeenCalled()
      expect(placeMlegOrderMock).not.toHaveBeenCalled()
    })

    it(`${name}: ${flag}=on but base executor NOT armed -> no calls (layered gate)`, async () => {
      process.env[flag] = 'on'
      delete process.env.CUSTOMER_EXECUTOR_ENABLED
      const mod = await import('../executor')
      await (mod[fn] as (m: unknown) => Promise<void>)(master)
      expect(customerQueryMock).not.toHaveBeenCalled()
      expect(customerExecuteMock).not.toHaveBeenCalled()
      expect(getUserAccountBalanceMock).not.toHaveBeenCalled()
      expect(placeMlegOrderMock).not.toHaveBeenCalled()
    })

    it(`${name}: any value other than the exact string "on" reads as off (fails closed)`, async () => {
      process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
      const mod = await import('../executor')
      for (const v of ['1', 'true', 'yes', '']) {
        process.env[flag] = v
        await (mod[fn] as (m: unknown) => Promise<void>)(master)
      }
      expect(customerQueryMock).not.toHaveBeenCalled()
      expect(customerExecuteMock).not.toHaveBeenCalled()
      expect(placeMlegOrderMock).not.toHaveBeenCalled()
    })

    it(`${name}: "on" (case/whitespace tolerant) with the base armed reaches the customer loop`, async () => {
      process.env[flag] = ' ON '
      process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
      customerQueryMock.mockResolvedValueOnce([]) // eligibleCustomers -> no rows, but the query itself must run
      const mod = await import('../executor')
      await (mod[fn] as (m: unknown) => Promise<void>)(master)
      expect(customerQueryMock).toHaveBeenCalled()
    })
  }
})

describe('CUSTOMER_STOKE open mirror', () => {
  beforeEach(() => {
    process.env.CUSTOMER_STOKE = 'on'
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
  })

  it('places exactly 1 CALL-spread contract and records strategy=stoke / leg_kind=call_spread', async () => {
    customerQueryMock
      .mockResolvedValueOnce([makeCustomer()]) // eligibleCustomers
      .mockResolvedValueOnce([{ id: 'row-1' }]) // SELECT id after claim
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })

    const { mirrorStokeOpenToCustomers } = await import('../executor')
    await mirrorStokeOpenToCustomers(STOKE_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    const call = placeMlegOrderMock.mock.calls[0][0] as PlacedOrder
    expect(call.legs).toHaveLength(2)
    expect(call.legs[0]).toMatchObject({ action: 'SELL_TO_OPEN' })
    expect(call.legs[1]).toMatchObject({ action: 'BUY_TO_OPEN' })
    expect(call.legs[0].instrument.symbol).toContain('C00770000')
    expect(call.legs[1].instrument.symbol).toContain('C00772000')

    const claim = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('INSERT INTO customer_positions'))
    expect(String(claim?.[0])).toContain('ON CONFLICT (source_position_id, user_id) DO NOTHING')
    expect(claim?.[1]).toEqual(expect.arrayContaining(['call_spread', 'stoke', 'flame', STOKE_MASTER.positionId]))

    const update = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes("SET status = 'open'"))
    // [rowId, contracts, collateralCents, orderId, detail] — 1 contract, (2-0.40)*100+1.40 = $161.40
    expect(update?.[1]).toEqual(['row-1', 1, 16140, 'order-123', expect.any(String)])
  })

  it('FLAME-only: a spark master open is ignored with zero DB/broker calls', async () => {
    const { mirrorStokeOpenToCustomers } = await import('../executor')
    await mirrorStokeOpenToCustomers({ ...STOKE_MASTER, botName: 'spark' })
    expect(customerQueryMock).not.toHaveBeenCalled()
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
  })

  it('buying power below STOKE_BP_FLOOR_PER_CONTRACT ($200): skips, no claim, no order', async () => {
    customerQueryMock.mockResolvedValueOnce([makeCustomer()])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 150 }] })
    const { mirrorStokeOpenToCustomers } = await import('../executor')
    await mirrorStokeOpenToCustomers(STOKE_MASTER)
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    expect(customerExecuteMock.mock.calls.some((c) => String(c[0]).includes('INSERT INTO customer_positions'))).toBe(false)
  })

  it('STOKE profit cushion too small (max loss > the $500 standing floor): skips, no order', async () => {
    // credit so negative the max loss exceeds the $500 standing floor: (2+4)*100 = $600 > $500
    customerQueryMock.mockResolvedValueOnce([makeCustomer()])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })
    const { mirrorStokeOpenToCustomers } = await import('../executor')
    await mirrorStokeOpenToCustomers({ ...STOKE_MASTER, credit: -4 })
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
  })

  it('claim already taken (ON CONFLICT DO NOTHING -> 0 rows): no order placed', async () => {
    customerQueryMock.mockResolvedValueOnce([makeCustomer()])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })
    customerExecuteMock.mockResolvedValueOnce(0)
    const { mirrorStokeOpenToCustomers } = await import('../executor')
    await mirrorStokeOpenToCustomers(STOKE_MASTER)
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
  })

  it('broker failure: never throws, marks the claimed row status=error, and still reaches the next customer', async () => {
    customerQueryMock
      .mockResolvedValueOnce([makeCustomer(), makeCustomer({ user_id: 'user-2' })]) // eligibleCustomers
      .mockResolvedValueOnce([{ id: 'row-1' }]) // user-1 SELECT id
      .mockResolvedValueOnce([{ id: 'row-2' }]) // user-2 SELECT id
    getUserAccountBalanceMock.mockResolvedValue({ data: [{ buying_power: 2500 }] })
    placeMlegOrderMock
      .mockRejectedValueOnce(new Error('broker down'))
      .mockResolvedValueOnce({ data: { brokerage_order_id: 'order-2' } })

    const { mirrorStokeOpenToCustomers } = await import('../executor')
    await expect(mirrorStokeOpenToCustomers(STOKE_MASTER)).resolves.toBeUndefined()

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(2)
    const errUpdate = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes("SET status = 'error'"))
    expect(errUpdate?.[1]).toEqual([STOKE_MASTER.positionId, 'user-1', 'broker down'])
  })

  it('bot-account guard: a customer account the bots trade directly is skipped, no order', async () => {
    customerQueryMock.mockResolvedValueOnce([makeCustomer()])
    knownBotAccountsMock.mockReturnValue(['DECRYPTEDENCACCOUNTREF']) // normalized form of the mocked decrypt of the default ciphertext
    const { mirrorStokeOpenToCustomers } = await import('../executor')
    await mirrorStokeOpenToCustomers(STOKE_MASTER)
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    expect(getUserAccountBalanceMock).not.toHaveBeenCalled()
  })
})

describe('CUSTOMER_QUENCH open mirror', () => {
  beforeEach(() => {
    process.env.CUSTOMER_QUENCH = 'on'
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
  })

  it('down_call -> CALL vertical, leg_kind=call_spread, strategy=quench, clamped to the 1-lot cap', async () => {
    customerQueryMock
      .mockResolvedValueOnce([makeCustomer()])
      .mockResolvedValueOnce([{ id: 'row-1' }])
    // $2,500 BP * 20% = $500 deployable / $70 per contract = 7 contracts un-clamped
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })

    const { mirrorQuenchOpenToCustomers } = await import('../executor')
    await mirrorQuenchOpenToCustomers(QUENCH_MASTER)

    expect(placeMlegOrderMock).toHaveBeenCalledTimes(1)
    const call = placeMlegOrderMock.mock.calls[0][0] as PlacedOrder
    expect(call.legs.map((l) => l.instrument.symbol).join(' ')).toMatch(/C00770000.*C00771000/)
    expect(call.legs.every((l) => (l as unknown as { units: number }).units === 1)).toBe(true)

    const claim = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('INSERT INTO customer_positions'))
    expect(String(claim?.[0])).toContain('ON CONFLICT (source_position_id, user_id) DO NOTHING')
    // [..., put_short, put_long, call_short, call_long, leg_kind, strategy]
    expect(claim?.[1]).toEqual(expect.arrayContaining(['call_spread', 'quench']))
    expect((claim?.[1] as unknown[]).slice(8, 12)).toEqual([0, 0, 770, 771])

    const update = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes("SET status = 'open'"))
    // 1 contract (clamped from 7), collateral (1-0.30)*100 = $70 = 7000 cents
    expect(update?.[1]).toEqual(['row-1', 1, 7000, 'order-123', expect.any(String)])
  })

  it('up_put -> PUT vertical, leg_kind=put_spread, strikes land in the put columns', async () => {
    customerQueryMock
      .mockResolvedValueOnce([makeCustomer()])
      .mockResolvedValueOnce([{ id: 'row-1' }])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })

    const { mirrorQuenchOpenToCustomers } = await import('../executor')
    await mirrorQuenchOpenToCustomers({ ...QUENCH_MASTER, side: 'up_put', shortStrike: 775, longStrike: 774 })

    const call = placeMlegOrderMock.mock.calls[0][0] as PlacedOrder
    expect(call.legs.map((l) => l.instrument.symbol).join(' ')).toMatch(/P00775000.*P00774000/)

    const claim = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes('INSERT INTO customer_positions'))
    expect(claim?.[1]).toEqual(expect.arrayContaining(['put_spread', 'quench']))
    expect((claim?.[1] as unknown[]).slice(8, 12)).toEqual([775, 774, 0, 0])
  })

  it('size is never read from env or config: a huge BP and 100% deployment still places exactly 1', async () => {
    customerQueryMock
      .mockResolvedValueOnce([makeCustomer({ config_json: { max_deployment_pct: 100 } })])
      .mockResolvedValueOnce([{ id: 'row-1' }])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 1_000_000 }] })
    const { mirrorQuenchOpenToCustomers } = await import('../executor')
    await mirrorQuenchOpenToCustomers(QUENCH_MASTER)
    const update = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes("SET status = 'open'"))
    expect((update?.[1] as unknown[])[1]).toBe(1)
  })

  it('cannot afford one contract: skips, no claim, no order', async () => {
    customerQueryMock.mockResolvedValueOnce([makeCustomer()])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 100 }] }) // 20% of $100 = $20 < $70
    const { mirrorQuenchOpenToCustomers } = await import('../executor')
    await mirrorQuenchOpenToCustomers(QUENCH_MASTER)
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    expect(customerExecuteMock.mock.calls.some((c) => String(c[0]).includes('INSERT INTO customer_positions'))).toBe(false)
  })

  it('broker failure: never throws and marks the claimed row status=error', async () => {
    customerQueryMock
      .mockResolvedValueOnce([makeCustomer()])
      .mockResolvedValueOnce([{ id: 'row-1' }])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 2500 }] })
    placeMlegOrderMock.mockRejectedValueOnce(new Error('broker down'))
    const { mirrorQuenchOpenToCustomers } = await import('../executor')
    await expect(mirrorQuenchOpenToCustomers(QUENCH_MASTER)).resolves.toBeUndefined()
    const errUpdate = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes("SET status = 'error'"))
    expect(errUpdate?.[1]).toEqual([QUENCH_MASTER.positionId, 'user-1', 'broker down'])
  })
})

describe('CUSTOMER_ANVIL open mirror — stays fail-closed', () => {
  beforeEach(() => {
    process.env.CUSTOMER_ANVIL = 'on'
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
  })

  it('armed, eligible customer, plenty of BP: no claim row, no broker order, error recorded + never throws', async () => {
    customerQueryMock.mockResolvedValueOnce([makeCustomer()])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 10_000 }] })

    const { mirrorAnvilOpenToCustomers } = await import('../executor')
    await expect(mirrorAnvilOpenToCustomers(ANVIL_MASTER)).resolves.toBeUndefined()

    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    expect(customerExecuteMock.mock.calls.some((c) => String(c[0]).includes('INSERT INTO customer_positions'))).toBe(false)
    const errUpdate = customerExecuteMock.mock.calls.find((c) => String(c[0]).includes("SET status = 'error'"))
    expect(errUpdate?.[1]).toEqual([
      ANVIL_MASTER.positionId, 'user-1', expect.stringContaining("cannot place 'diagonal' yet"),
    ])
  })

  it('a customer who cannot afford the debit is skipped before the fail-closed throw (sized by sizeDiagonalContracts)', async () => {
    customerQueryMock.mockResolvedValueOnce([makeCustomer()])
    getUserAccountBalanceMock.mockResolvedValueOnce({ data: [{ buying_power: 100 }] }) // 20% = $20 < $150 debit
    const { mirrorAnvilOpenToCustomers } = await import('../executor')
    await mirrorAnvilOpenToCustomers(ANVIL_MASTER)
    expect(placeMlegOrderMock).not.toHaveBeenCalled()
    expect(customerExecuteMock.mock.calls.some((c) => String(c[0]).includes("SET status = 'error'"))).toBe(false)
  })
})
