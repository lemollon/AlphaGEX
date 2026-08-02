#!/usr/bin/env node
/**
 * Seed the sandbox customer database with fake customers at every funnel stage.
 *
 * WHY
 * ---
 * Testing the customer product used to require being a real customer: sign up,
 * receive a real verification email, pay a real card, connect a real brokerage.
 * That is slow, not repeatable, and impossible now that enrollment is closed
 * behind the waitlist gate. So the states are written directly instead.
 *
 * Each persona is a *stage*, not a variation — together they cover the whole
 * path from "just signed up" to "trading with open positions", so any page can
 * be opened in any state without clicking through the ones before it.
 *
 *   new@        signed up, email NOT verified          → verification wall
 *   verified@   email verified, no legal yet           → legal step
 *   legal@      legal accepted, not paid               → checkout / paywall
 *   paid@       active subscription, nothing set up    → setup_required
 *   pastdue@    subscription past_due                  → dunning / payment-due UX
 *   connected@  brokerage + valid agent config         → ready to activate
 *   active@     activated, trial running, positions    → the full /live dashboard
 *
 * All personas share the password below. All emails are @sandbox.ironforge.test,
 * a reserved-by-convention domain that cannot receive mail — so even if this were
 * somehow pointed at a real database, no real person is ever emailed.
 *
 * It writes to BOTH databases. The customer records above live in
 * CUSTOMERS_DATABASE_URL; the /live dashboard reads the master bot's book out of
 * DATABASE_URL instead, so `active@` also gets a SPARK book seeded there (see
 * seedTradingSide). With DATABASE_URL unset the customer half still seeds and
 * /live renders its empty state.
 *
 * USAGE
 *   IRONFORGE_ENV=sandbox CUSTOMERS_DATABASE_URL=... DATABASE_URL=... node scripts/seed-sandbox.js
 *   ... --reset    drop the seeded users first (default: reseed in place)
 *
 * REFUSES TO RUN unless IRONFORGE_ENV=sandbox and the sandbox guard passes. The
 * script writes fabricated billing and position rows; against production that
 * would be corruption, not a test.
 */

'use strict'

const { Client } = require('pg')
const bcrypt = require('bcryptjs')
const { checkSandboxEnv, databaseNameOf, PRODUCTION_DB_NAMES } = require('./sandbox-guard.js')

const PASSWORD = 'sandbox123'
const EMAIL_DOMAIN = 'sandbox.ironforge.test'
const RULE_VERSION = '2026-07-01'

// ── Trading-side constants ───────────────────────────────────────────────────
// /live does NOT read customer_positions. It reads the master bot's tables in the
// TRADING database, scoped by `person` (lib/live/viewer.ts scopeFilter). So a
// customer with a fully-seeded customer record still sees an empty dashboard
// until these exist too.
const SANDBOX_PERSON = 'Sandbox'
const LIVE_BOT = 'spark'
const LIVE_DTE = '1DTE' // dteMode('spark') — db.ts
const HEARTBEAT_NAME = 'SPARK' // heartbeatName('spark') — db.ts HEARTBEAT_MAP
// SPARK is a production-mode bot, so ledgerFilter('spark') keeps ONLY
// account_type='production' rows (viewer.ts). This label is how the read path
// partitions ledgers — it does not mean real money, and cannot: this is a
// throwaway database and the guard has already proven no live broker or Stripe
// credential is reachable from this process.
const LIVE_ACCOUNT_TYPE = 'production'

/** Tables to clear for seeded users, children before parents (FK order). */
const CLEANUP_ORDER = [
  'customer_positions',
  'trials',
  'activations',
  'agent_configs',
  'trade_approvals',
  'legal_acceptances',
  'community_reactions',
  'community_messages',
  'community_presence',
  'community_moderation_events',
  'community_forge_posts',
  'customer_bot_subscriptions',
  'email_verification_tokens',
  'password_reset_tokens',
  'risk_assessments',
  'oauth_states',
  'attio_sync_queue',
  'audit_events',
  'enrollments',
]

