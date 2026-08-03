/**
 * CRM event mappers — the 11 P0 integration events from the Integration Events sheet.
 *
 * Each handler turns a normalized backend payload into Attio record writes. Handlers are pure
 * translation plus HTTP: no business decisions are made here. In particular the customer
 * lifecycle is computed by the backend and passed in — this module never infers that a customer
 * is Active (spec §6.1: only the backend may publish Active).
 *
 * Every write goes through `assertSafe()`, which refuses to transmit a payload containing
 * credential-shaped fields. That is a hard stop, not a warning: AC-CRM-006 and AC-CRM-007 say no
 * payment, bank, Stripe secret, brokerage token, password, or credential may reach Attio, and a
 * redaction rule that merely logs is a rule that eventually leaks.
 */

import {
  assertRecord,
  createNote,
  type AttioRecordRef,
  type AttioResult,
} from '@/lib/crm/client'
import { MATCHING_ATTRIBUTE } from '@/lib/crm/schema'

export type CrmEventType =
  | 'crm.waitlist_submitted'
  | 'crm.invitation_sent'
  | 'crm.account_created'
  | 'crm.stripe_customer_created'
  | 'crm.subscription_active'
  | 'crm.brokerage_initiated'
  | 'crm.brokerage_connected'
  | 'crm.brokerage_failed'
  | 'crm.membership_paused'
  | 'crm.membership_canceled'
  | 'crm.reactivation'

export interface DeliveryResult {
  ok: boolean
  recordId?: string
  error?: string
  /** false = never retry (bad payload, unmapped type, redaction violation). */
  retryable?: boolean
}

// ---------------------------------------------------------------------------
// Sensitive-data firewall
// ---------------------------------------------------------------------------

/**
 * Key fragments that must never appear in an Attio payload. Matched case-insensitively against
 * every key we are about to send, at any nesting depth.
 *
 * Note what is NOT here: `stripe_customer_id` and `stripe_subscription_id` are reference
 * identifiers and are explicitly in scope (Data Dictionary), so the list matches on
 * secret-shaped words rather than on the vendor name.
 */
const FORBIDDEN_KEY_FRAGMENTS = [
  'token',
  'secret',
  'password',
  'passwd',
  'credential',
  'authorization',
  'auth_header',
  'api_key',
  'apikey',
  'card',
  'cvv',
  'cvc',
  'iban',
  'routing',
  'account_number',
  'bank',
  'ssn',
  'client_secret',
  'refresh',
  'access_token',
  'private_key',
]

/** Value patterns that look like a bearer token or key regardless of what the key is called. */
const SECRET_VALUE_PATTERNS: RegExp[] = [
  /\bBearer\s+[A-Za-z0-9._-]{12,}/i,
  /\bsk_(live|test)_[A-Za-z0-9]{8,}/,
  /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\./, // JWT
]

function violatingKey(values: unknown, path = ''): string | null {
  if (values === null || values === undefined) return null
  if (typeof values === 'string') {
    for (const re of SECRET_VALUE_PATTERNS) {
      if (re.test(values)) return `${path || '<value>'} (secret-shaped value)`
    }
    return null
  }
  if (Array.isArray(values)) {
    for (let i = 0; i < values.length; i++) {
      const hit = violatingKey(values[i], `${path}[${i}]`)
      if (hit) return hit
    }
    return null
  }
  if (typeof values === 'object') {
    for (const [key, value] of Object.entries(values as Record<string, unknown>)) {
      const lower = key.toLowerCase()
      if (FORBIDDEN_KEY_FRAGMENTS.some((frag) => lower.includes(frag))) {
        return path ? `${path}.${key}` : key
      }
      const hit = violatingKey(value, path ? `${path}.${key}` : key)
      if (hit) return hit
    }
  }
  return null
}

/**
 * Assert a record only if the payload is clean. A violation is a permanent failure: retrying
 * would just attempt the same leak again, so it dead-letters for a human to look at.
 */
async function assertSafe(
  objectSlug: string,
  values: Record<string, unknown>,
): Promise<AttioResult<{ data?: AttioRecordRef }>> {
  const bad = violatingKey(values)
  if (bad) {
    const message = `[crm] BLOCKED write to ${objectSlug}: payload contains forbidden field "${bad}"`
    console.error(message)
    return { ok: false, status: 0, error: message, retryable: false }
  }
  const matching = MATCHING_ATTRIBUTE[objectSlug] ?? 'email_addresses'
  return assertRecord(objectSlug, matching, values)
}

/** Truncate and scrub a provider error string down to something safe to show an operator. */
export function safeErrorSummary(raw: unknown, max = 300): string {
  if (typeof raw !== 'string' || !raw.trim()) return ''
  let out = raw.trim()
  for (const re of SECRET_VALUE_PATTERNS) out = out.replace(new RegExp(re.source, 'gi'), '[redacted]')
  return out.slice(0, max)
}

// ---------------------------------------------------------------------------
// Shared shapes
// ---------------------------------------------------------------------------

