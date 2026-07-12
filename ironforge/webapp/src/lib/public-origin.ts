import type { NextRequest } from 'next/server'

/**
 * Public origin for URLs that leave the server (emails, OAuth redirects, external
 * callbacks). On Render, `req.nextUrl.origin` resolves to the internal bind address
 * (https://0.0.0.0:3000), so links built from it are dead for customers — the same
 * trap documented in api/builder/health. IRONFORGE_PUBLIC_URL wins (custom domain),
 * then Render's auto-injected RENDER_EXTERNAL_URL, then the request origin (local dev).
 */
export function publicOrigin(req: NextRequest): string {
  const configured = process.env.IRONFORGE_PUBLIC_URL || process.env.RENDER_EXTERNAL_URL
  return (configured || req.nextUrl.origin).replace(/\/$/, '')
}
