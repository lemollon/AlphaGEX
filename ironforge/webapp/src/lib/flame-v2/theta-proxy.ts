/**
 * Read-only client for the private `thetadata-proxy` Render service
 * (spreadworks/thetadata_proxy/app.py). Supplies the two live inputs CALM
 * and LONGG need that are not already in IronForge's own Postgres:
 *   - VIX 1-minute index history (CALM's 120-minute pre-entry window)
 *   - SPY option open-interest + implied-volatility snapshots (LONGG's igex_net)
 *
 * FAIL-CLOSED BY CONSTRUCTION: every function here returns `{ ok: false,
 * reason }` on ANY problem — missing base URL, network error, non-200,
 * empty/unparseable CSV, non-finite numbers. Never a guess, never a stale
 * fallback. Callers (engine.ts) treat `ok:false` exactly like "missing
 * input" per the build spec: behave exactly as today.
 *
 * Base URL: `THETADATA_BASE_URL`, same env var name alphagex-api already
 * uses (render.yaml) for this same private service — set manually in the
 * Render dashboard on the ironforge-customer service; this module never
 * writes it. If unset, every call below returns `theta_proxy_unconfigured`
 * immediately (no network call attempted).
 *
 * Endpoint shapes mirror spreadworks/thetadata_proxy/app.py exactly
 * (`/v3/index/history/ohlc`, `/v3/option/snapshot/open_interest`,
 * `/v3/option/snapshot/greeks/implied_volatility`, `/v3/index/snapshot/price`,
 * `/v3/stock/snapshot/ohlc`). Unlike live_igex.py (which had no snapshot
 * access and had to invert IV from quote mids), this proxy's
 * implied_volatility snapshot endpoint gives IV directly — gamma is still
 * computed locally via igexFormulaNet because /greeks/all is unavailable on
 * the STANDARD ThetaData tier (per the proxy's own doc comment).
 */

export type ProxyResult<T> = { ok: true; data: T } | { ok: false; reason: string }

const DEFAULT_TIMEOUT_MS = 8000

function baseUrl(): string | null {
  const raw = (process.env.THETADATA_BASE_URL ?? '').trim()
  return raw.length > 0 ? raw.replace(/\/+$/, '') : null
}

async function getCsv(path: string, params: Record<string, string>, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<ProxyResult<string>> {
  const base = baseUrl()
  if (!base) return { ok: false, reason: 'theta_proxy_unconfigured(THETADATA_BASE_URL unset)' }
  const url = `${base}${path}?${new URLSearchParams(params).toString()}`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, { signal: controller.signal, headers: { Accept: 'text/csv' } })
    if (!res.ok) return { ok: false, reason: `theta_proxy_http_${res.status}` }
    const text = await res.text()
    if (!text || !text.trim()) return { ok: false, reason: 'theta_proxy_empty_response' }
    return { ok: true, data: text }
  } catch (e) {
    return { ok: false, reason: `theta_proxy_request_failed(${e instanceof Error ? e.message.slice(0, 80) : 'error'})` }
  } finally {
    clearTimeout(timer)
  }
}

/** Minimal RFC4180-ish CSV parser: no quoted-comma support needed since the
 *  proxy's own `_csv()` writes plain pandas `to_csv`, which never quotes
 *  these numeric/date columns. */
function parseCsv(text: string): Array<Record<string, string>> {
  const lines = text.trim().split(/\r?\n/)
  if (lines.length < 2) return []
  const header = lines[0].split(',').map((h) => h.trim())
  const rows: Array<Record<string, string>> = []
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue
    const cells = lines[i].split(',')
    const row: Record<string, string> = {}
    header.forEach((h, idx) => { row[h] = (cells[idx] ?? '').trim() })
    rows.push(row)
  }
  return rows
}

function toNum(v: string | undefined): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : NaN
}

/**
 * VIX 1-minute closes for [entry-120min, entry-1min] on `dateStr`
 * (YYYY-MM-DD), chronologically ordered. `entryHHMMSS` is the ET clock time
 * of the bot's entry minute (e.g. '14:05:00' FLAME, '11:05:00' SPARK).
 */
export async function fetchVixMinuteWindow(dateStr: string, entryHHMMSS: string): Promise<ProxyResult<number[]>> {
  const [h, m, s] = entryHHMMSS.split(':').map(Number)
  const entryMin = h * 60 + m
  const startMin = entryMin - 120
  if (startMin < 0) return { ok: false, reason: 'calm_window_before_session_open' }
  const startHHMMSS = `${String(Math.floor(startMin / 60)).padStart(2, '0')}:${String(startMin % 60).padStart(2, '0')}:00`
  const endMin = entryMin - 1
  const endHHMMSS = `${String(Math.floor(endMin / 60)).padStart(2, '0')}:${String(endMin % 60).padStart(2, '0')}:${String(s ?? 0).padStart(2, '0')}`
  const res = await getCsv('/v3/index/history/ohlc', {
    symbol: 'VIX', date: dateStr, interval: '1m', start_time: startHHMMSS, end_time: endHHMMSS,
  })
  if (!res.ok) return res
  const rows = parseCsv(res.data)
  const closeCol = rows.length > 0 && 'close' in rows[0] ? 'close' : Object.keys(rows[0] ?? {}).find((k) => /close/i.test(k))
  if (!closeCol) return { ok: false, reason: 'calm_no_close_column' }
  const closes = rows.map((r) => toNum(r[closeCol])).filter((v) => Number.isFinite(v))
  if (closes.length < 5) return { ok: false, reason: `calm_insufficient_bars(${closes.length})` }
  return { ok: true, data: closes }
}

