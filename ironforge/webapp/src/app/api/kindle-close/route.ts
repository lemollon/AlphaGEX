/**
 * KINDLE production position CLOSE (real money — account 6YB70795).
 *
 * GET  /api/kindle-close              → PREVIEW (read-only): lists the live Tradier
 *                                        option legs on the KINDLE account and the exact
 *                                        market close orders that WOULD be placed. No orders.
 * POST /api/kindle-close?confirm=YES  → EXECUTE: places a market order to flatten each
 *                                        open option leg (buy_to_close shorts / sell_to_close
 *                                        longs). Requires ?confirm=YES. Market hours only.
 *
 * Closes leg-by-leg with market orders — the repo's proven pattern
 * (lib/tradier.closeAllSandboxPositions) — so each leg fills independently rather than
 * risking an all-or-nothing multileg fill. Reads creds from TRADIER_KINDLE_* (prod);
 * never logs the key; account id is masked in responses.
 */
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
const PROD = 'https://api.tradier.com/v1'

function creds(): { key: string; acct: string } | null {
  const key = process.env.TRADIER_KINDLE_API_KEY
  const acct = process.env.TRADIER_KINDLE_ACCOUNT_ID
  return key && acct ? { key, acct } : null
}
function mask(a: string): string {
  return a.length > 4 ? `${a.slice(0, 3)}***${a.slice(-2)}` : '***'
}

async function tradier(
  path: string,
  key: string,
  init?: RequestInit,
): Promise<{ status: number; ok: boolean; body: Record<string, any> | null }> {
  const r = await fetch(`${PROD}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${key}`, Accept: 'application/json', ...(init?.headers || {}) },
    cache: 'no-store',
  })
  let body: Record<string, any> | null = null
  try { body = (await r.json()) as Record<string, any> } catch { body = null }
  return { status: r.status, ok: r.ok, body }
}

interface Leg {
  option_symbol: string
  underlying: string
  quantity: number               // signed: + long, − short
  cost_basis: number
  side: 'buy_to_close' | 'sell_to_close'
  exp: string                    // YYYY-MM-DD
  cp: 'C' | 'P'
}

/** Parse an OCC symbol's trailing YYMMDD+C/P+strike(8). underlying = the rest. */
function parseOcc(sym: string): { underlying: string; exp: string; cp: 'C' | 'P' } {
  const opt = sym.slice(-15)
  const underlying = sym.slice(0, sym.length - 15) || 'SPY'
  const exp = `20${opt.slice(0, 2)}-${opt.slice(2, 4)}-${opt.slice(4, 6)}`
  const cp = (opt[6] === 'P' ? 'P' : 'C') as 'C' | 'P'
  return { underlying, exp, cp }
}

/** Read the live OPTION legs (qty ≠ 0) on the KINDLE account. Equities skipped. */
async function readOpenLegs(key: string, acct: string): Promise<Leg[]> {
  const res = await tradier(`/accounts/${acct}/positions`, key)
  const raw = res.body?.positions
  if (!raw || raw === 'null') return []
  let arr = (raw as { position?: unknown }).position
  if (!arr) return []
  if (!Array.isArray(arr)) arr = [arr]
  const out: Leg[] = []
  for (const p of arr as Array<Record<string, unknown>>) {
    const sym = String(p.symbol || '')
    const qty = Number(p.quantity) || 0
    if (qty === 0) continue
    if (sym.length < 15) continue          // OCC option symbols are ≥15 chars; skip equities
    const { underlying, exp, cp } = parseOcc(sym)
    out.push({
      option_symbol: sym,
      underlying,
      quantity: qty,
      cost_basis: Number(p.cost_basis) || 0,
      side: qty > 0 ? 'sell_to_close' : 'buy_to_close',
      exp,
      cp,
    })
  }
  return out
}

/** Group legs into spreads by (expiration, call/put) — each pair is a vertical that
 *  must be closed as ONE multileg order so the margin nets (avoids the BP wall on a
 *  tight account: leg-by-leg buy_to_close needs cash the spread collateral is holding). */
function groupSpreads(legs: Leg[]): { key: string; legs: Leg[] }[] {
  const m = new Map<string, Leg[]>()
  for (const l of legs) {
    const k = `${l.exp}_${l.cp}`
    if (!m.has(k)) m.set(k, [])
    m.get(k)!.push(l)
  }
  return Array.from(m.entries()).map(([key, ls]) => ({ key, legs: ls }))
}

