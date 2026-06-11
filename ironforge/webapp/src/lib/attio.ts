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
    if (recordId) await attachSignupNote(recordId, c)
    return { synced: true, recordId }
  } catch (e) {
    return { synced: false, error: e instanceof Error ? e.message : 'attio sync failed' }
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
