import { describe, it, expect } from 'vitest'
import {
  AI_NOTE_PREFIX,
  AGENT_RULE_VERSION,
  buildAgentNote,
  checkAttributeWrite,
  checkListMembership,
  checkReadable,
} from '../agent'

/**
 * AC-CRM-008: "Claude cannot alter restricted lifecycle, billing, membership, or brokerage truth
 * without approval." These tests are the evidence for that sign-off, so they assert the
 * PROHIBITIONS as hard as the permissions — a permission matrix that only tests the happy path
 * proves nothing.
 */
describe('agent permission matrix — autonomous writes', () => {
  it('allows the two qualification fields the spec grants', () => {
    expect(checkAttributeWrite('people', 'lead_priority').allowed).toBe(true)
    expect(checkAttributeWrite('people', 'account_health').allowed).toBe(true)
  })

  it('requires approval for customer lifecycle — never applies it', () => {
    const v = checkAttributeWrite('people', 'customer_lifecycle')
    expect(v.allowed).toBe(false)
    expect(v.outcome).toBe('approval_required')
  })

  it('blocks every membership/billing attribute', () => {
    for (const attr of ['membership_status', 'plan', 'stripe_customer_id', 'stripe_subscription_id', 'start_date']) {
      const v = checkAttributeWrite('memberships', attr)
      expect(v.allowed, attr).toBe(false)
      expect(v.outcome, attr).toBe('blocked')
    }
  })

  it('blocks every brokerage attribute, including the reauthorization flag', () => {
    for (const attr of ['connection_status', 'reauthorization_required', 'last_error_code', 'connection_id']) {
      const v = checkAttributeWrite('brokerage_connections', attr)
      expect(v.allowed, attr).toBe(false)
      expect(v.outcome, attr).toBe('blocked')
    }
  })

  it('defaults to DENY for an attribute nobody enumerated', () => {
    const v = checkAttributeWrite('people', 'some_future_attribute')
    expect(v.allowed).toBe(false)
    expect(v.outcome).toBe('blocked')
  })

  it('does not let a read-only object be written even if the attribute name matches an allowed one', () => {
    // 'account_health' is autonomous on people; it must NOT leak onto a read-only object.
    const v = checkAttributeWrite('memberships', 'account_health')
    expect(v.allowed).toBe(false)
    expect(v.outcome).toBe('blocked')
  })

  it('blocks writes to an object that does not exist in the matrix at all', () => {
    expect(checkAttributeWrite('workspaces', 'anything').allowed).toBe(false)
  })
})

describe('agent permission matrix — lists', () => {
  it('allows the approved campaign list', () => {
    expect(checkListMembership('founding_member_outreach').allowed).toBe(true)
  })

  it('blocks an unapproved list — new permanent structures are a human decision', () => {
    expect(checkListMembership('ironforge_waitlist').allowed).toBe(false)
    expect(checkListMembership('customer_success').allowed).toBe(false)
    expect(checkListMembership('anything_else').allowed).toBe(false)
  })
})

describe('agent permission matrix — reads', () => {
  it('permits reading all four CRM objects (read is the broad routine capability)', () => {
    for (const o of ['people', 'companies', 'memberships', 'brokerage_connections']) {
      expect(checkReadable(o).allowed, o).toBe(true)
    }
  })

  it('refuses an unknown object', () => {
    expect(checkReadable('secrets').allowed).toBe(false)
  })
})

describe('AI note labelling (AC-CRM-014)', () => {
  it('labels the note and cites its sources', () => {
    const note = buildAgentNote('Lead looks high value.', ['wl_123', 'person_abc'])
    expect(note.startsWith(AI_NOTE_PREFIX)).toBe(true)
    expect(note).toContain('wl_123')
    expect(note).toContain('person_abc')
    expect(note).toContain(AGENT_RULE_VERSION)
    expect(note).toContain('Lead looks high value.')
  })

  it('is explicit when no sources were supplied rather than silently omitting the line', () => {
    expect(buildAgentNote('body', [])).toContain('none supplied')
  })
})
