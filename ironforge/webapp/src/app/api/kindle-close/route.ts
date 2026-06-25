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
    out.push({
      option_symbol: sym,
      underlying: sym.replace(/\d.*$/, '') || 'SPY',
      quantity: qty,
      cost_basis: Number(p.cost_basis) || 0,
      side: qty > 0 ? 'sell_to_close' : 'buy_to_close',
    })
  }
  return out
}

export async function GET(): Promise<Response> {
  const c = creds()
  if (!c) return NextResponse.json({ ok: false, error: 'TRADIER_KINDLE_API_KEY / TRADIER_KINDLE_ACCOUNT_ID not set' }, { status: 400 })
  const legs = await readOpenLegs(c.key, c.acct)
  return NextResponse.json({
    ok: true,
    preview: true,
    account: mask(c.acct),
    open_legs: legs.length,
    legs: legs.map((l) => ({
      option_symbol: l.option_symbol,
      quantity: l.quantity,
      cost_basis: l.cost_basis,
      close_order: `${l.side} ${Math.abs(l.quantity)} @ market`,
    })),
    note: legs.length
      ? 'POST /api/kindle-close?confirm=YES to place these market close orders (market hours only).'
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
  for (const l of legs) {
    const params = new URLSearchParams({
      class: 'option',
      symbol: l.underlying,
      option_symbol: l.option_symbol,
      side: l.side,
      quantity: String(Math.abs(l.quantity)),
      type: 'market',
      duration: 'day',
    })
    const r = await tradier(`/accounts/${c.acct}/orders`, c.key, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params.toString(),
    })
    results.push({
      option_symbol: l.option_symbol,
      side: l.side,
      quantity: Math.abs(l.quantity),
      order_id: r.body?.order?.id ?? null,
      order_status: r.body?.order?.status ?? null,
      error: r.body?.errors?.error ?? (r.ok ? null : `HTTP ${r.status}`),
    })
  }
  return NextResponse.json({
    ok: true,
    executed: true,
    account: mask(c.acct),
    legs: legs.length,
    orders_placed: results.filter((r) => r.order_id).length,
    results,
  })
}
