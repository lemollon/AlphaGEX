/**
 * Sandbox boot guard — refuses to start a sandbox service that can touch real money.
 *
 * WHY THIS EXISTS
 * ---------------
 * The sandbox is the same image as production. Every dangerous capability is one
 * env var away: a production Tradier key, an `sk_live_` Stripe key, SCANNER_ENABLED,
 * or a DATABASE_URL still pointing at the real trading database. A copy-pasted env
 * block is all it takes, and the failure is silent — the service boots, looks
 * correct, and places real orders or bills real cards.
 *
 * So the sandbox does not *ask* to be safe, it *proves* it at boot. If any check
 * below fails the process exits non-zero, Render marks the deploy failed, and no
 * traffic is ever served. A sandbox that cannot boot is strictly better than a
 * sandbox that quietly trades.
 *
 * This file is plain CommonJS with no dependencies on purpose: it is required from
 * start.js BEFORE the Next.js server is loaded, so it cannot import from src/lib.
 *
 * Activated only when IRONFORGE_ENV === 'sandbox'. Production is unaffected — the
 * guard returns immediately, so this can never break the live services.
 */

'use strict'

/**
 * Postgres databases that hold real money / real customers. A sandbox pointed at
 * any of these is the worst failure mode in this file — it would write test rows
 * into live tables and read live positions into a test UI. Names come from the
 * Render dashboard (ironforge-db, ironforge-customers, alphagex-db).
 */
const PRODUCTION_DB_NAMES = new Set([
  'ironforge',
  'ironforge_customers',
  'alphagex',
  'alphagex_backtest',
])

/** Env vars that carry real-money broker credentials. None may be set in sandbox. */
const PRODUCTION_BROKER_KEYS = [
  'TRADIER_API_KEY',
  'TRADIER_PROD_API_KEY',
  'TRADIER_PROD_ACCOUNT_ID',
  'TRADIER_SPARK2_API_KEY',
  'TRADIER_FLAME_API_KEY',
  'TRADIER_KINDLE_API_KEY',
]

/**
 * Integrations that write to real, shared, outside-world systems: the real CRM,
 * real phones, the real Discord. Test traffic here is not destructive but it is
 * visible and hard to undo, so it is opt-in via SANDBOX_ALLOW_OUTBOUND=true.
 * RESEND_API_KEY is deliberately NOT in this list — email verification is part of
 * the funnel being tested, and it only ever mails the seeded test addresses.
 */
const OUTBOUND_INTEGRATIONS = [
  'ATTIO_API_KEY',
  'TWILIO_ACCOUNT_SID',
  'TWILIO_AUTH_TOKEN',
  'DISCORD_WEBHOOK_URL',
]