function log(msg) {
  console.log(`[seed-sandbox] ${msg}`)
}

/** Abort unless this is unambiguously a sandbox. */
function assertSafe() {
  const { active, errors } = checkSandboxEnv(process.env)
  if (!active) {
    throw new Error(
      'IRONFORGE_ENV is not "sandbox". This script fabricates billing and position ' +
        'rows and must never run against production.',
    )
  }
  // A sandbox that fails any invariant is misconfigured enough not to trust —
  // except the trading DATABASE_URL, which this script never touches and which
  // you should not have to supply just to seed customers.
  const relevant = errors.filter((e) => !e.startsWith('DATABASE_URL is unset'))
  if (relevant.length > 0) {
    throw new Error(`sandbox guard failed:\n  - ${relevant.join('\n  - ')}`)
  }
  const url = process.env.CUSTOMERS_DATABASE_URL
  if (!url) throw new Error('CUSTOMERS_DATABASE_URL is unset — nothing to seed.')
  const name = databaseNameOf(url)
  if (PRODUCTION_DB_NAMES.has(name)) {
    throw new Error(`CUSTOMERS_DATABASE_URL points at production database "${name}". Refusing.`)
  }
  return name
}

/**
 * DELETE that tolerates a table or column not existing. The customer schema grows
 * by additive DDL and older sandbox databases legitimately lack newer tables; a
 * hard failure there would make the script unusable exactly when it is most useful.
 */
async function tolerantDelete(client, sql, params) {
  try {
    await client.query('SAVEPOINT sp')
    const res = await client.query(sql, params)
    await client.query('RELEASE SAVEPOINT sp')
    return res.rowCount
  } catch (err) {
    await client.query('ROLLBACK TO SAVEPOINT sp')
    // 42P01 undefined_table, 42703 undefined_column
    if (err.code === '42P01' || err.code === '42703') return 0
    throw err
  }
}

async function clearSeeded(client) {
  const pattern = `%@${EMAIL_DOMAIN}`
  const { rows } = await client.query('SELECT id FROM users WHERE email LIKE $1', [pattern])
  if (rows.length === 0) return 0
  const ids = rows.map((r) => r.id)

  // ORDER IS LOAD-BEARING. The user-keyed tables go first, because agent_configs
  // references broker_accounts:
  //
  //   customer_positions → (none)
  //   trials             → activations
  //   activations        → agent_configs
  //   agent_configs      → broker_accounts        ← the one that bit us
  //   broker_accounts    → brokerage_connections
  //   legal_acceptances  → enrollments
  //
  // Deleting broker_accounts before agent_configs raises
  //   "violates foreign key constraint agent_configs_broker_account_id_fkey".
  // That only surfaces on a RE-run — the first run has nothing to clear and
  // returns early above, so this stayed hidden until the second seed.
  for (const table of CLEANUP_ORDER) {
    await tolerantDelete(client, `DELETE FROM ${table} WHERE user_id = ANY($1::uuid[])`, [ids])
  }

  // Now the brokerage chain, which hangs off brokerage_connections rather than
  // users, so it cannot be driven by the user_id loop above.
  await tolerantDelete(
    client,
    `DELETE FROM broker_accounts WHERE connection_id IN
       (SELECT id FROM brokerage_connections WHERE user_id = ANY($1::uuid[]))`,
    [ids],
  )
  await tolerantDelete(client, 'DELETE FROM brokerage_connections WHERE user_id = ANY($1::uuid[])', [ids])

  await client.query('DELETE FROM users WHERE id = ANY($1::uuid[])', [ids])
  return ids.length
}

