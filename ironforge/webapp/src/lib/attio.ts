/**
 * Attio CRM contact sync (sub-project E).
 *
 * Guarded by ATTIO_API_KEY. When unset, syncs are skipped (no-op) — mirrors the
 * email.ts / customers-db.ts guards, so the app runs fine before Attio is wired.
 * Only this module talks to Attio's HTTP API.
 *
 * A new IronForge signup becomes a Person record in Attio, asserted (upserted) by
 * email so re-runs are idempotent. State / referral code / consents are attached
 * as a best-effort Note (not standard People attributes). On failure the contact is
 * queued to `attio_sync_queue` (in the customers DB) and an ATTIO_SYNC_FAILED audit
 * row is written by the caller; POST /api/auth/attio-retry drains the queue.
 */

import { customerExecute, customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'

const ATTIO_BASE = 'https://api.attio.com/v2'
const ATTIO_PEOPLE_ASSERT_URL = `${ATTIO_BASE}/objects/people/records?matching_attribute=email_addresses`
const ATTIO_NOTES_URL = `${ATTIO_BASE}/notes`

/** Give up after this many attempts so a permanently-bad record can't loop forever. */
export const MAX_ATTIO_ATTEMPTS = 6

export interface AttioContact {
  firstName: string
  lastName: string
  email: string
  phone: string // E.164, e.g. +15551234567
  state?: string
  referralCode?: string
}

export interface AttioSyncResult {
  synced: boolean
  skipped?: boolean
  error?: string
  recordId?: string
}

export function isAttioConfigured(): boolean {
  return !!process.env.ATTIO_API_KEY
}

/**
 * Attio validates phone numbers against the real numbering plan and rejects the WHOLE record
 * write with a 400 when one doesn't parse. Our own check only counts digits (10/11 → E.164), so
 * a typo'd or fake-but-well-formed number is accepted here and refused there — and the person
 * never lands in the CRM at all. Seen live on 8/3: a waitlist submission failed inline with
 * `"slug \"phone_numbers\"" / "Invalid phone number, possibly due to missing country
 * information"` and then dead-lettered out of the outbox, so the lead existed in Postgres and
 * nowhere else. Callers detect this and retry without the phone: a contact minus one field beats
 * no contact.
 */
export function isPhoneValidationError(detail: string | undefined): boolean {
  if (!detail) return false
  return /phone_numbers|original_phone_number/.test(detail)
}

/** The same values with the phone stripped, for the retry above. */
export function withoutPhone(values: Record<string, unknown>): Record<string, unknown> {
  const { phone_numbers: _dropped, ...rest } = values
  return rest
}

function authHeaders(): Record<string, string> {
  return {
    Authorization: `Bearer ${process.env.ATTIO_API_KEY}`,
    'Content-Type': 'application/json',
  }
}

/** Build the Attio People assert body. Uses only standard People attributes. */
export function buildPersonAssert(c: AttioContact): Record<string, unknown> {
  const fullName = [c.firstName, c.lastName].filter(Boolean).join(' ').trim()
  const values: Record<string, unknown> = {
    name: [{ first_name: c.firstName, last_name: c.lastName, full_name: fullName }],
    email_addresses: [{ email_address: c.email }],
  }
  if (c.phone) values.phone_numbers = [{ original_phone_number: c.phone }]
  return { data: { values } }
}

interface PersonAssertOutcome {
  ok: boolean
  status: number
  detail: string
  recordId?: string
  /** True when the record only landed because the phone was dropped — the caller should say so. */
  phoneDropped: boolean
}

/**
 * PUT the People assert, retrying ONCE without `phone_numbers` when that is the only thing Attio
 * objected to (see isPhoneValidationError). Never throws; the caller decides what a failure means.
 */
async function assertPersonWithPhoneFallback(values: Record<string, unknown>): Promise<PersonAssertOutcome> {
  const put = async (v: Record<string, unknown>) => {
    const res = await fetch(ATTIO_PEOPLE_ASSERT_URL, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify({ data: { values: v } }),
    })
    if (!res.ok) {
      return { ok: false, status: res.status, detail: (await res.text().catch(() => '')).slice(0, 300) }
    }
    const json = (await res.json().catch(() => null)) as { data?: { id?: { record_id?: string } } } | null
    return { ok: true, status: res.status, detail: '', recordId: json?.data?.id?.record_id }
  }

  const first = await put(values)
  if (first.ok || !('phone_numbers' in values)) return { ...first, phoneDropped: false }
  if (first.status !== 400 || !isPhoneValidationError(first.detail)) return { ...first, phoneDropped: false }

  console.warn('[attio] phone rejected by Attio — retrying person upsert without it')
  const retry = await put(withoutPhone(values))
  return { ...retry, phoneDropped: retry.ok }
}

