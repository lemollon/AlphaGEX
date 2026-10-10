import { describe, it, expect, vi } from 'vitest'
import {
  DEFAULT_FOUNDER_EMAILS,
  autoEnrollWaitlistDrip,
  autostartConfig,
  founderFirstName,
  founderSuppressionReason,
  isFounderEmail,
  parseFounderEmails,
  type AutostartDeps,
  type FounderFacts,
} from '../autostart'
import { firstSendAt } from '../schedule'
import type { BackfillResult } from '../sequence'

describe('autostartConfig — env parsing', () => {
  it('unset → disabled, default founders', () => {
    const c = autostartConfig({})
    expect(c.enabled).toBe(false)
    expect(c.startDate).toBeNull()
    expect(c.invalidReason).toBeUndefined()
    expect(c.founders).toEqual([...DEFAULT_FOUNDER_EMAILS])
  })

  it('blank → disabled without an invalid reason', () => {
    const c = autostartConfig({ WAITLIST_DRIP_START_DATE: '   ' })
    expect(c).toMatchObject({ enabled: false, startDate: null })
    expect(c.invalidReason).toBeUndefined()
  })

  for (const bad of ['tomorrow', '2026-13-01', '2026-02-30', '09/10/2026', '2026-9-10', '20260910']) {
    it(`invalid "${bad}" → disabled with a reason naming the env var`, () => {
      const c = autostartConfig({ WAITLIST_DRIP_START_DATE: bad })
      expect(c.enabled).toBe(false)
      expect(c.startDate).toBeNull()
      expect(c.invalidReason).toContain('WAITLIST_DRIP_START_DATE')
      expect(c.invalidReason).toContain(bad)
    })
  }

  it('valid date → enabled, trimmed', () => {
    const c = autostartConfig({ WAITLIST_DRIP_START_DATE: ' 2026-09-10 ' })
    expect(c).toMatchObject({ enabled: true, startDate: '2026-09-10' })
    expect(c.invalidReason).toBeUndefined()
  })

  it('founder override is parsed alongside the date', () => {
    const c = autostartConfig({
      WAITLIST_DRIP_START_DATE: '2026-09-10',
      WAITLIST_DRIP_FOUNDER_EMAILS: 'Leron@IronForge.trade, ops@ironforge.trade',
    })
    expect(c.founders).toEqual(['leron@ironforge.trade', 'ops@ironforge.trade'])
  })
})

describe('parseFounderEmails', () => {
  it('defaults to the two founders when unset or blank', () => {
    expect(parseFounderEmails(undefined)).toEqual(['leron@ironforge.trade', 'logan@ironforge.trade'])
    expect(parseFounderEmails('')).toEqual(['leron@ironforge.trade', 'logan@ironforge.trade'])
    expect(parseFounderEmails('  ')).toEqual(['leron@ironforge.trade', 'logan@ironforge.trade'])
  })
  it('lower-cases, trims, de-duplicates and drops junk', () => {
    expect(parseFounderEmails(' A@X.io ,a@x.io,, not-an-email , b@y.io ')).toEqual(['a@x.io', 'b@y.io'])
  })
  it('a list of only junk yields no founders (never silently falls back to the default)', () => {
    expect(parseFounderEmails('nope, also nope')).toEqual([])
  })
})

describe('founderFirstName', () => {
  it('capitalises the local part', () => {
    expect(founderFirstName('leron@ironforge.trade')).toBe('Leron')
    expect(founderFirstName('logan@ironforge.trade')).toBe('Logan')
    expect(founderFirstName('mary.ann@x.io')).toBe('Mary.ann')
    expect(founderFirstName('@x.io')).toBe('')
  })
})

describe('isFounderEmail', () => {
  it('is case-insensitive and honours the configured list', () => {
    const cfg = { founders: ['leron@ironforge.trade'] }
    expect(isFounderEmail('Leron@IronForge.trade', cfg)).toBe(true)
    expect(isFounderEmail('logan@ironforge.trade', cfg)).toBe(false)
  })
})

describe('founderSuppressionReason — exempt from the account rule ONLY', () => {
  const base: FounderFacts = { unsubscribed: false, complained: false, hardBounced: false, hasAccount: true }
  it('an account alone is not a reason', () => {
    expect(founderSuppressionReason(base)).toBeNull()
  })
  it('unsubscribe, complaint and hard bounce still apply', () => {
    expect(founderSuppressionReason({ ...base, unsubscribed: true })).toBe('unsubscribed')
    expect(founderSuppressionReason({ ...base, complained: true })).toBe('complaint')
    expect(founderSuppressionReason({ ...base, hardBounced: true })).toBe('hard_bounce')
  })
})

