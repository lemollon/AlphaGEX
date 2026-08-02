/**
 * Claude agent permission matrix — enforced server-side.
 *
 * Spec §8.2 grants Claude autonomous writes to a few operational fields, read-only access to
 * lifecycle/membership/brokerage truth, and prohibits delete/merge entirely. AC-CRM-008 requires
 * that this be ENFORCED, not merely instructed.
 *
 * An Attio API key cannot express it. Attio's record write scope is all-or-nothing per object,
 * so any key that lets the agent set `lead_priority` on a Person equally lets it overwrite
 * `customer_lifecycle` on that same Person. Handing Claude a key and writing "please don't"
 * in its instructions is not a control — it is a hope.
 *
 * So Claude gets no Attio credential at all. It calls this façade, which:
 *   1. resolves every request against the allowlist below,
 *   2. refuses anything not explicitly permitted (default deny),
 *   3. returns a PREPARED CHANGE rather than applying it for approval-required operations,
 *   4. writes every decision — applied, blocked, or approval-required — to crm_agent_actions
 *      with before/after values, so AC-CRM-009 is answerable from data.
 *
 * The blast radius of a compromised or confused agent is therefore bounded by this file, not by
 * the agent's good behaviour.
 */

import { customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'

/** Bump when the allowlist or the agent instructions change; recorded on every logged action. */
export const AGENT_RULE_VERSION = 'crm-agent-v1-2026-08-02'

export type AgentAction =
  | 'search'
  | 'qualify'
  | 'note'
  | 'task'
  | 'list_add'
  | 'list_remove'
  | 'propose_change'

export type AgentOutcome = 'applied' | 'blocked' | 'approval_required'

/**
 * Attributes the agent may write on its own authority. Everything absent from this map is
 * either read-only or approval-required — there is no implicit permission.
 */
export const AUTONOMOUS_ATTRIBUTES: Record<string, readonly string[]> = {
  people: ['lead_priority', 'account_health'],
}

/**
 * Attributes the agent may RECOMMEND but never write. A request against these returns a prepared
 * change for a human to apply; the spec is explicit that only the backend publishes lifecycle.
 */
export const APPROVAL_REQUIRED_ATTRIBUTES: Record<string, readonly string[]> = {
  people: ['customer_lifecycle'],
}

/**
 * Objects whose every attribute is read-only to the agent. These mirror Stripe and the brokerage
 * integrations; letting an agent edit them would let it manufacture billing or connection truth,
 * which is the single thing the whole architecture exists to prevent.
 */
export const READ_ONLY_OBJECTS: readonly string[] = ['memberships', 'brokerage_connections']

/** Lists the agent may add to and remove from. A new list is a human decision (spec §8.2). */
export const APPROVED_LISTS: readonly string[] = ['founding_member_outreach']

/** Objects the agent may read. Reading is the broadest routine capability and is safe. */
export const READABLE_OBJECTS: readonly string[] = [
  'people',
  'companies',
  'memberships',
  'brokerage_connections',
]

/**
 * Prefix on every agent-authored note. AC-CRM-014 requires AI content to be visibly labelled and
 * to cite what it was derived from — an operator must never mistake a model's inference for a
 * customer's statement.
 */
export const AI_NOTE_PREFIX = '🤖 AI-generated (IronForge CRM agent)'

export interface PermissionVerdict {
  allowed: boolean
  outcome: AgentOutcome
  reason: string
}

/**
 * The whole decision, in one place. Order matters: prohibitions are checked before permissions
 * so that a mistake in the allowlist cannot accidentally grant a prohibited capability.
 */
export function checkAttributeWrite(objectSlug: string, attributeSlug: string): PermissionVerdict {
  if (READ_ONLY_OBJECTS.includes(objectSlug)) {
    return {
      allowed: false,
      outcome: 'blocked',
      reason: `${objectSlug} is read-only to the agent — its values mirror Stripe/brokerage truth and may only be changed by backend events.`,
    }
  }
  if ((APPROVAL_REQUIRED_ATTRIBUTES[objectSlug] ?? []).includes(attributeSlug)) {
    return {
      allowed: false,
      outcome: 'approval_required',
      reason: `${objectSlug}.${attributeSlug} requires human approval; a prepared change has been recorded instead of applied.`,
    }
  }
  if ((AUTONOMOUS_ATTRIBUTES[objectSlug] ?? []).includes(attributeSlug)) {
    return { allowed: true, outcome: 'applied', reason: 'permitted autonomous write' }
  }
  // Default deny. An attribute nobody thought about is not writable by an agent.
  return {
    allowed: false,
    outcome: 'blocked',
    reason: `${objectSlug}.${attributeSlug} is not in the agent's autonomous write allowlist.`,
  }
}

export function checkListMembership(listSlug: string): PermissionVerdict {
  if (APPROVED_LISTS.includes(listSlug)) {
    return { allowed: true, outcome: 'applied', reason: 'approved operational list' }
  }
  return {
    allowed: false,
    outcome: 'blocked',
    reason: `${listSlug} is not an approved operational list. Creating or using new permanent structures is a human decision.`,
  }
}

export function checkReadable(objectSlug: string): PermissionVerdict {
  if (READABLE_OBJECTS.includes(objectSlug)) {
    return { allowed: true, outcome: 'applied', reason: 'readable' }
  }
  return { allowed: false, outcome: 'blocked', reason: `${objectSlug} is not a readable object.` }
}

export interface AgentActionLog {
  agentId: string
  action: AgentAction
  outcome: AgentOutcome
  objectSlug?: string | null
  recordId?: string | null
  attributeSlug?: string | null
  beforeValue?: unknown
  afterValue?: unknown
  approver?: string | null
  rationale?: string | null
  sourceRefs?: unknown
  error?: string | null
}

/**
 * Record what the agent did, or was stopped from doing. Never throws: losing the audit row must
 * not change the outcome of the request, but a failure is logged loudly because an unlogged
 * agent write would breach AC-CRM-009.
 */
export async function logAgentAction(entry: AgentActionLog): Promise<void> {
  if (!isCustomersDbConfigured()) return
  try {
    await customerExecute(
      `INSERT INTO crm_agent_actions
         (agent_id, action, outcome, object_slug, record_id, attribute_slug,
          before_value, after_value, rule_version, approver, rationale, source_refs, error)
       VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10,$11,$12::jsonb,$13)`,
      [
        entry.agentId,
        entry.action,
        entry.outcome,
        entry.objectSlug ?? null,
        entry.recordId ?? null,
        entry.attributeSlug ?? null,
        JSON.stringify(entry.beforeValue ?? null),
        JSON.stringify(entry.afterValue ?? null),
        AGENT_RULE_VERSION,
        entry.approver ?? null,
        entry.rationale ?? null,
        JSON.stringify(entry.sourceRefs ?? null),
        entry.error ? entry.error.slice(0, 500) : null,
      ],
    )
  } catch (e) {
    console.error('[crm-agent] FAILED to write audit row (action still governed):', e)
  }
}

/**
 * Build a labelled note body. Source references are mandatory, not decorative — an unattributed
 * AI summary is exactly the thing an operator cannot safely act on.
 */
export function buildAgentNote(body: string, sourceRefs: string[]): string {
  const sources = sourceRefs.length > 0 ? sourceRefs.join(', ') : 'none supplied'
  return `${AI_NOTE_PREFIX}\nRule version: ${AGENT_RULE_VERSION}\nSources: ${sources}\n\n${body.trim()}`
}
