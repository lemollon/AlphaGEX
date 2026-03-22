/**
 * Lightweight structured logging for IronForge.
 *
 * Replaces ad-hoc console.log with JSON-structured output that includes
 * timestamps, modules, optional request IDs, and arbitrary extra fields.
 * No external dependencies — just wraps console.log/warn/error.
 */

export type LogLevel = 'info' | 'warn' | 'error' | 'debug'

export interface LogEntry {
  ts: string
  level: LogLevel
  msg: string
  module: string
  request_id?: string
  bot?: string
  position_id?: string
  duration_ms?: number
  [key: string]: unknown
}

let _requestId: string | null = null

/** Set a request ID that will be included in all subsequent log entries. */
export function setRequestId(id: string): void {
  _requestId = id
}

/** Clear the current request ID. */
export function clearRequestId(): void {
  _requestId = null
}

/** Get the current request ID (for testing). */
export function getRequestId(): string | null {
  return _requestId
}

/**
 * Emit a structured JSON log entry.
 *
 * @param level  - info | warn | error | debug
 * @param module - source module (e.g. 'scanner', 'tradier', 'api')
 * @param msg    - human-readable message
 * @param extra  - additional key-value pairs merged into the entry
 */
export function log(
  level: LogLevel,
  module: string,
  msg: string,
  extra?: Record<string, unknown>,
): void {
  const entry: LogEntry = {
    ts: new Date().toISOString(),
    level,
    msg,
    module,
    ...(_requestId ? { request_id: _requestId } : {}),
    ...extra,
  }
  const out =
    level === 'error' ? console.error :
    level === 'warn' ? console.warn :
    console.log
  out(JSON.stringify(entry))
}
