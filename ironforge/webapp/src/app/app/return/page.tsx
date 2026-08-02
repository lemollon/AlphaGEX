import type { Metadata } from 'next'
import { safeAppRoute } from '@/lib/mobile/deep-link'
import ReturnBridge from './ReturnBridge'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Returning to IronForge',
  // A transient hand-off page — keep it out of search results entirely.
  robots: { index: false, follow: false },
}

/**
 * https bridge back into the mobile app.
 *
 * Exists because third parties will not redirect to `ironforge://`: Stripe rejects
 * non-https return URLs when the session is created, and brokerage portals behave the
 * same way. So the mobile round trip is provider → this page → app.
 *
 * When the app is installed, iOS/Android claim this URL as a Universal/App Link and the
 * customer never sees this render at all. It only paints when the association has not
 * verified or the app is missing — which is exactly when a human needs a way forward,
 * hence the visible fallback button rather than a bare redirect.
 *
 * `to` arrives from a third-party redirect, so it is untrusted and passes through
 * safeAppRoute (allowlist, no protocol-relative, no absolute URLs).
 */
export default function AppReturnPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>
}) {
  const raw = typeof searchParams.to === 'string' ? searchParams.to : undefined
  const route = safeAppRoute(raw)

  const passthrough: Record<string, string> = {}
  for (const key of ['status', 'checkout', 'welcome', 'canceled', 'session_id']) {
    const v = searchParams[key]
    if (typeof v === 'string') passthrough[key] = v
  }

  return <ReturnBridge route={route} params={passthrough} />
}
