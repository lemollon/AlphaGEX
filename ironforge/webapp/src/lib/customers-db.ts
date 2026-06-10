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
