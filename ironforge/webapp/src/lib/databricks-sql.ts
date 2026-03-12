/**
 * Databricks SQL Statement Execution API client for IronForge on Vercel.
 *
 * Uses the Databricks REST API to execute SQL against a SQL warehouse.
 * No npm packages needed — just fetch().
 *
 * Env vars (set in Vercel):
 *   DATABRICKS_SERVER_HOSTNAME
 *   DATABRICKS_WAREHOUSE_ID
 *   DATABRICKS_TOKEN
 *   DATABRICKS_CATALOG  (default: alpha_prime)
 *   DATABRICKS_SCHEMA   (default: ironforge)
 */

const HOSTNAME = process.env.DATABRICKS_SERVER_HOSTNAME || ''
const WAREHOUSE_ID = process.env.DATABRICKS_WAREHOUSE_ID || ''
const TOKEN = process.env.DATABRICKS_TOKEN || ''
const CATALOG = process.env.DATABRICKS_CATALOG || 'alpha_prime'
const SCHEMA = process.env.DATABRICKS_SCHEMA || 'ironforge'

/** Fully qualified table name: alpha_prime.ironforge.{name} */
export function sharedTable(name: string): string {
  return `${CATALOG}.${SCHEMA}.${name}`
}

/**
 * Execute a SQL statement against Databricks and return rows as objects.
 * Uses the SQL Statement Execution API with WAIT disposition.
 */
export async function dbQuery<T = Record<string, any>>(sql: string): Promise<T[]> {
  if (!HOSTNAME || !WAREHOUSE_ID || !TOKEN) {
    throw new Error('Databricks env vars not configured (DATABRICKS_SERVER_HOSTNAME, DATABRICKS_WAREHOUSE_ID, DATABRICKS_TOKEN)')
  }

  const url = `https://${HOSTNAME}/api/2.0/sql/statements/`
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      warehouse_id: WAREHOUSE_ID,
      catalog: CATALOG,
      schema: SCHEMA,
      statement: sql,
      wait_timeout: '30s',
      disposition: 'INLINE',
      format: 'JSON_ARRAY',
    }),
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Databricks API ${res.status}: ${text}`)
  }

  const body = await res.json()

  if (body.status?.state === 'FAILED') {
    throw new Error(`SQL error: ${body.status?.error?.message || 'Unknown error'}`)
  }

  // Parse result: columns + data_array
  const columns: string[] = (body.manifest?.schema?.columns || []).map(
    (c: { name: string }) => c.name,
  )
  const dataArray: any[][] = body.result?.data_array || []

  return dataArray.map((row) => {
    const obj: Record<string, any> = {}
    for (let i = 0; i < columns.length; i++) {
      obj[columns[i]] = row[i]
    }
    return obj as T
  })
}

/**
 * Execute a SQL statement that doesn't return rows (INSERT, UPDATE, DELETE, MERGE).
 */
export async function dbExecute(sql: string): Promise<void> {
  if (!HOSTNAME || !WAREHOUSE_ID || !TOKEN) {
    throw new Error('Databricks env vars not configured')
  }

  const url = `https://${HOSTNAME}/api/2.0/sql/statements/`
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      warehouse_id: WAREHOUSE_ID,
      catalog: CATALOG,
      schema: SCHEMA,
      statement: sql,
      wait_timeout: '30s',
      disposition: 'INLINE',
    }),
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Databricks API ${res.status}: ${text}`)
  }

  const body = await res.json()

  if (body.status?.state === 'FAILED') {
    throw new Error(`SQL error: ${body.status?.error?.message || 'Unknown error'}`)
  }
}

/** Escape single quotes for Databricks SQL string literals. */
export function escapeSql(val: string): string {
  return val.replace(/'/g, "''")
}

/** Bot-specific fully-qualified table name: alpha_prime.ironforge.{bot}_{suffix}. */
export function botTable(bot: string, suffix: string): string {
  return `${CATALOG}.${SCHEMA}.${bot}_${suffix}`
}

/** Validate bot name — only flame, spark, or inferno allowed. */
export function validateBot(bot: string): string | null {
  const b = bot.toLowerCase()
  if (b !== 'flame' && b !== 'spark' && b !== 'inferno') return null
  return b
}

/** Returns the dte_mode value for this bot. */
export function dteMode(bot: string): string | null {
  if (bot === 'flame') return '2DTE'
  if (bot === 'spark') return '1DTE'
  if (bot === 'inferno') return '0DTE'
  return null
}
