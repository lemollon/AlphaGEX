import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { publicOrigin } from '@/lib/public-origin'
import { isSnapTradeConfigured } from '@/lib/snaptrade'
import { isTradierOAuthConfigured, tradierBase } from '@/lib/tradier-oauth'
import { isCustomersDbConfigured } from '@/lib/customers-db'

/**
 * Brokerage readiness. Read-only. Answers one question: if a customer clicked
 * "Connect" on the onboarding brokerage step right now, would anything happen?
 *
 * This exists because the failure is invisible from the outside. Both connect routes
 * return a bare 503 when their provider credentials are unset, and the client
 * deliberately renders that as "That connection isn't available right now" — vague on
 * purpose, so it never leaks config state to customers. Correct for them, useless for
 * an operator: an unprovisioned integration and a broken one look identical.
 *
 * On 2026-07-27 the Tradier button failed for exactly this reason and diagnosing it
 * meant reading two route files to find the single 503 branch. This turns that into
 * one call.
 *
 * NEVER returns a secret value — only whether each env var is SET, plus the
 * non-sensitive values an operator needs to finish provisioning (callback URL, scopes,
 * API base). Same contract as /api/ops/billing-readiness.
 *
 * GET /api/ops/brokerage-readiness   (operator session required)
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface ProviderCheck {
  provider: 'tradier' | 'snaptrade'
  label: string
  configured: boolean
  /** Env var NAMES that are unset — never their values. */
  missingEnv: string[]
  /** Register this exact URL with the provider as the OAuth redirect/callback. */
  callbackUrl: string
  scopes?: string
  apiBase?: string
  detail?: string
}

function unset(...names: string[]): string[] {
  return names.filter((n) => !process.env[n]?.trim())
}

export async function GET(req: NextRequest) {
  const ops = await getSession()
  if (!ops.userId) {
    return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
  }

  const origin = publicOrigin(req)
  const customersDbConfigured = isCustomersDbConfigured()

  const tradier: ProviderCheck = {
    provider: 'tradier',
    label: 'Tradier (Recommended)',
    configured: isTradierOAuthConfigured(),
    missingEnv: unset('TRADIER_OAUTH_CLIENT_ID', 'TRADIER_OAUTH_CLIENT_SECRET'),
    callbackUrl: `${origin}/api/onboarding/brokerage/tradier/callback`,
    scopes: 'read,trade',
    apiBase: tradierBase(),
  }
  if (!tradier.configured) {
    tradier.detail =
      'Register an OAuth application with Tradier using the callbackUrl and scopes below, ' +
      'then set the missing env vars. Set TRADIER_OAUTH_BASE=https://sandbox.tradier.com to test against sandbox first.'
  }

  const snaptrade: ProviderCheck = {
    provider: 'snaptrade',
    label: 'All other brokers (SnapTrade hosted portal)',
    configured: isSnapTradeConfigured(),
    missingEnv: unset('SNAPTRADE_CLIENT_ID', 'SNAPTRADE_CONSUMER_KEY'),
    callbackUrl: `${origin}/api/onboarding/brokerage/callback`,
    detail: isSnapTradeConfigured()
      ? undefined
      : 'Set the missing env vars from the SnapTrade dashboard. The customer logs in on SnapTrade\'s portal, so no broker credentials ever reach us.',
  }

  const providers = [tradier, snaptrade]
  const usable = providers.filter((p) => p.configured && customersDbConfigured)

  const blockers: string[] = []
  if (!customersDbConfigured) {
    // Gates BOTH providers — each connect route checks it alongside its own creds.
    blockers.push('Customers DB is not configured — every brokerage connection returns 503 regardless of provider keys.')
  }
  for (const p of providers) {
    if (!p.configured) {
      blockers.push(`${p.provider}: not configured — missing ${p.missingEnv.join(', ')}. Its Connect button returns 503.`)
    }
  }

  return NextResponse.json({
    ok: true,
    // True when a customer can actually start at least one connection.
    ready: usable.length > 0,
    customersDbConfigured,
    publicOrigin: origin,
    summary: usable.length
      ? `${usable.length} of ${providers.length} providers can start a connection.`
      : 'No brokerage provider is configured — every Connect button returns 503 and the customer sees "That connection isn\'t available right now."',
    providers,
    ...(blockers.length ? { blockers } : {}),
    note: 'Env changes take effect on service restart; no deploy needed. Customers can still "Skip for now" and finish onboarding.',
  })
}
