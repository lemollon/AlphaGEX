/**
 * Attio REST client for the CRM integration.
 *
 * Hand-written over global fetch — no vendor SDK, matching the dependency-light pattern used by
 * lib/billing/stripe.ts and lib/support/anthropic.ts. Adding an npm dependency here would also
 * risk the phantom-dependency build failure the waitlist launch already hit.
 *
 * Every call returns a result object and NEVER throws. Callers are the outbox drain and the
 * provisioner, both of which need to distinguish "retry this" from "this will never work":
 *
 *   retryable: network error, timeout, 429, 5xx  → outbox backs off and tries again
 *   permanent: 4xx other than 429                → outbox dead-letters immediately
 *
 * The existing lib/attio.ts is untouched by this module; Phase 2 migrates its call sites onto
 * the outbox, at which point it becomes a thin wrapper over this client.
 */

import { isAttioConfigured } from '@/lib/attio'

const ATTIO_BASE = 'https://api.attio.com/v2'

/** House default. Schema calls pass a longer timeout — provisioning is not on a request path. */
const DEFAULT_TIMEOUT_MS = 5_000
const DEFAULT_MAX_ATTEMPTS = 3
/** Cap backoff so a drain cycle can't stall on one bad record. */
const MAX_BACKOFF_MS = 8_000

export { isAttioConfigured }

export interface AttioResult<T = unknown> {
  ok: boolean
  status: number
  data?: T
  error?: string
  /** True when the failure is worth retrying (network, timeout, 429, 5xx). */
  retryable?: boolean
  /** Seconds the server asked us to wait, from Retry-After. */
  retryAfterSec?: number
}

interface RequestOptions {
  timeoutMs?: number
  maxAttempts?: number
}

function authHeaders(): Record<string, string> {
  return {
    Authorization: `Bearer ${process.env.ATTIO_API_KEY}`,
    'Content-Type': 'application/json',
  }
}

/** Exponential backoff with jitter. Jitter matters: the drain fires many records at once. */
function backoffMs(attempt: number): number {
  const base = Math.min(MAX_BACKOFF_MS, 500 * 2 ** (attempt - 1))
  return Math.round(base * (0.5 + Math.random() * 0.5))
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * One Attio HTTP call with timeout + bounded retry. Retries only idempotent-safe failures:
 * a 429/5xx/network error means the write may not have landed, and every write this integration
 * makes is either an assert (idempotent by matching attribute) or guarded by the outbox's
 * event_id primary key, so a duplicate attempt is safe.
 */
export async function attioRequest<T = unknown>(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
  opts: RequestOptions = {},
): Promise<AttioResult<T>> {
  if (!isAttioConfigured()) {
    return { ok: false, status: 0, error: 'ATTIO_API_KEY unset', retryable: false }
  }

  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const maxAttempts = opts.maxAttempts ?? DEFAULT_MAX_ATTEMPTS
  const url = path.startsWith('http') ? path : `${ATTIO_BASE}${path}`

  let last: AttioResult<T> = { ok: false, status: 0, error: 'no attempt made', retryable: true }

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const res = await fetch(url, {
        method,
        headers: authHeaders(),
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      })

      if (res.ok) {
        const json = (await res.json().catch(() => null)) as T | null
        return { ok: true, status: res.status, data: json ?? undefined }
      }

      const detail = await res.text().catch(() => '')
      const retryAfterSec = Number(res.headers.get('retry-after')) || undefined
      const retryable = res.status === 429 || res.status >= 500
      last = {
        ok: false,
        status: res.status,
        error: `Attio ${res.status}: ${detail.slice(0, 300)}`,
        retryable,
        retryAfterSec,
      }
      if (!retryable) return last
      // Honour Retry-After when the server sends it; otherwise back off ourselves.
      await sleep(retryAfterSec ? retryAfterSec * 1000 : backoffMs(attempt))
    } catch (e) {
      const aborted = e instanceof Error && e.name === 'AbortError'
      last = {
        ok: false,
        status: 0,
        error: aborted ? `Attio timeout after ${timeoutMs}ms` : e instanceof Error ? e.message : 'attio request failed',
        retryable: true,
      }
      if (attempt < maxAttempts) await sleep(backoffMs(attempt))
    } finally {
      clearTimeout(timer)
    }
  }

  return last
}

