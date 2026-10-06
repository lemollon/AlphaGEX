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
 *   root          C=US, O=Google Trust Services LLC, CN=GTS Root R4  <- backup pin
 *                 issuer: C=BE, O=GlobalSign nv-sa, CN=GlobalSign Root CA
 *
 * The PRIMARY pin targets the INTERMEDIATE (WE1), not the leaf: Google
 * reissues ironforge.trade's leaf certificate every ~90 days from the same
 * WE1 intermediate, so pinning the leaf would brick the app on every routine
 * renewal.
 *
 * ---- Why FOUR backup pins, not one ----
 *
 * Render (IronForge's host) can issue ironforge.trade's certificate from
 * EITHER Google Trust Services OR Let's Encrypt, depending on which ACME
 * provider handles the renewal — this is Render's own infra choice, not
 * something this app controls or can predict per-renewal. Pinning only the
 * current GTS chain would mean the very next renewal, if it happened to land
 * on Let's Encrypt, bricks the app outright. So the backup set covers BOTH
 * CA families' roots, not just the current one's:
 *
 *   - GTS_ROOT_R4   — anchors WE1 AND its ECDSA sibling intermediate WE2
 *   - GTS_ROOT_R1   — anchors Google Trust Services' RSA intermediates
 *                     (WR1/WR2), in case Google ever issues the RSA leaf
 *                     instead of the current ECDSA one
 *   - ISRG_ROOT_X1  — anchors Let's Encrypt's RSA intermediates (R-series),
 *                     the chain most clients (incl. older Android) see
 *   - ISRG_ROOT_X2  — anchors Let's Encrypt's ECDSA intermediates (E-series)
 *
 * All four were downloaded as the actual root certificates and hashed
 * locally — never copied from memory or a third-party list:
 *
 *   GTS Root R4   -> https://pki.goog/repo/certs/gtsr4.pem  (same cert seen
 *                    in this domain's live chain above)
 *   GTS Root R1   -> https://pki.goog/repo/certs/gtsr1.pem
 *   ISRG Root X1  -> https://letsencrypt.org/certs/isrgrootx1.pem
 *   ISRG Root X2  -> https://letsencrypt.org/certs/isrg-root-x2.pem
 *
 * Pinning ROOTS (not a second tier of intermediates) for the backups means
 * this set survives ANY intermediate rotation within either CA, and even
 * Render switching ACME providers between GTS and Let's Encrypt on a future
 * renewal — the only way all five pins fail at once is ironforge.trade's
 * certificate coming from a CA outside both families entirely, which would
 * itself be a deliberate infra change worth knowing about.
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
 * For a CA's published root (rather than a leaf's live chain), download the
 * root's own PEM from that CA's repository (see the URLs above) and run the
 * same `openssl x509 -in root.pem -pubkey ...` pipeline against it.
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
const GTS_ROOT_R1_SPKI = 'hxqRlPTu1bMS/0DITB1SSu0vd4u/8l8TjPgfaAp63Gc='
const ISRG_ROOT_X1_SPKI = 'C5+lpZ7tcVwmwQIMcRtPbsQtWLABXhQzejna0wHFr8M='
const ISRG_ROOT_X2_SPKI = 'diGVwiVYbubAI3RW4hB9xU8e/CH2GnkuvVFZE8zmgzI='

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
        publicKeyHashes: [
          GTS_WE1_INTERMEDIATE_SPKI,
          GTS_ROOT_R4_SPKI,
          GTS_ROOT_R1_SPKI,
          ISRG_ROOT_X1_SPKI,
          ISRG_ROOT_X2_SPKI,
        ],
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
