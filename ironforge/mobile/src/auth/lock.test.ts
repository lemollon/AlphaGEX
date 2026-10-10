import { describe, it, expect } from 'vitest'
import { nextLockState, INITIAL_LOCK_STATE, type LockState } from './lock'

const policy = { foregroundLockSec: 300 }

describe('nextLockState', () => {
  it('stays unlocked when the app returns from the background under the threshold', () => {
    const backgrounded: LockState = { locked: false, backgroundedAtMs: 1_000_000_000 }
    const next = nextLockState(
      backgrounded,
      { type: 'app_foregrounded', nowMs: 1_000_000_000 + 299_000 },
      true,
      policy,
    )
    expect(next).toEqual({ locked: false, backgroundedAtMs: null })
  })

  it('locks when the app returns from the background over the threshold', () => {
    const backgrounded: LockState = { locked: false, backgroundedAtMs: 1_000_000_000 }
    const next = nextLockState(
      backgrounded,
      { type: 'app_foregrounded', nowMs: 1_000_000_000 + 301_000 },
      true,
      policy,
    )
    expect(next).toEqual({ locked: true, backgroundedAtMs: null })
  })

  it('always locks on a signed-in cold start', () => {
    const next = nextLockState(INITIAL_LOCK_STATE, { type: 'cold_start' }, true, policy)
    expect(next.locked).toBe(true)
  })

  it('never locks when signed out, regardless of the action', () => {
    expect(nextLockState(INITIAL_LOCK_STATE, { type: 'cold_start' }, false, policy)).toEqual(
      INITIAL_LOCK_STATE,
    )
    const overThreshold = nextLockState(
      { locked: false, backgroundedAtMs: 0 },
      { type: 'app_foregrounded', nowMs: 10_000_000 },
      false,
      policy,
    )
    expect(overThreshold.locked).toBe(false)
  })

  it('falls back to the 300s default when the policy is missing', () => {
    const backgrounded: LockState = { locked: false, backgroundedAtMs: 1_000_000_000 }
    const underDefault = nextLockState(
      backgrounded,
      { type: 'app_foregrounded', nowMs: 1_000_000_000 + 299_000 },
      true,
      null,
    )
    expect(underDefault.locked).toBe(false)

    const overDefault = nextLockState(
      backgrounded,
      { type: 'app_foregrounded', nowMs: 1_000_000_000 + 301_000 },
      true,
      null,
    )
    expect(overDefault.locked).toBe(true)
  })

  it('unlocking clears the lock and the backgrounded timestamp', () => {
    const locked: LockState = { locked: true, backgroundedAtMs: null }
    expect(nextLockState(locked, { type: 'unlocked' }, true, policy)).toEqual({
      locked: false,
      backgroundedAtMs: null,
    })
  })

  it('backgrounding preserves the current lock flag and records the timestamp', () => {
    const unlocked: LockState = { locked: false, backgroundedAtMs: null }
    expect(nextLockState(unlocked, { type: 'app_backgrounded', nowMs: 5_000 }, true, policy)).toEqual(
      { locked: false, backgroundedAtMs: 5_000 },
    )
  })
})
