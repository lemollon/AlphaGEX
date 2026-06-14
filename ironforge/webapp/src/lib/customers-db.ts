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