function toResult(res: AttioResult<{ data?: AttioRecordRef }>): DeliveryResult {
  if (res.ok) return { ok: true, recordId: res.data?.data?.id?.record_id }
  return { ok: false, error: res.error, retryable: res.retryable }
}

function personRef(recordId: string) {
  return [{ target_object: 'people', target_record_id: recordId }]
}

function str(payload: Record<string, unknown>, key: string): string | undefined {
  const v = payload[key]
  return typeof v === 'string' && v.trim() ? v.trim() : undefined
}

function bool(payload: Record<string, unknown>, key: string): boolean {
  return payload[key] === true
}

/**
 * Upsert the Person this event belongs to and return their Attio record id, which memberships
 * and brokerage connections need for their `member` reference. Email is the pre-account match
 * key; after account creation ironforge_user_id is the durable one (DEC-004), but we keep
 * asserting on email so a single code path serves both eras.
 */
async function upsertPerson(payload: Record<string, unknown>): Promise<{ id?: string; error?: string; retryable?: boolean }> {
  const email = str(payload, 'email')
  if (!email) return { error: 'event payload has no email', retryable: false }

  const values: Record<string, unknown> = {
    email_addresses: [{ email_address: email.toLowerCase() }],
  }
  const firstName = str(payload, 'firstName')
  const lastName = str(payload, 'lastName')
  if (firstName || lastName) {
    const full = [firstName, lastName].filter(Boolean).join(' ')
    values.name = [{ first_name: firstName ?? '', last_name: lastName ?? '', full_name: full }]
  }
  const phone = str(payload, 'phone')
  if (phone) values.phone_numbers = [{ original_phone_number: phone }]
  const userId = str(payload, 'ironforgeUserId')
  if (userId) values.ironforge_user_id = userId
  const lifecycle = str(payload, 'lifecycle')
  if (lifecycle) values.customer_lifecycle = lifecycle

  // Location, when the event carries it (signup does; billing and brokerage events don't).
  // Attio takes the location object whole, including explicit nulls.
  const city = str(payload, 'city')
  const state = str(payload, 'state')
  if (city || state) {
    values.primary_location = [
      {
        line_1: null,
        line_2: null,
        line_3: null,
        line_4: null,
        locality: city ?? null,
        region: state ?? null,
        postcode: null,
        country_code: 'US',
        latitude: null,
        longitude: null,
      },
    ]
  }

  // Attribution is write-when-known, never write-a-default: the waitlist route learned this the
  // hard way when a recomputed 'Organic' overwrote a real 'LinkedIn'. Emitters must send
  // leadSource only when they genuinely know it.
  const leadSource = str(payload, 'leadSource')
  if (leadSource) values.lead_source = leadSource

  const res = await assertSafe('people', values)
  if (!res.ok) return { error: res.error, retryable: res.retryable }
  return { id: res.data?.data?.id?.record_id }
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

/** Waitlist submitted → People upsert with the full qualification field set. */
async function waitlistSubmitted(payload: Record<string, unknown>): Promise<DeliveryResult> {
  const email = str(payload, 'email')
  if (!email) return { ok: false, error: 'waitlist event has no email', retryable: false }

  const firstName = str(payload, 'firstName') ?? ''
  const lastName = str(payload, 'lastName') ?? ''
  const values: Record<string, unknown> = {
    name: [{ first_name: firstName, last_name: lastName, full_name: `${firstName} ${lastName}`.trim() }],
    email_addresses: [{ email_address: email.toLowerCase() }],
    customer_lifecycle: 'Waitlist',
    marketing_consent: bool(payload, 'marketingConsent'),
  }
  const phone = str(payload, 'phone')
  if (phone) values.phone_numbers = [{ original_phone_number: phone }]

  const city = str(payload, 'city')
  const state = str(payload, 'state')
  if (city || state) {
    // Attio requires the location object whole, including explicit nulls.
    values.primary_location = [
      {
        line_1: null,
        line_2: null,
        line_3: null,
        line_4: null,
        locality: city ?? null,
        region: state ?? null,
        postcode: null,
        country_code: 'US',
        latitude: null,
        longitude: null,
      },
    ]
  }

  const tradingVolume = str(payload, 'tradingVolume')
  if (tradingVolume) values.trading_volume = tradingVolume
  const leadSource = str(payload, 'leadSource')
  if (leadSource) values.lead_source = leadSource
  const waitlistDate = str(payload, 'waitlistDate')
  if (waitlistDate) values.waitlist_date = waitlistDate

  return toResult(await assertSafe('people', values))
}

/** Lifecycle-only People updates: invitation sent, account created, pause/cancel projections. */
async function personLifecycle(payload: Record<string, unknown>, lifecycle: string): Promise<DeliveryResult> {
  const person = await upsertPerson({ ...payload, lifecycle })
  if (!person.id) return { ok: false, error: person.error ?? 'person upsert failed', retryable: person.retryable }
  return { ok: true, recordId: person.id }
}

/**
 * Membership upsert. `membershipId` is the Stripe subscription id where one exists, so a
 * returning customer gets a NEW membership record and prior history is preserved (AC-CRM-013).
 */
async function membership(payload: Record<string, unknown>): Promise<DeliveryResult> {
  const membershipId = str(payload, 'membershipId')
  if (!membershipId) return { ok: false, error: 'membership event has no membershipId', retryable: false }

  const person = await upsertPerson(payload)
  if (!person.id) return { ok: false, error: person.error ?? 'person upsert failed', retryable: person.retryable }

  const values: Record<string, unknown> = {
    membership_id: membershipId,
    member: personRef(person.id),
  }
  const plan = str(payload, 'plan')
  if (plan) values.plan = plan
  const botName = str(payload, 'bot')
  if (botName) values.bot = botName
  const status = str(payload, 'membershipStatus')
  if (status) values.membership_status = status
  const stripeCustomerId = str(payload, 'stripeCustomerId')
  if (stripeCustomerId) values.stripe_customer_id = stripeCustomerId
  const stripeSubscriptionId = str(payload, 'stripeSubscriptionId')
  if (stripeSubscriptionId) values.stripe_subscription_id = stripeSubscriptionId
  const startDate = str(payload, 'startDate')
  if (startDate) values.start_date = startDate
  const cancellationDate = str(payload, 'cancellationDate')
  if (cancellationDate) values.cancellation_date = cancellationDate
  const cancellationReason = str(payload, 'cancellationReason')
  if (cancellationReason) values.cancellation_reason = cancellationReason

  const res = await assertSafe('memberships', values)
  if (!res.ok) return toResult(res)

  // Mirror the backend-computed lifecycle onto the Person so the pipeline views move.
  const lifecycle = str(payload, 'lifecycle')
  if (lifecycle) await upsertPerson({ ...payload, lifecycle })

  return toResult(res)
}

/** Brokerage connection upsert, keyed on the immutable connection id. */
async function brokerageConnection(payload: Record<string, unknown>): Promise<DeliveryResult> {
  const connectionId = str(payload, 'connectionId')
  if (!connectionId) return { ok: false, error: 'brokerage event has no connectionId', retryable: false }

  const person = await upsertPerson(payload)
  if (!person.id) return { ok: false, error: person.error ?? 'person upsert failed', retryable: person.retryable }

  const values: Record<string, unknown> = {
    connection_id: connectionId,
    member: personRef(person.id),
    reauthorization_required: bool(payload, 'reauthorizationRequired'),
  }
  const status = str(payload, 'connectionStatus')
  if (status) values.connection_status = status
  const lastAttemptAt = str(payload, 'lastAttemptAt')
  if (lastAttemptAt) values.last_attempt_at = lastAttemptAt

  // Error fields are scrubbed on the way in as well as firewalled on the way out.
  const errorCode = str(payload, 'errorCode')
  if (errorCode) values.last_error_code = safeErrorSummary(errorCode, 100)
  const errorSummary = safeErrorSummary(payload.errorSummary)
  if (errorSummary) values.last_error_summary = errorSummary

  const res = await assertSafe('brokerage_connections', values)
  if (!res.ok) return toResult(res)

  const lifecycle = str(payload, 'lifecycle')
  if (lifecycle) await upsertPerson({ ...payload, lifecycle })

  return toResult(res)
}

/**
 * Invitation sent. Also drops a dated note so the outreach history is visible on the person,
 * since `Invited` is a status that gets overwritten as the customer progresses.
 */
async function invitationSent(payload: Record<string, unknown>): Promise<DeliveryResult> {
  const result = await personLifecycle(payload, 'Invited')
  if (!result.ok || !result.recordId) return result
  const invitedAt = str(payload, 'invitedAt') ?? new Date().toISOString()
  const invitedBy = str(payload, 'invitedBy') ?? 'IronForge operations'
  await createNote(
    'people',
    result.recordId,
    'IronForge invitation sent',
    `Enrollment invitation sent ${invitedAt} by ${invitedBy}.`,
  )
  return result
}

const HANDLERS: Record<CrmEventType, (p: Record<string, unknown>) => Promise<DeliveryResult>> = {
  'crm.waitlist_submitted': waitlistSubmitted,
  'crm.invitation_sent': invitationSent,
  'crm.account_created': (p) => personLifecycle(p, 'Enrollment Started'),
  'crm.stripe_customer_created': membership,
  'crm.subscription_active': membership,
  'crm.brokerage_initiated': brokerageConnection,
  'crm.brokerage_connected': brokerageConnection,
  'crm.brokerage_failed': brokerageConnection,
  'crm.membership_paused': membership,
  'crm.membership_canceled': membership,
  'crm.reactivation': membership,
}

/** Dispatch one queued event. Called only by the outbox drain. */
export async function deliverCrmEvent(
  eventType: CrmEventType,
  payload: Record<string, unknown>,
): Promise<DeliveryResult> {
  const handler = HANDLERS[eventType]
  if (!handler) {
    // Unknown type: a code/data mismatch that retrying cannot fix.
    return { ok: false, error: `unmapped CRM event type: ${eventType}`, retryable: false }
  }
  try {
    return await handler(payload)
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'crm delivery threw', retryable: true }
  }
}

/** Exported for tests — the firewall is the thing most worth asserting on. */
export const __testing = { violatingKey }
