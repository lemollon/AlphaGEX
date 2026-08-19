import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db'
import { isConfigured, getQuote, canPlaceLiveOrders, describeLiveGate } from '@/lib/tradier'

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
  }

  return NextResponse.json(
    { status: allOk ? 'ok' : 'degraded', checks, process: process_identity },
    { status: allOk ? 200 : 503 },
  )
}