/** Ensure the legal documents the acceptances reference exist. */
async function ensureLegalDocs(client) {
  const codes = ['TERMS', 'RISK', 'ELECTRONIC_CONSENT', 'TRADING_AUTH']
  const ids = {}
  for (const code of codes) {
    const { rows } = await client.query(
      `INSERT INTO legal_documents (code, plan_scope, version, active)
       VALUES ($1, 'core', $2, TRUE)
       ON CONFLICT (code, version) DO UPDATE SET active = TRUE
       RETURNING id`,
      [code, RULE_VERSION],
    )
    ids[code] = rows[0].id
  }
  return ids
}

async function createUser(client, { slug, first, last, status, step, verified }) {
  const hash = await bcrypt.hash(PASSWORD, 10)
  const { rows } = await client.query(
    `INSERT INTO users
       (password_hash, first_name, last_name, email, phone, state,
        account_status, onboarding_step, email_verified,
        age_confirmed, no_advice_acknowledged, electronic_comm_consent)
     VALUES ($1,$2,$3,$4,'+15125550100','TX',$5,$6,$7,TRUE,TRUE,TRUE)
     RETURNING id, email`,
    [hash, first, last, `${slug}@${EMAIL_DOMAIN}`, status, step, verified],
  )
  return rows[0]
}

async function createEnrollment(client, userId, { plan, status, step }) {
  const { rows } = await client.query(
    `INSERT INTO enrollments (user_id, selected_plan, status, current_step, source,
                              completed_at)
     VALUES ($1,$2,$3,$4,'sandbox-seed', CASE WHEN $3 = 'complete' THEN now() ELSE NULL END)
     RETURNING id`,
    [userId, plan, status, step],
  )
  return rows[0].id
}

async function acceptLegal(client, userId, enrollmentId, docIds) {
  for (const code of ['TERMS', 'RISK', 'ELECTRONIC_CONSENT']) {
    await client.query(
      `INSERT INTO legal_acceptances (user_id, enrollment_id, document_id, ip, user_agent)
       VALUES ($1,$2,$3,'127.0.0.1','sandbox-seed')`,
      [userId, enrollmentId, docIds[code]],
    )
  }
}

async function subscribe(client, userId, { bot, status, lookupKey }) {
  await client.query(
    `INSERT INTO customer_bot_subscriptions
       (user_id, bot, status, stripe_subscription_id, price_lookup_key, current_period_end)
     VALUES ($1,$2,$3,$4,$5, now() + interval '30 days')
     ON CONFLICT (user_id, bot) DO UPDATE SET status = EXCLUDED.status`,
    [userId, bot, status, `sub_sandbox_${userId.slice(0, 8)}_${bot}`, lookupKey],
  )
}

/** Brokerage connection + a synced, eligible account. */
async function connectBrokerage(client, userId) {
  const { rows: conn } = await client.query(
    `INSERT INTO brokerage_connections
       (user_id, authorization_id, brokerage_slug, account_id, account_name, status, last_synced_at)
     VALUES ($1,$2,'TRADIER',$3,'Sandbox Individual','active', now())
     RETURNING id`,
    [userId, `auth_sandbox_${userId.slice(0, 8)}`, `acct_sandbox_${userId.slice(0, 8)}`],
  )
  const connectionId = conn[0].id
  const { rows: acct } = await client.query(
    `INSERT INTO broker_accounts
       (connection_id, display_mask, account_type, options_level, eligibility,
        buying_power_cents, checked_at)
     VALUES ($1,'****4242','margin',3,'eligible',$2, now())
     RETURNING id`,
    [connectionId, 25_000_00],
  )
  return acct[0].id
}

async function configureAgent(client, userId, brokerAccountId, agentCode) {
  const { rows } = await client.query(
    `INSERT INTO agent_configs
       (user_id, broker_account_id, agent_code, rule_version, config_json, status, validated_at)
     VALUES ($1,$2,$3,$4,$5,'valid', now())
     RETURNING id`,
    [
      userId,
      brokerAccountId,
      agentCode,
      RULE_VERSION,
      JSON.stringify({ max_contracts: 2, capital_pct: 0.15, max_daily_loss_cents: 50_000 }),
    ],
  )
  return rows[0].id
}

