import type { SessionOptions } from 'iron-session'

export interface SessionData {
  userId?: number
  username?: string
  name?: string
  person?: string | null
}

export const SESSION_COOKIE = 'ironforge_session'

export const sessionOptions: SessionOptions = {
  password: process.env.IRONFORGE_SESSION_SECRET || '',
  cookieName: SESSION_COOKIE,
  cookieOptions: {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: '/',
  },
}

/** Constant-time string compare that works on the Edge runtime (no Node crypto). */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return diff === 0
}

/** True when the request header carries the configured internal service token. */
export function hasValidServiceToken(headerValue: string | null | undefined): boolean {
  const expected = process.env.IRONFORGE_SERVICE_TOKEN
  if (!expected || !headerValue) return false
  return safeEqual(headerValue, expected)
}

/** Headers for internal server-to-server calls to our own gated routes. */
export function serviceHeaders(): Record<string, string> {
  return { 'x-ironforge-service': process.env.IRONFORGE_SERVICE_TOKEN || '' }
}
