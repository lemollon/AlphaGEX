/**
 * EMBER Backtester — server-side catch-all proxy that forwards requests to the
 * AlphaGEX Python backend (avoids browser CORS).
 *
 * Proxied endpoints (on AlphaGEX, prefix /api/ember):
 *   POST /api/ember/build          — enqueue a new backtest build (returns immediately)
 *   GET  /api/ember/build/{id}     — poll build status / results
 *   POST /api/ember/evaluate       — evaluate a finished build
 *
 * Usage from the webapp:
 *   fetch('/api/ember/build', { method: 'POST', body: JSON.stringify(payload) })
 *   fetch('/api/ember/build/abc123')
 *   fetch('/api/ember/evaluate', { method: 'POST', body: JSON.stringify(payload) })
 */
import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const ALPHAGEX_BASE = process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com'
const FETCH_TIMEOUT_MS = 60_000

type RouteContext = { params: { path: string[] } }

async function proxyRequest(request: NextRequest, params: { path: string[] }): Promise<NextResponse> {
  const upstreamPath = (params.path ?? []).join('/')
  const search = request.nextUrl.search ?? ''
  const url = `${ALPHAGEX_BASE.replace(/\/$/, '')}/api/ember/${upstreamPath}${search}`

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)

  try {
    const isPost = request.method === 'POST'
    const body = isPost ? await request.text() : undefined

    const resp = await fetch(url, {
      method: request.method,
      signal: controller.signal,
      cache: 'no-store',
      headers: isPost ? { 'content-type': 'application/json' } : {},
      ...(body !== undefined ? { body } : {}),
    })

    const json = await resp.json()
    return NextResponse.json(json, { status: resp.status })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 502 })
  } finally {
    clearTimeout(timer)
  }
}

export async function GET(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context.params)
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context.params)
}
