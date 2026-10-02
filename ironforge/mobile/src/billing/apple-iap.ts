/**
 * Apple In-App Purchase (StoreKit 2 via expo-iap 5.6.x) — iOS only, the SECOND
 * billing rail (Apple IAP handoff, "Mobile contract"). Stripe stays the rail for web
 * and Android; this module drives the native purchase sheet on iOS and reconciles it
 * against the server, which is the sole source of truth for entitlement.
 *
 * expo-iap conforms to the OpenIAP spec. A StoreKit 2 purchase carries its signed
 * transaction as `purchase.purchaseToken` — the SDK's own doc comment on
 * `PurchaseCommon.purchaseToken` calls it the "Unified purchase token (iOS JWS,
 * Android purchaseToken)". On iOS that string IS the JWS `POST /api/billing/apple/
 * verify` expects; there is no separate JWS getter to reach for.
 *
 * Manual (non-`useIAP`) integration by design — the caller (`app/enroll/billing.tsx`)
 * is one screen, not a whole-app provider tree, and `initIap`/`teardownIap` here mirror
 * exactly what the `useIAP()` hook would otherwise do on mount/unmount.
 */
import {
  initConnection,
  endConnection,
  fetchProducts,
  requestPurchase,
  finishTransaction,
  getAvailablePurchases,
  restorePurchases as restorePurchasesNative,
  purchaseUpdatedListener,
  purchaseErrorListener,
  isUserCancelledError,
  getUserFriendlyErrorMessage,
  type Purchase,
  type PurchaseIOS,
  type ProductSubscription,
} from 'expo-iap'
import { api, ApiError } from '@/api/client'
import { APPLE_PRODUCTS } from './apple-products'

const PRODUCT_IDS = APPLE_PRODUCTS.map((p) => p.productId)

export interface IapProduct {
  productId: string
  title: string
  /** StoreKit-localized price string, e.g. "$50.00" — never format the raw USD
   *  number ourselves, the store's locale/currency rendering is the one Apple's
   *  disclosure requires. */
  displayPrice: string
}

/** True for a StoreKit (Apple) purchase — the discriminator for the `Purchase` union,
 *  since only `store` is common to both platform shapes. */
export function isAppleStorePurchase(purchase: Purchase): purchase is PurchaseIOS {
  return purchase.store === 'apple'
}

/** The StoreKit 2 signed transaction (JWS) for an Apple purchase, or null when this
 *  is not one (Android) or the store somehow returned no token. */
export function jwsFor(purchase: Purchase): string | null {
  if (!isAppleStorePurchase(purchase)) return null
  return purchase.purchaseToken ?? null
}

/**
 * When restore (or a replayed listener event) surfaces more than one transaction for
 * the same product — an expired trial plus the real renewal, a re-purchase after a
 * refund — only the one with the latest expiry is worth sending to the server;
 * verifying a stale one first would let a stale status win the upsert.
 */
export function pickNewestPerProduct(purchases: PurchaseIOS[]): PurchaseIOS[] {
  const byProduct = new Map<string, PurchaseIOS>()
  for (const p of purchases) {
    const existing = byProduct.get(p.productId)
    if (!existing || (p.expirationDateIOS ?? 0) > (existing.expirationDateIOS ?? 0)) {
      byProduct.set(p.productId, p)
    }
  }
  return Array.from(byProduct.values())
}

interface VerifyOutcome {
  ok: boolean
  reason?: 'no_jws' | 'network' | 'rejected'
  message?: string
}

/** POST the JWS to the verify route. One retry on a network failure (fetch threw, no
 *  response at all); a response the server actually sent back (ApiError — wrong
 *  bundle, unknown product, foreign account) is a rejection, not a network problem,
 *  and is never retried. */
async function verifyWithRetry(jws: string): Promise<VerifyOutcome> {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      await api('/api/billing/apple/verify', { method: 'POST', body: { jws } })
      return { ok: true }
    } catch (e) {
      if (e instanceof ApiError) {
        return { ok: false, reason: 'rejected', message: e.humanMessage }
      }
      if (attempt === 1) {
        return { ok: false, reason: 'network' }
      }
      // one retry, then give up
    }
  }
  return { ok: false, reason: 'network' }
}

/**
 * The purchase-updated handler: verify, then finish — and ONLY finish once the
 * server has accepted the transaction. `onError` is the caller's toast/Alert; a
 * missing JWS or a server rejection surfaces through it, a network failure surfaces
 * through it too (after the one retry above), and the transaction stays unfinished
 * in every one of those cases so StoreKit replays it on next launch instead of it
 * being silently lost.
 */
