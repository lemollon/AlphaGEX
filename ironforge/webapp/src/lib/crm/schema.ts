/**
 * IronForge CRM schema descriptor — the Attio data model as data.
 *
 * This is a direct transcription of IronForge_CRM_Data_Dictionary.xlsx (Data Dictionary sheet)
 * and is the single source of truth for BOTH the provisioner (src/lib/crm/provision.ts, which
 * creates this schema in the Attio workspace) and the runtime event mappers
 * (src/lib/crm/events.ts, which write records against these slugs).
 *
 * Rules that are load-bearing — do not "clean these up":
 *
 * 1. `apiSlug` values are integration identifiers. Renaming an attribute's UI label in Attio is
 *    safe; changing a slug here silently breaks every write that references it. Spec §13.1
 *    requires a Decision Log entry for any slug change.
 * 2. Attributes used as an upsert `matching_attribute` MUST be `isUnique: true` — Attio rejects
 *    a non-unique matching attribute. That is why ironforge_user_id / membership_id /
 *    connection_id are unique and, e.g., stripe_customer_id is not (one customer, many
 *    memberships over time).
 * 3. Select/status option ORDER is meaningful — it drives the Enrollment Pipeline kanban column
 *    order and the Views & Lists sort specs. Append new options at the end rather than
 *    reordering.
 * 4. Nothing sensitive appears here by construction. Payment credentials, bank data, brokerage
 *    tokens, passwords, and raw provider payloads are excluded from the CRM entirely
 *    (spec §2.2 / §9, AC-CRM-006 and AC-CRM-007). The only brokerage error fields are a
 *    normalized code and a customer-safe summary.
 */

/** Attio attribute types used by this schema. */
export type CrmAttributeType =
  | 'text'
  | 'checkbox'
  | 'date'
  | 'timestamp'
  | 'select'
  | 'status'
  | 'record-reference'

export interface CrmAttribute {
  /** Stable integration identifier. Never rename without a Decision Log entry. */
  apiSlug: string
  /** Human label shown in the Attio UI. */
  title: string
  type: CrmAttributeType
  /** Attio `is_unique`. Required for any attribute used as an upsert matching key. */
  isUnique?: boolean
  /** Ordered option list for `select` / `status` attributes. Order is significant. */
  options?: readonly string[]
  /** For `record-reference`: the object slug this attribute points at. */
  referenceTarget?: string
  /** Why this field exists / where its value comes from. Surfaces in the drift report. */
  description: string
}

export interface CrmObject {
  /** Attio object slug. `people` and `companies` are standard objects that already exist. */
  apiSlug: string
  singularNoun: string
  pluralNoun: string
  /** True for Attio's built-in objects — the provisioner adds attributes but never creates them. */
  isStandard: boolean
  /** Custom attributes this integration owns. Standard Attio attributes are not listed. */
  attributes: readonly CrmAttribute[]
}

// ---------------------------------------------------------------------------
// Allowed-value vocabularies (Data Dictionary "Allowed Values" column)
// ---------------------------------------------------------------------------

/**
 * Customer lifecycle. Backend-owned: only IronForge events may publish these (spec §6).
 * Claude may recommend a change but never write one (AC-CRM-008).
 */
export const CUSTOMER_LIFECYCLE = [
  'Waitlist',
  'Invited',
  'Enrollment Started',
  'Billing Complete',
  'Active',
  'Paused',
  'Canceled',
] as const

/**
 * The six Data Dictionary bands, PLUS '$50K+'.
 *
 * Documented deviation: the live waitlist form (lib/waitlist.ts CAPITAL_RANGES) offers five
 * options whose top band is the open-ended `50000_plus`. That value cannot be split into
 * '$50K-$100K' vs '$100K+' without inventing information about the lead, and dropping it would
 * blank out Trading Volume for exactly the segment the "Waitlist - Priority" view sorts on.
 * '$50K+' is therefore the truthful landing spot for today's form; the two finer bands stay in
 * the vocabulary for when the form is widened. Needs a Decision Log entry (spec §13.1).
 */
