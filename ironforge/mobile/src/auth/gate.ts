/**
 * Pure routing-gate logic for app/_layout.tsx's auth redirect. Extracted so the
 * "auth group" segment set is unit-testable without mounting the full layout
 * (AppState, useFonts, the router) — same pattern as lock.ts for the lock state machine.
 *
 * "Auth group" drives TWO behaviors in the gate, both now covering the same segments:
 * - signed OUT on one of these segments → never bounced to /sign-in (that would make
 *   password recovery unreachable for a locked-out customer)
 * - signed IN on one of these segments → bounced to '/' (seeing a sign-in/reset form
 *   while already authenticated is never the right state)
 */
const AUTH_GROUP_SEGMENTS = new Set([
  'sign-in',
  // Reached from /sign-in's "Forgot password?" link, and from the emailed reset deep
  // link — a locked-out customer cannot be signed in to follow either path. Previously
  // missing here, so both screens were unreachable while signed out: the gate bounced
  // straight back to /sign-in before either could render.
  'forgot-password',
  'reset-password',
])

/** True if this top-level route segment is part of the sign-in/password-recovery group. */
export function isAuthGroupSegment(segment: string | undefined): boolean {
  return segment != null && AUTH_GROUP_SEGMENTS.has(segment)
}
