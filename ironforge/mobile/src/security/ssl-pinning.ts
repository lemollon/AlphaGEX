/**
 * Public-key (SPKI) pinning for IronForge's own API host — native security
 * requirement from the dev handoff's mobile Security checklist ("Certificate
 * pinning for the API domain").
 *
 * Scope is deliberately ONE host: `ironforge.trade` (api/client.ts's
 * `API_BASE`, which EXPO_PUBLIC_API_BASE can only ever point at a different
 * environment of this same first-party backend, never a third party). Apple,
 * Stripe, Expo's OTA update server, and Sentry are NEVER pinned — this app
 * does not own their certificate chains, so pinning them would mean a
 * renewal on THEIR side (not ours) bricks every installed copy of the app
 * with no way to recover. Those hosts are reached through their own SDKs
 * (StoreKit, expo-updates, @sentry/react-native) or the system browser
 * (`WebBrowser.openBrowserAsync` for Stripe's hosted portal), never through
 * `fetch`, so excluding them here is simply not listing them below — nothing
 * else to configure.
 *
 * ---- Current chain (captured 2026-10-06) ----
 *
 *   `echo | openssl s_client -connect ironforge.trade:443 \
 *      -servername ironforge.trade -showcerts`
 *
 *   leaf          CN=ironforge.trade
 *                 issuer: C=US, O=Google Trust Services, CN=WE1
 *   intermediate  C=US, O=Google Trust Services, CN=WE1        <- PRIMARY pin
 *                 issuer: C=US, O=Google Trust Services LLC, CN=GTS Root R4
 *   root          C=US, O=Google Trust Services LLC, CN=GTS Root R4  <- BACKUP pin
 *                 issuer: C=BE, O=GlobalSign nv-sa, CN=GlobalSign Root CA
 *
 * The PRIMARY pin targets the INTERMEDIATE (WE1), not the leaf: Google
 * reissues ironforge.trade's leaf certificate every ~90 days from the same
 * WE1 intermediate, so pinning the leaf would brick the app on every routine
 * renewal. The BACKUP pin targets the ROOT (GTS Root R4) rather than a second
 * intermediate: GTS Root R4 is the shared anchor for WE1 AND its sibling
 * intermediate WE2, so this backup also survives Google moving issuance from
 * WE1 to WE2, which is the one rotation a same-leaf-same-intermediate pin set
 * would NOT survive. Only a deliberate move off Google Trust Services
 * entirely (not a renewal) breaks both pins at once.
 *
 * ---- Rotation ----
 *
 * If pinning starts failing (customers see "Secure connection failed"),
 * re-fetch the live chain and recompute SPKI hashes for the cert you intend
 * to pin — NEVER hand-copy a hash from anywhere else:
 *
 *   echo | openssl s_client -connect ironforge.trade:443 \
 *     -servername ironforge.trade -showcerts
 *   # paste the relevant -----BEGIN/END CERTIFICATE----- block into cert.pem, then:
 *   openssl x509 -in cert.pem -pubkey -noout \
 *     | openssl pkey -pubin -outform der \
 *     | openssl dgst -sha256 -binary | openssl enc -base64
 *
 * Ship the new hash set alongside the OLD one for one release before dropping
 * the old pair (this is a native change — it ships in a store build, never an
 * OTA update, so there is a real rollout tail of installs still on the prior
 * pin set).
 */
import {
  initializeSslPinning,
  isSslPinningAvailable,
  addSslPinningErrorListener,
} from 'react-native-ssl-public-key-pinning'

const GTS_WE1_INTERMEDIATE_SPKI = 'kIdp6NNEd8wsugYyyIYFsi1ylMCED3hZbSR8ZFsa/A4='
const GTS_ROOT_R4_SPKI = 'mEflZT5enoR1FuXLgYYGqnVEoZvmf9c2bVBpiOjYQ0c='

export const PINNED_API_HOST = 'ironforge.trade'

let initialized = false

/**
 * Call once, as early as possible — app/_layout.tsx's module top, before the
 * sign-in gate's first `hasSession()` fetch and before any enrollment screen
 * (both live OUTSIDE app/(tabs), which is as far as monitoring/sentry.ts's
 * later init point would reach). Idempotent and fails OPEN: Expo Go and any
 * build that predates this native module have no pinning module at all, and
 * this must never crash app startup over an optional hardening layer.
 */
export async function initializeApiPinning(): Promise<void> {
  if (initialized) return
  initialized = true

  if (!isSslPinningAvailable()) {
    console.log('[ssl-pinning] native module unavailable (Expo Go or pre-pinning build) — skipping')
    return
  }

  try {
    await initializeSslPinning({
      [PINNED_API_HOST]: {
        includeSubdomains: false,
        publicKeyHashes: [GTS_WE1_INTERMEDIATE_SPKI, GTS_ROOT_R4_SPKI],
      },
    })
  } catch (err) {
    console.error('[ssl-pinning] failed to initialize', err)
  }
}

/**
 * Subscribes to pin-mismatch failures against OUR host specifically (the
 * library's listener fires for any pinned domain; there is only one here,
 * but the hostname check keeps this correct if a second is ever added).
 * Returns an unsubscribe suitable for useEffect.
 */
export function onApiPinningError(callback: (hostname: string) => void): () => void {
  const sub = addSslPinningErrorListener((error) => {
    if (error.serverHostname === PINNED_API_HOST) callback(error.serverHostname)
  })
  return () => sub.remove()
}
