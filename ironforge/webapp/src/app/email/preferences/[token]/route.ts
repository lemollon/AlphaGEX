import { NextRequest, NextResponse } from 'next/server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import {
  isPlausibleToken,
  preferenceStateForToken,
  resubscribeByToken,
  unsubscribeByToken,
} from '@/lib/waitlist-drip/sequence'
import { notFoundPage, preferencesPage } from '@/lib/waitlist-drip/pages'

/**
 * /email/preferences/[token] — public, token-addressed (lib/auth/access.ts).
 *
 * GET  → current state for the address behind the token.
 * POST → form body `action=unsubscribe` | `action=resubscribe`, then re-render with a notice.
 *
 * Route Handler, not a page, so GET and POST share the URL printed in the email footer.
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
  return html(preferencesPage(state))
}

export async function POST(req: NextRequest, { params }: { params: { token: string } }) {
  if (!isCustomersDbConfigured() || !isPlausibleToken(params.token)) return html(notFoundPage(), 404)
  const bodyText = await req.text().catch(() => '')
  const action = new URLSearchParams(bodyText).get('action')
  let state = null
  let notice = ''
  try {
    if (action === 'resubscribe') {
      state = await resubscribeByToken(params.token, 'preferences')
      notice = state?.unsubscribed === false ? 'Waitlist emails resumed.' : 'This address cannot be resumed from here. Reply to any IronForge email and we will help.'
    } else if (action === 'unsubscribe') {
      state = await unsubscribeByToken(params.token, 'preferences')
      notice = 'You are unsubscribed from waitlist emails.'
    } else {
      state = await preferenceStateForToken(params.token)
      notice = 'No change made.'
    }
  } catch (e) {
    console.error('[email/preferences] failed:', e)
    state = null
  }
  if (!state) return html(notFoundPage(), 404)
  return html(preferencesPage(state, notice))
}
