import { NextRequest, NextResponse } from 'next/server'
import { safeEqual } from '@/lib/auth/session'

export const dynamic = 'force-dynamic'

/**
 * POST /api/webhooks/ghl-translate
 *
 * GHL workflow webhook. A Spanish-speaking lead fills out the intake survey
 * in GoHighLevel; this route pulls the free-text custom-field answers off the
 * contact, translates them to English via Claude Haiku, and writes the
 * translation back to GHL (a `notes_en` custom field + a contact note) so the
 * (English-only) design team can read them without leaving GHL.
 *
 * Auth: shared-secret header (`x-vibe-secret`) — this is a public URL handed
 * to a GHL "Custom Webhook" workflow action, not a logged-in user request.
 *
 * See ./README.md for the required env vars and the exact GHL workflow setup.
 */

const GHL_API_BASE = 'https://services.leadconnectorhq.com'
const GHL_VERSION = '2021-07-28'

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
const ANTHROPIC_MODEL = 'claude-haiku-4-5'
const ANTHROPIC_MAX_TOKENS = 2000
const ANTHROPIC_VERSION = '2023-06-01'

const SYSTEM_PROMPT =
  "You translate Spanish customer answers into plain English for a web-design agency. " +
  "Be factual. Add nothing that is not in the source. Keep the labels exactly as given. " +
  "Output one line per item, in the form 'Label: translated text'. " +
  "If a value is already English, pass it through unchanged."

// Spanish free-text survey fields to translate, in display order.
const SURVEY_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'customers', label: 'Customers' },
  { key: 'success_metric', label: 'Success metric' },
  { key: 'competitors', label: 'Competitors' },
  { key: 'sites_liked', label: 'Sites liked' },
  { key: 'sites_liked_why', label: 'Why liked' },
  { key: 'current_site_dislikes', label: 'Current site dislikes' },
  { key: 'brand_colors', label: 'Brand colors' },
  { key: 'brand_fonts', label: 'Brand fonts' },
  { key: 'tagline', label: 'Tagline' },
  { key: 'template_name', label: 'Template name' },
  { key: 'keywords', label: 'Keywords' },
  { key: 'deadline_reason', label: 'Deadline reason' },
  { key: 'domain_name', label: 'Domain' },
  { key: 'notes', label: 'Notes' },
]

/** Custom-field key -> GHL field id, cached in module scope (fields rarely change). */
let customFieldMapCache: Record<string, string> | null = null

class UpstreamError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function ghlHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    Authorization: `Bearer ${process.env.GHL_PIT_TOKEN}`,
    Version: GHL_VERSION,
    Accept: 'application/json',
    ...extra,
  }
}

/** Slugify a field name the same way a human would name a custom-field key. */
function slugify(s: string): string {
  return s.toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
}

async function fetchContact(contactId: string): Promise<Record<string, unknown>> {
  const resp = await fetch(`${GHL_API_BASE}/contacts/${contactId}`, { headers: ghlHeaders() })
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '<unreadable>')
    throw new UpstreamError(resp.status, `GHL contact fetch ${resp.status}: ${errText.slice(0, 300)}`)
  }
  const data = await resp.json()
  return (data?.contact ?? data) as Record<string, unknown>
}

async function fetchCustomFieldMap(): Promise<Record<string, string>> {
  if (customFieldMapCache) return customFieldMapCache
  const locationId = process.env.GHL_LOCATION_ID
  const resp = await fetch(`${GHL_API_BASE}/locations/${locationId}/customFields`, {
    headers: ghlHeaders(),
  })
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '<unreadable>')
    throw new UpstreamError(resp.status, `GHL customFields fetch ${resp.status}: ${errText.slice(0, 300)}`)
  }
  const data = await resp.json()
  const fields = Array.isArray(data?.customFields) ? data.customFields : []
  const map: Record<string, string> = {}
  for (const f of fields as Array<Record<string, unknown>>) {
    const id = f?.id ? String(f.id) : null
    if (!id) continue
    // fieldKey usually comes back as "contact.customers" — index by both the
    // bare key and a slug of the display name, so a key naming mismatch
    // between this route and the GHL location doesn't silently drop a field.
    const fieldKey = typeof f.fieldKey === 'string' ? f.fieldKey.replace(/^contact\./, '') : null
    if (fieldKey) map[fieldKey] = id
    const name = typeof f.name === 'string' ? slugify(f.name) : null
    if (name && !map[name]) map[name] = id
  }
  customFieldMapCache = map
  return map
}

