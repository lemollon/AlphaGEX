/**
 * Sandbox mode — is this deployment the disposable test copy?
 *
 * The enforcement lives in scripts/sandbox-guard.js, which runs at boot (before
 * Next loads) and refuses to start a sandbox that can reach real money. This
 * module is the read-only view of the same flag for application code, whose only
 * job is to make the sandbox *visibly* not production so nobody reads a test
 * number as a real one.
 *
 * Server-only: IRONFORGE_ENV is not a NEXT_PUBLIC_* var, so client components must
 * receive the flag as a prop from a server component (see app/layout.tsx).
 */

/** True when this process is the sandbox deployment. */
export function isSandbox(): boolean {
  return String(process.env.IRONFORGE_ENV || '').trim().toLowerCase() === 'sandbox'
}

/**
 * Banner text for the sandbox ribbon. Deliberately mentions both halves of the
 * lie a sandbox tells — the money isn't real and neither are the customers —
 * because screenshots of this UI will end up in issues and chats.
 */
export const SANDBOX_BANNER_TEXT =
  'SANDBOX — test data only. No real money, no real customers.'
