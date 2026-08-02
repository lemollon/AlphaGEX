/**
 * Attio schema provisioner.
 *
 * Reconciles the live Attio workspace against CRM_OBJECTS / CRM_LISTS in schema.ts. Idempotent
 * and safe to re-run: it only ever CREATES what is missing.
 *
 * It never deletes, renames, or archives anything. That is deliberate, not timidity — an
 * attribute's api_slug is the integration identifier every event mapper writes against, so a
 * rename is indistinguishable from "delete the field and drop all its data" as far as this
 * codebase is concerned (spec §13.1). Removing something is a human decision made in the Attio
 * UI plus a Decision Log entry.
 *
 * What it CANNOT do: saved views. Attio's REST API exposes objects, attributes, select options,
 * statuses, lists, records, notes, tasks and webhooks — there is no create-view endpoint. All
 * seven views in the Views & Lists spec are a manual UI build (AC-CRM-011 is verified by hand).
 *
 * Usage: GET /api/ops/crm/provision for a drift report (read-only), POST to apply.
 */

import {
  CRM_LISTS,
  CRM_OBJECTS,
  MATCHING_ATTRIBUTE,
  SEED_COMPANIES,
  type CrmAttribute,
  type CrmObject,
} from '@/lib/crm/schema'
import {
  assertRecord,
  createAttribute,
  createList,
  createListAttribute,
  createObject,
  createSelectOption,
  createStatus,
  isAttioConfigured,
  listAttributes,
  listListAttributes,
  listLists,
  listObjects,
  listSelectOptions,
  listStatuses,
} from '@/lib/crm/client'

export type ProvisionAction = 'create-object' | 'create-attribute' | 'create-option' | 'create-list' | 'seed-company'

export interface ProvisionItem {
  action: ProvisionAction
  /** Dotted identity, e.g. "memberships.membership_status.Past Due". */
  target: string
  /** 'missing' in a dry run; 'created' / 'exists' / 'error' after an apply. */
  outcome: 'missing' | 'created' | 'exists' | 'error'
  error?: string
}

export interface ProvisionReport {
  configured: boolean
  dryRun: boolean
  items: ProvisionItem[]
  created: number
  existing: number
  errors: number
  /** Reminders the API cannot satisfy — currently the manual view build. */
  manualFollowUps: string[]
}

const MANUAL_FOLLOW_UPS = [
  'Attio has no create-view API: build the 7 saved views (Waitlist - All, Waitlist - Priority, ' +
    'Enrollment Pipeline, Active Members, Brokerage Issues, Paused & Canceled, Founding Member ' +
    'Outreach) by hand per the Views & Lists sheet. AC-CRM-011 is verified against that build sheet.',
  'Set ATTIO_WAITLIST_LIST=ironforge_waitlist on ironforge-customer so POST /api/waitlist starts ' +
    'writing list entries (today addToWaitlistList returns early and the failure is swallowed).',
]

function push(items: ProvisionItem[], item: ProvisionItem): void {
  items.push(item)
}

/** Select and status options live behind different endpoints but reconcile identically. */
async function reconcileOptions(
  items: ProvisionItem[],
  dryRun: boolean,
  objectSlug: string,
  attr: CrmAttribute,
): Promise<void> {
  if (!attr.options || attr.options.length === 0) return
  const isStatus = attr.type === 'status'
  const existing = isStatus
    ? await listStatuses(objectSlug, attr.apiSlug)
    : await listSelectOptions(objectSlug, attr.apiSlug)

  if (!existing.ok) {
    // The attribute was very likely just created in this same run; in a dry run it may not exist
    // at all. Either way we can't enumerate options, so report rather than guess.
    push(items, {
      action: 'create-option',
      target: `${objectSlug}.${attr.apiSlug}.*`,
      outcome: dryRun ? 'missing' : 'error',
      error: existing.error,
    })
    return
  }

  const have = new Set((existing.data?.data ?? []).map((o) => (o.title ?? '').trim()))
  for (const title of attr.options) {
    const target = `${objectSlug}.${attr.apiSlug}.${title}`
    if (have.has(title)) {
      push(items, { action: 'create-option', target, outcome: 'exists' })
      continue
    }
    if (dryRun) {
      push(items, { action: 'create-option', target, outcome: 'missing' })
      continue
    }
    const res = isStatus
      ? await createStatus(objectSlug, attr.apiSlug, title)
      : await createSelectOption(objectSlug, attr.apiSlug, title)
    push(items, {
      action: 'create-option',
      target,
      outcome: res.ok ? 'created' : 'error',
      error: res.ok ? undefined : res.error,
    })
  }
}

