import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db'
import { isConfigured, getQuote } from '@/lib/tradier'

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

  return NextResponse.json(
    { status: allOk ? 'ok' : 'degraded', checks },
    { status: allOk ? 200 : 503 },
  )
}