/** Free-text note carrying the signup fields that aren't standard People attributes. */
export function buildSignupNote(recordId: string, c: AttioContact): Record<string, unknown> {
  const lines = [
    'IronForge signup',
    `State: ${c.state || '—'}`,
    `Referral code: ${c.referralCode || '—'}`,
  ]
  return {
    data: {
      parent_object: 'people',
      parent_record_id: recordId,
      title: 'IronForge signup',
      format: 'plaintext',
      content: lines.join('\n'),
    },
  }
}

/**
 * Best-effort: record a phone Attio refused to store. Without this the fallback above would
 * trade one silent loss (the whole person) for a smaller one (their phone number) — the operator
 * would see a contact with no phone and no reason why. Never throws.
 */
async function attachRejectedPhoneNote(recordId: string, phone: string): Promise<void> {
  if (!phone) return
  try {
    await fetch(ATTIO_NOTES_URL, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        data: {
          parent_object: 'people',
          parent_record_id: recordId,
          title: 'Phone number rejected by Attio',
          format: 'plaintext',
          content: `Submitted phone: ${phone}\nAttio rejected it as not a valid number, so it is not on the record. Verify with the prospect before calling.`,
        },
      }),
    })
  } catch (e) {
    console.error('[attio] rejected-phone note failed (non-fatal):', e)
  }
}

/** Best-effort: attach the signup note. Never throws; a note failure is non-fatal. */
async function attachSignupNote(recordId: string, c: AttioContact): Promise<void> {
  if (!c.state && !c.referralCode) return
  try {
    await fetch(ATTIO_NOTES_URL, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(buildSignupNote(recordId, c)),
    })
  } catch (e) {
    console.error('[attio] note attach failed (non-fatal):', e)
  }
}

/**
 * Create/update the Attio Person for this contact. Idempotent (asserted by email).
 * Returns {skipped:true} when ATTIO_API_KEY is unset. Never throws.
 */
export async function syncContactToAttio(c: AttioContact): Promise<AttioSyncResult> {
  if (!isAttioConfigured()) return { synced: false, skipped: true }
  try {
    const values = (buildPersonAssert(c) as { data: { values: Record<string, unknown> } }).data.values
    const out = await assertPersonWithPhoneFallback(values)
    if (!out.ok) return { synced: false, error: `Attio ${out.status}: ${out.detail}` }
    if (out.recordId) {
      if (out.phoneDropped) await attachRejectedPhoneNote(out.recordId, c.phone)
      await attachSignupNote(out.recordId, c)
    }
    return { synced: true, recordId: out.recordId }
  } catch (e) {
    return { synced: false, error: e instanceof Error ? e.message : 'attio sync failed' }
  }
}

export interface BrokerageConnectionInfo {
  brokerage?: string // institution name, e.g. "Tastytrade"
  accountName?: string
  accountCount?: number
  connectedAt?: string // ISO timestamp
}

/** Free-text note recording that the prospect connected a brokerage (a key funnel milestone). */
export function buildBrokerageNote(
  recordId: string,
  info: BrokerageConnectionInfo,
): Record<string, unknown> {
  const lines = [
    'IronForge brokerage connected',
    `Brokerage: ${info.brokerage || '—'}`,
    info.accountName ? `Account: ${info.accountName}` : null,
    info.accountCount != null ? `Accounts: ${info.accountCount}` : null,
    `Connected at: ${info.connectedAt || '—'}`,
  ].filter(Boolean) as string[]
  return {
    data: {
      parent_object: 'people',
      parent_record_id: recordId,
      title: 'IronForge brokerage connected',
      format: 'plaintext',
      content: lines.join('\n'),
    },
  }
}

