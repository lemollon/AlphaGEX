/**
 * PostgreSQL client for the dedicated `ironforge-customers` database
 * (Render dpg-d8eeek740ujc73dh446g-a, Oregon). SEPARATE from the bot DB (`@/lib/db`).
 *
 * Holds customer/prospect enrollment data: users, audit_events,
 * email_verification_tokens. Connected over the internal URL via CUSTOMERS_DATABASE_URL.
 *
 * If CUSTOMERS_DATABASE_URL is unset (not yet wired in Render), every call throws
 * CustomersDbNotConfiguredError so routes can degrade to a clean 503 instead of crashing.
 */

import { Pool } from 'pg'

export class CustomersDbNotConfiguredError extends Error {
  constructor() {
    super('CUSTOMERS_DATABASE_URL is not configured')
    this.name = 'CustomersDbNotConfiguredError'
  }
}

export function isCustomersDbConfigured(): boolean {
  return !!process.env.CUSTOMERS_DATABASE_URL
}

let _pool: Pool | null = null

function getPool(): Pool {
  if (!isCustomersDbConfigured()) throw new CustomersDbNotConfiguredError()
  if (!_pool) {
    _pool = new Pool({
      connectionString: process.env.CUSTOMERS_DATABASE_URL,
      ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
      max: 5,
    })
  }
  return _pool
}