/** Parse the database name out of a Postgres URL. Returns '' when unparseable. */
function databaseNameOf(url) {
  if (!url) return ''
  try {
    // pathname is '/dbname'; strip the leading slash and any query string.
    return new URL(url).pathname.replace(/^\//, '').trim()
  } catch {
    return ''
  }
}

function isTruthy(v) {
  return String(v || '').trim().toLowerCase() === 'true'
}

/**
 * Run every sandbox invariant. Pure: reads `env`, returns findings, throws nothing.
 * Exported so the unit tests can exercise it without spawning a process.
 *
 * @param {Record<string, string|undefined>} env
 * @returns {{ active: boolean, errors: string[], warnings: string[] }}
 */
function checkSandboxEnv(env) {
  const errors = []
  const warnings = []

  if (String(env.IRONFORGE_ENV || '').trim().toLowerCase() !== 'sandbox') {
    return { active: false, errors, warnings }
  }

  // ── 1. Broker: no real-money credentials, no production host ───────────────
  for (const key of PRODUCTION_BROKER_KEYS) {
    if (env[key]) {
      errors.push(
        `${key} is set. Sandbox must carry no production broker credentials. ` +
          `Use TRADIER_SANDBOX_KEY_USER instead — with TRADIER_API_KEY unset, ` +
          `tradier.ts already defaults to sandbox.tradier.com.`,
      )
    }
  }

  const base = (env.TRADIER_BASE_URL || '').trim()
  if (base && !base.includes('sandbox.tradier.com')) {
    errors.push(
      `TRADIER_BASE_URL is "${base}", which is not a sandbox host. ` +
        `Set it to https://sandbox.tradier.com/v1 or leave it unset.`,
    )
  }

  // ── 2. Billing: test mode only ─────────────────────────────────────────────
  const stripeKey = (env.STRIPE_SECRET_KEY || '').trim()
  if (stripeKey && !/^(sk|rk)_test_/.test(stripeKey)) {
    errors.push(
      'STRIPE_SECRET_KEY is not a test-mode key (expected sk_test_… or rk_test_…). ' +
        'A live key here would charge real cards from the sandbox.',
    )
  } else if (!stripeKey) {
    warnings.push('STRIPE_SECRET_KEY is unset — checkout and billing cannot be tested.')
  }

  // ── 3. Order-placing switches must all be off ──────────────────────────────
  if (isTruthy(env.SCANNER_ENABLED)) {
    errors.push('SCANNER_ENABLED=true. The scanner places orders; it must never run in sandbox.')
  }
  if (isTruthy(env.CUSTOMER_EXECUTOR_ENABLED)) {
    errors.push('CUSTOMER_EXECUTOR_ENABLED=true. The customer executor places orders on customer accounts.')
  }
  if (isTruthy(env.IRONFORGE_FLAME_LIVE)) {
    errors.push('IRONFORGE_FLAME_LIVE=true. This marks FLAME as real-money.')
  }

  // ── 4. Databases: never the production ones ────────────────────────────────
  for (const key of ['DATABASE_URL', 'CUSTOMERS_DATABASE_URL']) {
    const name = databaseNameOf(env[key])
    if (name && PRODUCTION_DB_NAMES.has(name)) {
      errors.push(
        `${key} points at production database "${name}". ` +
          `Point it at a dedicated sandbox database.`,
      )
    }
  }
  if (!env.DATABASE_URL) {
    errors.push('DATABASE_URL is unset — the service cannot start.')
  }
  if (!env.CUSTOMERS_DATABASE_URL) {
    warnings.push(
      'CUSTOMERS_DATABASE_URL is unset — signup, billing and /live will not work. ' +
        'The customer funnel is the main thing a sandbox exists to test.',
    )
  }

  // ── 5. Outbound integrations that hit shared real systems ──────────────────
  if (!isTruthy(env.SANDBOX_ALLOW_OUTBOUND)) {
    for (const key of OUTBOUND_INTEGRATIONS) {
      if (env[key]) {
        errors.push(
          `${key} is set. Sandbox traffic would reach the real system. ` +
            `Unset it, or set SANDBOX_ALLOW_OUTBOUND=true to accept that.`,
        )
      }
    }
  }

  // ── 6. Gates that would make the sandbox pointless ─────────────────────────
  if (isTruthy(env.ENROLLMENT_WAITLIST_MODE)) {
    warnings.push(
      'ENROLLMENT_WAITLIST_MODE=true — signup and enrollment are CLOSED, which is ' +
        'exactly what the sandbox exists to test. Unset it here.',
    )
  }

  return { active: true, errors, warnings }
}

/**
 * Enforce the invariants against process.env. Called from start.js.
 * Exits the process on any error — a failed boot is the intended outcome.
 */
function enforceSandboxGuard(env = process.env, exit = (code) => process.exit(code)) {
  const { active, errors, warnings } = checkSandboxEnv(env)
  if (!active) return

  console.log('[sandbox-guard] IRONFORGE_ENV=sandbox — verifying this service cannot touch real money.')
  for (const w of warnings) console.warn(`[sandbox-guard] WARN  ${w}`)

  if (errors.length > 0) {
    console.error('')
    console.error('[sandbox-guard] REFUSING TO START — sandbox can reach real money or real customers:')
    for (const e of errors) console.error(`[sandbox-guard]   ✗ ${e}`)
    console.error('')
    console.error(`[sandbox-guard] ${errors.length} blocking problem(s). Fix the env vars and redeploy.`)
    return exit(1)
  }

  console.log(`[sandbox-guard] OK — ${warnings.length} warning(s), 0 blocking problems.`)
}

module.exports = { checkSandboxEnv, enforceSandboxGuard, databaseNameOf, PRODUCTION_DB_NAMES }