async function activate(client, userId, configId, agentCode) {
  const { rows } = await client.query(
    `INSERT INTO activations
       (user_id, config_id, status, preview_hash, risk_ack_at, authorization_at, activated_at)
     VALUES ($1,$2,'active',$3, now(), now(), now())
     RETURNING id`,
    [userId, configId, `sandboxhash_${configId.slice(0, 8)}`],
  )
  const activationId = rows[0].id
  await client.query(
    `INSERT INTO trials (user_id, agent_code, activation_id, status, started_at, eligible_days_used)
     VALUES ($1,$2,$3,'active', now() - interval '3 days', 2)
     ON CONFLICT (user_id, agent_code) DO UPDATE SET status = 'active'`,
    [userId, agentCode, activationId],
  )
  return activationId
}

/** One open and one closed mirrored position, so P&L surfaces have both shapes. */
async function seedPositions(client, userId, activationId, configId, agentCode) {
  const base = {
    user_id: userId,
    activation_id: activationId,
    config_id: configId,
    agent_code: agentCode,
  }
  await client.query(
    `INSERT INTO customer_positions
       (user_id, activation_id, config_id, agent_code, source_position_id, ticker,
        expiration, put_short, put_long, call_short, call_long, contracts,
        collateral_cents, status, open_order_id, opened_at, detail_json)
     VALUES ($1,$2,$3,$4,'sandbox-src-open','SPY',
        CURRENT_DATE + 1, 630, 625, 655, 660, 2, 100000, 'open', 'ord_sandbox_open',
        now() - interval '2 hours', $5)`,
    [base.user_id, base.activation_id, base.config_id, base.agent_code,
     JSON.stringify({ entry_credit: 1.15, note: 'sandbox seed — open iron condor' })],
  )
  await client.query(
    `INSERT INTO customer_positions
       (user_id, activation_id, config_id, agent_code, source_position_id, ticker,
        expiration, put_short, put_long, call_short, call_long, contracts,
        collateral_cents, status, open_order_id, close_order_id, close_reason,
        opened_at, closed_at, detail_json)
     VALUES ($1,$2,$3,$4,'sandbox-src-closed','SPY',
        CURRENT_DATE - 1, 625, 620, 650, 655, 2, 100000, 'closed',
        'ord_sandbox_c1','ord_sandbox_c2','profit_target',
        now() - interval '2 days', now() - interval '1 day', $5)`,
    [base.user_id, base.activation_id, base.config_id, base.agent_code,
     JSON.stringify({ entry_credit: 1.2, exit_debit: 0.36, realized_pnl: 168 })],
  )
}

/**
 * Seed the TRADING database so the activated customer's /live page renders.
 *
 * Why this is separate: /live shows the master bot's book, not the customer's
 * mirrored rows. `ironforge_customer_bots` is what authorizes a customer to see a
 * bot at all, and it carries the `person` that every downstream query is scoped
 * to. scopeFilter() FAILS CLOSED — a customer whose mapping has person = NULL
 * matches nothing (deliberately: on 2026-07-27 a NULL person showed one customer
 * the operator's real SPARK account). So person is set on every row here.
 */
