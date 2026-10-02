import { NextResponse } from 'next/server'
import { getAfternoonSpreadSummary } from '@/lib/afternoon-spread-tracker'

export const dynamic = 'force-dynamic'

/**
 * Operator-only visibility for the "dynamic hedge V2" paper research tracker
 * (AFTERNOON_SPREAD_PAPER). READ-ONLY — this route never places, closes, or
 * cancels anything; see lib/afternoon-spread-tracker.ts's hard safety rule.
 * Classified operator-only in lib/surface.ts (OPERATOR_API_PREFIXES) — this
 * is a research instrument, not a customer-facing feature.
 */
export async function GET() {
  try {
    const { ledger, totals } = await getAfternoonSpreadSummary()
    return NextResponse.json({ ledger, totals })
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status: 500 })
  }
}