export async function handlePurchaseUpdated(
  purchase: Purchase,
  onError?: (message: string) => void,
): Promise<VerifyOutcome> {
  const jws = jwsFor(purchase)
  if (!jws) {
    onError?.('This purchase could not be verified. Please contact support.')
    return { ok: false, reason: 'no_jws' }
  }

  const result = await verifyWithRetry(jws)
  if (!result.ok) {
    onError?.(
      result.reason === 'network'
        ? 'Could not reach IronForge to confirm your purchase. It will retry automatically.'
        : (result.message ?? 'Your purchase could not be applied to this account.'),
    )
    return result
  }

  // Never leave a transaction unfinished after the server accepted it.
  await finishTransaction({ purchase, isConsumable: false })
  return result
}

/**
 * expo-iap's public `PurchaseError` type (re-exported from types.ts) and the
 * parameter `purchaseErrorListener` actually delivers (utils/errorMapping.ts) are two
 * different, structurally incompatible declarations in the installed package —
 * extracted straight off the listener's own signature so this always matches whatever
 * shape it really hands over, rather than guessing which `PurchaseError` was meant.
 */
type ListenerError = Parameters<Parameters<typeof purchaseErrorListener>[0]>[0]

/** User-cancelled is silent by design (spec: "user-cancelled = silent"). Every other
 *  purchase error surfaces through `onError` with expo-iap's own user-facing copy. */
export function handlePurchaseError(error: ListenerError, onError?: (message: string) => void): void {
  if (isUserCancelledError(error)) return
  onError?.(getUserFriendlyErrorMessage(error))
}

let listenersAttached = false

/**
 * Connect to the store and attach the purchase-updated / purchase-error listeners.
 * Idempotent — safe to call on every mount of the billing screen; the listeners are
 * only attached once per app session.
 *
 * `onVerified` fires after a purchase has been verified AND finished, so the caller
 * can refresh membership state and continue the enrollment flow exactly like
 * "I already subscribed on the web" does.
 */
export async function initIap(callbacks: {
  onError?: (message: string) => void
  onVerified?: () => void
} = {}): Promise<void> {
  await initConnection()
  if (listenersAttached) return
  listenersAttached = true

  purchaseUpdatedListener((purchase) => {
    handlePurchaseUpdated(purchase, callbacks.onError)
      .then((result) => {
        if (result.ok) callbacks.onVerified?.()
      })
      .catch(() => {
        callbacks.onError?.('Something went wrong finishing your purchase. Please contact support.')
      })
  })

  purchaseErrorListener((error) => {
    handlePurchaseError(error, callbacks.onError)
  })
}

/** Close the store connection. The listeners stay attached for the app session (per
 *  expo-iap convention) — this just releases the connection when the billing screen
 *  unmounts. */
export async function teardownIap(): Promise<void> {
  await endConnection()
}

/** Fetch the four subscription products with StoreKit-localized pricing. */
export async function loadProducts(): Promise<IapProduct[]> {
  const products = (await fetchProducts({ skus: PRODUCT_IDS, type: 'subs' })) as ProductSubscription[] | null
  return (products ?? []).map((p) => ({
    productId: p.id,
    title: p.title,
    displayPrice: p.displayPrice,
  }))
}

/**
 * Start a purchase. The RESULT arrives through the `purchaseUpdatedListener` attached
 * in `initIap`, never through this promise — `requestPurchase` only dispatches the
 * request (or throws synchronously on validation failure).
 *
 * `userId` becomes StoreKit's `appAccountToken`, matching a transaction back to a
 * customer server-side without a receipt round trip.
 */
export async function purchase(productId: string, userId: string): Promise<void> {
  await requestPurchase({
    type: 'subs',
    request: { apple: { sku: productId, appAccountToken: userId } },
  })
}

export interface RestoreResult {
  verified: number
  failed: number
}

/**
 * Restore Purchases: sync with the App Store, then re-verify every distinct product
 * this Apple ID currently holds (newest transaction per product wins — see
 * `pickNewestPerProduct`). Used both for "I bought this on another device" and for
 * StoreKit purchases the purchase-updated listener never saw (e.g. a family-shared
 * subscription).
 */
export async function restorePurchases(): Promise<RestoreResult> {
  await restorePurchasesNative()
  const available = await getAvailablePurchases()
  const newest = pickNewestPerProduct(available.filter(isAppleStorePurchase))

  let verified = 0
  let failed = 0
  for (const p of newest) {
    const jws = jwsFor(p)
    if (!jws) {
      failed++
      continue
    }
    const result = await verifyWithRetry(jws)
    if (result.ok) verified++
    else failed++
  }
  return { verified, failed }
}
