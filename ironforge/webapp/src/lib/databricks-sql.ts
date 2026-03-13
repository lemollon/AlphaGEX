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

  // Bust Databricks SQL warehouse result cache (persists up to 24h, survives
  // warehouse restarts on serverless).  The result cache is keyed on the full
  // SQL statement text — any change in the text causes a cache miss.
  //
  // The Statement Execution API has NO request-level parameter to disable
  // caching.  `use_cached_result = false` is a session-level SET command, but
  // the REST API is stateless (no persistent session), so we cannot use it.
  //
  // Adding a unique timestamp comment to every query is the documented
  // workaround: each request produces a different statement hash, guaranteeing
  // a cache miss every time.
  //
  // Ref: https://docs.databricks.com/aws/en/sql/user/queries/query-caching
  // Ref: https://community.databricks.com/t5/data-engineering/control-query-caching-using-sql-statement-execution-api/td-p/3561
  const cacheBust = `/* ts=${Date.now()} */`
  const statement = `${sql} ${cacheBust}`

  const url = `https://${HOSTNAME}/api/2.0/sql/statements/`
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify({
      warehouse_id: WAREHOUSE_ID,
      catalog: CATALOG,
      schema: SCHEMA,
      statement,
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
 *
 * Returns num_affected_rows for DML (UPDATE/DELETE/MERGE), 0 for DDL/INSERT.
 * Databricks returns a single-row result with the affected count for DML.
 */
export async function dbExecute(sql: string): Promise<number> {
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
    cache: 'no-store',
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

  // Extract num_affected_rows from DML result (first value of first row)
  try {
    const dataArray: any[][] = body.result?.data_array || []
    if (dataArray.length > 0 && dataArray[0].length > 0) {
      const val = dataArray[0][0]
      if (val != null) {
        const n = parseInt(String(val), 10)
        if (!isNaN(n)) return n
      }
    }
  } catch {
    // Non-fatal — return 0 for operations that don't report affected rows
  }
  return 0
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

/** Parse a value as a float, defaulting to 0. */
export function num(val: unknown): number {
  if (val == null || val === '') return 0
  const n = parseFloat(String(val))
  return isNaN(n) ? 0 : n
}

/** Parse a value as an int, defaulting to 0. */
export function int(val: unknown): number {
  if (val == null || val === '') return 0
  const n = parseInt(String(val), 10)
  return isNaN(n) ? 0 : n
}

/** Map bot name to heartbeat bot_name value in bot_heartbeats table. */
export function heartbeatName(bot: string): string {
  return bot.toUpperCase()
}

/**
 * SQL expression for "today" in Central Time for Databricks.
 * Databricks CURRENT_DATE() uses the warehouse timezone, but to be
 * explicit we convert from UTC to CT before extracting the date.
 */
export const CT_TODAY = "CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', CURRENT_TIMESTAMP()) AS DATE)"
