/**
 * POST /api/waitlist — same public, unauthenticated endpoint the web /waitlist form
 * calls (webapp/src/app/api/waitlist/route.ts). Not routed through api()/apiPublic()
 * in api/client.ts because those two assume an `error` string field on failure; this
 * route answers with `code` + `message` (+ `fieldErrors` on 422), so the ApiError class
 * (built for exactly this "code for the caller, sentence for the customer" shape — see
 * its own docstring) is used directly against the shared API_BASE instead.
 */
import { API_BASE, ApiError } from '@/api/client'
import type { CapitalRange } from './validation'

export interface WaitlistSubmitRequest {
  firstName: string
  lastName: string
  email: string
  phone: string
  city: string
  state: string
  tradingCapitalRange: CapitalRange
  communicationConsent: true
}

export interface WaitlistSubmitResponse {
  ok: true
  submissionId: string
  existing: boolean
  message: string
}

export async function submitWaitlist(fields: WaitlistSubmitRequest): Promise<WaitlistSubmitResponse> {
  const res = await fetch(`${API_BASE}/api/waitlist`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(fields),
  })
  const json = (await res.json().catch(() => null)) as Record<string, unknown> | null
  if (!res.ok || !json?.ok) {
    const msg = typeof json?.message === 'string' ? json.message : `Request failed (${res.status})`
    throw new ApiError(msg, res.status, json)
  }
  return json as unknown as WaitlistSubmitResponse
}