/**
 * Push a brokerage-connection milestone to Attio: assert the Person by email (idempotent,
 * keeps the contact fresh) and attach a "brokerage connected" Note. Best-effort; never throws.
 * Returns {skipped:true} when ATTIO_API_KEY is unset. (sub-project: brokerage connection)
 */
export async function syncBrokerageConnectionToAttio(
  c: AttioContact,
  info: BrokerageConnectionInfo,
): Promise<AttioSyncResult> {
  if (!isAttioConfigured()) return { synced: false, skipped: true }
  try {
    const res = await fetch(ATTIO_PEOPLE_ASSERT_URL, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify(buildPersonAssert(c)),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return { synced: false, error: `Attio ${res.status}: ${detail.slice(0, 300)}` }
    }
    const json = (await res.json().catch(() => null)) as { data?: { id?: { record_id?: string } } } | null
    const recordId = json?.data?.id?.record_id
    if (recordId) {
      try {
        await fetch(ATTIO_NOTES_URL, {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify(buildBrokerageNote(recordId, info)),
        })
      } catch (e) {
        console.error('[attio] brokerage note attach failed (non-fatal):', e)
      }
    }
    return { synced: true, recordId }
  } catch (e) {
    return { synced: false, error: e instanceof Error ? e.message : 'attio brokerage sync failed' }
  }
}

/** Queue a failed contact for later retry. Never throws (best-effort persistence). */
export async function enqueueAttioSync(
  userId: string | null,
  c: AttioContact,
  lastError: string,
): Promise<void> {
  if (!isCustomersDbConfigured()) return
  try {
    await customerExecute(
      `INSERT INTO attio_sync_queue (user_id, payload, last_error, attempts, status)
       VALUES ($1, $2, $3, 1, 'pending')`,
      [userId, JSON.stringify(c), lastError.slice(0, 500)],
    )
  } catch (e) {
    console.error('[attio] enqueue failed:', e)
  }
}

export interface DrainResult {
  processed: number
  synced: number
  failed: number
}

/**
 * Re-attempt every pending queued sync (up to `limit`). Marks each row synced /
 * failed (after MAX_ATTIO_ATTEMPTS) or leaves it pending with a bumped attempt count.
 */
export async function drainAttioSyncQueue(limit = 25): Promise<DrainResult> {
  if (!isAttioConfigured() || !isCustomersDbConfigured()) {
    return { processed: 0, synced: 0, failed: 0 }
  }
  const rows = await customerQuery<{
    id: string
    user_id: string | null
    payload: AttioContact | string
    attempts: number
  }>(
    `SELECT id, user_id, payload, attempts FROM attio_sync_queue
     WHERE status = 'pending' AND attempts < $1
     ORDER BY created_at ASC LIMIT $2`,
    [MAX_ATTIO_ATTEMPTS, limit],
  )

  let synced = 0
  let failed = 0
  for (const row of rows) {
    const c = (typeof row.payload === 'string' ? JSON.parse(row.payload) : row.payload) as AttioContact
    const res = await syncContactToAttio(c)
    if (res.skipped) break // config vanished mid-drain — stop, leave rows pending
    if (res.synced) {
      synced++
      await customerExecute(
        `UPDATE attio_sync_queue
         SET status='synced', synced_at=now(), updated_at=now(), attio_record_id=$2
         WHERE id=$1`,
        [row.id, res.recordId ?? null],
      )
    } else {
      failed++
      const attempts = row.attempts + 1
      const status = attempts >= MAX_ATTIO_ATTEMPTS ? 'failed' : 'pending'
      await customerExecute(
        `UPDATE attio_sync_queue
         SET attempts=$2, status=$3, last_error=$4, updated_at=now()
         WHERE id=$1`,
        [row.id, attempts, status, (res.error ?? '').slice(0, 500)],
      )
    }
  }
  return { processed: rows.length, synced, failed }
}

