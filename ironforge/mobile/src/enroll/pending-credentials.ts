/**
 * In-memory-only holder for the password typed on /enroll/create-account, so
 * /enroll/verify can auto-sign-in once the code is confirmed without asking the
 * customer to retype a password they entered ten seconds ago.
 *
 * Deliberately NOT an expo-router route param: route params are serialized into
 * the navigation state and can surface in deep links, logs, Sentry breadcrumbs,
 * and web URLs — a password must never travel through any of those. This is a
 * plain module-scoped variable instead: never persisted (no secure-store, no
 * AsyncStorage), never logged, gone the moment the process restarts.
 *
 * Contract: create-account calls setPendingPassword() right before navigating;
 * verify reads it once via getPendingPassword() and calls clearPendingPassword()
 * on success or on unmount, so it never outlives the one screen transition that
 * needs it.
 */
let pendingPassword: string | null = null

export function setPendingPassword(password: string): void {
  pendingPassword = password
}

/** Non-destructive read — verify may need it across a resend + retry. */
export function getPendingPassword(): string | null {
  return pendingPassword
}

export function clearPendingPassword(): void {
  pendingPassword = null
}
