'use client'

import { useEffect, useState } from 'react'

function GoogleGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" aria-hidden="true">
      <path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.4-.2-2H12v3.8h5.4a4.6 4.6 0 01-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.3z" />
      <path fill="#34A853" d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.6A10 10 0 0012 22z" />
      <path fill="#FBBC05" d="M6.4 14c-.2-.6-.3-1.3-.3-2s.1-1.4.3-2V7.4H3.1a10 10 0 000 9.2z" />
      <path fill="#EA4335" d="M12 5.9c1.5 0 2.8.5 3.8 1.5l2.9-2.9A10 10 0 003.1 7.4L6.4 10c.8-2.3 3-4.1 5.6-4.1z" />
    </svg>
  )
}

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  invalid_state: 'That sign-in link expired. Please try again.',
  denied: 'Google sign-in was cancelled.',
  missing_code: 'Google sign-in was interrupted. Please try again.',
  invalid_token: "We couldn't verify that Google account. Please try again.",
  email_unverified: 'That Google account has an unverified email — verify it with Google first.',
  unverified_existing:
    'An IronForge account already uses that email but has not verified it yet. Check your inbox, or reset your password.',
  server_error: 'Something went wrong signing in with Google. Please try again.',
  unavailable: 'Google sign-in is temporarily unavailable. Please try again shortly.',
}

/**
 * "Continue with Google" — a plain navigation to GET /api/auth/google/start, which
 * mints the state+PKCE cookie and redirects on to Google. No client SDK, no popup.
 *
 * Hidden entirely when the server has not configured GOOGLE_CLIENT_ID/SECRET
 * (checked via the public /api/auth/google/status probe), so a half-configured
 * deployment never shows a button whose click 404s.
 */
export default function ContinueWithGoogle({ next }: { next?: string }) {
  const [enabled, setEnabled] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/auth/google/status')
      .then((r) => r.json())
      .then((d) => setEnabled(Boolean(d?.enabled)))
      .catch(() => setEnabled(false))
    const err = new URLSearchParams(window.location.search).get('googleError')
    if (err) setError(GOOGLE_ERROR_MESSAGES[err] || 'Something went wrong signing in with Google.')
  }, [])

  if (!enabled) return null

  const href = `/api/auth/google/start${next ? `?next=${encodeURIComponent(next)}` : ''}`

  return (
    <div className="space-y-2">
      <a
        href={href}
        className="flex w-full items-center justify-center gap-2 rounded-md border border-white/15 bg-white px-4 py-2.5 text-sm font-semibold text-gray-800 transition hover:bg-gray-100"
      >
        <GoogleGlyph />
        Continue with Google
      </a>
      {error && <p className="text-center text-xs text-red-400">{error}</p>}
    </div>
  )
}
