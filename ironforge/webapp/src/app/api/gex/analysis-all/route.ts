import { NextRequest } from 'next/server'
import { proxyGet } from '@/lib/gex/proxy'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get('symbol') || 'SPY'
  // Full board can be slow on a cold cache; allow a longer timeout.
  return proxyGet(`/api/watchtower/gex-analysis/all?symbol=${encodeURIComponent(symbol)}`, 60000)
}
