import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db'
import { isConfigured, getQuote, canPlaceLiveOrders, describeLiveGate, resolveEligibleAccounts } from '@/lib/tradier'
import { isNtfyConfigured, isSmsGatewayConfigured, isTwilioConfigured, isDiscordConfigured } from '@/lib/sms'

export const dynamic = 'force-dynamic'

/**
 * GET /api/health
 *
 * Health check endpoint. Tests PostgreSQL and Tradier connectivity.
 */
export async function GET() {
  const checks: Record<string, { status: string; detail?: string }> = {}

  // PostgreSQL connectivity
  try {
    const rows = await dbQuery('SELECT NOW() as ts')
    checks.database = { status: 'ok', detail: rows[0]?.ts }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    checks.database = { status: 'error', detail: msg }
  }

  // Tradier connectivity
  if (isConfigured()) {
    try {
      const quote = await getQuote('SPY')
      checks.tradier = {
        status: quote ? 'ok' : 'error',
        detail: quote ? `SPY $${quote.last}` : 'No quote returned',
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      checks.tradier = { status: 'error', detail: msg }
    }
  } else {
    checks.tradier = { status: 'not_configured', detail: 'TRADIER_API_KEY not set' }
  }

  const allOk = Object.values(checks).every((c) => c.status === 'ok' || c.status === 'not_configured')

  // WHICH PROCESS AM I, AND WOULD I PLACE A REAL ORDER?
  //
  // 🚨 IronForge runs the same image as several Render services and only ONE of
  // them scans (SCANNER_ENABLED). On 2026-08-19 FLAME's arm env was set on the
  // operator console, which never scans, while the scanning service had no FLAME
  // creds — so /flame/preview-order answered `live_orders_allowed: true` about a
  // process that cannot trade, and the bot ran paper-only in silence. Arming is
  // per-service, so the answer has to come from the service you ask.
  //
  // Booleans and condition NAMES only — never a credential — so this stays safe
  // on an unauthenticated endpoint.
  const scannerEnabled = process.env.SCANNER_ENABLED === 'true'
  const bots = ['flame', 'spark', 'inferno', 'kindle']
  const process_identity = {
    mode: process.env.IRONFORGE_MODE ?? 'both',
    scanner_enabled: scannerEnabled,
    // The only place an order is ever placed is the scan loop, so a service with
    // the arm env but no scanner trades nothing, however green it looks.
    places_orders: scannerEnabled,
    live_gates: Object.fromEntries(
      bots.map((b) => [b, canPlaceLiveOrders(b) ? 'armed' : describeLiveGate(b)]),
    ),
    // HOW MANY PRODUCTION ACCOUNTS WOULD AN ORDER ACTUALLY REACH?
    //
    // 🚨 "armed" was never the whole answer. On 2026-08-20 FLAME reported
    // `armed` here, reached the live branch, and filled nothing: the order path
    // composes its accounts from ironforge_accounts, and FLAME's live account is
    // credentialed by env, so the eligible list held three sandbox accounts and
    // no production one. `live:no_fill` — indistinguishable from a broker
    // rejection, and only discoverable by waiting for the 13:05 CT entry minute.
    //
    // So this asks the ORDER PATH'S OWN function (resolveEligibleAccounts) the
    // same question it will answer at the entry minute. armed + 0 is the bug
    // that took a day to see; armed + 1 means an order has somewhere to go.
    // A COUNT, never names or keys — this endpoint is unauthenticated.
    // CAN THIS PROCESS ACTUALLY WAKE SOMEBODY UP?
    //
    // 🚨 Same per-service trap as the arming block above, one floor down. The
    // alert env vars (ALERT_NTFY_TOPIC, ALERT_SMS_GATEWAY_TO, ALERT_DISCORD_WEBHOOK)
    // are set on ironforge-customer, which is where the scanner runs — but
    // /api/sms-test is classified operator-only, so the only test anyone could run
    // answered from ironforge-legacy, which has NONE of them. It reported
    // `sms_configured: false` about a service that never raises an alert, while the
    // service that does was fully wired. Nobody could tell those two apart.
    //
    // 🚨 `reaches_a_phone` deliberately EXCLUDES the Discord webhook. A webhook posts
    // to a channel; it is a RECORD, not an alert. `@here` does not push to a phone —
    // only `<@USER_ID>` does — which is how a whole family of IronForge alerts sat
    // unread. Counting Discord here would restate exactly that mistake in a field
    // whose entire job is to say whether anyone will be woken.
    //
    // Booleans only, same rule as the rest of this endpoint: never a topic, number
    // or key. A topic name is a credential — anyone holding it can push to the
    // subscriber — so it must never appear here.
    alerting: {
      ntfy: isNtfyConfigured(),
      sms_gateway: isSmsGatewayConfigured(),
      twilio: isTwilioConfigured(),
      discord_webhook: isDiscordConfigured(),
      discord_user_id: !!process.env.DISCORD_ALERT_USER_ID?.trim(),
      reaches_a_phone: isNtfyConfigured() || isSmsGatewayConfigured() || isTwilioConfigured(),
    },
    live_accounts: Object.fromEntries(
      await Promise.all(bots.map(async (b) => {
        try {
          const accts = await resolveEligibleAccounts(b)
          return [b, accts.filter((a) => a.type === 'production').length] as const
        } catch {
          return [b, null] as const
        }
      })),
    ),
  }

  return NextResponse.json(
    { status: allOk ? 'ok' : 'degraded', checks, process: process_identity },
    { status: allOk ? 200 : 503 },
  )
}
