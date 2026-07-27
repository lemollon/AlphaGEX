import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('../repo', () => ({
  findCurrentBlackout: vi.fn(),
}))
vi.mock('../../db', () => ({
  query: vi.fn(),
}))

import { findCurrentBlackout } from '../repo'
import { query } from '../../db'
import { BLACKOUT_HALT_ENABLED, isEventBlackoutActive } from '../gate'

const mockedFindBlackout = vi.mocked(findCurrentBlackout)
const mockedQuery = vi.mocked(query)

beforeEach(() => {
  mockedFindBlackout.mockReset()
  mockedQuery.mockReset()
})

/**
 * The event-blackout halt was globally DISABLED on 2026-07-02 (see the
 * BLACKOUT_HALT_ENABLED docblock in gate.ts for the rationale).
 *
 * These tests previously asserted the ARMED behaviour — blocked=true on a
 * matching window, and that the repo was consulted — and had been failing
 * silently ever since. They now assert the contract that is actually live:
 * the master switch short-circuits before any I/O.
 *
 * The underlying machinery is deliberately left intact and is still covered
 * elsewhere: halt-window.test.ts pins the window math, and repo tests pin the
 * range query. What is NOT covered while the switch is off is the armed
 * end-to-end path — see the re-arming note at the bottom of this file.
 */
describe('isEventBlackoutActive — master switch', () => {
  it('is currently disabled', () => {
    // Pins the operator decision. Flipping the switch fails this immediately,
    // which is the point: re-arming a trading halt should never be a quiet
    // one-character change.
    expect(BLACKOUT_HALT_ENABLED).toBe(false)
  })

  it('never blocks any bot while disabled, even with a live window matching', async () => {
    // If the short-circuit were removed, this mocked window would block.
    mockedQuery.mockResolvedValue([{ event_blackout_enabled: true }] as never)
    mockedFindBlackout.mockResolvedValue({
      event_id: 'finnhub:FOMC:2025-06-18',
      title: 'FOMC Meeting',
      halt_end_ts: new Date('2025-06-18T19:00:00Z'),
    } as never)

    for (const bot of ['flame', 'spark', 'inferno']) {
      const result = await isEventBlackoutActive(bot, new Date('2025-06-18T15:00:00Z'))
      expect(result.blocked, `${bot} must not be blocked while the halt is disabled`).toBe(false)
      expect(result.reason).toBeUndefined()
    }
  })

  it('does no database work at all while disabled', async () => {
    // The short-circuit is before both the per-bot config read and the window
    // query, so a disabled halt costs the scanner nothing per cycle.
    mockedQuery.mockResolvedValue([{ event_blackout_enabled: true }] as never)
    mockedFindBlackout.mockResolvedValue(null as never)

    await isEventBlackoutActive('flame', new Date())

    expect(mockedQuery).not.toHaveBeenCalled()
    expect(mockedFindBlackout).not.toHaveBeenCalled()
  })

  it('still returns the documented shape', async () => {
    const result = await isEventBlackoutActive('flame', new Date())
    expect(result).toEqual({ blocked: false })
  })

  it('rejects unknown bot names without querying', async () => {
    const result = await isEventBlackoutActive('bogus', new Date())
    expect(result.blocked).toBe(false)
    expect(mockedQuery).not.toHaveBeenCalled()
    expect(mockedFindBlackout).not.toHaveBeenCalled()
  })
})

/**
 * RE-ARMING CHECKLIST — if BLACKOUT_HALT_ENABLED goes back to true:
 *
 * The "is currently disabled" test above will fail and lead you here. Restore
 * behavioural coverage for the armed path before shipping it, specifically:
 *   1. blocked=false when the per-bot `event_blackout_enabled` toggle is false
 *      (and that findCurrentBlackout is NOT consulted in that case)
 *   2. blocked=false when no window matches
 *   3. blocked=true with reason / eventId / eventTitle / resumesAt populated
 *      when a window does match
 *   4. a missing config row defaults to ENABLED (the fail-safe direction)
 *   5. both failure paths fail OPEN — a throwing config read or a throwing
 *      findCurrentBlackout must return blocked=false, never freeze trading
 *
 * Those were the assertions this file used to make; they are recorded here so
 * re-arming does not ship untested.
 */