async function seedTradingSide(customerId) {
  const client = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
  })
  await client.connect()
  const dbName = databaseNameOf(process.env.DATABASE_URL)
  if (PRODUCTION_DB_NAMES.has(dbName)) {
    await client.end()
    throw new Error(`DATABASE_URL points at production database "${dbName}". Refusing.`)
  }
  log(`trading db: connected to "${dbName}"`)

  const { rows: exists } = await client.query(
    `SELECT to_regclass('public.ironforge_customer_bots') IS NOT NULL AS ok`,
  )
  if (!exists[0].ok) {
    await client.end()
    throw new Error(
      'The trading schema does not exist yet. Open the sandbox site once (or hit ' +
        '/api/health) so the app creates its tables, then re-run this script.',
    )
  }

  const pos = `${LIVE_BOT}_positions`
  const acct = `${LIVE_BOT}_paper_account`
  const snaps = `${LIVE_BOT}_equity_snapshots`

  await client.query('BEGIN')
  try {
    // Idempotent: clear only what this script owns (person = 'Sandbox').
    // The mapping is keyed by customer_id, and re-seeding mints new user UUIDs —
    // so without this every run leaves an orphaned row pointing at a deleted user.
    await tolerantDelete(client, `DELETE FROM ironforge_customer_bots WHERE person = $1`, [
      SANDBOX_PERSON,
    ])
    await tolerantDelete(client, `DELETE FROM ${pos} WHERE person = $1`, [SANDBOX_PERSON])
    await tolerantDelete(client, `DELETE FROM ${snaps} WHERE person = $1`, [SANDBOX_PERSON])
    await tolerantDelete(client, `DELETE FROM ${acct} WHERE person = $1`, [SANDBOX_PERSON])

    // 1. Authorize this customer to see SPARK. Without this row allowedBots is
    //    empty, viewer.bot is null and every /live route returns { empty: true }.
    await client.query(
      `INSERT INTO ironforge_customer_bots (customer_id, bot, person)
       VALUES ($1, $2, $3)
       ON CONFLICT (customer_id, bot) DO UPDATE SET person = EXCLUDED.person`,
      [customerId, LIVE_BOT, SANDBOX_PERSON],
    )

    // 2. The account the balance/buying-power tiles read.
    await client.query(
      `INSERT INTO ${acct}
         (starting_capital, current_balance, cumulative_pnl, total_trades,
          collateral_in_use, buying_power, high_water_mark, max_drawdown,
          is_active, dte_mode, account_type, person)
       VALUES (10000, 10336, 336, 2, 1000, 9000, 10336, 0, TRUE, $1, $2, $3)`,
      [LIVE_DTE, LIVE_ACCOUNT_TYPE, SANDBOX_PERSON],
    )

    // 3. One open iron condor (positions tab + collateral) and one closed today
    //    (today's realized P&L — summary.ts filters close_time to CT today).
    await client.query(
      `INSERT INTO ${pos}
         (position_id, ticker, expiration,
          put_short_strike, put_long_strike, put_credit,
          call_short_strike, call_long_strike, call_credit,
          contracts, spread_width, total_credit, max_loss, max_profit,
          collateral_required, underlying_at_entry, vix_at_entry, gex_regime,
          status, open_time, open_date, dte_mode, account_type, person)
       VALUES ('sbx-open-1', 'SPY', CURRENT_DATE + 1,
          630, 625, 0.58, 655, 660, 0.57,
          2, 5, 1.15, 770, 230,
          1000, 747.03, 14.2, 'positive',
          'open', now() - interval '2 hours', CURRENT_DATE, $1, $2, $3)`,
      [LIVE_DTE, LIVE_ACCOUNT_TYPE, SANDBOX_PERSON],
    )
    await client.query(
      `INSERT INTO ${pos}
         (position_id, ticker, expiration,
          put_short_strike, put_long_strike, put_credit,
          call_short_strike, call_long_strike, call_credit,
          contracts, spread_width, total_credit, max_loss, max_profit,
          collateral_required, underlying_at_entry, vix_at_entry, gex_regime,
          status, open_time, open_date, close_time, close_price, close_reason,
          realized_pnl, dte_mode, account_type, person)
       VALUES ('sbx-closed-1', 'SPY', CURRENT_DATE,
          625, 620, 0.62, 650, 655, 0.58,
          2, 5, 1.20, 760, 240,
          1000, 744.10, 13.8, 'positive',
          'closed', now() - interval '1 day', CURRENT_DATE - 1,
          now() - interval '3 hours', 0.36, 'profit_target',
          168, $1, $2, $3)`,
      [LIVE_DTE, LIVE_ACCOUNT_TYPE, SANDBOX_PERSON],
    )

    // 4. Intraday equity curve. A single point draws no line (the chart needs at
    //    least two), so lay down a series across today in CT.
    await client.query(
      `INSERT INTO ${snaps}
         (snapshot_time, balance, unrealized_pnl, realized_pnl, open_positions,
          note, dte_mode, account_type, person)
       SELECT
         ((CURRENT_DATE + time '08:30') AT TIME ZONE 'America/Chicago') + (g * interval '45 minutes'),
         10000 + (g * 42), (g * 12), CASE WHEN g >= 4 THEN 168 ELSE 0 END,
         CASE WHEN g >= 2 THEN 1 ELSE 0 END,
         'sandbox seed', $1, $2, $3
       FROM generate_series(0, 7) AS g`,
      [LIVE_DTE, LIVE_ACCOUNT_TYPE, SANDBOX_PERSON],
    )

    // 5. Heartbeat so the status pill reads healthy instead of "no signal".
    await client.query(
      `INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
       VALUES ($1, now(), 'running', 128, 'sandbox seed')
       ON CONFLICT (bot_name) DO UPDATE
         SET last_heartbeat = EXCLUDED.last_heartbeat,
             status = EXCLUDED.status,
             details = EXCLUDED.details`,
      [HEARTBEAT_NAME],
    )

    await client.query('COMMIT')
    log(`trading db: ${LIVE_BOT.toUpperCase()} book seeded for person "${SANDBOX_PERSON}"`)
  } catch (err) {
    await client.query('ROLLBACK')
    throw err
  } finally {
    await client.end()
  }
}

