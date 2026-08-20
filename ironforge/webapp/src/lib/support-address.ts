/**
 * The one support address, for every surface that shows or replies to one.
 *
 * It was hardcoded as a string literal in lib/email.ts (twice, on the `reply_to` of
 * password-reset and trade-approval mail), read from an env var in lib/support/persona.ts,
 * and written into the Forge AI system prompt as plain prose. Three definitions of the
 * same fact, only one of which could be changed without a deploy.
 *
 * That matters right now because support@ironforge.trade IS NOT A REAL MAILBOX yet — the
 * alias needs a Google Workspace admin to create it. Until it exists, every customer who
 * hits reply on a password-reset or a trade-approval email is writing to nowhere. Routing
 * this through one env var means the fix is a Render setting, not a code change and a
 * deploy, whichever way that decision goes.
 *
 * Set SUPPORT_EMAIL on the customer service to override.
 */
export const DEFAULT_SUPPORT_EMAIL = 'support@ironforge.trade'

export function supportEmail(): string {
  const v = process.env.SUPPORT_EMAIL?.trim()
  return v || DEFAULT_SUPPORT_EMAIL
}