export type LiveGexChain = {
  spot: number
  rows: Array<{ strike: number; iv: number; callOi: number; putOi: number; dteCalendarDays: number }>
}

/**
 * Live SPY option chain (dte 0..60) for igex_net: open-interest + IV
 * snapshots, joined by (expiration, strike), plus live SPY spot. Any one of
 * the three sub-calls failing fails the whole thing closed (no partial-chain
 * igex_net — a thin chain silently understates risk in exactly the way the
 * build spec's "fail closed, never a guess" rule forbids).
 */
export async function fetchLiveGexChain(symbol = 'SPY', maxDte = 60): Promise<ProxyResult<LiveGexChain>> {
  const [spotRes, oiRes, ivRes] = await Promise.all([
    getCsv('/v3/stock/snapshot/ohlc', { symbol }),
    getCsv('/v3/option/snapshot/open_interest', { symbol, expiration: '*', max_dte: String(maxDte) }),
    getCsv('/v3/option/snapshot/greeks/implied_volatility', { symbol, expiration: '*', max_dte: String(maxDte) }),
  ])
  if (!spotRes.ok) return spotRes
  if (!oiRes.ok) return oiRes
  if (!ivRes.ok) return ivRes

  const spotRows = parseCsv(spotRes.data)
  const closeCol = Object.keys(spotRows[0] ?? {}).find((k) => /close|last|price/i.test(k))
  const spot = closeCol ? toNum(spotRows[0]?.[closeCol]) : NaN
  if (!Number.isFinite(spot) || spot <= 0) return { ok: false, reason: 'gex_no_live_spot' }

  const oiRows = parseCsv(oiRes.data)
  const ivRows = parseCsv(ivRes.data)
  if (oiRows.length === 0 || ivRows.length === 0) return { ok: false, reason: 'gex_empty_chain' }

  const key = (r: Record<string, string>) => `${r.expiration ?? r.exp ?? ''}|${r.strike ?? ''}|${(r.right ?? r.option_right ?? '').toUpperCase().slice(0, 1)}`
  const ivByKey = new Map<string, number>()
  for (const r of ivRows) {
    const iv = toNum(r.implied_volatility ?? r.iv)
    if (Number.isFinite(iv)) ivByKey.set(key(r), iv)
  }

  const byStrikeExp = new Map<string, { strike: number; expiration: string; iv: number; callOi: number; putOi: number }>()
  for (const r of oiRows) {
    const strike = toNum(r.strike)
    const expiration = r.expiration ?? r.exp ?? ''
    const right = (r.right ?? r.option_right ?? '').toUpperCase().slice(0, 1)
    const oi = toNum(r.open_interest ?? r.oi)
    if (!Number.isFinite(strike) || !expiration || !Number.isFinite(oi)) continue
    const iv = ivByKey.get(key(r))
    if (!Number.isFinite(iv)) continue
    const mapKey = `${expiration}|${strike}`
    const existing = byStrikeExp.get(mapKey) ?? { strike, expiration, iv: iv as number, callOi: 0, putOi: 0 }
    if (right === 'C') existing.callOi = oi
    else if (right === 'P') existing.putOi = oi
    existing.iv = iv as number
    byStrikeExp.set(mapKey, existing)
  }
  if (byStrikeExp.size === 0) return { ok: false, reason: 'gex_no_matched_strikes' }

  const today = new Date()
  const rows = Array.from(byStrikeExp.values())
    .filter((r) => r.callOi > 0 || r.putOi > 0)
    .map((r) => {
      const expDate = new Date(`${r.expiration.length === 8 ? `${r.expiration.slice(0, 4)}-${r.expiration.slice(4, 6)}-${r.expiration.slice(6, 8)}` : r.expiration}T00:00:00Z`)
      const dteCalendarDays = Math.max(0, Math.round((expDate.getTime() - today.getTime()) / 86400000))
      return { strike: r.strike, iv: r.iv, callOi: r.callOi, putOi: r.putOi, dteCalendarDays }
    })
  if (rows.length === 0) return { ok: false, reason: 'gex_no_usable_rows' }
  return { ok: true, data: { spot, rows } }
}
