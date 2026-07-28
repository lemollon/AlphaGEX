import { describe, it, expect } from 'vitest'
import { ownsStrategyFromRows } from '../membership'

/**
 * Who may see the Live dashboard.
 *
 * The bug this guards: the marketing nav asked `/api/auth/customer-me` whether someone
 * was "a customer", but `ok` there only ever meant SIGNED IN. Anyone with a free account
 * saw "Live" in the nav while owning nothing — the fourth appearance of the same
 * conflation of "anonymous" with "signed in, nothing bought".
 */

describe('ownsStrategyFromRows', () => {
  it('is false with no subscriptions at all', () => {
    expect(ownsStrategyFromRows([])).toBe(false)
  })

  it('is true for a live strategy subscription', () => {
    for (const status of ['active', 'trialing', 'past_due']) {
      expect(ownsStrategyFromRows([{ bot: 'spark', status }]), status).toBe(true)
      expect(ownsStrategyFromRows([{ bot: 'flame', status }]), status).toBe(true)
    }
  })

  it('is false for a dead strategy subscription', () => {
    for (const status of ['canceled', 'incomplete', 'incomplete_expired', 'unpaid', 'paused', '']) {
      expect(ownsStrategyFromRows([{ bot: 'spark', status }]), status).toBe(false)
    }
  })

  it('is FALSE for Community alone — chat is not the strategy product', () => {
    // The exact case that was showing Live to non-owners had no subscription at all,
    // but Community-only is the same error one step later: a real membership that
    // does not entitle you to the strategy dashboard.
    expect(ownsStrategyFromRows([{ bot: 'community', status: 'active' }])).toBe(false)
    expect(ownsStrategyFromRows([{ bot: 'community', status: 'trialing' }])).toBe(false)
  })

  it('is true when a strategy sits alongside Community', () => {
    expect(
      ownsStrategyFromRows([
        { bot: 'community', status: 'active' },
        { bot: 'flame', status: 'active' },
      ]),
    ).toBe(true)
  })

  it('ignores a canceled strategy even when Community is live', () => {
    expect(
      ownsStrategyFromRows([
        { bot: 'community', status: 'active' },
        { bot: 'spark', status: 'canceled' },
      ]),
    ).toBe(false)
  })

  it('does not treat an unknown bot slug as Community', () => {
    // Fails toward "owns it" only for a live status, which matches the table's
    // free-text `bot` column: a future strategy slug should work without a code change.
    expect(ownsStrategyFromRows([{ bot: 'someNewStrategy', status: 'active' }])).toBe(true)
    expect(ownsStrategyFromRows([{ bot: 'someNewStrategy', status: 'canceled' }])).toBe(false)
  })
})
