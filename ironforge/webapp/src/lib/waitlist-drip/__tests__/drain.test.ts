import { describe, it, expect, vi } from 'vitest'
import { advanceAfterSend, drainWaitlistDrip, idempotencyKeyFor, sendPreconditionBlocker, type ClaimedRow, type DrainDeps } from '../drain'
import { fromCtWallClock } from '../schedule'
import type { SuppressionFacts } from '../suppression'

/**
 * A tiny in-memory stand-in for the four SQL statements the drain issues, keyed on the
 * statement's shape. It records every send and every status transition so the tests can
 * assert on the SEQUENCE of what happened, which is what idempotency is about.
 */
function fakeDeps(opts: {
  rows?: ClaimedRow[]
  facts?: Partial<SuppressionFacts>
  send?: DrainDeps['send']
  now?: Date
  founders?: string[]
}): DrainDeps & { log: string[]; sends: Parameters<DrainDeps['send']>[0][]; crm: unknown[] } {
  const log: string[] = []
  const sends: Parameters<DrainDeps['send']>[0][] = []
  const crm: unknown[] = []
  const facts: SuppressionFacts = {
    unsubscribed: false,
    hardBounced: false,
    complained: false,
    hasAccount: false,
    alreadySentThisStage: false,
    ...opts.facts,
  }
  const rows = opts.rows ?? []
  return {
    log,
    sends,
    crm,
    query: vi.fn(async (sql: string) => {
      if (/FOR UPDATE SKIP LOCKED/.test(sql)) {
        log.push(`claim:${rows.length}`)
        return rows as never[]
      }
      return []
    }) as DrainDeps['query'],
    execute: vi.fn(async (sql: string, params?: unknown[]) => {
      if (/status = 'active', updated_at = now\(\)\s+WHERE status = 'sending'/.test(sql)) log.push('recover-stale')
      else if (/INSERT INTO waitlist_sequence_sends/.test(sql)) log.push(`log:${params?.[1]}:${/'sent'/.test(sql) ? 'sent' : 'failed'}`)
      else if (/status = 'suppressed'/.test(sql)) log.push(`suppress:${params?.[1]}`)
      else if (/SET stage = \$2/.test(sql)) log.push(`advance:stage=${params?.[1]}:${params?.[2]}:next=${params?.[3] ?? 'null'}`)
      else if (/UPDATE waitlist_submissions/.test(sql)) log.push('legacy-email-status')
      else if (/send_attempts = \$3/.test(sql)) log.push(`retry:${params?.[1]}:attempts=${params?.[2]}`)
      else log.push(`exec:${sql.slice(0, 40).replace(/\s+/g, ' ')}`)
      return 1
    }),
    send:
      opts.send ??
      (async (input) => {
        sends.push(input)
        return { sent: true, id: `re_${sends.length}` }
      }),
    lookupFacts: async () => facts,
    enqueueCrm: (async (e: unknown) => {
      crm.push(e)
      return { enqueued: true }
    }) as DrainDeps['enqueueCrm'],
    now: () => opts.now ?? fromCtWallClock('2026-09-08', 9),
    origin: () => 'https://ironforge.example',
    businessAddress: () => 'IronForge Technologies LLC | Austin, TX',
    emailConfigured: () => true,
    dbConfigured: () => true,
    isFounder: (email) => (opts.founders ?? []).includes(email.toLowerCase()),
  }
}

const row: ClaimedRow = { id: 'seq-1', email: 'Ada@Example.com', first_name: 'Ada', stage: 0, send_attempts: 0, unsubscribe_token: 'tok_1234567890abcdefghij' }

describe('preconditions', () => {
  it('names the missing env var and touches nothing', async () => {
    const deps = fakeDeps({ rows: [row] })
    deps.businessAddress = () => ''
    const r = await drainWaitlistDrip({}, deps)
    expect(r.blocked).toMatch(/IRONFORGE_BUSINESS_ADDRESS/)
    expect(r.processed).toBe(0)
    expect(deps.log).toEqual([])
    expect(deps.sends).toEqual([])
  })

  it('blocks on a missing public origin and on unconfigured email', () => {
    expect(sendPreconditionBlocker({ origin: () => null, businessAddress: () => 'x', emailConfigured: () => true })).toMatch(/IRONFORGE_PUBLIC_URL/)
    expect(sendPreconditionBlocker({ origin: () => 'https://x', businessAddress: () => 'x', emailConfigured: () => false })).toMatch(/RESEND_API_KEY/)
    expect(sendPreconditionBlocker({ origin: () => 'https://x', businessAddress: () => 'x', emailConfigured: () => true })).toBeNull()
  })
})