/* ── Waitlist (8/26 handoff) ─────────────────────────────────────────────────
 * Upsert the People record by email (with primary_location), then add/update the
 * person in the IronForge Waitlist list with waitlist-specific attributes. Reuses
 * the existing ATTIO_API_KEY auth; the list slug comes from ATTIO_WAITLIST_LIST.
 * Location is atomic — the full object is sent, including null street fields. */

export interface WaitlistAttioContact {
  firstName: string
  lastName: string
  email: string
  phone: string
  city: string
  state: string
  tradingCapitalRange: string
  consentVersion: string
  submissionId: string
}

export interface WaitlistAttioResult {
  synced: boolean
  skipped?: boolean
  recordId?: string
  error?: string
}

function buildWaitlistPersonAssert(c: WaitlistAttioContact): Record<string, unknown> {
  const fullName = [c.firstName, c.lastName].filter(Boolean).join(' ').trim()
  const values: Record<string, unknown> = {
    name: [{ first_name: c.firstName, last_name: c.lastName, full_name: fullName }],
    email_addresses: [{ email_address: c.email }],
    // Location is atomic: send the whole object incl. nulls (handoff §6).
    primary_location: [{
      line_1: null, line_2: null, line_3: null, line_4: null,
      locality: c.city || null,
      region: c.state || null,
      postcode: null,
      country_code: 'US',
      latitude: null, longitude: null,
    }],
  }
  if (c.phone) values.phone_numbers = [{ original_phone_number: c.phone }]
  return { data: { values } }
}

/**
 * Upsert the waitlist prospect into Attio. Returns synced:false (with error) on any
 * failure so the caller can keep the local row + surface the integration error —
 * the lead is never lost. skipped:true when Attio isn't configured (dev/no-op).
 */
export async function upsertWaitlistToAttio(c: WaitlistAttioContact): Promise<WaitlistAttioResult> {
  if (!isAttioConfigured()) return { synced: false, skipped: true }
  try {
    const values = (buildWaitlistPersonAssert(c) as { data: { values: Record<string, unknown> } }).data.values
    const out = await assertPersonWithPhoneFallback(values)
    if (!out.ok) return { synced: false, error: `Attio people ${out.status}: ${out.detail}` }
    const recordId = out.recordId
    // List add is best-effort — the person is captured either way — but it must be VISIBLE.
    // This used to be `.catch(() => {})`, so a missing list, a bad slug, or an unset
    // ATTIO_WAITLIST_LIST failed in total silence while attio_status still read 'synced'.
    if (recordId) {
      if (out.phoneDropped) await attachRejectedPhoneNote(recordId, c.phone)
      await addToWaitlistList(recordId, c).catch((e: unknown) => {
        console.warn('[attio] waitlist list entry failed (person captured):', e instanceof Error ? e.message : e)
      })
    }
    return { synced: true, recordId }
  } catch (e) {
    return { synced: false, error: e instanceof Error ? e.message : 'attio waitlist upsert failed' }
  }
}

/** Add/update the person in the IronForge Waitlist list with list-level attributes. */
async function addToWaitlistList(personRecordId: string, c: WaitlistAttioContact): Promise<void> {
  const listSlug = process.env.ATTIO_WAITLIST_LIST
  if (!listSlug) {
    console.warn('[attio] ATTIO_WAITLIST_LIST unset — waitlist list entry skipped')
    return
  }
  const res = await fetch(`${ATTIO_BASE}/lists/${encodeURIComponent(listSlug)}/entries`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      data: {
        parent_record_id: personRecordId,
        parent_object: 'people',
        entry_values: {
          trading_capital_range: c.tradingCapitalRange,
          communication_consent: true,
          consent_version: c.consentVersion,
          submission_id: c.submissionId,
          confirmation_email_status: 'Pending',
        },
      },
    }),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Attio list entry ${res.status}: ${detail.slice(0, 200)}`)
  }
}
