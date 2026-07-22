import { describe, it, expect, vi } from 'vitest'

// viewer.ts pulls in the Tradier client for isFlameLiveArmed(); stub it so these
// pure-string helpers can be tested without broker/env wiring.
vi.mock('@/lib/tradier', () => ({ isFlameLiveArmed: () => false }))
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
    const scoped = scopeFilter('spark', 'User')
    expect(scoped).toContain("COALESCE(account_type, 'sandbox') = 'production'")
    expect(scoped).toContain("AND person = 'User'")
  })

  it('keeps paper bots on the non-production ledger', () => {
    const scoped = scopeFilter('flame', 'User')
    expect(scoped).toContain("COALESCE(account_type, 'sandbox') <> 'production'")
    expect(scoped).toContain("AND person = 'User'")
  })

  it('degrades to the ledger filter alone when no owner is mapped', () => {
    expect(scopeFilter('spark', null).trim()).toBe(
      "AND COALESCE(account_type, 'sandbox') = 'production'",
    )
  })
})
