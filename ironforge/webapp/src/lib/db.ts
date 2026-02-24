/**
 * PostgreSQL client for IronForge on Render.
 *
 * Replaces the Databricks REST API client. Uses node-postgres (pg) directly.
 */

import { Pool } from 'pg'

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
  max: 5,
})

/** Bot-specific table name */
export function botTable(bot: string, suffix: string): string {
  return `${bot}_${suffix}`
}

/**
 * Execute a SQL query and return rows as objects.
 * Uses parameterized queries when params provided.
 */
export async function query<T = Record<string, any>>(
  sql: string,
  params?: any[],
): Promise<T[]> {
  const client = await pool.connect()
  try {
    const result = await client.query(sql, params)
    return result.rows as T[]
  } finally {
    client.release()
  }
}

/** Parse a value as a float, defaulting to 0. */
export function num(val: any): number {
  if (val == null || val === '') return 0
  const n = parseFloat(val)
  return isNaN(n) ? 0 : n
}

/** Parse a value as an int, defaulting to 0. */
export function int(val: any): number {
  if (val == null || val === '') return 0
  const n = parseInt(val, 10)
  return isNaN(n) ? 0 : n
}

/** Validate bot name parameter — only flame or spark allowed. */
export function validateBot(bot: string): string | null {
  const b = bot.toLowerCase()
  if (b !== 'flame' && b !== 'spark') return null
  return b
}
