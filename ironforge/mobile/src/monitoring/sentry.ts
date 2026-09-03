/**
 * Crash + performance monitoring (APP-049).
 *
 * A deliberate no-op until EXPO_PUBLIC_SENTRY_DSN is set. Leron has not created the
 * Sentry project yet (see the build report for what he still has to fill in), and
 * shipping the SDK wired-but-silent is safer than either alternative: crashing the
 * app because a build-time env var is missing, or leaving this unimplemented and
 * losing every crash report from the first release while someone remembers to build
 * it later.
 */
import Constants from 'expo-constants'
import * as Sentry from '@sentry/react-native'
import { ApiError } from '@/api/errors'

/** Same rule as analytics/track.ts — kept local rather than shared to avoid a
 * monitoring <-> analytics import cycle over three lines of regex. */
const SENSITIVE_KEY_RE = /account|token|password|secret/i

let initCalled = false
let enabled = false

/** Redacts sensitive keys anywhere in a Sentry event, recursively, before it leaves the device. */
function scrub<T>(value: T, depth = 0): T {
  if (depth > 6 || value === null || typeof value !== 'object') return value
  if (Array.isArray(value)) {
    return value.map((v) => scrub(v, depth + 1)) as unknown as T
  }
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (SENSITIVE_KEY_RE.test(k) || k.toLowerCase() === 'authorization') continue
    out[k] = scrub(v, depth + 1)
  }
  return out as T
}

function environment(): 'sandbox' | 'production' {
  const apiBase = (Constants.expoConfig?.extra as { apiBase?: string } | undefined)?.apiBase ?? ''
  return apiBase.includes('sandbox') ? 'sandbox' : 'production'
}

/** Call once, as early as possible — see app/(tabs)/_layout.tsx's module top. Idempotent. */
export function initMonitoring(): void {
  if (initCalled) return
  initCalled = true

  const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN
  if (!dsn) {
    console.log('[monitoring] EXPO_PUBLIC_SENTRY_DSN not set — crash reporting disabled')
    return
  }

  Sentry.init({
    dsn,
    environment: environment(),
    release: Constants.expoConfig?.version ?? '0.0.0',
    tracesSampleRate: 0.2,
    beforeSend(event) {
      const headers = event.request?.headers as Record<string, unknown> | undefined
      if (headers) {
        delete headers.Authorization
        delete headers.authorization
      }
      return scrub(event)
    },
  })
  enabled = true
}

/**
 * Report a server failure that is IronForge's fault, not the customer's — a 5xx, not
 * a validation 4xx. analytics/track.ts also calls this for `api_error` events whose
 * status is >= 500, so any screen that already calls track() on a failed request gets
 * this for free without a second call site to remember.
 */
export function captureApiError(err: unknown): void {
  if (!enabled) return
  if (err instanceof ApiError && err.status >= 500) {
    Sentry.captureException(err)
  }
}