export async function GET(req: Request): Promise<Response> {
  const c = creds()
  if (!c) return NextResponse.json({ ok: false, error: 'TRADIER_KINDLE_API_KEY / TRADIER_KINDLE_ACCOUNT_ID not set' }, { status: 400 })

  // ?show=orders -> recent order statuses (diagnose stuck/pending/rejected closes).
  if (new URL(req.url).searchParams.get('show') === 'orders') {
    const res = await tradier(`/accounts/${c.acct}/orders`, c.key)
    let arr = (res.body?.orders as { order?: unknown })?.order
    if (!arr) arr = []
    if (!Array.isArray(arr)) arr = [arr]
    return NextResponse.json({
      ok: true, account: mask(c.acct), orders: (arr as Array<Record<string, unknown>>).map((o) => ({
        id: o.id, symbol: o.option_symbol || o.symbol, side: o.side, qty: o.quantity,
        type: o.type, status: o.status, reason: o.reason_description ?? null,
        last_fill_price: o.last_fill_price ?? null, create_date: o.create_date,
      })),
    })
  }

  const legs = await readOpenLegs(c.key, c.acct)
  const spreads = groupSpreads(legs)
  return NextResponse.json({
    ok: true,
    preview: true,
    account: mask(c.acct),
    open_legs: legs.length,
    close_orders: spreads.map((s) => ({
      spread: s.key,
      type: s.legs.length === 2 ? 'multileg (2-leg vertical)' : `single x${s.legs.length}`,
      legs: s.legs.map((l) => `${l.side} ${Math.abs(l.quantity)} ${l.option_symbol}`),
    })),
    note: legs.length
      ? 'POST /api/kindle-close?confirm=YES — closes each vertical as ONE multileg market order (margin nets; no BP wall). Market hours only.'
      : 'No open option legs on the KINDLE account.',
  })
}

export async function POST(req: Request): Promise<Response> {
  const c = creds()
  if (!c) return NextResponse.json({ ok: false, error: 'TRADIER_KINDLE_API_KEY / TRADIER_KINDLE_ACCOUNT_ID not set' }, { status: 400 })
  if (new URL(req.url).searchParams.get('confirm') !== 'YES') {
    return NextResponse.json({ ok: false, error: 'Refused: add ?confirm=YES to place real closing orders.' }, { status: 400 })
  }
  const legs = await readOpenLegs(c.key, c.acct)
  if (!legs.length) return NextResponse.json({ ok: true, executed: true, orders_placed: 0, note: 'No open option legs to close.' })

  const results: Array<Record<string, unknown>> = []
  for (const sp of groupSpreads(legs)) {
    const params = new URLSearchParams({ symbol: sp.legs[0].underlying, type: 'market', duration: 'day' })
    if (sp.legs.length === 2) {
      // Vertical: ONE multileg order — Tradier nets the margin so a tight account can close it.
      params.set('class', 'multileg')
      sp.legs.forEach((l, i) => {
        params.append(`option_symbol[${i}]`, l.option_symbol)
        params.append(`side[${i}]`, l.side)
        params.append(`quantity[${i}]`, String(Math.abs(l.quantity)))
      })
    } else {
      // Unexpected (unpaired) — fall back to a single-leg order for the first leg.
      const l = sp.legs[0]
      params.set('class', 'option')
      params.set('option_symbol', l.option_symbol)
      params.set('side', l.side)
      params.set('quantity', String(Math.abs(l.quantity)))
    }
    const r = await tradier(`/accounts/${c.acct}/orders`, c.key, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params.toString(),
    })
    results.push({
      spread: sp.key,
      class: sp.legs.length === 2 ? 'multileg' : 'option',
      legs: sp.legs.map((l) => `${l.side} ${Math.abs(l.quantity)} ${l.option_symbol}`),
      order_id: r.body?.order?.id ?? null,
      order_status: r.body?.order?.status ?? null,
      error: r.body?.errors?.error ?? (r.ok ? null : `HTTP ${r.status}`),
    })
  }
  return NextResponse.json({
    ok: true,
    executed: true,
    account: mask(c.acct),
    spreads: results.length,
    orders_placed: results.filter((r) => r.order_id).length,
    results,
  })
}
