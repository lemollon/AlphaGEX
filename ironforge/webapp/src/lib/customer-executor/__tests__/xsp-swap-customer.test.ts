import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

/**
 * Mocked-SnapTrade integration test for the customer-executor half of
 * XSP_SWAP (R4): mirrorOneOpen's XSP block in executor.ts. Everything I/O
 * (DB, SnapTrade, crypto, production pause, the bot-account registry) is
 * mocked — same convention as executor.test.ts (the 6YB71371 double-trade
 * guard tests), which this file re-verifies stays wired ahead of the new
 * XSP logic.
 */

type EligibleRow = {
  activation_id: string
  activation_status: string
  config_id: string
  user_id: string
  config_json: Record<string, unknown> | null
  broker_account_id: string
  external_account_ref_ciphertext: string | null
  display_mask: string | null
  brokerage_slug: string | null
  buying_power_cents: number | null
  connection_status: string | null
  provider: string | null
  subscription_status: string | null
}

const state = {
  eligible: [] as EligibleRow[],
  claimedOpen: new Set<string>(),
  positionRowId: 'pos-row-1',
}

const execCalls: Array<{ sql: string; params: unknown[] }> = []
type PlacedOrder = { accountId: string; symbols: string[] }
const placedOrders: PlacedOrder[] = []
let snaptradeShouldFailForXsp = false

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerExecute: async (sql: string, params: unknown[] = []) => {
    execCalls.push({ sql, params })
    if (sql.includes('INSERT INTO customer_positions') && sql.includes('ON CONFLICT')) {
      // Both the main-leg claim (param[4] = source_position_id) and the
      // XSP-leg insert (also param[4] in its own INSERT) use this same shape.
      const key = `${params[4]}|${params[0]}`
      if (state.claimedOpen.has(key)) return 0
      state.claimedOpen.add(key)
      return 1
    }
    return 1
  },
  customerQuery: async (sql: string) => {
    if (sql.includes('FROM activations a')) return state.eligible
    if (sql.includes('SELECT id FROM customer_positions WHERE source_position_id')) {
      return [{ id: state.positionRowId }]
    }
    return []
  },
  customerTransaction: async () => { throw new Error('not used in these tests') },
}))

vi.mock('@/lib/snaptrade', () => ({
  isSnapTradeConfigured: () => true,
  getSnapTrade: () => ({
    accountInformation: {
      getUserAccountBalance: async () => ({ data: [{ buying_power: 100000, cash: 100000 }] }),
    },
    trading: {
      placeMlegOrder: async (args: { accountId: string; legs: Array<{ instrument: { symbol: string } }> }) => {
        const symbols = args.legs.map((l) => l.instrument.symbol)
        const isXsp = symbols.some((s) => s.trim().startsWith('XSP'))
        if (isXsp && snaptradeShouldFailForXsp) {
          throw new Error('SnapTrade: unsupported instrument for this broker')
        }
        placedOrders.push({ accountId: args.accountId, symbols })
        return { data: { brokerage_order_id: isXsp ? 'ord-xsp-1' : 'ord-spy-1' } }
      },
    },
  }),
}))

vi.mock('@/lib/brokerage/snaptrade-user', () => ({
  loadSnapTradeCreds: async () => ({ snaptradeUserId: 'st-user', userSecret: 'st-secret' }),
}))

vi.mock('@/lib/tradier', () => ({
  getProductionPauseState: async () => ({ paused: false }),
}))

vi.mock('@/lib/crypto/secret-box', () => ({
  decryptSecret: (token: string) => token,
  encryptSecret: (plaintext: string) => plaintext,
}))

vi.mock('../bot-account-registry', () => ({
  getKnownBotTradedTradierAccountNumbers: () => ['6YB71371'],
}))

const BASE_ROW: EligibleRow = {
  activation_id: 'act-1',
  activation_status: 'active',
  config_id: 'cfg-1',
  user_id: 'user-1',
  config_json: { max_deployment_pct: 50 },
  broker_account_id: 'ba-1',
  external_account_ref_ciphertext: 'CUSTOMER-ACCT-9',
  display_mask: '••••CT-9',
  brokerage_slug: 'Tastytrade',
  buying_power_cents: null,
  connection_status: 'active',
  provider: 'snaptrade',
  subscription_status: 'active',
}