export const TRADING_VOLUME = [
  'Under $5K',
  '$5K-$10K',
  '$10K-$25K',
  '$25K-$50K',
  '$50K+',
  '$50K-$100K',
  '$100K+',
] as const

/**
 * Waitlist form value → Trading Volume band. Exhaustive over CAPITAL_RANGES; an unrecognised
 * value maps to undefined so the attribute is simply omitted rather than guessed at.
 */
export const CAPITAL_RANGE_TO_VOLUME: Record<string, string> = {
  under_5000: 'Under $5K',
  '5000_10000': '$5K-$10K',
  '10000_25000': '$10K-$25K',
  '25000_50000': '$25K-$50K',
  '50000_plus': '$50K+',
}

/**
 * Campaign attribution → Lead Source. The form stores raw utm_source plus a referral code;
 * anything unmapped becomes 'Other' rather than being dropped, so attribution is never silently
 * lost. A present referral code wins — a referred lead is a referral regardless of utm_source.
 */
export function toLeadSource(campaign: Record<string, unknown> | null | undefined): string {
  if (!campaign) return 'Organic'
  if (typeof campaign.referralCode === 'string' && campaign.referralCode.trim()) return 'Referral'
  const raw = typeof campaign.utm_source === 'string' ? campaign.utm_source.trim().toLowerCase() : ''
  if (!raw) return 'Organic'
  const map: Record<string, string> = {
    linkedin: 'LinkedIn',
    x: 'X',
    twitter: 'X',
    instagram: 'Instagram',
    ig: 'Instagram',
    facebook: 'Facebook',
    fb: 'Facebook',
    referral: 'Referral',
    partner: 'Partner',
    organic: 'Organic',
    google: 'Organic',
    direct: 'Organic',
  }
  return map[raw] ?? 'Other'
}

export const LEAD_SOURCE = [
  'Organic',
  'LinkedIn',
  'X',
  'Instagram',
  'Facebook',
  'Referral',
  'Partner',
  'Other',
] as const

/** Claude may set this autonomously using versioned rules (spec §8.2). */
export const LEAD_PRIORITY = ['High', 'Medium', 'Low', 'Needs Review'] as const

/** Claude may set non-billing flags autonomously. */
export const ACCOUNT_HEALTH = ['Healthy', 'Needs Review', 'At Risk', 'Blocked'] as const

/**
 * Plan family. The spec's vocabulary, kept because it is what drives the activation rule:
 * Community activates on billing alone; Automate additionally requires a Connected brokerage
 * (spec §6.1, AC-CRM-004 / AC-CRM-005).
 */
export const MEMBERSHIP_PLAN = ['Forge Community', 'Forge Automate'] as const

/**
 * The actual thing purchased. The live catalogue is Spark $50 / Flame $50 / bundle $75 /
 * community $10 (lib/billing/plans.ts) — "Forge Automate" is a family, not a Stripe product,
 * so the plan family alone cannot tell you what a customer bought. Community memberships
 * carry '—'.
 */
export const MEMBERSHIP_BOT = ['Spark', 'Flame', 'Spark + Flame Bundle', '—'] as const

/** Mirrors customer_bot_subscriptions.status, normalized by the backend. */
export const MEMBERSHIP_STATUS = ['Pending', 'Active', 'Paused', 'Past Due', 'Canceled'] as const

export const CANCELLATION_REASON = [
  'Price',
  'Product Fit',
  'Performance Concern',
  'Technical Issue',
  'Brokerage Issue',
  'Support',
  'Other',
] as const

/**
 * Brokerage connection state. Richer than the internal brokerage_connections.status
 * (pending|active|disabled|removed) — the backend maps onto this, splitting 'disabled' into
 * Disconnected vs Reauthorization Required, because the Brokerage Issues view exists to make
 * "customer must reauthorize" actionable.
 */
export const CONNECTION_STATUS = [
  'Not Started',
  'Pending',
  'Connected',
  'Failed',
  'Disconnected',
  'Reauthorization Required',
] as const

export const COMPANY_TYPE = ['Brokerage', 'Technology Vendor', 'Partner', 'Other'] as const

// ---------------------------------------------------------------------------
// Objects
// ---------------------------------------------------------------------------

