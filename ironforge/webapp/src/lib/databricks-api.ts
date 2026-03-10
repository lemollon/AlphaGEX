/**
 * Helper for proxying requests to the Databricks FastAPI (ironforge_api.py).
 *
 * The Databricks API URL is configured via IRONFORGE_API_URL env var.
 * This is a server-side only module — never imported from client components.
 */

const BASE_URL = process.env.IRONFORGE_API_URL || ''

export function databricksUrl(path: string): string {
  if (!BASE_URL) {
    throw new Error('IRONFORGE_API_URL environment variable is not set')
  }
  // Strip trailing slash from base, ensure path starts with /
  const base = BASE_URL.replace(/\/$/, '')
  const p = path.startsWith('/') ? path : `/${path}`
  return `${base}${p}`
}

/**
 * Fetch from the Databricks API and return the JSON response.
 * Throws on network errors or non-2xx responses.
 */
export async function databricksFetch(
  path: string,
  init?: RequestInit,
): Promise<any> {
  const url = databricksUrl(path)
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Databricks API ${res.status}: ${text}`)
  }
  return res.json()
}
