/**
 * Shared fixtures for the tenant-isolation suite (APP-045).
 *
 * NOT named *.test.ts on purpose — vitest.config.ts collects `src/**\/*.test.ts`, and a
 * helper file collected as a suite fails the run with "no tests found".
 */
import { vi, expect } from 'vitest'

/** Two tenants with distinct ids and distinct ledger owners. */
export const TENANT_A = {
  customerId: 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
  person: 'Alpha',
  bot: 'spark' as const,
}
export const TENANT_B = {
  customerId: 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb',
  person: 'Bravo',
  bot: 'flame' as const,
}

export interface SqlCall {
  sql: string
  params: unknown[]
}

/**
 * Records every SQL statement the bot-ledger client is asked to run so the
 * assertions below can inspect what WOULD have hit the database.
 */
export function makeSqlSpy() {
  const calls: SqlCall[] = []
  return {
    calls,
    dbQuery: async (sql: string, params: unknown[] = []) => {
      calls.push({ sql, params })
      return []
    },
    reset: () => {
      calls.length = 0
    },
  }
}

/** Tables that hold per-owner trading state. A query touching one MUST be scoped. */
const LEDGER_TABLE = /\b(spark|flame|inferno|blaze|flare|kindle)_(positions|equity_snapshots|paper_account|daily_perf|logs|signals)\b/i

export function touchesLedger(sql: string): boolean {
  return LEDGER_TABLE.test(sql)
}

/**
 * The core invariant: every ledger-touching query issued for a NON-OPERATOR is either
 * pinned to that owner (`AND person = '<person>'`) or neutered (`AND FALSE`).
 *
 * Asserting on the generated SQL rather than on returned rows is deliberate — it is the
 * only form that also catches a NEW query added to these modules later without a scope
 * filter, which is the actual recurring failure mode.
 */
export function expectEveryLedgerQueryScoped(calls: SqlCall[], person: string | null) {
  const ledger = calls.filter((c) => touchesLedger(c.sql))
  expect(ledger.length).toBeGreaterThan(0) // guard against a vacuous pass
  const unscoped: string[] = []
  for (const c of ledger) {
    const pinned = person ? c.sql.includes(`person = '${person}'`) : false
    const blocked = /\bAND\s+FALSE\b/i.test(c.sql)
    if (!pinned && !blocked) unscoped.push(c.sql.replace(/\s+/g, ' ').slice(0, 220))
  }
  if (unscoped.length) {
    throw new Error(
      `${unscoped.length} ledger query/queries were neither pinned to person ` +
        `${person === null ? '(none)' : `'${person}'`} nor blocked with AND FALSE:\n\n` +
        unscoped.join('\n\n'),
    )
  }
}

/** No query may mention the other tenant's owner, under any circumstances. */
export function expectNeverMentions(calls: SqlCall[], person: string) {
  const leaks = calls.filter((c) => c.sql.includes(`'${person}'`))
  if (leaks.length) {
    throw new Error(
      `${leaks.length} query/queries referenced foreign owner '${person}':\n` +
        leaks.map((c) => c.sql.replace(/\s+/g, ' ').slice(0, 200)).join('\n'),
    )
  }
}

export { vi }