async function reconcileObject(items: ProvisionItem[], dryRun: boolean, obj: CrmObject, liveSlugs: Set<string>): Promise<void> {
  const objectExists = liveSlugs.has(obj.apiSlug)

  if (!objectExists) {
    if (obj.isStandard) {
      // people/companies ship with every workspace. If one is missing something is very wrong —
      // report it rather than trying to create a standard object.
      push(items, {
        action: 'create-object',
        target: obj.apiSlug,
        outcome: 'error',
        error: 'standard object not found in workspace',
      })
      return
    }
    if (dryRun) {
      push(items, { action: 'create-object', target: obj.apiSlug, outcome: 'missing' })
    } else {
      const res = await createObject(obj.apiSlug, obj.singularNoun, obj.pluralNoun)
      push(items, {
        action: 'create-object',
        target: obj.apiSlug,
        outcome: res.ok ? 'created' : 'error',
        error: res.ok ? undefined : res.error,
      })
      // A quota_exceeded here means the workspace plan is at its custom-object limit; there is
      // no point attempting the attributes.
      if (!res.ok) return
    }
  } else {
    push(items, { action: 'create-object', target: obj.apiSlug, outcome: 'exists' })
  }

  // In a dry run against an object that does not exist yet, every attribute is by definition
  // missing — skip the (guaranteed 404) attribute listing.
  if (dryRun && !objectExists) {
    for (const attr of obj.attributes) {
      push(items, { action: 'create-attribute', target: `${obj.apiSlug}.${attr.apiSlug}`, outcome: 'missing' })
    }
    return
  }

  const live = await listAttributes(obj.apiSlug)
  if (!live.ok) {
    push(items, {
      action: 'create-attribute',
      target: `${obj.apiSlug}.*`,
      outcome: 'error',
      error: live.error,
    })
    return
  }
  const have = new Set((live.data?.data ?? []).map((a) => a.api_slug ?? ''))

  for (const attr of obj.attributes) {
    const target = `${obj.apiSlug}.${attr.apiSlug}`
    if (have.has(attr.apiSlug)) {
      push(items, { action: 'create-attribute', target, outcome: 'exists' })
    } else if (dryRun) {
      push(items, { action: 'create-attribute', target, outcome: 'missing' })
    } else {
      const res = await createAttribute(obj.apiSlug, {
        apiSlug: attr.apiSlug,
        title: attr.title,
        type: attr.type,
        description: attr.description,
        isUnique: attr.isUnique,
        referenceTarget: attr.referenceTarget,
      })
      push(items, {
        action: 'create-attribute',
        target,
        outcome: res.ok ? 'created' : 'error',
        error: res.ok ? undefined : res.error,
      })
      if (!res.ok) continue
    }
    await reconcileOptions(items, dryRun, obj.apiSlug, attr)
  }
}

