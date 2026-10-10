import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * EBB settles at the close. No path may buy it back at the 14:45 cutoff.
 *
 * There are THREE independent closers in this codebase and each learned the
 * lesson separately: the scanner's monitor path (settleDefer, 8/16), the EOD
 * safety-net sweep (8/17, after FLAME's first trade was force-closed for -$13),
 * and this route — a second, older EOD close fired by the dashboard's
 * position-monitor poll. On 2026-08-19 it flattened FLAME at 14:45:04 and SPARK
 * at 14:49:19, fifteen minutes before settlement, with no CLOSE_TRIGGER row
 * because it writes close_reason straight to SQL.
 *
 * These tests pin the guard on the route that was missed.
 */

const dbQuery = vi.fn()
const dbExecute = vi.fn()

vi.mock('@/lib/db', async () => {
  const actual = await vi.importActual<typeof import('../db')>('../db')
  return {
    ...actual,
    dbQuery: (...a: unknown[]) => dbQuery(...a),
    dbExecute: (...a: unknown[]) => dbExecute(...a),
  }
})
vi.mock('@/lib/tradier', () => ({
  getIcMarkToMarket: vi.fn(),
  isConfigured: () => true,
  closeIcOrderAllAccounts: vi.fn(),
}))

import { POST } from '@/app/api/[bot]/eod-close/route'
import { isSettleAtExpiryBot } from '../db'

function req() {
  return new NextRequest('https://ironforge.test/api/flame/eod-close', { method: 'POST' })
}

beforeEach(() => {
  dbQuery.mockReset()
  dbExecute.mockReset()
})

describe('EOD close route — settle-at-expiry bots are never bought back', () => {
  it.each(['flame', 'spark'])('%s is refused outright', async (bot) => {
    expect(isSettleAtExpiryBot(bot)).toBe(true)
    const res = await POST(req(), { params: { bot } })
    const body = await res.json()
    expect(body.closed).toBe(0)
    expect(body.results).toEqual([])
    expect(body.message).toMatch(/settles at the close/i)
  })

  it('never reads the positions table for a settle-at-expiry bot', async () => {
    await POST(req(), { params: { bot: 'flame' } })
    // The guard must return BEFORE any query — a bot that cannot be closed here
    // should not even be enumerated, so a later refactor cannot reintroduce a
    // close path below the guard.
    expect(dbQuery).not.toHaveBeenCalled()
    expect(dbExecute).not.toHaveBeenCalled()
  })

  it('leaves the bots this route was built for alone', () => {
    // INFERNO is the 0DTE iron condor this generic EOD close was written for.
    expect(isSettleAtExpiryBot('inferno')).toBe(false)
    expect(isSettleAtExpiryBot('kindle')).toBe(false)
  })
})