const INIT_DDL = `
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user_id TEXT UNIQUE,
  password_hash TEXT NOT NULL,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  phone TEXT NOT NULL,
  state TEXT NOT NULL,
  referral_code TEXT,
  promo_code TEXT,
  account_status TEXT NOT NULL DEFAULT 'pending_email_verification',
  onboarding_step TEXT NOT NULL DEFAULT 'account_created',
  email_verified BOOLEAN NOT NULL DEFAULT FALSE,
  phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
  age_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  no_advice_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
  electronic_comm_consent BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  event_type TEXT NOT NULL,
  event_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_address TEXT,
  user_agent TEXT,
  metadata JSONB
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_evt_token_hash ON email_verification_tokens(token_hash);

CREATE TABLE IF NOT EXISTS attio_sync_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  payload JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT,
  attio_record_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  synced_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_attio_queue_pending ON attio_sync_queue(status, attempts);

CREATE TABLE IF NOT EXISTS risk_assessments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  answers JSONB NOT NULL,
  score INT NOT NULL,
  tier TEXT NOT NULL,
  recommended_bot TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_assessments_user ON risk_assessments(user_id);

ALTER TABLE users ADD COLUMN IF NOT EXISTS risk_tier TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS recommended_bot TEXT;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prt_token_hash ON password_reset_tokens(token_hash);

ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

-- TradingView indicator perk (7/30): the member-provided TradingView username that
-- invite-only script access is granted to, and when the grant was completed. Setting a
-- NEW username resets granted_at — access follows the username, not the account.
ALTER TABLE users ADD COLUMN IF NOT EXISTS tradingview_username TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS tradingview_granted_at TIMESTAMPTZ;

-- Founding promo captured at signup (e.g. FORGE50). Honoured at activation until
-- billing/Stripe lands; then it becomes a real coupon. See lib/promo.ts.
ALTER TABLE users ADD COLUMN IF NOT EXISTS promo_code TEXT;

-- Brokerage connection (Model A: customers link their own brokerage via SnapTrade) --
ALTER TABLE users ADD COLUMN IF NOT EXISTS snaptrade_user_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS snaptrade_user_secret TEXT;       -- AES-256-GCM ciphertext
ALTER TABLE users ADD COLUMN IF NOT EXISTS brokerage_connected BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS brokerage_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  authorization_id TEXT,
  brokerage_slug TEXT,
  account_id TEXT,
  account_name TEXT,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | active | disabled | removed
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_brokerage_conn_user ON brokerage_connections(user_id);

CREATE TABLE IF NOT EXISTS trade_approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  account_id TEXT NOT NULL,
  bot TEXT,
  symbol TEXT NOT NULL,
  action TEXT NOT NULL,                      -- BUY | SELL
  units NUMERIC,
  order_type TEXT NOT NULL DEFAULT 'Market',
  preview JSONB,
  snaptrade_trade_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending',    -- pending | approved | placed | failed | expired | declined
  expires_at TIMESTAMPTZ NOT NULL,
  placed_order_id TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_trade_approvals_user_status ON trade_approvals(user_id, status);

-- Multi-provider brokerage support: SnapTrade (default) or direct Tradier OAuth.
ALTER TABLE brokerage_connections ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'snaptrade';
ALTER TABLE trade_approvals       ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'snaptrade';
ALTER TABLE users ADD COLUMN IF NOT EXISTS tradier_access_token TEXT;       -- AES-256-GCM ciphertext
ALTER TABLE users ADD COLUMN IF NOT EXISTS tradier_refresh_token TEXT;      -- AES-256-GCM ciphertext
ALTER TABLE users ADD COLUMN IF NOT EXISTS tradier_token_expires_at TIMESTAMPTZ;

-- Forge Community (members-only chat; see IronForge_Forge_Community_V1 design doc) --
CREATE TABLE IF NOT EXISTS community_channels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO community_channels (slug, name, sort_order) VALUES
  ('all-chat', 'All Chat', 0),
  ('market-talk', 'Market Talk', 1),
  ('trade-ideas', 'Trade Ideas', 2),
  ('news-events', 'News & Events', 3),
  ('general', 'General', 4)
ON CONFLICT (slug) DO NOTHING;

CREATE TABLE IF NOT EXISTS community_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_id UUID NOT NULL REFERENCES community_channels(id),
  user_id UUID REFERENCES users(id),
  sender_name TEXT NOT NULL,
  sender_type VARCHAR(25) NOT NULL DEFAULT 'USER',   -- USER | FORGE | SYSTEM
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_community_messages_channel_time
  ON community_messages(channel_id, created_at);

CREATE TABLE IF NOT EXISTS community_reactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES community_messages(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  emoji TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (message_id, user_id, emoji)
);

CREATE TABLE IF NOT EXISTS community_presence (
  user_id UUID PRIMARY KEY REFERENCES users(id),
  display_name TEXT NOT NULL,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS community_moderation_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  message_excerpt TEXT,
  category TEXT NOT NULL,
  score NUMERIC,
  action TEXT NOT NULL,                              -- REJECTED | WARNING
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dedupe ledger for Forge's scheduled community posts (one row per slot).
CREATE TABLE IF NOT EXISTS community_forge_posts (
  slot_key TEXT PRIMARY KEY,                         -- e.g. 2026-07-09-premarket
  message_id UUID REFERENCES community_messages(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Billing (Stripe subscriptions; see lib/billing/*). A customer subscribes to a
-- bot ("spark"/"flame") or the "both" bundle via Stripe Checkout. stripe_customer_id
-- is the one Stripe Customer per user; one subscription row per bot they run.
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
CREATE TABLE IF NOT EXISTS customer_bot_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  bot TEXT NOT NULL,                                 -- spark | flame
  status TEXT NOT NULL,                              -- trialing | active | past_due | canceled | incomplete
  stripe_subscription_id TEXT,
  price_lookup_key TEXT,                             -- spark_monthly | flame_monthly | both_monthly
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, bot)
);
CREATE INDEX IF NOT EXISTS idx_customer_bot_subs_user ON customer_bot_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_customer_bot_subs_sub ON customer_bot_subscriptions(stripe_subscription_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Enrollment / activation (Enrollment spec §5). The rule these exist to enforce:
-- paid membership is NOT authority to trade, so membership, brokerage, agent
-- configuration, activation and the trial are SEPARATE records with separate
-- lifecycles. Domain rules live in lib/enrollment/ (pure + tested).
--
-- DELIBERATELY NOT CREATED: a memberships table. customer_bot_subscriptions
-- above already is one, written by the verified Stripe webhook — the spec's own
-- authority for membership state. A second would be pure redundancy.
-- ─────────────────────────────────────────────────────────────────────────────

-- Resumable, server-owned enrollment. Replaces reading intent off the single
-- users.onboarding_step string, which cannot express "which plan" or "why stuck".
CREATE TABLE IF NOT EXISTS enrollments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  selected_plan TEXT,                                -- community | spark | flame | both
  status TEXT NOT NULL DEFAULT 'draft',              -- draft|legal_pending|billing_pending|setup_required|complete|abandoned
  current_step TEXT,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_enrollments_user ON enrollments(user_id);

-- Immutable document versions. A changed version invalidates ONLY its own prior
-- acceptance (§11), which is impossible to express without versioning them.
CREATE TABLE IF NOT EXISTS legal_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL,                                -- TERMS | RISK | ELECTRONIC_CONSENT | TRADING_AUTH
  plan_scope TEXT NOT NULL DEFAULT 'core',           -- core | automate
  version TEXT NOT NULL,
  effective_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  content_uri TEXT,
  sha256 TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (code, version)
);
CREATE INDEX IF NOT EXISTS idx_legal_docs_active ON legal_documents(code, active);

-- APPEND-ONLY evidence. Never updated or deleted: the audit requirement is that any
-- past consent can be reconstructed with its version and timestamp (§12).
CREATE TABLE IF NOT EXISTS legal_acceptances (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  enrollment_id UUID REFERENCES enrollments(id),
  document_id UUID NOT NULL REFERENCES legal_documents(id),
  accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip TEXT,
  user_agent TEXT
);
-- UNIQUE so re-accepting is idempotent (ON CONFLICT DO NOTHING) rather than appending a
-- duplicate row every time a customer revisits the legal step. Accepting a NEW version
-- still creates a row, because document_id is per (code, version) — which is exactly the
-- granularity "a changed document invalidates only that acceptance" needs.
--
-- A NON-unique index of the old name already shipped. CREATE UNIQUE INDEX IF NOT EXISTS
-- under that name would find it, skip, and leave it non-unique — and then ON CONFLICT
-- (user_id, document_id) fails at runtime with "no unique or exclusion constraint
-- matching". So the old one is dropped by name and the unique one gets a new name.
-- Safe: the only writer of this table is the v1 acceptances route, which has no UI yet.
DROP INDEX IF EXISTS idx_legal_acc_user;
CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_acc_user_doc ON legal_acceptances(user_id, document_id);

-- E-signature (July 29 handoff LEGAL-AUTO-01 / §17): the member's typed full legal
-- name at acceptance time. Nullable ADD COLUMN on an append-only table — existing rows
-- are never updated, so pre-signature acceptances simply have no signature. Required
-- (server-enforced) only for automate-family plans.
ALTER TABLE legal_acceptances ADD COLUMN IF NOT EXISTS signature_name TEXT;

-- One brokerage connection has MANY accounts; the existing brokerage_connections row
-- conflated the two. Never store a full account number — mask for display, ciphertext
-- for the reference (§8).
CREATE TABLE IF NOT EXISTS broker_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  connection_id UUID NOT NULL REFERENCES brokerage_connections(id),
  external_account_ref_ciphertext TEXT,
  display_mask TEXT NOT NULL,                        -- e.g. ****6411
  account_type TEXT,
  options_level INT,
  eligibility TEXT NOT NULL DEFAULT 'unknown',       -- eligible | ineligible | unknown
  ineligible_reason TEXT,
  -- Captured at sync. The agent-config form sizes limits from this; activation
  -- re-reads it live, and the preview hash catches any drift in between (§4).
  buying_power_cents BIGINT,
  checked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_broker_accounts_conn ON broker_accounts(connection_id);

-- Versioned config snapshot. rule_version is what makes a config go stale when the
-- approved rule set moves under it.
CREATE TABLE IF NOT EXISTS agent_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  broker_account_id UUID REFERENCES broker_accounts(id),
  agent_code TEXT NOT NULL,                          -- spark | flame
  rule_version TEXT NOT NULL,
  config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft',              -- not_started|draft|valid|stale|archived
  validated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_configs_user ON agent_configs(user_id, agent_code);

-- The record that authorizes orders. preview_hash pins the immutable snapshot the
-- customer actually consented to (§4) so a changed account/config invalidates it.
CREATE TABLE IF NOT EXISTS activations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  config_id UUID NOT NULL REFERENCES agent_configs(id),
  status TEXT NOT NULL DEFAULT 'activating',         -- inactive|activating|active|paused|blocked|revoked
  preview_hash TEXT,
  risk_ack_at TIMESTAMPTZ,
  authorization_at TIMESTAMPTZ,
  activated_at TIMESTAMPTZ,
  paused_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_activations_user ON activations(user_id, status);

-- FIVE ELIGIBLE TRADING DAYS, not calendar days — Stripe's trial_period_days cannot
-- express this, so the calendar authority lives here and Stripe stays the billing
-- authority. Opened ONLY inside the activation transaction (§7).
CREATE TABLE IF NOT EXISTS trials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  agent_code TEXT NOT NULL,
  activation_id UUID REFERENCES activations(id),
  status TEXT NOT NULL DEFAULT 'not_started',        -- not_started|active|completed|converted|canceled
  started_at TIMESTAMPTZ,
  eligible_days_used INT NOT NULL DEFAULT 0,
  last_counted_market_date DATE,                     -- makes day-counting idempotent
  completed_at TIMESTAMPTZ,
  converts_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, agent_code)
);
CREATE INDEX IF NOT EXISTS idx_trials_status ON trials(status);

-- OAuth state + PKCE verifier, SERVER-SIDE (§8 threat table: state + PKCE +
-- one-time callback + short expiry). A stateless signed token cannot give the last
-- two: single-use needs a record to mark, and a verifier that travels with the
-- request defeats the point of PKCE. 10-minute TTL per §3 BROKER-01.
-- return_to: which surface initiated the OAuth round-trip ('enroll' | 'onboarding').
-- An allowlisted literal resolved to a fixed route at callback time — NEVER a raw URL,
-- so it cannot become an open redirect.
CREATE TABLE IF NOT EXISTS oauth_states (
  state TEXT PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  broker_code TEXT NOT NULL,
  code_verifier TEXT,                                -- NULL when the broker has no PKCE
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ                            -- set exactly once; enforces one-time use
);
CREATE INDEX IF NOT EXISTS idx_oauth_states_expiry ON oauth_states(expires_at);
ALTER TABLE oauth_states ADD COLUMN IF NOT EXISTS return_to TEXT;

-- DASH-FIRST-01: the first-entry confirmation renders ONCE per activation. A server
-- field, not client storage, because the flow crosses a hard redirect (/enroll → /live)
-- and a fresh device must not re-show it.
ALTER TABLE activations ADD COLUMN IF NOT EXISTS confirmation_shown_at TIMESTAMPTZ;

-- "Repeated payment or activation requests create one logical result" (§12).
CREATE TABLE IF NOT EXISTS idempotency_keys (
  key TEXT NOT NULL,
  user_id UUID NOT NULL REFERENCES users(id),
  operation TEXT NOT NULL,
  response_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (key, operation)
);

-- Token lifecycle on the EXISTING connection row rather than a parallel table (§8).
ALTER TABLE brokerage_connections ADD COLUMN IF NOT EXISTS broker_code TEXT;
ALTER TABLE brokerage_connections ADD COLUMN IF NOT EXISTS token_ciphertext TEXT;
ALTER TABLE brokerage_connections ADD COLUMN IF NOT EXISTS token_expiry TIMESTAMPTZ;
ALTER TABLE brokerage_connections ADD COLUMN IF NOT EXISTS scopes TEXT;
ALTER TABLE brokerage_connections ADD COLUMN IF NOT EXISTS external_user_ref TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- Phase B: customer order executor (lib/customer-executor). One row per
-- (master position × customer) — simultaneously the durable idempotency record
-- (the unique index below is the restart-proof double-place guard; the scanner's
-- in-memory guards do not survive restarts) and the customer-side audit trail.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customer_positions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  activation_id UUID,
  config_id UUID,
  agent_code TEXT NOT NULL,                          -- spark | flame
  source_position_id TEXT NOT NULL,                  -- the master bot's position_id
  broker_account_id UUID,
  ticker TEXT NOT NULL,
  expiration DATE NOT NULL,
  put_short NUMERIC, put_long NUMERIC,
  call_short NUMERIC, call_long NUMERIC,             -- 0/0 → 2-leg put credit spread
  contracts INTEGER NOT NULL DEFAULT 0,
  collateral_cents BIGINT,
  status TEXT NOT NULL DEFAULT 'claimed',            -- claimed|skipped|open|close_pending|closed|close_failed|error
  skip_reason TEXT,
  open_order_id TEXT,
  close_order_id TEXT,
  close_reason TEXT,
  close_attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  detail_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  opened_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ
);
-- Fresh unique index name (see the #2654 note above) — this IS the double-place guard.
CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_positions_source_user
  ON customer_positions (source_position_id, user_id);
CREATE INDEX IF NOT EXISTS idx_customer_positions_user ON customer_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_customer_positions_status ON customer_positions(status);
`

