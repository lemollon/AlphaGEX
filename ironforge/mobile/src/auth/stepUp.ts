/**
 * Face ID + password step-up (APP-010 / mobile fidelity #273) — the gate in front of
 * billing and brokerage changes: cancelling the membership (delete-account) and
 * disconnecting a brokerage connection (BrokerageSection).
 *
 * Two layers, in order, matching api/auth/mobile/reauth's own doc comment ("a
 * fingerprint proves the phone's owner is present, not that the account holder
 * authorised a money-moving action"):
 *
 *   1. Face ID / fingerprint, if enrolled and enabled in Account — a fast local
 *      presence check. A cancel or failure here stops the whole flow; it is never
 *      skipped silently.
 *   2. The account password, traded at POST /api/auth/mobile/reauth for a real
 *      step-up token (MOBILE_SESSION_POLICY.stepUpTtlSec, 5 minutes). This is the
 *      token the server actually requires — see lib/auth/mobile-step-up.ts on the
 *      webapp — biometrics alone never mint one.
 *
 * A plain pub/sub bus + host component, same shape as notifications/toast.ts: the
 * caller is deep inside an action handler (disconnect, delete-account) with no
 * reason to otherwise touch React state, and `requestStepUp()` returns a Promise so
 * the caller can simply `await` the token (or null on cancel/failure) inline.
 */
import { biometricsAvailable, isBiometricEnabled, unlockWithBiometrics } from '@/auth/session'

export interface StepUpRequest {
  id: number
  action: string
  resolve: (token: string | null) => void
}

type Listener = (req: StepUpRequest) => void

let nextId = 1
let listeners: Listener[] = []

/**
 * Ask for a step-up token for `action` (one of MOBILE_SESSION_POLICY.stepUpActions —
 * not type-checked here since the server is the source of truth for that list).
 * Resolves with the token on success, or `null` if the person cancels at any point.
 */
export function requestStepUp(action: string): Promise<string | null> {
  return new Promise((resolve) => {
    const req: StepUpRequest = { id: nextId++, action, resolve }
    listeners.forEach((l) => l(req))
  })
}

export function subscribeStepUp(listener: Listener): () => void {
  listeners.push(listener)
  return () => {
    listeners = listeners.filter((l) => l !== listener)
  }
}

/** Face ID / fingerprint gate — true to proceed to the password step, false to abort. */
export async function biometricPresenceCheck(): Promise<boolean> {
  const [enabled, available] = await Promise.all([isBiometricEnabled(), biometricsAvailable()])
  if (!enabled || !available) return true // nothing enrolled — fall straight through to password
  return unlockWithBiometrics()
}