const MASTER_OPEN_ELIGIBLE = {
  botName: 'flame',
  positionId: 'master-pos-xsp-1',
  ticker: 'SPY',
  expiration: '2026-10-01',
  putShort: 630,
  putLong: 625,
  callShort: 0,
  callLong: 0,
  spreadWidth: 5,
  credit: 1.2,
  xspSwap: { eligible: true, xspCreditPerContract: 1.25 },
}

beforeEach(() => {
  process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
  delete process.env.ALERT_NTFY_TOPIC
  delete process.env.XSP_SWAP
  snaptradeShouldFailForXsp = false
  state.eligible = []
  state.claimedOpen.clear()
  execCalls.length = 0
  placedOrders.length = 0
})

afterEach(() => {
  delete process.env.CUSTOMER_EXECUTOR_ENABLED
  delete process.env.XSP_SWAP
  vi.resetModules()
})

describe('mirrorOneOpen — XSP_SWAP (R4) kill switch', () => {
  it('XSP_SWAP unset: one SPY order only, even when the master says eligible', async () => {
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{ ...BASE_ROW }]
    await mirrorOpenToCustomers(MASTER_OPEN_ELIGIBLE)
    expect(placedOrders).toHaveLength(1)
    expect(placedOrders[0].symbols.some((s) => s.trim().startsWith('XSP'))).toBe(false)
  })

  it("XSP_SWAP='off': one SPY order only", async () => {
    process.env.XSP_SWAP = 'off'
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{ ...BASE_ROW }]
    await mirrorOpenToCustomers(MASTER_OPEN_ELIGIBLE)
    expect(placedOrders).toHaveLength(1)
    expect(placedOrders[0].symbols.some((s) => s.trim().startsWith('XSP'))).toBe(false)
  })
})

describe('mirrorOneOpen — XSP_SWAP (R4) on', () => {
  beforeEach(() => { process.env.XSP_SWAP = 'on' })

  it('places a separate XSP order for min(contracts,2) and a reduced SPY order for the remainder', async () => {
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{ ...BASE_ROW }]
    await mirrorOpenToCustomers(MASTER_OPEN_ELIGIBLE)
    expect(placedOrders).toHaveLength(2)
    const xspOrder = placedOrders.find((o) => o.symbols.some((s) => s.trim().startsWith('XSP')))
    const spyOrder = placedOrders.find((o) => o.symbols.some((s) => s.trim().startsWith('SPY')))
    expect(xspOrder).toBeTruthy()
    expect(spyOrder).toBeTruthy()
  })

  it('does not attempt XSP when the master says not eligible', async () => {
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{ ...BASE_ROW }]
    await mirrorOpenToCustomers({ ...MASTER_OPEN_ELIGIBLE, positionId: 'master-pos-xsp-2', xspSwap: { eligible: false, xspCreditPerContract: 0.9 } })
    expect(placedOrders).toHaveLength(1)
    expect(placedOrders[0].symbols.some((s) => s.trim().startsWith('XSP'))).toBe(false)
  })

  it('falls back to 100% SPY when the SnapTrade XSP order throws — trade is never skipped', async () => {
    snaptradeShouldFailForXsp = true
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{ ...BASE_ROW }]
    await mirrorOpenToCustomers({ ...MASTER_OPEN_ELIGIBLE, positionId: 'master-pos-xsp-3' })
    // The failed XSP attempt is never recorded as a placed order (it threw);
    // exactly one order (the SPY fallback) must still land.
    expect(placedOrders).toHaveLength(1)
    expect(placedOrders[0].symbols.some((s) => s.trim().startsWith('XSP'))).toBe(false)
  })

  it('the 6YB71371 bot-account guard still blocks BOTH legs — XSP_SWAP does not bypass it', async () => {
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{
      ...BASE_ROW,
      external_account_ref_ciphertext: '6YB71371',
      display_mask: '••••1371',
      brokerage_slug: 'Tradier',
    }]
    await mirrorOpenToCustomers({ ...MASTER_OPEN_ELIGIBLE, positionId: 'master-pos-xsp-4' })
    expect(placedOrders).toHaveLength(0)
  })
})
