import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

/**
 * Integration-style tests for the 6YB71371 double-trade guard wired into
 * mirrorOpenToCustomers / mirrorCloseToCustomers. Everything I/O (DB, SnapTrade,
 * crypto, the production pause) is mocked; only executor.ts's own control flow is
 * real. The point of these tests is narrow and load-bearing: prove the guard
 * actually stops a broker order from being placed, not just that the pure
 * matching function returns the right verdict (that's bot-account-guard.test.ts).
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
  claimedOpen: new Set<string>(), // `${positionId}|${userId}` already claimed
  positionRowId: 'pos-row-1',
  openCustomerPositions: [] as Array<Record<string, unknown>>,
  refFacts: {
    external_account_ref_ciphertext: null as string | null,
    display_mask: null as string | null,
    brokerage_slug: null as string | null,
  },
}

const execCalls: Array<{ sql: string; params: unknown[] }> = []
const placedOrders: Array<{ accountId: string }> = []

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerExecute: async (sql: string, params: unknown[] = []) => {
    execCalls.push({ sql, params })
    if (sql.includes('INSERT INTO customer_positions') && sql.includes('ON CONFLICT')) {
      const key = `${params[4]}|${params[0]}` // positionId|userId
      if (state.claimedOpen.has(key)) return 0
      state.claimedOpen.add(key)
      return 1
    }
    // close claim / status updates / audit inserts — always "succeed"
    return 1
  },
  customerQuery: async (sql: string, params: unknown[] = []) => {
    if (sql.includes('FROM activations a')) return state.eligible
    if (sql.includes('SELECT id FROM customer_positions WHERE source_position_id')) {
      return [{ id: state.positionRowId }]
    }
    if (sql.includes("status = 'open'") && sql.includes('FROM customer_positions')) {
      return state.openCustomerPositions
    }
    if (sql.includes('FROM customer_positions cp') && sql.includes('JOIN broker_accounts')) {
      return [state.refFacts]
    }
    return []
  },
  customerTransaction: async () => { throw new Error('not used in these tests') },
}))

const getUserAccountBalanceMock = vi.fn(async () => ({ data: [{ buying_power: 100000, cash: 100000 }] }))

vi.mock('@/lib/snaptrade', () => ({
  isSnapTradeConfigured: () => true,
  getSnapTrade: () => ({
    accountInformation: {
      getUserAccountBalance: getUserAccountBalanceMock,
    },
    trading: {
      placeMlegOrder: async (args: { accountId: string }) => {
        placedOrders.push({ accountId: args.accountId })
        return { data: { brokerage_order_id: 'ord-1' } }
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

/** Deterministic stand-in for AES-GCM: ciphertext IS the plaintext, except the
 *  literal sentinel 'CORRUPT', which simulates a decrypt failure (bad key/tamper). */