const PEOPLE: CrmObject = {
  apiSlug: 'people',
  singularNoun: 'Person',
  pluralNoun: 'People',
  isStandard: true,
  attributes: [
    {
      apiSlug: 'ironforge_user_id',
      title: 'IronForge User ID',
      type: 'text',
      // NOT unique, though the data dictionary implies it should be. Attio rejects a new unique
      // attribute on a STANDARD object with 400 "Cannot set attribute as unique" — verified
      // against the live workspace, where the same is_unique:true succeeded on both custom
      // objects. Harmless in practice: People are always upserted on email_addresses (Attio's
      // own unique attribute), so ironforge_user_id is a stored cross-reference rather than a
      // match key, and DEC-004's "durable identifier after account creation" still holds for
      // every internal lookup. Worth a Decision Log entry.
      description:
        'users.id from the customers DB. Cross-reference to the durable internal identity ' +
        '(DEC-004); email_addresses remains the Attio match key because Attio will not allow a ' +
        'second unique attribute on People.',
    },
    {
      apiSlug: 'customer_lifecycle',
      title: 'Customer Lifecycle',
      type: 'status',
      options: CUSTOMER_LIFECYCLE,
      description:
        'Backend-derived relationship stage. Published only by IronForge events — Claude is ' +
        'approval-required here (AC-CRM-008).',
    },
    {
      apiSlug: 'trading_volume',
      title: 'Trading Volume',
      type: 'select',
      options: TRADING_VOLUME,
      description:
        'Self-reported band from the waitlist form. Maps from waitlist_submissions.trading_capital_range.',
    },
    {
      apiSlug: 'lead_source',
      title: 'Lead Source',
      type: 'select',
      options: LEAD_SOURCE,
      description:
        'Acquisition source, normalized from the waitlist campaign jsonb (utm_source / referralCode).',
    },
    {
      apiSlug: 'lead_priority',
      title: 'Lead Priority',
      type: 'select',
      options: LEAD_PRIORITY,
      description:
        'Operational qualification. The one People field Claude may write autonomously, using ' +
        'versioned rules; every write is logged to crm_agent_actions.',
    },
    {
      apiSlug: 'waitlist_date',
      title: 'Waitlist Date',
      type: 'timestamp',
      description: 'First waitlist registration. Write-once — never updated on resubmission.',
    },
    {
      apiSlug: 'marketing_consent',
      title: 'Marketing Consent',
      type: 'checkbox',
      description:
        'Captured from the source form with a consent version. Read-only to Claude (spec §9).',
    },
    {
      apiSlug: 'account_health',
      title: 'Account Health',
      type: 'status',
      options: ACCOUNT_HEALTH,
      description:
        'Operational health derived from enrollment/billing/connection state. Claude may set ' +
        'non-billing flags autonomously.',
    },
  ],
}

const COMPANIES: CrmObject = {
  apiSlug: 'companies',
  singularNoun: 'Company',
  pluralNoun: 'Companies',
  isStandard: true,
  attributes: [
    {
      apiSlug: 'company_type',
      title: 'Company Type',
      type: 'select',
      options: COMPANY_TYPE,
      description: 'Business classification. Brokerages are the parent of Brokerage Connections.',
    },
  ],
}

