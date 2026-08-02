import { NextRequest, NextResponse } from 'next/server'
import { safeEqual } from '@/lib/auth/session'
import {
  AGENT_RULE_VERSION,
  buildAgentNote,
  checkAttributeWrite,
  checkListMembership,
  checkReadable,
  logAgentAction,
  type AgentAction,
} from '@/lib/crm/agent'
import {
  addListEntry,
  assertRecord,
  attioRequest,
  createNote,
  createTask,
  isAttioConfigured,
} from '@/lib/crm/client'

/**
 * The Claude agent's ONLY door into the CRM.
 *
 * Claude holds no Attio credential. Every capability it has is an action below, and anything not
 * explicitly allowlisted in lib/crm/agent.ts is refused — default deny. Approval-required
 * operations return a prepared change and are recorded; they are never applied here.
 *
 * Actions:
 *   search        {object, filter?, limit?}                     read
 *   qualify       {recordId, attribute, value, rationale?}      autonomous (allowlisted attrs only)
 *   note          {object, recordId, title, body, sourceRefs[]} autonomous, always AI-labelled
 *   task          {content, deadlineAt?, linkedRecords[]}       autonomous
 *   list_add      {list, recordId, entryValues?}                autonomous (approved lists only)
 *   list_remove   {list, entryId}                               autonomous (approved lists only)
 *   propose_change{object, recordId, attribute, value, rationale} always approval-required
 *
 * Deliberately absent: delete, merge, and bulk write. They are prohibited outright (spec §8.2),
 * so there is no code path to reach them — the agent can only flag duplicates via a note.
 *
 * Auth is a dedicated CRM_AGENT_TOKEN, distinct from the operator session and the service token,
 * so agent traffic is separable in logs and revocable on its own.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function agentAuthorized(req: NextRequest): boolean {
  const expected = process.env.CRM_AGENT_TOKEN
  if (!expected) return false // unset = closed, per the repo's fail-safe env convention
  return safeEqual(req.headers.get('x-crm-agent-token') ?? '', expected)
}

function agentIdOf(req: NextRequest): string {
  // Lets the three personas (waitlist / enrollment-ops / customer-ops) be told apart in the log.
  const raw = req.headers.get('x-crm-agent-id') ?? 'unknown-agent'
  return raw.slice(0, 64)
}

export async function POST(req: NextRequest) {
  if (!agentAuthorized(req)) {
    return NextResponse.json({ ok: false, error: 'CRM agent token required.' }, { status: 401 })
  }
  if (!isAttioConfigured()) {
    return NextResponse.json({ ok: false, error: 'ATTIO_API_KEY is not set.' }, { status: 503 })
  }

  const agentId = agentIdOf(req)
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const action = String(body.action ?? '') as AgentAction

  const str = (k: string): string => (typeof body[k] === 'string' ? (body[k] as string).trim() : '')
  const arr = (k: string): string[] =>
    Array.isArray(body[k]) ? (body[k] as unknown[]).filter((v): v is string => typeof v === 'string') : []

  switch (action) {
    // ---------------------------------------------------------------- read
    case 'search': {
      const object = str('object')
      const verdict = checkReadable(object)
      if (!verdict.allowed) {
        await logAgentAction({ agentId, action, outcome: 'blocked', objectSlug: object, error: verdict.reason })
        return NextResponse.json({ ok: false, outcome: 'blocked', reason: verdict.reason }, { status: 403 })
      }
      const limit = Math.min(Number(body.limit ?? 25) || 25, 100)
      const res = await attioRequest(`POST` as const, `/objects/${encodeURIComponent(object)}/records/query`, {
        limit,
        filter: (body.filter as Record<string, unknown>) ?? undefined,
      })
      await logAgentAction({
        agentId,
        action,
        outcome: 'applied',
        objectSlug: object,
        rationale: typeof body.rationale === 'string' ? body.rationale : null,
      })
      return NextResponse.json({ ok: res.ok, outcome: 'applied', data: res.data, error: res.error })
    }

    // ------------------------------------------------------- autonomous write
    case 'qualify': {
      const object = 'people'
      const recordId = str('recordId')
      const attribute = str('attribute')
      const value = body.value
      const verdict = checkAttributeWrite(object, attribute)

      if (!verdict.allowed) {
        await logAgentAction({
          agentId,
          action,
          outcome: verdict.outcome,
          objectSlug: object,
          recordId,
          attributeSlug: attribute,
          afterValue: value,
          rationale: str('rationale') || null,
          error: verdict.reason,
        })
        // 409 for approval-required (the request is well-formed but needs a human), 403 for blocked.
        return NextResponse.json(
          {
            ok: false,
            outcome: verdict.outcome,
            reason: verdict.reason,
            preparedChange:
              verdict.outcome === 'approval_required'
                ? { object, recordId, attribute, value, ruleVersion: AGENT_RULE_VERSION }
                : undefined,
          },
          { status: verdict.outcome === 'approval_required' ? 409 : 403 },
        )
      }

      // Read the current value so the audit row can reconstruct the change (AC-CRM-009).
      const current = await attioRequest<{ data?: { values?: Record<string, unknown> } }>(
        'GET',
        `/objects/${object}/records/${encodeURIComponent(recordId)}`,
      )
      const before = current.data?.data?.values?.[attribute] ?? null

      const res = await attioRequest(
        'PATCH',
        `/objects/${object}/records/${encodeURIComponent(recordId)}`,
        { data: { values: { [attribute]: value } } },
      )
      await logAgentAction({
        agentId,
        action,
        outcome: res.ok ? 'applied' : 'blocked',
        objectSlug: object,
        recordId,
        attributeSlug: attribute,
        beforeValue: before,
        afterValue: value,
        rationale: str('rationale') || null,
        error: res.ok ? null : res.error,
      })
      return NextResponse.json({ ok: res.ok, outcome: res.ok ? 'applied' : 'blocked', error: res.error })
    }

    case 'note': {
      const object = str('object') || 'people'
      const recordId = str('recordId')
      const verdict = checkReadable(object)
      if (!verdict.allowed || !recordId) {
        await logAgentAction({ agentId, action, outcome: 'blocked', objectSlug: object, recordId, error: verdict.reason })
        return NextResponse.json({ ok: false, outcome: 'blocked', reason: verdict.reason }, { status: 403 })
      }
      const sourceRefs = arr('sourceRefs')
      const content = buildAgentNote(str('body'), sourceRefs)
      const res = await createNote(object, recordId, str('title') || 'IronForge CRM agent', content)
      await logAgentAction({
        agentId,
        action,
        outcome: res.ok ? 'applied' : 'blocked',
        objectSlug: object,
        recordId,
        afterValue: { title: str('title'), labelled: true },
        sourceRefs,
        error: res.ok ? null : res.error,
      })
      return NextResponse.json({ ok: res.ok, outcome: 'applied', error: res.error })
    }

    case 'task': {
      const linked = Array.isArray(body.linkedRecords)
        ? (body.linkedRecords as Array<{ target_object: string; target_record_id: string }>)
        : []
      const res = await createTask(str('content'), str('deadlineAt') || null, linked)
      await logAgentAction({
        agentId,
        action,
        outcome: res.ok ? 'applied' : 'blocked',
        afterValue: { content: str('content'), deadlineAt: str('deadlineAt') || null },
        rationale: str('rationale') || null,
        sourceRefs: linked,
        error: res.ok ? null : res.error,
      })
      return NextResponse.json({ ok: res.ok, outcome: 'applied', error: res.error })
    }

    case 'list_add':
    case 'list_remove': {
      const list = str('list')
      const verdict = checkListMembership(list)
      if (!verdict.allowed) {
        await logAgentAction({ agentId, action, outcome: 'blocked', objectSlug: list, error: verdict.reason })
        return NextResponse.json({ ok: false, outcome: 'blocked', reason: verdict.reason }, { status: 403 })
      }
      const res =
        action === 'list_add'
          ? await addListEntry(list, str('recordId'), str('object') || 'people', (body.entryValues as Record<string, unknown>) ?? {})
          // Removing a LIST ENTRY is explicitly autonomous under spec §8.2 ("add/remove records
          // from approved operational lists"). It detaches the person from a campaign; it does
          // not delete the Person record, which remains prohibited.
          : await attioRequest('DELETE', `/lists/${encodeURIComponent(list)}/entries/${encodeURIComponent(str('entryId'))}`)
      await logAgentAction({
        agentId,
        action,
        outcome: res.ok ? 'applied' : 'blocked',
        objectSlug: list,
        recordId: str('recordId') || str('entryId'),
        error: res.ok ? null : res.error,
      })
      return NextResponse.json({ ok: res.ok, outcome: 'applied', error: res.error })
    }

    // ------------------------------------------------- always human-approved
    case 'propose_change': {
      const object = str('object')
      const recordId = str('recordId')
      const attribute = str('attribute')
      const prepared = { object, recordId, attribute, value: body.value, ruleVersion: AGENT_RULE_VERSION }
      await logAgentAction({
        agentId,
        action,
        outcome: 'approval_required',
        objectSlug: object,
        recordId,
        attributeSlug: attribute,
        afterValue: body.value,
        rationale: str('rationale') || null,
        sourceRefs: arr('sourceRefs'),
      })
      return NextResponse.json(
        {
          ok: true,
          outcome: 'approval_required',
          preparedChange: prepared,
          reason: 'Recorded for human approval. Nothing was written.',
        },
        { status: 202 },
      )
    }

    default:
      await logAgentAction({ agentId, action: 'search', outcome: 'blocked', error: `unknown action "${action}"` })
      return NextResponse.json(
        {
          ok: false,
          outcome: 'blocked',
          reason: `Unknown or prohibited action "${action}". Delete, merge and bulk writes have no code path here.`,
        },
        { status: 403 },
      )
  }
}

/** Lets an operator (or the agent itself) read back the effective permission matrix. */
export async function GET(req: NextRequest) {
  if (!agentAuthorized(req)) {
    return NextResponse.json({ ok: false, error: 'CRM agent token required.' }, { status: 401 })
  }
  const { AUTONOMOUS_ATTRIBUTES, APPROVAL_REQUIRED_ATTRIBUTES, READ_ONLY_OBJECTS, APPROVED_LISTS } =
    await import('@/lib/crm/agent')
  return NextResponse.json({
    ok: true,
    ruleVersion: AGENT_RULE_VERSION,
    autonomous: AUTONOMOUS_ATTRIBUTES,
    approvalRequired: APPROVAL_REQUIRED_ATTRIBUTES,
    readOnlyObjects: READ_ONLY_OBJECTS,
    approvedLists: APPROVED_LISTS,
    prohibited: ['delete', 'merge', 'bulk_write', 'object_configuration'],
  })
}
