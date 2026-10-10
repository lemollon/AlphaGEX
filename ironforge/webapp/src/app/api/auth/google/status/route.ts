import { NextResponse } from 'next/server'
import { isGoogleOAuthConfigured } from '@/lib/auth/google-oauth'

export const dynamic = 'force-dynamic'

/**
 * Public, no-session probe so /login and /signup can hide "Continue with Google"
 * entirely on a deployment where GOOGLE_CLIENT_ID/SECRET are not set, rather than
 * show a button whose click 404s at /api/auth/google/start.
 */
export async function GET() {
  return NextResponse.json({ enabled: isGoogleOAuthConfigured() })
}
