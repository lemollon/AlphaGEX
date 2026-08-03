/**
 * Sign-in, biometric unlock, and the foreground lock (APP-007 / APP-008 / APP-010).
 *
 * The lock is a UI gate, not a security boundary — the tokens are already in the
 * Keychain and the OS protects them. What it actually buys is that a handed-over or
 * shoulder-surfed phone does not display someone's balance, which is the realistic
 * threat for a trading app.
 */
import * as LocalAuthentication from 'expo-local-authentication'
import { setItem, getItem } from '@/api/storage'
import { api, apiPublic, saveTokens, clearTokens, hasSession, AuthExpiredError } from '@/api/client'
import type { MobileMe } from '@/api/types'

const BIOMETRIC_PREF_KEY = 'ironforge.biometricEnabled'

export interface SessionPolicy {
  version: number
  accessTtlSec: number
  refreshTtlSec: number
  refreshIdleTtlSec: number
  foregroundLockSec: number
  stepUpTtlSec: number
  stepUpActions: string[]
  biometricUnlockAllowed: boolean
  rotateRefreshOnUse: boolean
}

interface LoginResponse {
  ok: boolean
  accessToken: string
  refreshToken: string
  customer: { id: string; email: string; emailVerified: boolean; onboardingStep: string }
  next: string
  policy: SessionPolicy
}

export async function signIn(
  email: string,
  password: string,
  device: { deviceId?: string; platform?: string; appVersion?: string } = {},
): Promise<LoginResponse> {
  const res = await apiPublic<LoginResponse>('/api/auth/mobile/login', {
    email,
    password,
    ...device,
  })
  await saveTokens({ accessToken: res.accessToken, refreshToken: res.refreshToken })
  return res
}

export async function signOut(): Promise<void> {
  const refreshToken = await getItem('ironforge.refreshToken')
  // Best-effort server-side revoke, then ALWAYS clear locally. If the network call
  // fails we must still forget the tokens — a "sign out" that leaves credentials on
  // the device because the request timed out is the worst possible outcome.
  if (refreshToken) {
    await api('/api/auth/mobile/logout', { method: 'POST', body: { refreshToken } }).catch(
      () => {},
    )
  }
  await clearTokens()
}

export async function fetchMe(): Promise<MobileMe> {
  return api<MobileMe>('/api/auth/mobile/me')
}

// ── Biometrics (APP-008) ──

export async function biometricsAvailable(): Promise<boolean> {
  const [hasHardware, enrolled] = await Promise.all([
    LocalAuthentication.hasHardwareAsync(),
    LocalAuthentication.isEnrolledAsync(),
  ])
  return hasHardware && enrolled
}

export async function isBiometricEnabled(): Promise<boolean> {
  return (await getItem(BIOMETRIC_PREF_KEY)) === 'true'
}

export async function setBiometricEnabled(on: boolean): Promise<void> {
  await setItem(BIOMETRIC_PREF_KEY, on ? 'true' : 'false')
}

/**
 * Prompt for Face ID / fingerprint.
 *
 * Falls back to the device passcode rather than failing outright, and returns false on
 * cancel so the caller keeps the app locked instead of assuming success. APP-008 also
 * requires that failure never exposes a password or a raw token — nothing here touches
 * either; the tokens stay in the Keychain regardless of the outcome.
 */
export async function unlockWithBiometrics(): Promise<boolean> {
  if (!(await biometricsAvailable())) return false
  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Unlock IronForge',
    fallbackLabel: 'Use passcode',
    disableDeviceFallback: false,
    cancelLabel: 'Cancel',
  })
  return result.success
}

/**
 * Should the app re-prompt after being backgrounded?
 * Policy-driven (foregroundLockSec) so the timeout can be tightened server-side
 * without an app-store release.
 */
export function shouldLock(
  backgroundedAtMs: number | null,
  policy: Pick<SessionPolicy, 'foregroundLockSec'>,
  now: number = Date.now(),
): boolean {
  if (backgroundedAtMs == null) return false
  return now - backgroundedAtMs > policy.foregroundLockSec * 1000
}

export { hasSession, AuthExpiredError }
