import { describe, it, expect } from 'vitest'

// Plain CJS module — required rather than imported so the test exercises the
// exact same file start.js loads at boot.
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { checkSandboxEnv, databaseNameOf } = require('../../../scripts/sandbox-guard.js')

/** A sandbox env that passes every check — the baseline each test perturbs. */
function safeEnv(overrides: Record<string, string | undefined> = {}) {
  return {
    IRONFORGE_ENV: 'sandbox',
    DATABASE_URL: 'postgresql://u:p@host.oregon-postgres.render.com/ironforge_sandbox',
    CUSTOMERS_DATABASE_URL: 'postgresql://u:p@host.oregon-postgres.render.com/ironforge_customers_sandbox',
    STRIPE_SECRET_KEY: 'sk_test_abc123',
    TRADIER_SANDBOX_KEY_USER: 'sandboxkey',
    ...overrides,
  }
}

describe('checkSandboxEnv', () => {
  it('is inert when IRONFORGE_ENV is not sandbox', () => {
    // The production services must be completely unaffected by this guard, even
    // holding every credential that would be fatal in a sandbox.
    const res = checkSandboxEnv({
      DATABASE_URL: 'postgresql://u:p@host/ironforge',
      TRADIER_PROD_API_KEY: 'real',
      STRIPE_SECRET_KEY: 'sk_live_real',
      SCANNER_ENABLED: 'true',
    })
    expect(res.active).toBe(false)
    expect(res.errors).toEqual([])
  })

  it('passes a correctly configured sandbox', () => {
    const res = checkSandboxEnv(safeEnv())
    expect(res.active).toBe(true)
    expect(res.errors).toEqual([])
  })

  describe('broker credentials', () => {
    it.each([
      'TRADIER_API_KEY',
      'TRADIER_PROD_API_KEY',
      'TRADIER_PROD_ACCOUNT_ID',
      'TRADIER_SPARK2_API_KEY',
      'TRADIER_FLAME_API_KEY',
      'TRADIER_KINDLE_API_KEY',
    ])('rejects %s', (key) => {
      const res = checkSandboxEnv(safeEnv({ [key]: 'leaked-real-key' }))
      expect(res.errors.some((e: string) => e.includes(key))).toBe(true)
    })

    it('rejects a production Tradier host', () => {
      const res = checkSandboxEnv(safeEnv({ TRADIER_BASE_URL: 'https://api.tradier.com/v1' }))
      expect(res.errors.some((e: string) => e.includes('TRADIER_BASE_URL'))).toBe(true)
    })

    it('accepts the sandbox Tradier host', () => {
      const res = checkSandboxEnv(safeEnv({ TRADIER_BASE_URL: 'https://sandbox.tradier.com/v1' }))
      expect(res.errors).toEqual([])
    })
  })

  describe('billing', () => {
    it('rejects a live Stripe key', () => {
      const res = checkSandboxEnv(safeEnv({ STRIPE_SECRET_KEY: 'sk_live_deadbeef' }))
      expect(res.errors.some((e: string) => e.includes('STRIPE_SECRET_KEY'))).toBe(true)
    })

    it('accepts restricted test keys', () => {
      expect(checkSandboxEnv(safeEnv({ STRIPE_SECRET_KEY: 'rk_test_abc' })).errors).toEqual([])
    })

    it('warns rather than fails when Stripe is unconfigured', () => {
      const res = checkSandboxEnv(safeEnv({ STRIPE_SECRET_KEY: undefined }))
      expect(res.errors).toEqual([])
      expect(res.warnings.some((w: string) => w.includes('STRIPE_SECRET_KEY'))).toBe(true)
    })
  })

  describe('order-placing switches', () => {
    it.each(['SCANNER_ENABLED', 'CUSTOMER_EXECUTOR_ENABLED', 'IRONFORGE_FLAME_LIVE'])(
      'rejects %s=true',
      (key) => {
        const res = checkSandboxEnv(safeEnv({ [key]: 'true' }))
        expect(res.errors.some((e: string) => e.includes(key))).toBe(true)
      },
    )

    it('tolerates the switches being explicitly false', () => {
      const res = checkSandboxEnv(safeEnv({ SCANNER_ENABLED: 'false', CUSTOMER_EXECUTOR_ENABLED: 'false' }))
      expect(res.errors).toEqual([])
    })
  })

  describe('databases', () => {
    it.each([
      ['DATABASE_URL', 'ironforge'],
      ['DATABASE_URL', 'alphagex'],
      ['CUSTOMERS_DATABASE_URL', 'ironforge_customers'],
    ])('rejects %s pointing at production db "%s"', (key, dbName) => {
      const res = checkSandboxEnv(
        safeEnv({ [key]: `postgresql://u:p@host.oregon-postgres.render.com/${dbName}` }),
      )
      expect(res.errors.some((e: string) => e.includes(key) && e.includes(dbName))).toBe(true)
    })

    it('allows sandbox database names that merely start with a production name', () => {
      // "ironforge_sandbox" must not trip the "ironforge" rule — exact match only,
      // otherwise every legitimate sandbox name is rejected.
      const res = checkSandboxEnv(safeEnv({ DATABASE_URL: 'postgresql://u:p@h/ironforge_sandbox' }))
      expect(res.errors).toEqual([])
    })

    it('fails when DATABASE_URL is missing entirely', () => {
      const res = checkSandboxEnv(safeEnv({ DATABASE_URL: undefined }))
      expect(res.errors.some((e: string) => e.includes('DATABASE_URL is unset'))).toBe(true)
    })

    it('warns when the customer DB is missing', () => {
      const res = checkSandboxEnv(safeEnv({ CUSTOMERS_DATABASE_URL: undefined }))
      expect(res.errors).toEqual([])
      expect(res.warnings.some((w: string) => w.includes('CUSTOMERS_DATABASE_URL'))).toBe(true)
    })
  })

  describe('outbound integrations', () => {
    it.each(['ATTIO_API_KEY', 'TWILIO_ACCOUNT_SID', 'DISCORD_WEBHOOK_URL'])(
      'rejects %s by default',
      (key) => {
        const res = checkSandboxEnv(safeEnv({ [key]: 'set' }))
        expect(res.errors.some((e: string) => e.includes(key))).toBe(true)
      },
    )

    it('allows them behind the explicit opt-in', () => {
      const res = checkSandboxEnv(
        safeEnv({ ATTIO_API_KEY: 'set', DISCORD_WEBHOOK_URL: 'set', SANDBOX_ALLOW_OUTBOUND: 'true' }),
      )
      expect(res.errors).toEqual([])
    })

    it('never blocks Resend — email verification is part of the funnel under test', () => {
      const res = checkSandboxEnv(safeEnv({ RESEND_API_KEY: 're_abc123' }))
      expect(res.errors).toEqual([])
    })
  })

  it('warns when the enrollment gate would block the funnel', () => {
    const res = checkSandboxEnv(safeEnv({ ENROLLMENT_WAITLIST_MODE: 'true' }))
    expect(res.errors).toEqual([])
    expect(res.warnings.some((w: string) => w.includes('ENROLLMENT_WAITLIST_MODE'))).toBe(true)
  })

  it('reports every problem at once rather than stopping at the first', () => {
    // A one-error-at-a-time guard means one redeploy per mistake; env blocks are
    // usually wrong in several places at once.
    const res = checkSandboxEnv(
      safeEnv({
        TRADIER_PROD_API_KEY: 'real',
        STRIPE_SECRET_KEY: 'sk_live_x',
        SCANNER_ENABLED: 'true',
        DATABASE_URL: 'postgresql://u:p@h/ironforge',
      }),
    )
    expect(res.errors.length).toBeGreaterThanOrEqual(4)
  })
})

describe('databaseNameOf', () => {
  it('extracts the database name', () => {
    expect(databaseNameOf('postgresql://user:pw@host.render.com:5432/ironforge_sandbox')).toBe(
      'ironforge_sandbox',
    )
  })

  it('ignores query strings such as sslmode', () => {
    expect(databaseNameOf('postgresql://u:p@h/ironforge?sslmode=require')).toBe('ironforge')
  })

  it('returns empty for unparseable or missing input', () => {
    expect(databaseNameOf('')).toBe('')
    expect(databaseNameOf(undefined)).toBe('')
    expect(databaseNameOf('not a url')).toBe('')
  })
})
