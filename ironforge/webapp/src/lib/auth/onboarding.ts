/**
 * Onboarding handoff token (sub-project F).
 *
 * After email verification a customer has no login session yet (customer auth is a
 * later sub-project), so we issue a short-lived HMAC-signed cookie that lets them —
 * and only them — reach the /onboarding/* funnel. It carries the customer user id and
 * an expiry; it is NOT a login session and grants nothing but onboarding access.
 *
 * Signed/verified with Web Crypto (SHA-256 HMAC) so the SAME code runs in the Edge
 * middleware, the Node verify route, and the Node onboarding page. Secret =
 * IRONFORGE_SESSION_SECRET (shared with iron-session). When the secret is unset,
 * verification returns null (fail-closed) and signing throws.
 */

import { safeEqual } from '@/lib/auth/session'

export const ONBOARDING_COOKIE = 'ironforge_onboarding'
export const ONBOARDING_TTL_MS = 7 * 24 * 60 * 60 * 1000 // 7 days to finish onboarding

export interface OnboardingClaims {
  uid: string
  exp: number
}

const encoder = new TextEncoder()

function b64urlFromBytes(bytes: Uint8Array): string {
  let bin = ''
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function b64urlEncode(s: string): string {
  return b64urlFromBytes(encoder.encode(s))
}

function b64urlDecode(s: string): string {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/')
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new TextDecoder().decode(bytes)
}

async function hmacB64url(secret: string, data: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  )
  const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(data))
  return b64urlFromBytes(new Uint8Array(sig))
}

export async function signOnboardingToken(uid: string, now: number = Date.now()): Promise<string> {
  const secret = process.env.IRONFORGE_SESSION_SECRET
  if (!secret) throw new Error('IRONFORGE_SESSION_SECRET is not set')
  const payload = b64urlEncode(JSON.stringify({ uid, exp: now + ONBOARDING_TTL_MS }))
  const sig = await hmacB64url(secret, payload)
  return `${payload}.${sig}`
}

export async function verifyOnboardingToken(
  token: string | undefined | null,
  now: number = Date.now(),
): Promise<OnboardingClaims | null> {
  const secret = process.env.IRONFORGE_SESSION_SECRET
  if (!secret || !token) return null
  const dot = token.indexOf('.')
  if (dot < 1) return null
  const payload = token.slice(0, dot)
  const sig = token.slice(dot + 1)
  const expected = await hmacB64url(secret, payload)
  if (!safeEqual(sig, expected)) return null
  try {
    const claims = JSON.parse(b64urlDecode(payload)) as OnboardingClaims
    if (!claims || typeof claims.uid !== 'string' || !claims.uid) return null
    if (typeof claims.exp !== 'number' || now >= claims.exp) return null
    return claims
  } catch {
    return null
  }
}

export function onboardingCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    maxAge: Math.floor(ONBOARDING_TTL_MS / 1000),
    path: '/',
  }
}
