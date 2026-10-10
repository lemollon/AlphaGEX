import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * Contract test for the operator backstop on #218's held posts — source-level,
 * same convention as ops/__tests__/customers-grant.test.ts: this route reaches
 * an operator session gate, the customers DB, and store.ts's publish/reject
 * paths, and the risk here is a missing guard or the wrong function wired in,
 * not logic a mock would meaningfully exercise. The behavioural coverage for
 * publish/reject/retry itself lives in
 * lib/community/__tests__/pending-moderation-retry.test.ts.
 */
const SRC = readFileSync(join(__dirname, '..', 'route.ts'), 'utf8')

describe('ops/community-pending-posts', () => {
  it('requires an operator session unless public mode is on', () => {
    expect(SRC).toContain('isPublicMode()')
    expect(SRC).toContain('getSession()')
    expect(SRC).toMatch(/Operator session required/)
  })

  it('both GET and POST are gated, not just one', () => {
    const getBody = SRC.slice(SRC.indexOf('export async function GET'), SRC.indexOf('export async function POST'))
    const postBody = SRC.slice(SRC.indexOf('export async function POST'))
    expect(getBody).toContain('await gate()')
    expect(postBody).toContain('await gate()')
  })

  it('lists through the same store function the retry job itself reads', () => {
    expect(SRC).toContain('listPendingMessages')
  })

  it('approve publishes through the exact function the retry job uses on a clean verdict', () => {
    const approveBranch = SRC.slice(SRC.indexOf("action === 'approve'"))
    expect(approveBranch).toContain('publishPendingMessage(pending)')
  })

  it('reject uses the exact function the retry job uses on a REJECTED verdict', () => {
    expect(SRC).toContain('rejectPendingMessage(pending')
  })

  it('rejects an unrecognized action rather than silently falling through to approve', () => {
    expect(SRC).toMatch(/action !== 'approve' && action !== 'reject'/)
    expect(SRC).toContain('status: 400')
  })

  it('404s a missing or already-resolved id instead of throwing', () => {
    expect(SRC).toContain('if (!pending)')
    expect(SRC).toContain('status: 404')
  })
})