let _ensured: Promise<void> | null = null

export async function ensureCustomerTables(): Promise<void> {
  if (!_ensured) {
    _ensured = (async () => {
      const client = await getPool().connect()
      try {
        await client.query(INIT_DDL)
      } finally {
        client.release()
      }
    })().catch((e) => {
      _ensured = null // allow retry on next call
      throw e
    })
  }
  return _ensured
}

export async function customerQuery<T = Record<string, any>>(
  sql: string,
  params?: any[],
): Promise<T[]> {
  await ensureCustomerTables()
  const client = await getPool().connect()
  try {
    const result = await client.query(sql, params)
    return result.rows as T[]
  } finally {
    client.release()
  }
}

export async function customerExecute(sql: string, params?: any[]): Promise<number> {
  await ensureCustomerTables()
  const client = await getPool().connect()
  try {
    const result = await client.query(sql, params)
    return result.rowCount ?? 0
  } finally {
    client.release()
  }
}

/** Run a set of statements inside a single transaction on a dedicated client. */
export async function customerTransaction<T>(
  fn: (q: (sql: string, params?: any[]) => Promise<any[]>) => Promise<T>,
): Promise<T> {
  await ensureCustomerTables()
  const client = await getPool().connect()
  try {
    await client.query('BEGIN')
    const run = async (sql: string, params?: any[]) => (await client.query(sql, params)).rows
    const out = await fn(run)
    await client.query('COMMIT')
    return out
  } catch (e) {
    try {
      await client.query('ROLLBACK')
    } catch {
      /* ignore rollback failure */
    }
    throw e
  } finally {
    client.release()
  }
}