async function main() {
  const dbName = assertSafe()
  const reset = process.argv.includes('--reset')

  const client = new Client({
    connectionString: process.env.CUSTOMERS_DATABASE_URL,
    ssl: { rejectUnauthorized: false },
  })
  await client.connect()
  log(`connected to "${dbName}"`)

  // The schema is created by the app (customers-db.ts ensureCustomerTables) on its
  // first request. Seeding a database the app has never touched would half-create
  // tables from these INSERTs' perspective, so require it explicitly.
  const { rows: exists } = await client.query(
    `SELECT to_regclass('public.users') IS NOT NULL AS ok`,
  )
  if (!exists[0].ok) {
    throw new Error(
      'The customer schema does not exist yet. Open the sandbox site once (or hit ' +
        '/api/health) so the app creates its tables, then re-run this script.',
    )
  }

  await client.query('BEGIN')
  try {
    if (reset) {
      const n = await clearSeeded(client)
      log(`--reset: removed ${n} previously seeded user(s)`)
    } else {
      const n = await clearSeeded(client)
      if (n > 0) log(`replaced ${n} existing seeded user(s)`)
    }

    const docIds = await ensureLegalDocs(client)
    const made = []

    // ── 1. signed up, email not verified ──────────────────────────────────────
    let u = await createUser(client, {
      slug: 'new', first: 'Nina', last: 'Newman',
      status: 'pending_email_verification', step: 'account_created', verified: false,
    })
    await createEnrollment(client, u.id, { plan: null, status: 'draft', step: 'account' })
    made.push([u.email, 'signed up, email unverified'])

    // ── 2. verified, legal not accepted ───────────────────────────────────────
    u = await createUser(client, {
      slug: 'verified', first: 'Vic', last: 'Verified',
      status: 'active', step: 'email_verified', verified: true,
    })
    await createEnrollment(client, u.id, { plan: 'spark', status: 'legal_pending', step: 'legal' })
    made.push([u.email, 'verified, legal pending'])

    // ── 3. legal accepted, unpaid ─────────────────────────────────────────────
    u = await createUser(client, {
      slug: 'legal', first: 'Lena', last: 'Legal',
      status: 'active', step: 'legal_accepted', verified: true,
    })
    let e = await createEnrollment(client, u.id, { plan: 'spark', status: 'billing_pending', step: 'billing' })
    await acceptLegal(client, u.id, e, docIds)
    made.push([u.email, 'legal accepted, awaiting payment'])

    // ── 4. paid, nothing configured ───────────────────────────────────────────
    u = await createUser(client, {
      slug: 'paid', first: 'Pat', last: 'Paid',
      status: 'active', step: 'billing_complete', verified: true,
    })
    e = await createEnrollment(client, u.id, { plan: 'spark', status: 'setup_required', step: 'brokerage' })
    await acceptLegal(client, u.id, e, docIds)
    await subscribe(client, u.id, { bot: 'spark', status: 'active', lookupKey: 'spark_monthly' })
    made.push([u.email, 'paid, setup required'])

    // ── 5. past_due — the dunning / payment-due surface ───────────────────────
    u = await createUser(client, {
      slug: 'pastdue', first: 'Dana', last: 'Dunning',
      status: 'active', step: 'billing_complete', verified: true,
    })
    e = await createEnrollment(client, u.id, { plan: 'spark', status: 'setup_required', step: 'billing' })
    await acceptLegal(client, u.id, e, docIds)
    await subscribe(client, u.id, { bot: 'spark', status: 'past_due', lookupKey: 'spark_monthly' })
    made.push([u.email, 'subscription past_due'])

    // ── 6. brokerage connected + valid config, not activated ──────────────────
    u = await createUser(client, {
      slug: 'connected', first: 'Cory', last: 'Connected',
      status: 'active', step: 'brokerage_connected', verified: true,
    })
    e = await createEnrollment(client, u.id, { plan: 'spark', status: 'setup_required', step: 'activate' })
    await acceptLegal(client, u.id, e, docIds)
    await subscribe(client, u.id, { bot: 'spark', status: 'active', lookupKey: 'spark_monthly' })
    let acctId = await connectBrokerage(client, u.id)
    await configureAgent(client, u.id, acctId, 'spark')
    made.push([u.email, 'brokerage connected, ready to activate'])

    // ── 7. fully active with positions ────────────────────────────────────────
    u = await createUser(client, {
      slug: 'active', first: 'Alex', last: 'Active',
      status: 'active', step: 'complete', verified: true,
    })
    e = await createEnrollment(client, u.id, { plan: 'both', status: 'complete', step: 'done' })
    await acceptLegal(client, u.id, e, docIds)
    await subscribe(client, u.id, { bot: 'spark', status: 'active', lookupKey: 'both_monthly' })
    await subscribe(client, u.id, { bot: 'flame', status: 'active', lookupKey: 'both_monthly' })
    acctId = await connectBrokerage(client, u.id)
    const cfgId = await configureAgent(client, u.id, acctId, 'spark')
    const actId = await activate(client, u.id, cfgId, 'spark')
    await seedPositions(client, u.id, actId, cfgId, 'spark')
    made.push([u.email, 'active, trial running, 1 open + 1 closed position'])
    const activeUserId = u.id

    await client.query('COMMIT')

    // Trading side, AFTER the customer commit — it needs the committed user id,
    // and it is a different database so it cannot share the transaction. Only the
    // activated persona gets a bot mapping: `paid@` and `connected@` seeing an
    // empty /live is the correct depiction of their state, not a gap.
    if (process.env.DATABASE_URL) {
      await seedTradingSide(activeUserId)
    } else {
      log('DATABASE_URL unset — skipped the trading side; active@ will see an EMPTY /live.')
    }

    log('')
    log(`seeded ${made.length} personas — password for all: ${PASSWORD}`)
    log('')
    for (const [email, desc] of made) log(`  ${email.padEnd(34)} ${desc}`)
    log('')
  } catch (err) {
    await client.query('ROLLBACK')
    throw err
  } finally {
    await client.end()
  }
}

main().catch((err) => {
  console.error(`[seed-sandbox] FAILED: ${err.message}`)
  process.exit(1)
})
