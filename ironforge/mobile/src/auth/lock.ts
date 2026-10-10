/**
 * Foreground lock state machine (APP-010).
 *
 * Deliberately independent of session.ts — session.ts reaches expo-local-authentication
 * and, through api/client, react-native — so this can be exercised with plain vitest.
 * `nextLockState` is the ONLY place that decides whether the app is locked; app/_layout.tsx
 * should be a thin AppState listener that calls it and renders the result, nothing more.
 */

export interface LockPolicy {
  foregroundLockSec: number
}

/** Used when no policy has ever been fetched or persisted. */
export const DEFAULT_FOREGROUND_LOCK_SEC = 300

export interface LockState {
  locked: boolean
  /** ms timestamp the app was last sent to the background, or null while foregrounded. */
  backgroundedAtMs: number | null
}

export const INITIAL_LOCK_STATE: LockState = { locked: false, backgroundedAtMs: null }

export type LockAction =
  | { type: 'cold_start' }
  | { type: 'app_backgrounded'; nowMs: number }
  | { type: 'app_foregrounded'; nowMs: number }
  | { type: 'unlocked' }

/**
 * Advance the lock state machine by one action.
 *
 * `signedIn` gates everything: a signed-out app has no session worth protecting, and
 * locking it would just be a confusing second sign-in screen layered on top of the real
 * one.
 */
export function nextLockState(
  prev: LockState,
  action: LockAction,
  signedIn: boolean,
  policy: LockPolicy | null,
): LockState {
  if (!signedIn) return INITIAL_LOCK_STATE

  const foregroundLockSec = policy?.foregroundLockSec ?? DEFAULT_FOREGROUND_LOCK_SEC

  switch (action.type) {
    case 'cold_start':
      // A fresh launch is treated as "backgrounded since the beginning of time" — a
      // signed-in cold start always re-proves identity rather than trusting whatever
      // state a killed/relaunched process happens to remember.
      return { locked: true, backgroundedAtMs: 0 }

    case 'app_backgrounded':
      return { locked: prev.locked, backgroundedAtMs: action.nowMs }

    case 'app_foregrounded': {
      if (prev.backgroundedAtMs == null) return { locked: prev.locked, backgroundedAtMs: null }
      const over = action.nowMs - prev.backgroundedAtMs > foregroundLockSec * 1000
      return { locked: prev.locked || over, backgroundedAtMs: null }
    }

    case 'unlocked':
      return { locked: false, backgroundedAtMs: null }

    default:
      return prev
  }
}