/** In-memory stand-in: a set of enrolled addresses so the second run really enrolls nothing. */
function fakeDeps(opts: {
  enabled?: boolean
  startDate?: string
  founders?: string[]
  waitlist?: string[]
  founderFacts?: Partial<FounderFacts>
  dbConfigured?: boolean
}) {
  const enrolled = new Set<string>()
  const lines: string[] = []
  const calls: string[] = []
  const sql: string[] = []
  const founderFacts: FounderFacts = { unsubscribed: false, complained: false, hardBounced: false, hasAccount: true, ...opts.founderFacts }
  const deps: AutostartDeps & { enrolled: Set<string>; lines: string[]; calls: string[]; sql: string[] } = {
    enrolled,
    lines,
    calls,
    sql,
    config: () => ({
      enabled: opts.enabled ?? true,
      startDate: opts.enabled === false ? null : (opts.startDate ?? '2026-09-10'),
      founders: opts.founders ?? ['leron@ironforge.trade', 'logan@ironforge.trade'],
    }),
    dbConfigured: () => opts.dbConfigured ?? true,
    backfill: vi.fn(async ({ firstSendDate, dryRun }): Promise<BackfillResult> => {
      calls.push(`backfill:${firstSendDate}:${dryRun}`)
      let n = 0
      for (const e of opts.waitlist ?? []) {
        if (enrolled.has(e)) continue
        enrolled.add(e)
        n++
      }
      return {
        dryRun,
        firstSendDate,
        firstSendAt: firstSendAt(firstSendDate).toISOString(),
        candidates: n,
        enrolled: n,
        suppressed: {},
        alreadyEnrolled: enrolled.size - n,
      }
    }),
    founderFacts: async (email) => {
      calls.push(`facts:${email}`)
      return founderFacts
    },
    query: vi.fn(async (q: string, params?: unknown[]) => {
      sql.push(q)
      const email = String(params?.[0])
      calls.push(`founder-upsert:${email}:${params?.[2]}:${params?.[4] ?? 'null'}`)
      if (enrolled.has(email)) return [] as never[] // ON CONFLICT ... WHERE false → no row
      enrolled.add(email)
      return [{ inserted: true }] as never[]
    }) as AutostartDeps['query'],
    log: (line) => {
      lines.push(line)
    },
  }
  return deps
}

describe('autoEnrollWaitlistDrip', () => {
  it('disabled → touches nothing', async () => {
    const deps = fakeDeps({ enabled: false, waitlist: ['ada@example.com'] })
    const r = await autoEnrollWaitlistDrip(deps)
    expect(r).toMatchObject({ enabled: false, skipped: true, enrolled: 0, founders: [] })
    expect(deps.calls).toEqual([])
    expect(deps.lines).toEqual([])
  })

  it('no customers DB → touches nothing', async () => {
    const deps = fakeDeps({ dbConfigured: false, waitlist: ['ada@example.com'] })
    const r = await autoEnrollWaitlistDrip(deps)
    expect(r.skipped).toBe(true)
    expect(deps.calls).toEqual([])
  })

  it('enrolls founders first, then the list on the configured date, for real (dryRun false), and logs once', async () => {
    const deps = fakeDeps({ waitlist: ['ada@example.com', 'bob@example.com'] })
    const r = await autoEnrollWaitlistDrip(deps)
    expect(r).toMatchObject({ enabled: true, startDate: '2026-09-10', enrolled: 2 })
    expect(r.founders).toEqual([
      { email: 'leron@ironforge.trade', outcome: 'inserted', reason: null },
      { email: 'logan@ironforge.trade', outcome: 'inserted', reason: null },
    ])
    expect(deps.calls).toEqual([
      'facts:leron@ironforge.trade',
      'founder-upsert:leron@ironforge.trade:active:null',
      'facts:logan@ironforge.trade',
      'founder-upsert:logan@ironforge.trade:active:null',
      'backfill:2026-09-10:false',
    ])
    expect(deps.lines).toHaveLength(1)
    expect(deps.lines[0]).toContain('enrolled=2')
    expect(deps.lines[0]).toContain('leron@ironforge.trade:inserted')
    // Founder rows: stage 0, first name from the local part, same first-send instant as the list.
    const founderParams = vi.mocked(deps.query).mock.calls[0][1] as unknown[]
    expect(founderParams[1]).toBe('Leron')
    expect(founderParams[3]).toBe(firstSendAt('2026-09-10').toISOString())
    expect(deps.sql[0]).toMatch(/INSERT INTO waitlist_sequence/)
    expect(deps.sql[0]).toMatch(/stage, status/)
    expect(deps.sql.join('\n')).not.toMatch(/waitlist_submissions/)
  })

  it('is idempotent: the second run enrolls 0, changes no founder, and logs nothing', async () => {
    const deps = fakeDeps({ waitlist: ['ada@example.com'] })
    await autoEnrollWaitlistDrip(deps)
    deps.lines.length = 0
    const r = await autoEnrollWaitlistDrip(deps)
    expect(r.enrolled).toBe(0)
    expect(r.founders.every((f) => f.outcome === 'exists')).toBe(true)
    expect(deps.lines).toEqual([])
  })

  it('a founder WITH a customer account is enrolled active (exempt from the account rule)', async () => {
    const deps = fakeDeps({ founders: ['leron@ironforge.trade'], founderFacts: { hasAccount: true } })
    const r = await autoEnrollWaitlistDrip(deps)
    expect(r.founders).toEqual([{ email: 'leron@ironforge.trade', outcome: 'inserted', reason: null }])
    expect(deps.calls).toContain('founder-upsert:leron@ironforge.trade:active:null')
  })

  it('an unsubscribed founder is enrolled suppressed — the unsubscribe rule still applies', async () => {
    const deps = fakeDeps({ founders: ['leron@ironforge.trade'], founderFacts: { unsubscribed: true, hasAccount: true } })
    const r = await autoEnrollWaitlistDrip(deps)
    expect(r.founders).toEqual([{ email: 'leron@ironforge.trade', outcome: 'inserted', reason: 'unsubscribed' }])
    expect(deps.calls).toContain('founder-upsert:leron@ironforge.trade:suppressed:unsubscribed')
    const params = vi.mocked(deps.query).mock.calls[0][1] as unknown[]
    expect(params[3]).toBeNull() // no next_send_at for a suppressed row
  })

  it('a failure is reported, never thrown', async () => {
    const deps = fakeDeps({})
    deps.backfill = async () => {
      throw new Error('db down')
    }
    const r = await autoEnrollWaitlistDrip(deps)
    expect(r.error).toBe('db down')
  })
})
