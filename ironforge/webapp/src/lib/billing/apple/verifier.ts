/**
 * Apple's SignedDataVerifier, wired to this app's environment/bundle. ONE instance per
 * process (verifying JWS is cheap but the internal public-key cache is worth keeping warm
 * across requests), built lazily so a missing root cert fails the first request that needs
 * it rather than boot.
 *
 * Online checks (revocation + real-time expiry) are OFF for v1 per spec — that requires an
 * App Store Connect key we don't have yet. The cryptographic signature + chain-of-trust
 * check still runs; this only skips the extra network round trip to Apple's OCSP responder.
 */

import { readFileSync } from 'fs'
import path from 'path'
import { SignedDataVerifier, Environment } from '@apple/app-store-server-library'
import { isSandbox } from '@/lib/sandbox'

export const APPLE_IAP_BUNDLE_ID = process.env.APPLE_IAP_BUNDLE_ID?.trim() || 'trade.ironforge.app'

/** App Store Connect's numeric app id — omitted only in the sandbox environment per Apple's own SDK contract. */
const APPLE_APP_APPLE_ID = 6804037937

/**
 * 'Production' | 'Sandbox', explicit override via APPLE_IAP_ENVIRONMENT. Falls back to the
 * SAME prod/sandbox switch the rest of this codebase already uses (lib/sandbox.ts,
 * IRONFORGE_ENV=sandbox on the ironforge-sandbox.onrender.com deploy) — so a sandbox Render
 * service verifies against Apple's sandbox environment without needing its own Apple-specific
 * env var set.
 */
export function resolveAppleEnvironment(): Environment {
  const override = process.env.APPLE_IAP_ENVIRONMENT?.trim()
  if (override === 'Sandbox') return Environment.SANDBOX
  if (override === 'Production') return Environment.PRODUCTION
  return isSandbox() ? Environment.SANDBOX : Environment.PRODUCTION
}

function loadRootCertificate(): Buffer {
  // Env override lets a deploy point at the cert without relying on the committed binary
  // surviving Next's standalone file trace (see the fallback note on APPLE_ROOT_CA_PATH).
  const override = process.env.APPLE_ROOT_CA_PATH?.trim()
  const certPath = override || path.join(__dirname, 'AppleRootCA-G3.cer')
  return readFileSync(certPath)
}

let _verifier: SignedDataVerifier | null = null

export function getAppleVerifier(): SignedDataVerifier {
  if (!_verifier) {
    _verifier = new SignedDataVerifier(
      [loadRootCertificate()],
      false, // enableOnlineChecks — no ASC key in v1
      resolveAppleEnvironment(),
      APPLE_IAP_BUNDLE_ID,
      APPLE_APP_APPLE_ID,
    )
  }
  return _verifier
}