function getFieldValue(contact: Record<string, unknown>, fieldMap: Record<string, string>, key: string): string | null {
  const id = fieldMap[key]
  if (!id) return null
  const arr = Array.isArray(contact?.customFields) ? (contact.customFields as Array<Record<string, unknown>>) : []
  const entry = arr.find((f) => String(f?.id) === id)
  const val = entry?.value
  return typeof val === 'string' && val.trim() ? val.trim() : null
}

async function callClaude(userContent: string): Promise<string> {
  const apiKey = process.env.ANTHROPIC_API_KEY
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY env var is not set')
  const resp = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'anthropic-version': ANTHROPIC_VERSION,
      'x-api-key': apiKey,
    },
    body: JSON.stringify({
      model: ANTHROPIC_MODEL,
      max_tokens: ANTHROPIC_MAX_TOKENS,
      temperature: 0,
      system: SYSTEM_PROMPT,
      messages: [{ role: 'user', content: userContent }],
    }),
  })
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '<unreadable>')
    throw new UpstreamError(resp.status, `Claude API ${resp.status}: ${errText.slice(0, 500)}`)
  }
  const data = await resp.json()
  const blocks = Array.isArray(data?.content) ? data.content : []
  const text = blocks.map((b: { text?: string }) => b?.text ?? '').join('').trim()
  if (!text) throw new Error('Claude API returned empty content')
  return text
}

async function writeTranslationField(contactId: string, translated: string, fieldMap: Record<string, string>): Promise<void> {
  const notesEnId = fieldMap['notes_en']
  if (!notesEnId) {
    console.error(`[ghl-translate] notes_en custom field not found for contact ${contactId} — skipping customFields write, still adding note`)
    return
  }
  const resp = await fetch(`${GHL_API_BASE}/contacts/${contactId}`, {
    method: 'PUT',
    headers: ghlHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ customFields: [{ id: notesEnId, field_value: translated }] }),
  })
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '<unreadable>')
    throw new UpstreamError(resp.status, `GHL contact update ${resp.status}: ${errText.slice(0, 300)}`)
  }
}

/** Best-effort — a note failure must not fail the whole webhook. */
async function addTranslationNote(contactId: string, translated: string): Promise<void> {
  try {
    const resp = await fetch(`${GHL_API_BASE}/contacts/${contactId}/notes`, {
      method: 'POST',
      headers: ghlHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ body: `English translation (auto):\n${translated}` }),
    })
    if (!resp.ok) {
      const errText = await resp.text().catch(() => '<unreadable>')
      console.error(`[ghl-translate] note create failed for contact ${contactId}: ${resp.status} ${errText.slice(0, 300)}`)
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[ghl-translate] note create threw for contact ${contactId}: ${msg}`)
  }
}

export async function POST(req: NextRequest) {
  const expectedSecret = process.env.VIBE_WEBHOOK_SECRET
  if (!expectedSecret) {
    return NextResponse.json({ error: 'VIBE_WEBHOOK_SECRET is not configured' }, { status: 503 })
  }
  const gotSecret = req.headers.get('x-vibe-secret')
  if (!gotSecret || !safeEqual(gotSecret, expectedSecret)) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid JSON body' }, { status: 400 })
  }

  const contactId = (body.contact_id ?? body.contactId ?? body.id) as string | undefined
  if (!contactId || typeof contactId !== 'string') {
    return NextResponse.json({ error: 'missing contact_id / contactId / id' }, { status: 400 })
  }

  try {
    const contact = await fetchContact(contactId)
    const fieldMap = await fetchCustomFieldMap()

    const sourceLines: string[] = []
    for (const { key, label } of SURVEY_FIELDS) {
      const value = getFieldValue(contact, fieldMap, key)
      if (value) sourceLines.push(`${label}: ${value}`)
    }

    if (sourceLines.length === 0) {
      return NextResponse.json({ skipped: 'no free text' })
    }

    const translated = await callClaude(sourceLines.join('\n'))

    await writeTranslationField(contactId, translated, fieldMap)
    await addTranslationNote(contactId, translated)

    return NextResponse.json({ ok: true, contactId, fieldsTranslated: sourceLines.length })
  } catch (err: unknown) {
    if (err instanceof UpstreamError) {
      console.error(`[ghl-translate] upstream failure for contact ${contactId}: ${err.status} ${err.message}`)
      return NextResponse.json({ error: err.message }, { status: err.status })
    }
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[ghl-translate] failed for contact ${contactId}: ${msg}`)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
