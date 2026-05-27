import { NextRequest } from 'next/server'
import { proxyGet } from '@/lib/gex/proxy'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams
  const symbol = sp.get('symbol') || 'SPY'
  const expiration = sp.get('expiration')
  const qs = new URLSearchParams({ symbol })
  if (expiration) qs.set('expiration', expiration)
  return proxyGet(`/api/watchtower/gex-analysis?${qs.toString()}`)
}
