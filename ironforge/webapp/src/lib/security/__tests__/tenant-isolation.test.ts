/**
 * APP-045 tenant isolation — marked a critical launch blocker.
 *
 * These assert on the SQL the live query builders GENERATE, not on the rows they
 * return. That is the point: a row-level test only proves today's queries are scoped,
 * while a SQL-level sweep also fails the moment someone adds a NEW query to these
 * modules without a scope filter — which is the failure that actually happened.
 *
 * On 2026-07-27 the single ironforge_customer_bots row had person = NULL, so a
 * signed-in customer's Live page rendered the SPARK production account (person
 * 'Logan', a real Tradier account) as "your account" — balance, P&L, open position.
 * The "customer with no person mapping" case below is that incident as a test.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { TENANT_A, TENANT_B, makeSqlSpy, expectEveryLedgerQueryScoped, expectNeverMentions } from './harness'

const spy = makeSqlSpy()

// Same partial-mock reasoning as @/lib/db: keep the real module and stub only the
// calls that would hit the broker network.
vi.mock('@/lib/tradier', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/tradier')>()
  return {
    ...actual,
    isFlameLiveArmed: () => false,
    getTradierBalances: async () => null,
    getPositionMtm: async () => null,
    getProductionPauseState: async () => ({ paused: false }),
    // Per-owner pause returns a SET of paused owners, not a boolean.
    getOwnerPauseState: async () => ({ paused: new Set<string>() }),
    getSandboxAccountBalances: async () => [],
  }
})
// Partial mock: keep every real helper (escapeSql, botTable, dteMode, heartbeatName, …)
// and intercept ONLY the query functions. Mocking the module wholesale would mean this
// suite silently rots — and worse, would test escaping logic I reimplemented in the mock
// rather than the escaping that actually ships.
vi.mock('@/lib/db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/db')>()
  return {
    ...actual,
    dbQuery: (sql: string, params: unknown[] = []) => spy.dbQuery(sql, params),
    dbExecute: (sql: string, params: unknown[] = []) => spy.dbQuery(sql, params),
    query: (sql: string, params: unknown[] = []) => spy.dbQuery(sql, params),
  }
})
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => false,
  customerQuery: async () => [],
  customerExecute: async () => 0,
  customerTransaction: async () => undefined,
}))

const { getLiveSummary, getLiveTrade } = await import('@/lib/live/summary')
const { getHomeData } = await import('@/lib/live/home')
const { getPerformance } = await import('@/lib/live/performance')
const { getCustomerTrades } = await import('@/lib/live/trades-history')

beforeEach(() => spy.reset())

describe('every live query is owner-scoped for a customer', () => {
  const A = TENANT_A

  it('getLiveSummary pins every ledger query to the caller', async () => {
    await getLiveSummary(A.bot, { allowAggregate: false, person: A.person })
    expectEveryLedgerQueryScoped(spy.calls, A.person)
    expectNeverMentions(spy.calls, TENANT_B.person)
  })

  it('getLiveTrade pins every ledger query to the caller', async () => {
    await getLiveTrade(A.bot, A.person, false)
    expectEveryLedgerQueryScoped(spy.calls, A.person)
    expectNeverMentions(spy.calls, TENANT_B.person)
  })

  it('getHomeData pins every ledger query to the caller', async () => {
    await getHomeData(A.bot, A.person, false)
    expectEveryLedgerQueryScoped(spy.calls, A.person)
  })

  it('getPerformance pins every ledger query to the caller', async () => {
    await getPerformance([A.bot], { [A.bot]: A.person }, false)
    expectEveryLedgerQueryScoped(spy.calls, A.person)
    expectNeverMentions(spy.calls, TENANT_B.person)
  })

  it('getCustomerTrades pins every ledger query to the caller', async () => {
    await getCustomerTrades([A.bot], { [A.bot]: A.person }, [], false)
    expectEveryLedgerQueryScoped(spy.calls, A.person)
    expectNeverMentions(spy.calls, TENANT_B.person)
  })
})

describe('a customer with NO person mapping sees nothing — the 2026-07-27 leak', () => {
  // Negative control. An unscoped production query returns another person's
  // real-money account, so "no mapping" must mean "matches nothing", never
  // "no restriction".
  it.each([
    ['getLiveSummary', () => getLiveSummary(TENANT_A.bot, { allowAggregate: false, person: null })],
    ['getLiveTrade', () => getLiveTrade(TENANT_A.bot, null, false)],
    ['getHomeData', () => getHomeData(TENANT_A.bot, null, false)],
    ['getPerformance', () => getPerformance([TENANT_A.bot], {}, false)],
    ['getCustomerTrades', () => getCustomerTrades([TENANT_A.bot], {}, [], false)],
  ])('%s blocks every ledger query with AND FALSE', async (_name, run) => {
    await run()
    const ledger = spy.calls.filter((c) => /_(positions|equity_snapshots|paper_account|daily_perf)\b/i.test(c.sql))
    expect(ledger.length).toBeGreaterThan(0)
    for (const c of ledger) {
      expect(c.sql, c.sql.replace(/\s+/g, ' ').slice(0, 200)).toMatch(/\bAND\s+FALSE\b/i)
    }
  })
})

describe('one tenant can never surface another tenant', () => {
  it('B\'s owner never appears when A is the caller, across every builder', async () => {
    await getLiveSummary(TENANT_A.bot, { allowAggregate: false, person: TENANT_A.person })
    await getLiveTrade(TENANT_A.bot, TENANT_A.person, false)
    await getHomeData(TENANT_A.bot, TENANT_A.person, false)
    await getCustomerTrades([TENANT_A.bot], { [TENANT_A.bot]: TENANT_A.person }, [], false)
    expectNeverMentions(spy.calls, TENANT_B.person)
  })

  it('an owner name cannot break out of the quoted literal', async () => {
    // personFilter escapes via escapeSql; this pins that the classic payload stays inert
    // rather than becoming a second SQL clause.
    await getLiveTrade(TENANT_A.bot, "x' OR '1'='1", false)
    const ledger = spy.calls.filter((c) => /_positions\b/i.test(c.sql))
    expect(ledger.length).toBeGreaterThan(0)
    for (const c of ledger) {
      expect(c.sql).toContain("person = 'x'' OR ''1''=''1'")
      expect(c.sql).not.toMatch(/OR\s+'1'\s*=\s*'1'/)
    }
  })
})

describe('operators keep the fleet view', () => {
  // The mirror image: isOperator must NOT be neutered, or the ops console goes blank.
  it('an operator gets unscoped ledger queries', async () => {
    await getLiveSummary(TENANT_A.bot, { allowAggregate: true, person: null })
    const ledger = spy.calls.filter((c) => /_(positions|paper_account)\b/i.test(c.sql))
    expect(ledger.length).toBeGreaterThan(0)
    expect(ledger.every((c) => !/\bAND\s+FALSE\b/i.test(c.sql))).toBe(true)
  })
})