describe('a due row: claim → suppression → send → log → advance → mirror', () => {
  it('sends Email 1 with the unsubscribe headers and an idempotency key, then schedules Email 2 three business days out', async () => {
    const deps = fakeDeps({ rows: [row] })
    const r = await drainWaitlistDrip({}, deps)
    expect(r).toMatchObject({ processed: 1, sent: 1, suppressed: 0, failed: 0, completed: 0 })

    expect(deps.sends).toHaveLength(1)
    const s = deps.sends[0]
    expect(s.to).toBe('Ada@Example.com')
    expect(s.subject).toBe('Welcome to IronForge—you’re on the list.')
    expect(s.html).toContain('Hello Ada,')
    expect(s.text).toContain('Hello Ada,')
    expect(s.headers?.['List-Unsubscribe']).toBe('<https://ironforge.example/email/unsubscribe/tok_1234567890abcdefghij>')
    expect(s.headers?.['List-Unsubscribe-Post']).toBe('List-Unsubscribe=One-Click')
    expect(s.idempotencyKey).toBe(idempotencyKeyFor('seq-1', 1))

    // Sep 8 (Tue) 09:00 CT + 3 business days = Fri Sep 11 09:00 CT.
    const fri = fromCtWallClock('2026-09-11', 9).toISOString()
    expect(deps.log).toEqual(['recover-stale', 'claim:1', 'log:1:sent', `advance:stage=1:active:next=${fri}`, 'legacy-email-status'])

    expect(deps.crm).toHaveLength(1)
    expect(deps.crm[0]).toMatchObject({
      eventId: 'waitlist_email:seq-1:1',
      eventType: 'crm.waitlist_email_sent',
      payload: { email: 'ada@example.com', waitlistEmailStage: 1 },
    })
  })

  it('stage 6 completes the sequence with no next send', async () => {
    const deps = fakeDeps({ rows: [{ ...row, stage: 5 }] })
    const r = await drainWaitlistDrip({}, deps)
    expect(r).toMatchObject({ sent: 1, completed: 1 })
    expect(deps.sends[0].subject).toBe("Meet Tradier, IronForge's brokerage partner")
    expect(deps.log).toContain('advance:stage=6:completed:next=null')
    expect(deps.log).not.toContain('legacy-email-status')
  })
})

describe('send-time suppression', () => {
  for (const [fact, reason] of [
    ['unsubscribed', 'unsubscribed'],
    ['hardBounced', 'hard_bounce'],
    ['complained', 'complaint'],
    ['hasAccount', 'onboarding'],
  ] as const) {
    it(`${fact} → suppressed as ${reason}, nothing sent, reason kept`, async () => {
      const deps = fakeDeps({ rows: [row], facts: { [fact]: true } })
      const r = await drainWaitlistDrip({}, deps)
      expect(r).toMatchObject({ processed: 1, sent: 0, suppressed: 1 })
      expect(deps.sends).toEqual([])
      expect(deps.log).toEqual(['recover-stale', 'claim:1', `suppress:${reason}`])
      expect(deps.crm).toEqual([])
    })
  }
})

