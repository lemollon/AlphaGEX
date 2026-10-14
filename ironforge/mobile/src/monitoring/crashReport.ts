/**
 * Self-hosted crash/error beacon (2026-10-14) — closes the zero-visibility gap
 * until Sentry has a real DSN (see sentry.ts). Posts to IronForge's own
 * `POST /api/client-error`, which just logs a structured `[CLIENT_CRASH]`
 * line to Render — see that route for why this isn't Sentry or the
 * analytics_events pipe.
 *
 * Deliberately a RAW fetch, not `api()`: a crash can happen before sign-in,
 * before SSL pinning init, or — critically — INSIDE api()'s own refresh/retry
 * path, and a reporting call that depends on the thing that might be broken
 * is useless exactly when it matters most. No auth header, no token refresh,
 * no retry: best-effort, fire-and-forget, never throws.
 */
import Constants from 'expo-constants'
import { Platform } from 'react-native'

const API_BASE: string =
  (Constants.expoConfig?.extra as { apiBase?: string } | undefined)?.apiBase ?? 'https://ironforge.trade'

let installed = false

function currentScreen(): string | null {
  // Best-effort only — expo-router's state isn't threaded through here, and a
  // crash handler must never risk importing something that could itself throw
  // mid-crash. Left null; the server-side timestamp + stack is usually enough
  // to correlate against which screen was open.
  return null
}

export function reportClientError(opts: {
  kind: 'js_exception' | 'unhandled_rejection' | 'network_error'
  message: string
  stack?: string
  fatal?: boolean
}): void {
  try {
    void fetch(`${API_BASE}/api/client-error`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        kind: opts.kind,
        message: opts.message.slice(0, 4000),
        stack: opts.stack?.slice(0, 4000),
        screen: currentScreen(),
        build: Constants.expoConfig?.extra?.eas?.projectId ?? null,
        appVersion: Constants.expoConfig?.version ?? null,
        platform: Platform.OS,
      }),
      // Crash reporting must never hang the handler it's attached to.
    }).catch(() => {})
  } catch {
    // Never throw from a crash handler.
  }
}

/**
 * Installs global JS-exception and unhandled-rejection reporting. Call once,
 * as early as possible — same tier as initializeApiPinning() at
 * app/_layout.tsx's module top, so it is live before the sign-in gate and
 * the whole enrollment funnel, not just the authenticated (tabs) tree that
 * monitoring/sentry.ts's initMonitoring() reaches.
 *
 * Idempotent. Wraps whatever handler RN already installed (the default
 * red-box/fatal-error UI in dev, the production error screen in a release
 * build) rather than replacing it — this must add visibility, never remove
 * existing crash behavior.
 */
export function installCrashReporting(): void {
  if (installed) return
  installed = true

  try {
    const g = global as unknown as {
      ErrorUtils?: { setGlobalHandler: (fn: (e: Error, isFatal?: boolean) => void) => void; getGlobalHandler: () => (e: Error, isFatal?: boolean) => void }
    }
    if (g.ErrorUtils) {
      const previousHandler = g.ErrorUtils.getGlobalHandler()
      g.ErrorUtils.setGlobalHandler((error, isFatal) => {
        reportClientError({
          kind: 'js_exception',
          message: error?.message ?? String(error),
          stack: error?.stack,
          fatal: isFatal,
        })
        previousHandler(error, isFatal)
      })
    }
  } catch {
    // Never let installing the reporter crash the app it's meant to protect.
  }

  try {
    // RN's bundled Promise polyfill ships this tracker; it's how the engine
    // itself can tell us about a rejection nothing ever .catch()'d.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const rejectionTracking = require('promise/setimmediate/rejection-tracking')
    rejectionTracking.enable({
      allRejections: true,
      onUnhandled: (_id: number, error: Error) => {
        reportClientError({
          kind: 'unhandled_rejection',
          message: error?.message ?? String(error),
          stack: error?.stack,
        })
      },
      onHandled: () => {},
    })
  } catch {
    // Optional — if the polyfill module ever moves, this degrades silently
    // rather than crashing startup over a diagnostics feature.
  }
}
