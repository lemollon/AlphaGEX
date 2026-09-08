import { NextRequest, NextResponse } from 'next/server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { isPlausibleToken, preferenceStateForToken, unsubscribeByToken } from '@/lib/waitlist-drip/sequence'
import { notFoundPage, unsubscribeConfirmPage, unsubscribedPage } from '@/lib/waitlist-drip/pages'

/**
 * /email/unsubscribe/[token] — public, token-addressed (lib/auth/access.ts).
 *
 * GET  → confirmation page showing the current state (a link click must not unsubscribe on
 *        its own: mail scanners prefetch links, and a GET that mutates would unsubscribe
 *        everyone whose corporate filter opened the email).
 * POST → unsubscribe. Accepts the page's form AND RFC 8058 one-click posts from mail
 *        clients (`List-Unsubscribe=One-Click` form body, no page render expected).
 *
 * A Route Handler rather than a page so one URL takes both verbs — see lib/waitlist-drip/pages.ts.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function html(body: string, status = 200): NextResponse {
  return new NextResponse(body, { status, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } })
}

export async function GET(_req: NextRequest, { params }: { params: { token: string } }) {
  if (!isCustomersDbConfigured() || !isPlausibleToken(params.token)) return html(notFoundPage(), 404)
  const state = await preferenceStateForToken(params.token).catch(() => null)
  if (!state) return html(notFoundPage(), 404)
  return html(unsubscribeConfirmPage(state, `/email/preferences/${params.token}`))
}

export async function POST(req: NextRequest, { params }: { params: { token: string } }) {
  if (!isCustomersDbConfigured() || !isPlausibleToken(params.token)) return html(notFoundPage(), 404)
  const bodyText = await req.text().catch(() => '')
  const oneClick = /List-Unsubscribe=One-Click/i.test(bodyText)
  const state = await unsubscribeByToken(params.token, oneClick ? 'one-click' : 'link').catch((e) => {
    console.error('[email/unsubscribe] failed:', e)
    return null
  })
  if (!state) return html(notFoundPage(), 404)
  if (oneClick) return NextResponse.json({ ok: true })
  return html(unsubscribedPage(state, `/email/preferences/${params.token}`))
}