const MEMBERSHIPS: CrmObject = {
  apiSlug: 'memberships',
  singularNoun: 'Membership',
  pluralNoun: 'Memberships',
  isStandard: false,
  attributes: [
    {
      apiSlug: 'membership_id',
      title: 'Membership ID',
      type: 'text',
      isUnique: true,
      description:
        'Upsert matching key. Sourced from stripe_subscription_id (falling back to ' +
        '"{user_id}:{bot}" for community/no-subscription rows) rather than the ' +
        'customer_bot_subscriptions row id, because that row is UNIQUE(user_id, bot) and is ' +
        'overwritten on reactivation. Keying on the subscription makes a returning customer a ' +
        'NEW membership record and leaves history intact (AC-CRM-013).',
    },
    {
      apiSlug: 'member',
      title: 'Member',
      type: 'record-reference',
      referenceTarget: 'people',
      description: 'The person who owns this membership. One person may hold many over time.',
    },
    {
      apiSlug: 'plan',
      title: 'Plan',
      type: 'select',
      options: MEMBERSHIP_PLAN,
      description: 'Plan family. Drives the activation rule (Community vs Automate).',
    },
    {
      apiSlug: 'bot',
      title: 'Bot',
      type: 'select',
      options: MEMBERSHIP_BOT,
      description:
        'What was actually purchased, derived from the Stripe price lookup key. Carries the ' +
        'truth the plan family cannot express.',
    },
    {
      apiSlug: 'membership_status',
      title: 'Membership Status',
      type: 'status',
      options: MEMBERSHIP_STATUS,
      description: 'Billing/entitlement status, backend-normalized from Stripe. Read-only to Claude.',
    },
    {
      apiSlug: 'stripe_customer_id',
      title: 'Stripe Customer ID',
      type: 'text',
      description: 'Reference identifier only. No card, bank, or secret data (AC-CRM-006).',
    },
    {
      apiSlug: 'stripe_subscription_id',
      title: 'Stripe Subscription ID',
      type: 'text',
      description: 'Reference identifier only.',
    },
    {
      apiSlug: 'start_date',
      title: 'Start Date',
      type: 'date',
      description: 'Date the membership became active.',
    },
    {
      apiSlug: 'cancellation_date',
      title: 'Cancellation Date',
      type: 'date',
      description:
        'Date the membership terminated. Not in the Data Dictionary sheet but required as a ' +
        'column and sort key by the Paused & Canceled view (Views & Lists sheet).',
    },
    {
      apiSlug: 'cancellation_reason',
      title: 'Cancellation Reason',
      type: 'select',
      options: CANCELLATION_REASON,
      description: 'Standardized reason captured at cancellation. Staff/Claude may correct it.',
    },
  ],
}

const BROKERAGE_CONNECTIONS: CrmObject = {
  apiSlug: 'brokerage_connections',
  singularNoun: 'Brokerage Connection',
  pluralNoun: 'Brokerage Connections',
  isStandard: false,
  attributes: [
    {
      apiSlug: 'connection_id',
      title: 'Connection ID',
      type: 'text',
      isUnique: true,
      description:
        'brokerage_connections.id — immutable upsert matching key for every connection event.',
    },
    {
      apiSlug: 'member',
      title: 'Member',
      type: 'record-reference',
      referenceTarget: 'people',
      description: 'The customer this connection belongs to.',
    },
    {
      apiSlug: 'brokerage',
      title: 'Brokerage',
      type: 'record-reference',
      referenceTarget: 'companies',
      description: 'The brokerage company (Tradier, tastytrade, SnapTrade).',
    },
    {
      apiSlug: 'connection_status',
      title: 'Connection Status',
      type: 'status',
      options: CONNECTION_STATUS,
      description: 'Operational state, backend-normalized. Read-only to Claude.',
    },
    {
      apiSlug: 'last_attempt_at',
      title: 'Last Attempt',
      type: 'timestamp',
      description: 'Most recent connect or refresh attempt. Sort key for the Brokerage Issues view.',
    },
    {
      apiSlug: 'last_error_code',
      title: 'Last Error Code',
      type: 'text',
      description:
        'Normalized, non-secret integration error code (e.g. ACCOUNT_NOT_ACTIVE). Never a raw ' +
        'provider payload.',
    },
    {
      apiSlug: 'last_error_summary',
      title: 'Last Error Summary',
      type: 'text',
      description:
        'Customer-safe one-line explanation. Redaction is enforced in crm/events.ts — tokens, ' +
        'credentials, and raw payloads must never reach this field (AC-CRM-007).',
    },
    {
      apiSlug: 'reauthorization_required',
      title: 'Reauthorization Required',
      type: 'checkbox',
      description: 'True when the customer must re-grant access. Drives the Brokerage Issues view.',
    },
  ],
}

export const CRM_OBJECTS: readonly CrmObject[] = [
  PEOPLE,
  COMPANIES,
  MEMBERSHIPS,
  BROKERAGE_CONNECTIONS,
]

