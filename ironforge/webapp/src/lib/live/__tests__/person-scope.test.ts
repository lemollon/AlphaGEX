import { describe, it, expect, vi } from 'vitest'

// viewer.ts pulls in the Tradier client for canReadProductionBalance(); stub it so these
// pure-string helpers can be tested without broker/env wiring.
// canReadProductionBalance drives resolveAccountMode for FLAME as of 2026-08-17
// (was isFlameLiveArmed — showing an account is not permission to trade it).
// false here keeps these scope tests on the paper ledger, which is what they assert.
vi.mock('@/lib/tradier', () => ({
  canReadProductionBalance: () => false,
  isFlameLiveArmed: () => false,
}))
vi.mock('@/lib/db', () => ({
  dbQuery: async () => [],
  escapeSql: (v: string) => String(v).replace(/'/g, "''"),
}))
vi.mock('@/lib/auth/server', () => ({ getSession: async () => ({}) }))
vi.mock('@/lib/auth/customer-session-server', () => ({ getCustomerSession: async () => ({}) }))

const { personFilter, scopeFilter } = await import('../viewer')

describe('personFilter', () => {
  it('is empty when unscoped — the operator fleet view', () => {
    expect(personFilter(null)).toBe('')
    expect(personFilter(undefined)).toBe('')
    expect(personFilter('')).toBe('')
  })

  it('pins to one account owner', () => {
    expect(personFilter('User')).toBe("AND person = 'User'")
  })

  it('escapes quotes so a person name cannot break out of the clause', () => {
    expect(personFilter("O'Brien")).toBe("AND person = 'O''Brien'")
    // The classic injection attempt must end up inert inside the quoted literal.
    expect(personFilter("x' OR '1'='1")).toBe("AND person = 'x'' OR ''1''=''1'")
  })
})

describe('scopeFilter', () => {
  it('combines the ledger filter with the owner filter', () => {
    // 🚨 Every production-branch test below passes modeOverride='production'
    // EXPLICITLY. They used to rely on SPARK being declared a production bot,
    // which stopped being true on 2026-08-28 — and when that declaration flipped,
    // the 2026-07-27 leak guard would have quietly stopped being exercised by any
    // bot at all. The branch, not the bot, is the thing under test.
    const scoped = scopeFilter('spark', 'User', false, 'production')
    expect(scoped).toContain("COALESCE(account_type, 'sandbox') = 'production'")
    expect(scoped).toContain("AND person = 'User'")
  })

  it('puts SPARK on its paper ledger, unscoped, with no override', () => {
    // The 2026-08-28 fix. SPARK is declared 'paper' (it has no production account:
    // live_accounts.spark = 0), so the customer read must reach the sandbox rows
    // the scanner actually writes — NOT the inactive $5,000 production row, and
    // NOT `AND FALSE`, both of which hid a book with real trades in it.
    const f = scopeFilter('spark', null)
    expect(f).toContain("COALESCE(account_type, 'sandbox') <> 'production'")
    expect(f).not.toContain('AND FALSE')
    expect(f).not.toContain('person')
  })

  it('keeps paper bots on the non-production ledger, and does NOT scope them by owner', () => {
    // This previously asserted `AND person = 'User'`, which reads as safe and is a
    // query that can never match: EVERY sandbox paper_account row, on every bot, has
    // person = NULL — the scanner keeps one house ledger per (bot, dte_mode) and its
    // sandbox writes never mention person. So the "scoped" paper query returned zero
    // rows, accountLinked came back false, and the Live page told a customer their
    // bot "isn't connected to your account yet" while it was trading normally.
    const scoped = scopeFilter('flame', 'User')
    expect(scoped).toContain("COALESCE(account_type, 'sandbox') <> 'production'")
    expect(scoped).not.toContain('person')
  })

  it('shows a paper bot to a customer with no owner mapped, instead of AND FALSE', () => {
    // The demo / App-Review account is exactly this case. Simulated house money that
    // nobody owns is not the 2026-07-27 leak, which was a real Tradier account.
    const f = scopeFilter('flame', null)
    expect(f).not.toContain('AND FALSE')
    expect(f).toContain("COALESCE(account_type, 'sandbox') <> 'production'")
  })

  it('honours an explicit paper override on a production read', () => {
    // FLAME's Paper/Live switch. Choosing the paper ledger must not drag
    // the production owner filter along with it.
    const f = scopeFilter('spark', 'Logan', false, 'paper')
    expect(f).toContain("COALESCE(account_type, 'sandbox') <> 'production'")
    expect(f).not.toContain('person')
  })

  it('an explicit production override still fails closed', () => {
    // The override must never become a way around the guard.
    expect(scopeFilter('flame', null, false, 'production')).toContain('AND FALSE')
  })

  it('FAILS CLOSED for a customer with no owner mapped', () => {
    // This test previously asserted the opposite — that a null person "degrades
    // to the ledger filter alone", i.e. an UNSCOPED production query. That is the
    // bug, not the contract. On 2026-07-27 the one row in ironforge_customer_bots
    // had person = NULL, so the query returned the SPARK production account
    // (person 'Logan', real money) to whoever loaded the page.
    const f = scopeFilter('spark', null, false, 'production')
    expect(f).toContain('AND FALSE')
    expect(f).not.toBe("AND COALESCE(account_type, 'sandbox') = 'production'")
  })

  it('still gives an operator the unscoped fleet view', () => {
    // The fleet aggregate is legitimate for an operator and must not regress.
    expect(scopeFilter('spark', null, true, 'production').trim()).toBe(
      "AND COALESCE(account_type, 'sandbox') = 'production'",
    )
  })

  it('scopes to the owner when one IS mapped, operator or not', () => {
    for (const isOperator of [false, true]) {
      expect(scopeFilter('spark', 'Logan', isOperator, 'production')).toContain(
        "AND person = 'Logan'",
      )
    }
  })
})