describe('founders', () => {
  const founder: ClaimedRow = { ...row, id: 'seq-f', email: 'Leron@IronForge.trade', first_name: 'Leron' }

  it('a founder with a customer account is still sent to, and is NOT mirrored to Attio', async () => {
    const deps = fakeDeps({ rows: [founder], facts: { hasAccount: true }, founders: ['leron@ironforge.trade'] })
    const r = await drainWaitlistDrip({}, deps)
    expect(r).toMatchObject({ processed: 1, sent: 1, suppressed: 0 })
    expect(deps.sends).toHaveLength(1)
    expect(deps.sends[0].to).toBe('Leron@IronForge.trade')
    expect(deps.sends[0].html).toContain('Hello Leron,')
    expect(deps.log).toContain('log:1:sent')
    expect(deps.crm).toEqual([])
  })

  for (const [fact, reason] of [
    ['unsubscribed', 'unsubscribed'],
    ['hardBounced', 'hard_bounce'],
    ['complained', 'complaint'],
  ] as const) {
    it(`a founder who ${fact} is suppressed as ${reason} like anyone else`, async () => {
      const deps = fakeDeps({ rows: [founder], facts: { [fact]: true, hasAccount: true }, founders: ['leron@ironforge.trade'] })
      const r = await drainWaitlistDrip({}, deps)
      expect(r).toMatchObject({ sent: 0, suppressed: 1 })
      expect(deps.log).toEqual(['recover-stale', 'claim:1', `suppress:${reason}`])
    })
  }

  it('a non-founder with an account is still suppressed as onboarding', async () => {
    const deps = fakeDeps({ rows: [row], facts: { hasAccount: true }, founders: ['leron@ironforge.trade'] })
    const r = await drainWaitlistDrip({}, deps)
    expect(r).toMatchObject({ sent: 0, suppressed: 1 })
    expect(deps.log).toContain('suppress:onboarding')
  })
})

describe('idempotency', () => {
  it('a stage whose send is already logged is advanced WITHOUT sending again', async () => {
    const deps = fakeDeps({ rows: [row], facts: { alreadySentThisStage: true } })
    const r = await drainWaitlistDrip({}, deps)
    expect(r).toMatchObject({ processed: 1, sent: 0, skippedDuplicate: 1 })
    expect(deps.sends).toEqual([])
    expect(deps.log.some((l) => l.startsWith('advance:stage=1:active'))).toBe(true)
  })

  it('the idempotency key is stable per (subscriber, stage) and differs across stages', () => {
    expect(idempotencyKeyFor('a', 1)).toBe(idempotencyKeyFor('a', 1))
    expect(idempotencyKeyFor('a', 1)).not.toBe(idempotencyKeyFor('a', 2))
    expect(idempotencyKeyFor('a', 1)).not.toBe(idempotencyKeyFor('b', 1))
  })

  it('an empty claim does no work (the common tick)', async () => {
    const deps = fakeDeps({ rows: [] })
    const r = await drainWaitlistDrip({}, deps)
    expect(r.processed).toBe(0)
    expect(deps.log).toEqual(['recover-stale', 'claim:0'])
  })
})

describe('send failures', () => {
  it('logs the failure, releases the row for retry, and does not advance the stage', async () => {
    const deps = fakeDeps({ rows: [row], send: async () => ({ sent: false, error: 'Resend 500: boom' }) })
    const r = await drainWaitlistDrip({}, deps)
    expect(r).toMatchObject({ processed: 1, sent: 0, failed: 1 })
    expect(deps.log).toEqual(['recover-stale', 'claim:1', 'log:1:failed', 'retry:active:attempts=1'])
    expect(deps.crm).toEqual([])
  })

  it('parks the row as failed after the fifth consecutive failure', async () => {
    const deps = fakeDeps({ rows: [{ ...row, send_attempts: 4 }], send: async () => ({ sent: false, error: 'Resend 500' }) })
    await drainWaitlistDrip({}, deps)
    expect(deps.log).toContain('retry:failed:attempts=5')
  })

  it('a skipped (unconfigured) send releases the claim untouched', async () => {
    const deps = fakeDeps({ rows: [row], send: async () => ({ sent: false, skipped: true }) })
    const r = await drainWaitlistDrip({}, deps)
    expect(r).toMatchObject({ processed: 1, sent: 0, failed: 0 })
    expect(deps.log.at(-1)).toMatch(/^exec:UPDATE waitlist_sequence SET status/)
  })
})

describe('advanceAfterSend', () => {
  it('schedules from the actual send instant and completes at the final stage', () => {
    const at = fromCtWallClock('2026-09-18', 11, 5) // a Friday, sent late
    const a = advanceAfterSend(2, at)
    expect(a.status).toBe('active')
    expect(a.nextSendAt?.toISOString()).toBe(fromCtWallClock('2026-09-23', 9).toISOString())
    expect(advanceAfterSend(6, at)).toEqual({ stage: 6, status: 'completed', nextSendAt: null })
  })
})