// ---------------------------------------------------------------------------
// Lists
// ---------------------------------------------------------------------------

export interface CrmList {
  apiSlug: string
  name: string
  parentObject: string
  attributes: readonly CrmAttribute[]
  description: string
}

/**
 * Lists model temporary/campaign workflow. Per spec §5.1 these fields deliberately live on the
 * list entry rather than on People, so campaign state never pollutes the permanent person record.
 */
export const CRM_LISTS: readonly CrmList[] = [
  {
    apiSlug: 'ironforge_waitlist',
    name: 'IronForge Waitlist',
    parentObject: 'people',
    description:
      'Every waitlist submission. NOTE: POST /api/waitlist already writes entries here via ' +
      'ATTIO_WAITLIST_LIST, but the list does not exist in the workspace yet and ' +
      'addToWaitlistList swallows the failure — so these entry values have been silently ' +
      'dropped since launch. Provisioning this list is what makes that path start working.',
    attributes: [
      {
        apiSlug: 'trading_capital_range',
        title: 'Trading Capital Range',
        type: 'text',
        description: 'Raw enum from the form (under_5000 … 50000_plus), as the API already sends it.',
      },
      {
        apiSlug: 'communication_consent',
        title: 'Communication Consent',
        type: 'checkbox',
        description: 'Consent captured at submission.',
      },
      {
        apiSlug: 'consent_version',
        title: 'Consent Version',
        type: 'text',
        description: 'e.g. waitlist-v1-2026-08-01. Compliance evidence for what was agreed to.',
      },
      {
        apiSlug: 'submission_id',
        title: 'Submission ID',
        type: 'text',
        description: 'wl_<uuid> — correlates the Attio entry back to waitlist_submissions.',
      },
      {
        apiSlug: 'confirmation_email_status',
        title: 'Confirmation Email Status',
        type: 'text',
        description: 'Pending | sent | failed, mirrored from waitlist_submissions.email_status.',
      },
    ],
  },
  {
    apiSlug: 'founding_member_outreach',
    name: 'Founding Member Outreach',
    parentObject: 'people',
    description:
      'Campaign list for founder outreach to high-priority waitlist leads. Claude may add and ' +
      'remove entries autonomously (spec §8.2).',
    attributes: [
      {
        apiSlug: 'outreach_owner',
        title: 'Outreach Owner',
        type: 'text',
        description: 'Who owns the follow-up.',
      },
      {
        apiSlug: 'outreach_status',
        title: 'Outreach Status',
        type: 'select',
        options: ['Not Started', 'Contacted', 'Replied', 'Meeting Booked', 'Closed', 'No Response'],
        description: 'Where this lead stands in the campaign.',
      },
      {
        apiSlug: 'last_touch',
        title: 'Last Touch',
        type: 'timestamp',
        description: 'Most recent outbound contact.',
      },
      {
        apiSlug: 'next_follow_up',
        title: 'Next Follow-up',
        type: 'date',
        description: 'Sort key for the Founding Member Outreach view.',
      },
      {
        apiSlug: 'response',
        title: 'Response',
        type: 'text',
        description: 'Factual summary of what the lead said. Never a fabricated quote (spec §8.2).',
      },
    ],
  },
]

// ---------------------------------------------------------------------------
// Reference data
// ---------------------------------------------------------------------------

/**
 * Brokerage companies seeded so Brokerage Connections always resolve a parent. Matches the
 * providers the codebase actually integrates: direct Tradier OAuth, and tastytrade via SnapTrade.
 */
export const SEED_COMPANIES = [
  { name: 'Tradier', companyType: 'Brokerage', domain: 'tradier.com' },
  { name: 'tastytrade', companyType: 'Brokerage', domain: 'tastytrade.com' },
  { name: 'SnapTrade', companyType: 'Technology Vendor', domain: 'snaptrade.com' },
] as const

/** Object slugs whose upsert matching attribute is not the Attio default. */
export const MATCHING_ATTRIBUTE: Record<string, string> = {
  people: 'email_addresses',
  memberships: 'membership_id',
  brokerage_connections: 'connection_id',
}
