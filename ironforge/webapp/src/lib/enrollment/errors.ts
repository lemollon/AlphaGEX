import { randomUUID } from 'crypto'

/**
 * The standard error envelope (Enrollment spec §6).
 *
 *   { code, message, field?, correlation_id, retryable }
 *
 * Two rules the spec is emphatic about, both encoded here rather than left to each
 * route to remember:
 *
 *  1. NEVER expose a raw broker or Stripe response to the client. Provider errors are
 *     mapped to a stable machine code and a user-safe message; the provider's own text
 *     goes to the server log with the correlation id and no further.
 *  2. Every error screen shows a NON-SENSITIVE correlation id (§11) so support can find
 *     the request without the customer reading out anything private.
 *
 * The status codes are fixed by the spec: 409 stale state/version conflict, 422
 * validation, 401/403 auth, 429 rate limit, 503 retryable provider outage.
 */

export type ErrorCode =
  // auth / ownership
  | 'UNAUTHORIZED' | 'FORBIDDEN'
  // validation
  | 'VALIDATION_FAILED' | 'PLAN_INVALID' | 'LEGAL_ACCEPTANCE_INCOMPLETE'
  // conflict / staleness
  | 'STATE_CONFLICT' | 'PREVIEW_STALE' | 'LEGAL_VERSION_CHANGED' | 'ALREADY_ACTIVE'
  // brokerage
  | 'OAUTH_STATE_INVALID' | 'OAUTH_DENIED' | 'BROKER_ACCOUNT_INELIGIBLE'
  | 'BROKER_REAUTH_REQUIRED' | 'NO_ELIGIBLE_ACCOUNTS'
  // activation
  | 'ACTIVATION_BLOCKED' | 'KILL_SWITCH_ENGAGED'
  // infrastructure
  | 'RATE_LIMITED' | 'PROVIDER_UNAVAILABLE' | 'NOT_CONFIGURED' | 'INTERNAL'

export interface ErrorEnvelope {
  code: ErrorCode
  message: string
  field?: string
  correlation_id: string
  retryable: boolean
}

const STATUS: Record<ErrorCode, number> = {
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  VALIDATION_FAILED: 422,
  PLAN_INVALID: 422,
  LEGAL_ACCEPTANCE_INCOMPLETE: 422,
  STATE_CONFLICT: 409,
  PREVIEW_STALE: 409,
  LEGAL_VERSION_CHANGED: 409,
  ALREADY_ACTIVE: 409,
  OAUTH_STATE_INVALID: 400,
  OAUTH_DENIED: 400,
  BROKER_ACCOUNT_INELIGIBLE: 422,
  BROKER_REAUTH_REQUIRED: 409,
  NO_ELIGIBLE_ACCOUNTS: 422,
  ACTIVATION_BLOCKED: 409,
  KILL_SWITCH_ENGAGED: 503,
  RATE_LIMITED: 429,
  PROVIDER_UNAVAILABLE: 503,
  NOT_CONFIGURED: 503,
  INTERNAL: 500,
}

/** Only 5xx-ish transients are worth a client retry; a 422 never is. */
const RETRYABLE: ErrorCode[] = ['RATE_LIMITED', 'PROVIDER_UNAVAILABLE', 'KILL_SWITCH_ENGAGED', 'INTERNAL']

export function newCorrelationId(): string {
  return randomUUID()
}

export function statusFor(code: ErrorCode): number {
  return STATUS[code] ?? 500
}

export function errorEnvelope(
  code: ErrorCode,
  message: string,
  opts: { field?: string; correlationId?: string } = {},
): ErrorEnvelope {
  return {
    code,
    message,
    ...(opts.field ? { field: opts.field } : {}),
    correlation_id: opts.correlationId ?? newCorrelationId(),
    retryable: RETRYABLE.includes(code),
  }
}

/**
 * Log the provider's real error, return the customer's.
 *
 * The raw text is the thing that must not cross the boundary — it routinely contains
 * account identifiers, internal ids and provider phrasing that means nothing useful to
 * a customer. Pairing them by correlation id is what keeps support able to work.
 */
export function redactProviderError(
  scope: string,
  raw: unknown,
  code: ErrorCode,
  userMessage: string,
): ErrorEnvelope {
  const env = errorEnvelope(code, userMessage)
  const detail = raw instanceof Error ? raw.message : String(raw)
  console.error(`[${scope}] ${env.correlation_id} ${code}: ${detail}`)
  return env
}