vi.mock('@/lib/crypto/secret-box', () => ({
  decryptSecret: (token: string) => {
    if (token === 'CORRUPT') throw new Error('malformed secret token')
    return token
  },
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
  external_account_ref_ciphertext: null,
  display_mask: null,
  brokerage_slug: null,
  buying_power_cents: null,
  connection_status: 'active',
  provider: 'snaptrade',
  subscription_status: 'active',
}

const MASTER_OPEN = {
  botName: 'flame',
  positionId: 'master-pos-1',
  ticker: 'SPY',
  expiration: '2026-10-01',
  putShort: 630,
  putLong: 625,
  callShort: 0,
  callLong: 0,
  spreadWidth: 5,
  credit: 1.2,
}

beforeEach(() => {
  process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
  delete process.env.ALERT_NTFY_TOPIC
  state.eligible = []
  state.claimedOpen.clear()
  state.openCustomerPositions = []
  state.refFacts = { external_account_ref_ciphertext: null, display_mask: null, brokerage_slug: null }
  execCalls.length = 0
  placedOrders.length = 0
  getUserAccountBalanceMock.mockReset()
  getUserAccountBalanceMock.mockResolvedValue({ data: [{ buying_power: 100000, cash: 100000 }] })
})

afterEach(() => {
  delete process.env.CUSTOMER_EXECUTOR_ENABLED
  delete process.env.FLAME_CUSTOMER_EXECUTOR_ENABLED
  vi.resetModules()
})

function skipReasonsFor(userId: string): string[] {
  return execCalls
    .filter((c) => c.sql.includes("status = 'skipped'") && c.params[0] === state.positionRowId)
    .map((c) => String(c.params[1]))
}

describe('Flame-only customer arm', () => {
  it('can arm Flame without arming Spark or the legacy fleet switch', async () => {
    delete process.env.CUSTOMER_EXECUTOR_ENABLED
    process.env.FLAME_CUSTOMER_EXECUTOR_ENABLED = 'true'
    const { isExecutorArmedForAgent } = await import('../executor')
    expect(isExecutorArmedForAgent('flame')).toBe(true)
    expect(isExecutorArmedForAgent('spark')).toBe(false)
  })

  it('allows an eligible Flame mirror under the Flame-only arm', async () => {
    delete process.env.CUSTOMER_EXECUTOR_ENABLED
    process.env.FLAME_CUSTOMER_EXECUTOR_ENABLED = 'true'
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{ ...BASE_ROW, external_account_ref_ciphertext: 'customer-account-1' }]
    await mirrorOpenToCustomers(MASTER_OPEN)
    expect(placedOrders).toHaveLength(1)
  })
})

describe('mirrorOpenToCustomers — bot-account guard', () => {
  it('never mirrors an OPEN into the production account the bots already trade (6YB71371)', async () => {
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{
      ...BASE_ROW,
      external_account_ref_ciphertext: '6YB71371',
      display_mask: '••••1371',
      brokerage_slug: 'Tradier',
    }]
    await mirrorOpenToCustomers(MASTER_OPEN)
    expect(placedOrders).toHaveLength(0)
    expect(skipReasonsFor('user-1').some((r) => r.startsWith('bot_account_guard:full_number_match'))).toBe(true)
  })

  it('mirrors a normal customer account normally', async () => {
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{
      ...BASE_ROW,
      external_account_ref_ciphertext: 'CUSTOMER-ACCT-9',
      display_mask: '••••CT-9',
      brokerage_slug: 'Tastytrade',
    }]
    await mirrorOpenToCustomers(MASTER_OPEN)
    expect(placedOrders).toHaveLength(1)
    expect(placedOrders[0].accountId).toBe('CUSTOMER-ACCT-9')
  })

  it('skips an unverifiable account (undecryptable ref, unknown institution) — never mirrored', async () => {
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{
      ...BASE_ROW,
      external_account_ref_ciphertext: 'CORRUPT',
      display_mask: null,
      brokerage_slug: null,
    }]
    await mirrorOpenToCustomers(MASTER_OPEN)
    expect(placedOrders).toHaveLength(0)
    expect(skipReasonsFor('user-1').some((r) => r === 'bot_account_guard:unverifiable')).toBe(true)
  })

  it('skips on a masked last-4 match against a Tradier account when the full number is unreadable', async () => {
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{
      ...BASE_ROW,
      external_account_ref_ciphertext: 'CORRUPT',
      display_mask: '••••1371',
      brokerage_slug: 'Tradier',
    }]
    await mirrorOpenToCustomers(MASTER_OPEN)
    expect(placedOrders).toHaveLength(0)
    expect(skipReasonsFor('user-1').some((r) => r.startsWith('bot_account_guard:masked_last4_match'))).toBe(true)
  })
})

describe('mirrorCloseToCustomers — bot-account guard', () => {
  const openPos = {
    id: 'cpos-1',
    user_id: 'user-1',
    agent_code: 'flame',
    ticker: 'SPY',
    expiration: '2026-10-01',
    put_short: 630,
    put_long: 625,
    call_short: 0,
    call_long: 0,
    contracts: 1,
    close_attempts: 0,
  }

  it('never sends a CLOSE order into the production account the bots already trade (6YB71371)', async () => {
    const { mirrorCloseToCustomers } = await import('../executor')
    state.openCustomerPositions = [openPos]
    state.refFacts = {
      external_account_ref_ciphertext: '6YB71371',
      display_mask: '••••1371',
      brokerage_slug: 'Tradier',
    }
    await mirrorCloseToCustomers('flame', 'master-pos-1', 'profit_target')
    expect(placedOrders).toHaveLength(0)
    const blocked = execCalls.find((c) =>
      c.sql.includes("status = 'close_failed'") && String(c.params[1]).startsWith('bot_account_guard:'),
    )
    expect(blocked).toBeTruthy()
  })

  it('closes a normal customer position normally', async () => {
    const { mirrorCloseToCustomers } = await import('../executor')
    state.openCustomerPositions = [openPos]
    state.refFacts = {
      external_account_ref_ciphertext: 'CUSTOMER-ACCT-9',
      display_mask: '••••CT-9',
      brokerage_slug: 'Tastytrade',
    }
    await mirrorCloseToCustomers('flame', 'master-pos-1', 'profit_target')
    expect(placedOrders).toHaveLength(1)
    expect(placedOrders[0].accountId).toBe('CUSTOMER-ACCT-9')
  })
})

