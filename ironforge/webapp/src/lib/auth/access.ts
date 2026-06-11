/** Paths reachable without a session. */
const PUBLIC_EXACT = new Set<string>([
  '/login',
  '/signup',
  '/pricing',
  '/ops/login',
  '/forgot-password',
  '/reset-password',
  '/api/auth/login',
  '/api/auth/signup',
  '/api/auth/verify',
  '/api/auth/resend-verification',
  '/api/auth/logout',
  '/api/auth/seed',
  '/api/auth/customer-login',
  '/api/auth/customer-logout',
  '/api/auth/customer-me',
  '/api/auth/forgot-password',
  '/api/auth/reset-password',
  '/api/health',
])

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_EXACT.has(pathname)
}

export type AccessDecision = 'allow' | 'redirect-login' | 'unauthorized'

export function decideAccess(opts: {
  pathname: string
  isApi: boolean
  hasSession: boolean
  hasServiceToken: boolean
}): AccessDecision {
  if (opts.hasServiceToken) return 'allow'
  if (isPublicPath(opts.pathname)) return 'allow'
  if (opts.hasSession) return 'allow'
  return opts.isApi ? 'unauthorized' : 'redirect-login'
}
