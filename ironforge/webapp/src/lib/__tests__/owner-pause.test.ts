import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

/**
 * PER-OWNER pause: one customer stopping their own account must not stop
 * everyone else's, and must never be silently ignored.
 *
 * ironforge_production_pause is ONE ROW PER BOT. Any customer mapped to a bot
 * could pause it, so a single customer pressing Pause halted every other
 * owner's real-money trading. ironforge_owner_pause scopes it per account owner.
 *
 * These tests drive the real getProductionAccountsForBot — the single
 * load-bearing gate on the trade side — through FLAME's armed path, which
 * yields exactly one production account named 'Flame'.
 */

const db = vi.hoisted(() => ({
  fleetPaused: false,
  pausedOwners: [] as string[],
  ownerReadThrows: false,
}))

// Routed by SQL text so the fleet and owner layers stay independently controllable.
vi.mock('../db', async () => {
  const actual = await vi.importActual<typeof import('../db')>('../db')
  return {
    ...actual,
    query: vi.fn(async (sql: string) => {
      if (sql.includes('ironforge_owner_pause')) {
        if (db.ownerReadThrows) throw new Error('relation "ironforge_owner_pause" does not exist')
        return db.pausedOwners.map((person) => ({ person, paused: true }))
      }
      if (sql.includes('ironforge_production_pause')) {
        return [{
          bot_name: 'FLAME', paused: db.fleetPaused,
          paused_at: null, paused_by: null, paused_reason: null, updated_at: null,
        }]
      }
      return []
    }),
  }
})

import { getProductionAccountsForBot } from '../tradier'

const ENV = {
  IRONFORGE_FLAME_LIVE: 'true',
  TRADIER_FLAME_API_KEY: 'test-key',
  TRADIER_FLAME_ACCOUNT_ID: 'test-account',
}

beforeEach(() => {
  db.fleetPaused = false
  db.pausedOwners = []
  db.ownerReadThrows = false
  Object.assign(process.env, ENV)
})

afterEach(() => {
  for (const k of Object.keys(ENV)) delete process.env[k]
})

describe('per-owner production pause', () => {
  it('returns the fully-armed account when nobody has paused', async () => {
    const accounts = await getProductionAccountsForBot('flame')
    expect(accounts).toHaveLength(1)
    expect(accounts[0]).toMatchObject({ name: 'Flame', accountId: 'test-account' })
  })

  it('drops the owner who paused', async () => {
    db.pausedOwners = ['Flame']
    expect(await getProductionAccountsForBot('flame')).toEqual([])
  })

  it("another owner's pause does not stop this one — the whole point", async () => {
    db.pausedOwners = ['Logan', 'Spark2']
    expect((await getProductionAccountsForBot('flame')).map((a) => a.name)).toEqual(['Flame'])
  })

  it('FAILS CLOSED when the owner-pause table cannot be read', async () => {
    // A missed read here would place a real order for someone who pressed Pause.
    // A skipped scan is recoverable; that is not.
    db.ownerReadThrows = true
    expect(await getProductionAccountsForBot('flame')).toEqual([])
  })

  it('the fleet switch still stops everyone, independently of owner rows', async () => {
    db.fleetPaused = true
    expect(await getProductionAccountsForBot('flame')).toEqual([])
  })
})