async function reconcileLists(items: ProvisionItem[], dryRun: boolean): Promise<void> {
  const live = await listLists()
  if (!live.ok) {
    push(items, { action: 'create-list', target: '*', outcome: 'error', error: live.error })
    return
  }
  const have = new Set((live.data?.data ?? []).map((l) => l.api_slug ?? ''))

  for (const list of CRM_LISTS) {
    const exists = have.has(list.apiSlug)
    if (exists) {
      push(items, { action: 'create-list', target: list.apiSlug, outcome: 'exists' })
    } else if (dryRun) {
      push(items, { action: 'create-list', target: list.apiSlug, outcome: 'missing' })
      for (const attr of list.attributes) {
        push(items, {
          action: 'create-attribute',
          target: `${list.apiSlug}.${attr.apiSlug}`,
          outcome: 'missing',
        })
      }
      continue
    } else {
      const res = await createList(list.apiSlug, list.name, list.parentObject)
      push(items, {
        action: 'create-list',
        target: list.apiSlug,
        outcome: res.ok ? 'created' : 'error',
        error: res.ok ? undefined : res.error,
      })
      if (!res.ok) continue
    }

    const liveAttrs = await listListAttributes(list.apiSlug)
    if (!liveAttrs.ok) {
      push(items, {
        action: 'create-attribute',
        target: `${list.apiSlug}.*`,
        outcome: 'error',
        error: liveAttrs.error,
      })
      continue
    }
    const haveAttrs = new Set((liveAttrs.data?.data ?? []).map((a) => a.api_slug ?? ''))
    for (const attr of list.attributes) {
      const target = `${list.apiSlug}.${attr.apiSlug}`
      if (haveAttrs.has(attr.apiSlug)) {
        push(items, { action: 'create-attribute', target, outcome: 'exists' })
      } else if (dryRun) {
        push(items, { action: 'create-attribute', target, outcome: 'missing' })
      } else {
        const res = await createListAttribute(list.apiSlug, {
          apiSlug: attr.apiSlug,
          title: attr.title,
          type: attr.type,
          description: attr.description,
        })
        push(items, {
          action: 'create-attribute',
          target,
          outcome: res.ok ? 'created' : 'error',
          error: res.ok ? undefined : res.error,
        })
      }
    }
  }
}

/**
 * Seed the brokerage companies so a Brokerage Connection always resolves a parent company.
 * Asserted on `domains`, the unique attribute Attio ships on Companies, so re-runs update rather
 * than duplicate.
 */
async function seedCompanies(items: ProvisionItem[], dryRun: boolean): Promise<void> {
  for (const company of SEED_COMPANIES) {
    const target = `companies.${company.name}`
    if (dryRun) {
      push(items, { action: 'seed-company', target, outcome: 'missing' })
      continue
    }
    const res = await assertRecord('companies', 'domains', {
      name: company.name,
      domains: [{ domain: company.domain }],
      company_type: company.companyType,
    })
    push(items, {
      action: 'seed-company',
      target,
      outcome: res.ok ? 'created' : 'error',
      error: res.ok ? undefined : res.error,
    })
  }
}

/**
 * Reconcile the whole schema.
 *
 * @param dryRun when true nothing is written — the report lists what WOULD be created. Always
 *   run a dry run first: a wrong api_slug applied to a live workspace is effectively permanent.
 */
export async function provisionCrmSchema(dryRun: boolean): Promise<ProvisionReport> {
  const items: ProvisionItem[] = []

  if (!isAttioConfigured()) {
    return {
      configured: false,
      dryRun,
      items,
      created: 0,
      existing: 0,
      errors: 0,
      manualFollowUps: MANUAL_FOLLOW_UPS,
    }
  }

  const objects = await listObjects()
  if (!objects.ok) {
    push(items, { action: 'create-object', target: '*', outcome: 'error', error: objects.error })
  } else {
    const liveSlugs = new Set((objects.data?.data ?? []).map((o) => o.api_slug ?? ''))
    for (const obj of CRM_OBJECTS) {
      await reconcileObject(items, dryRun, obj, liveSlugs)
    }
    await reconcileLists(items, dryRun)
    await seedCompanies(items, dryRun)
  }

  return {
    configured: true,
    dryRun,
    items,
    created: items.filter((i) => i.outcome === 'created').length,
    existing: items.filter((i) => i.outcome === 'exists').length,
    errors: items.filter((i) => i.outcome === 'error').length,
    manualFollowUps: MANUAL_FOLLOW_UPS,
  }
}

/** Re-exported so the runtime mappers and the route agree on the matching attribute per object. */
export { MATCHING_ATTRIBUTE }