// ---------------------------------------------------------------------------
// Schema reads/writes (used only by the provisioner)
//
// Schema calls get a longer timeout and a single attempt: they run from an operator endpoint,
// not a customer request path, and a half-applied retry on object creation is more confusing
// than a clean failure the operator can re-run (provisioning is idempotent by design).
// ---------------------------------------------------------------------------

const SCHEMA_OPTS: RequestOptions = { timeoutMs: 20_000, maxAttempts: 2 }

export interface AttioObjectSummary {
  id?: { object_id?: string }
  api_slug?: string
  singular_noun?: string
  plural_noun?: string
}

export function listObjects() {
  return attioRequest<{ data?: AttioObjectSummary[] }>('GET', '/objects', undefined, SCHEMA_OPTS)
}

export function createObject(apiSlug: string, singularNoun: string, pluralNoun: string) {
  return attioRequest<{ data?: AttioObjectSummary }>(
    'POST',
    '/objects',
    { data: { api_slug: apiSlug, singular_noun: singularNoun, plural_noun: pluralNoun } },
    SCHEMA_OPTS,
  )
}

export interface AttioAttributeSummary {
  id?: { attribute_id?: string }
  api_slug?: string
  title?: string
  type?: string
  is_unique?: boolean
}

export function listAttributes(objectSlug: string) {
  return attioRequest<{ data?: AttioAttributeSummary[] }>(
    'GET',
    `/objects/${encodeURIComponent(objectSlug)}/attributes`,
    undefined,
    SCHEMA_OPTS,
  )
}

/**
 * Create an attribute. `config` carries the type-specific extras — record-reference needs its
 * allowed target objects, everything else this schema uses needs nothing.
 */
export function createAttribute(
  objectSlug: string,
  attr: {
    apiSlug: string
    title: string
    type: string
    description?: string
    isUnique?: boolean
    referenceTarget?: string
  },
) {
  const data: Record<string, unknown> = {
    title: attr.title,
    description: attr.description ?? '',
    api_slug: attr.apiSlug,
    type: attr.type,
    is_required: false,
    is_unique: attr.isUnique ?? false,
    is_multiselect: false,
    // `config` is REQUIRED on every attribute type, not just the ones with type-specific
    // settings. Omitting it returns 400 invalid_type at path ["data","config"] — verified
    // against the live API, where an otherwise-identical body with config:{} returns 200.
    config: attr.referenceTarget
      ? { record_reference: { allowed_objects: [attr.referenceTarget] } }
      : {},
  }
  return attioRequest<{ data?: AttioAttributeSummary }>(
    'POST',
    `/objects/${encodeURIComponent(objectSlug)}/attributes`,
    { data },
    SCHEMA_OPTS,
  )
}

export interface AttioOptionSummary {
  id?: { option_id?: string; status_id?: string }
  title?: string
}

export function listSelectOptions(targetSlug: string, attributeSlug: string) {
  return attioRequest<{ data?: AttioOptionSummary[] }>(
    'GET',
    `/objects/${encodeURIComponent(targetSlug)}/attributes/${encodeURIComponent(attributeSlug)}/options`,
    undefined,
    SCHEMA_OPTS,
  )
}

export function createSelectOption(targetSlug: string, attributeSlug: string, title: string) {
  return attioRequest<{ data?: AttioOptionSummary }>(
    'POST',
    `/objects/${encodeURIComponent(targetSlug)}/attributes/${encodeURIComponent(attributeSlug)}/options`,
    { data: { title } },
    SCHEMA_OPTS,
  )
}

export function listStatuses(targetSlug: string, attributeSlug: string) {
  return attioRequest<{ data?: AttioOptionSummary[] }>(
    'GET',
    `/objects/${encodeURIComponent(targetSlug)}/attributes/${encodeURIComponent(attributeSlug)}/statuses`,
    undefined,
    SCHEMA_OPTS,
  )
}