/**
 * 2026-09-29 correction: an OPEN used to fall back to c.buying_power_cents (the
 * connect-time stored value, never refreshed since) on ANY live SnapTrade
 * balance-fetch failure — a customer who has since traded that number down (or
 * up) would size a real order against buying power they may no longer have.
 * OPENS must now fail CLOSED on a fetch failure: skip that customer for today
 * and log it, never size off the stale stored number. CLOSES are untouched —
 * mirrorOneClose/closeOne never read buying power at all, so a broken balance
 * read must never block closing an open position.
 */
describe('mirrorOpenToCustomers — live buying-power fetch failure fails CLOSED', () => {
  it('a rejected balance fetch skips the OPEN and places no order — never sizes off the stored value', async () => {
    getUserAccountBalanceMock.mockReset()
    getUserAccountBalanceMock.mockRejectedValue(new Error('SnapTrade 503'))
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{
      ...BASE_ROW,
      buying_power_cents: 500_000, // a large stored value — must NEVER be used to size this order
      external_account_ref_ciphertext: 'CUSTOMER-ACCT-9',
      display_mask: '••••CT-9',
      brokerage_slug: 'Tastytrade',
    }]
    await mirrorOpenToCustomers(MASTER_OPEN)
    expect(placedOrders).toHaveLength(0)
    expect(skipReasonsFor('user-1')).toContain('buying_power_fetch_failed')
  })

  it('a balance response with no usable buying_power/cash also skips the OPEN, distinctly from an exception', async () => {
    getUserAccountBalanceMock.mockReset()
    getUserAccountBalanceMock.mockResolvedValue({ data: [] })
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{
      ...BASE_ROW,
      buying_power_cents: 500_000,
      external_account_ref_ciphertext: 'CUSTOMER-ACCT-9',
      display_mask: '••••CT-9',
      brokerage_slug: 'Tastytrade',
    }]
    await mirrorOpenToCustomers(MASTER_OPEN)
    expect(placedOrders).toHaveLength(0)
    expect(skipReasonsFor('user-1')).toContain('buying_power_unavailable')
  })

  it('a healthy live fetch still sizes and places normally — the fix only changes the FAILURE path', async () => {
    getUserAccountBalanceMock.mockReset()
    getUserAccountBalanceMock.mockResolvedValue({ data: [{ buying_power: 100000, cash: 100000 }] })
    const { mirrorOpenToCustomers } = await import('../executor')
    state.eligible = [{
      ...BASE_ROW,
      buying_power_cents: 1, // stored value irrelevant now — must not be what sizes this
      external_account_ref_ciphertext: 'CUSTOMER-ACCT-9',
      display_mask: '••••CT-9',
      brokerage_slug: 'Tastytrade',
    }]
    await mirrorOpenToCustomers(MASTER_OPEN)
    expect(placedOrders).toHaveLength(1)
  })

  it('CLOSES are unaffected by a broken balance read — a rejected fetch never blocks closing an open position', async () => {
    getUserAccountBalanceMock.mockReset()
    getUserAccountBalanceMock.mockRejectedValue(new Error('SnapTrade 503'))
    const { mirrorCloseToCustomers } = await import('../executor')
    state.openCustomerPositions = [{
      id: 'cpos-1', user_id: 'user-1', agent_code: 'flame', ticker: 'SPY', expiration: '2026-10-01',
      put_short: 630, put_long: 625, call_short: 0, call_long: 0, contracts: 1, close_attempts: 0,
    }]
    state.refFacts = {
      external_account_ref_ciphertext: 'CUSTOMER-ACCT-9',
      display_mask: '••••CT-9',
      brokerage_slug: 'Tastytrade',
    }
    await mirrorCloseToCustomers('flame', 'master-pos-1', 'profit_target')
    expect(placedOrders).toHaveLength(1)
    expect(getUserAccountBalanceMock).not.toHaveBeenCalled()
  })
})
