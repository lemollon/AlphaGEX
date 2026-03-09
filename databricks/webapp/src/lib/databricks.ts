/**
 * Databricks SQL Statement Execution REST API client.
 *
 * Uses the REST API (no native driver) so it works in Vercel serverless functions.
 * Docs: https://docs.databricks.com/api/workspace/statementexecution
 */

const HOSTNAME = process.env.DATABRICKS_SERVER_HOSTNAME || ''
const TOKEN = process.env.DATABRICKS_TOKEN || ''
const CATALOG = process.env.DATABRICKS_CATALOG || 'alpha_prime'
const SCHEMA = process.env.DATABRICKS_SCHEMA || 'ironforge'

function getWarehouseId(): string {
  if (process.env.DATABRICKS_WAREHOUSE_ID) return process.env.DATABRICKS_WAREHOUSE_ID
  // Try extracting from HTTP_PATH: /sql/1.0/warehouses/{id}
  const httpPath = process.env.DATABRICKS_HTTP_PATH || ''
  const match = httpPath.match(/warehouses\/(.+)$/)
  if (match) return match[1]
  throw new Error('Set DATABRICKS_WAREHOUSE_ID or DATABRICKS_HTTP_PATH')
}

/** Fully qualified table name: catalog.schema.table */
export function t(name: string): string {
  return `${CATALOG}.${SCHEMA}.${name}`
}

/** Bot-specific table name: catalog.schema.{bot}_{suffix} */
export function botTable(bot: string, suffix: string): string {
  return t(`${bot}_${suffix}`)
}

interface StatementResponse {
  status: { state: string; error?: { message: string } }
  manifest?: { schema: { columns: Array<{ name: string; type_name: string }> } }
  result?: { data_array: Array<Array<string | null>> }
}

/**
 * Execute a SQL query against Databricks and return rows as objects.
 * All values come back as strings from the REST API — callers cast as needed.
 */
export async function query<T = Record<string, string | null>>(
  sql: string,
): Promise<T[]> {
  if (!HOSTNAME || !TOKEN) {
    throw new Error('Databricks credentials not configured')
  }

  const res = await fetch(
    `https://${HOSTNAME}/api/2.0/sql/statements/`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        warehouse_id: getWarehouseId(),
        statement: sql,
        wait_timeout: '30s',
        catalog: CATALOG,
        schema: SCHEMA,
      }),
      cache: 'no-store',
    },
  )

  if (!res.ok) {
    throw new Error(`Databricks API error: ${res.status} ${res.statusText}`)
  }

  const data: StatementResponse = await res.json()

  if (data.status.state !== 'SUCCEEDED') {
    throw new Error(
      `Query failed (${data.status.state}): ${data.status.error?.message || 'unknown error'}`,
    )
  }

  const columns = data.manifest?.schema.columns.map((c) => c.name) || []
  const rows = data.result?.data_array || []

  return rows.map((row) => {
    const obj: Record<string, string | null> = {}
    columns.forEach((col, i) => {
      obj[col] = row[i] ?? null
    })
    return obj as T
  })
}

/** Parse a string value as a float, defaulting to 0. */
export function num(val: string | null | undefined): number {
  if (val == null || val === '') return 0
  const n = parseFloat(val)
  return isNaN(n) ? 0 : n
}

/** Parse a string value as an int, defaulting to 0. */
export function int(val: string | null | undefined): number {
  if (val == null || val === '') return 0
  const n = parseInt(val, 10)
  return isNaN(n) ? 0 : n
}

/** Validate bot name parameter — flame, spark, or inferno allowed. */
export function validateBot(bot: string): string | null {
  const b = bot.toLowerCase()
  if (b !== 'flame' && b !== 'spark' && b !== 'inferno') return null
  return b
}

/** Get DTE mode string for a bot. */
export function dteMode(bot: string): string {
  if (bot === 'flame') return '2DTE'
  if (bot === 'inferno') return '0DTE'
  return '1DTE'
}

/** Get heartbeat bot name (uppercase). */
export function heartbeatName(bot: string): string {
  return bot.toUpperCase()
}