export function createStatus(targetSlug: string, attributeSlug: string, title: string) {
  return attioRequest<{ data?: AttioOptionSummary }>(
    'POST',
    `/objects/${encodeURIComponent(targetSlug)}/attributes/${encodeURIComponent(attributeSlug)}/statuses`,
    { data: { title, is_archived: false } },
    SCHEMA_OPTS,
  )
}

export interface AttioListSummary {
  id?: { list_id?: string }
  api_slug?: string
  name?: string
}

export function listLists() {
  return attioRequest<{ data?: AttioListSummary[] }>('GET', '/lists', undefined, SCHEMA_OPTS)
}

export function createList(apiSlug: string, name: string, parentObject: string) {
  return attioRequest<{ data?: AttioListSummary }>(
    'POST',
    '/lists',
    {
      data: {
        name,
        api_slug: apiSlug,
        parent_object: parentObject,
        // 'full-access' is the ONLY workspace_access value Attio accepts alongside an empty
        // workspace_member_access — 'read-and-write' and 'read-only' both 400 with "ensure that
        // at least some members of your workspace will have access to the list" (verified
        // against the live API). Per-member access can be narrowed in the UI afterwards.
        workspace_access: 'full-access',
        workspace_member_access: [],
      },
    },
    SCHEMA_OPTS,
  )
}

export function listListAttributes(listSlug: string) {
  return attioRequest<{ data?: AttioAttributeSummary[] }>(
    'GET',
    `/lists/${encodeURIComponent(listSlug)}/attributes`,
    undefined,
    SCHEMA_OPTS,
  )
}

export function createListAttribute(
  listSlug: string,
  attr: { apiSlug: string; title: string; type: string; description?: string },
) {
  return attioRequest<{ data?: AttioAttributeSummary }>(
    'POST',
    `/lists/${encodeURIComponent(listSlug)}/attributes`,
    {
      data: {
        title: attr.title,
        description: attr.description ?? '',
        api_slug: attr.apiSlug,
        type: attr.type,
        is_required: false,
        is_unique: false,
        is_multiselect: false,
        config: {}, // required on list attributes too — see createAttribute
      },
    },
    SCHEMA_OPTS,
  )
}

// ---------------------------------------------------------------------------
// Record writes (used by the outbox drain)
// ---------------------------------------------------------------------------

export interface AttioRecordRef {
  id?: { record_id?: string }
}

/**
 * Upsert a record by a unique matching attribute. This is what makes every CRM event idempotent
 * at the Attio end — replaying an event updates the same record instead of duplicating it
 * (AC-CRM-002).
 */
export function assertRecord(objectSlug: string, matchingAttribute: string, values: Record<string, unknown>) {
  return attioRequest<{ data?: AttioRecordRef }>(
    'PUT',
    `/objects/${encodeURIComponent(objectSlug)}/records?matching_attribute=${encodeURIComponent(matchingAttribute)}`,
    { data: { values } },
  )
}

export function createNote(parentObject: string, parentRecordId: string, title: string, content: string) {
  return attioRequest<{ data?: { id?: { note_id?: string } } }>('POST', '/notes', {
    data: { parent_object: parentObject, parent_record_id: parentRecordId, title, format: 'plaintext', content },
  })
}

export function createTask(content: string, deadlineAt: string | null, linkedRecords: Array<{ target_object: string; target_record_id: string }>) {
  return attioRequest<{ data?: { id?: { task_id?: string } } }>('POST', '/tasks', {
    data: {
      content,
      format: 'plaintext',
      deadline_at: deadlineAt,
      is_completed: false,
      linked_records: linkedRecords,
      assignees: [],
    },
  })
}

export function addListEntry(listSlug: string, parentRecordId: string, parentObject: string, entryValues: Record<string, unknown>) {
  return attioRequest<{ data?: { id?: { entry_id?: string } } }>(
    'POST',
    `/lists/${encodeURIComponent(listSlug)}/entries`,
    { data: { parent_record_id: parentRecordId, parent_object: parentObject, entry_values: entryValues } },
  )
}
