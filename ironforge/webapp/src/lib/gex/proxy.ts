// Server-side proxy to the AlphaGEX backend for GEX data.
// Mirrors the fetch+retry pattern in src/lib/blaze/gex-client.ts.

const ALPHAGEX_BASE = process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com'

async function fetchOnce(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { signal: controller.signal, cache: 'no-store' })
  } finally {
    clearTimeout(timeout)
  }
}

/**
 * Proxy a GET to the AlphaGEX backend. Single retry with 1s backoff.
 * Returns a Response with the upstream JSON, or a 502 on failure.
 */
export async function proxyGet(path: string, timeoutMs = 20000): Promise<Response> {
  const url = `${ALPHAGEX_BASE.replace(/\/$/, '')}${path}`
  let resp: Response
  try {
    resp = await fetchOnce(url, timeoutMs)
  } catch {
    await new Promise((r) => setTimeout(r, 1000))
    try {
      resp = await fetchOnce(url, timeoutMs)
    } catch (err) {
      return Response.json(
        { success: false, error: `AlphaGEX proxy error: ${(err as Error).message}` },
        { status: 502 },
      )
    }
  }
  const text = await resp.text()
  return new Response(text, {
    status: resp.status,
    headers: { 'content-type': resp.headers.get('content-type') || 'application/json' },
  })
}
