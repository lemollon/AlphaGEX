import { NextRequest, NextResponse } from 'next/server'
import { validateBot, dteMode } from '@/lib/db'
import {
  getQuote,
  getPutSpreadEntryCredit,
  buildOccSymbol,
  buildLegs,
  isTwoLegSpread,
  placeIcOrderAllAccounts,
  canPlaceLiveOrders,
  describeLiveGate,
  isConfigured,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * Show the EXACT order body FLAME/SPARK would send, and optionally place it on
 * SANDBOX ONLY.
 *
 * Why this exists: the live order path was tested at the unit level (leg map,
 * gates) but the body had never been sent to a real Tradier endpoint. force-trade
 * could not answer that — it builds a 4-leg CONDOR at 2DTE, the retired
 * structure, so firing it would exercise the wrong path and leave a misleading
 * position row behind.
 *
 *   GET                    dry run. Builds strikes, credit and the JSON body.
 *                          Places NOTHING. Safe with the market closed.
 *   POST ?place=sandbox    actually places, on SANDBOX accounts only.
 *
 * 🚨 PRODUCTION IS UNREACHABLE FROM HERE, BY CONSTRUCTION. The placement call
 * passes { sandboxOnly: true } and this route never passes productionOnly. This
 * is a proving tool; arming real money goes through the scanner and its gates.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  return build(req, params.bot, false)
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const place = req.nextUrl.searchParams.get('place') === 'sandbox'
  return build(req, params.bot, place)
}

async function build(req: NextRequest, botParam: string, place: boolean) {
  const bot = validateBot(botParam)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'flame' && bot !== 'spark') {
    return NextResponse.json({ error: 'preview-order covers the EBB bots only (flame, spark)' }, { status: 400 })
  }
  if (!isConfigured()) {
    return NextResponse.json({ error: 'tradier_not_configured' }, { status: 503 })
  }

  const ticker = 'SPY'
  const OTM = 1      // short at spot - $1
  const WIDTH = 2    // $2 wing

  const q = await getQuote(ticker)
  const spot = q?.last ?? 0
  if (!(spot > 0)) return NextResponse.json({ error: 'no_spot_quote' }, { status: 503 })

  // 0DTE — today, in Central Time (the session the bot would trade).
  const ct = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const expiration = ct.toISOString().slice(0, 10)

  const putShort = Math.round(spot - OTM)
  const putLong = putShort - WIDTH
  const callShort = 0
  const callLong = 0
  const twoLeg = isTwoLegSpread(callShort, callLong)

  const occPs = buildOccSymbol(ticker, expiration, putShort, 'P')
  const occPl = buildOccSymbol(ticker, expiration, putLong, 'P')

  let credit: number | null = null
  let creditError: string | null = null
  try {
    const c = await getPutSpreadEntryCredit(ticker, expiration, putShort, putLong)
    credit = c ? c.putCredit : null
    if (!c) creditError = 'no_quotes — expected when the market is closed'
  } catch (e) {
    creditError = e instanceof Error ? e.message : String(e)
  }

  const orderBody = {
    class: 'multileg',
    symbol: ticker,
    type: 'market',
    duration: 'day',
    ...buildLegs(occPs, occPl, '', '', 1, { shortSide: 'sell_to_open', longSide: 'buy_to_open' }, twoLeg),
  }

  const payload: Record<string, unknown> = {
    bot,
    dte_mode: dteMode(bot),
    structure: 'SPY 0DTE put credit spread',
    spot,
    expiration,
    strikes: { put_short: putShort, put_long: putLong, wing: WIDTH },
    legs: twoLeg ? 2 : 4,
    occ: { short: occPs, long: occPl },
    modelled_credit: credit,
    credit_error: creditError,
    max_loss_per_contract: credit != null ? Math.round((WIDTH - credit) * 100 * 100) / 100 : null,
    order_body: orderBody,
    live_orders_allowed: canPlaceLiveOrders(bot),
    // 🚨 THE LINE ABOVE IS ABOUT *THIS* PROCESS, NOT ABOUT THE BOT.
    // Arming is per-service env, and only the service with SCANNER_ENABLED ever
    // places an order. On 2026-08-19 this endpoint answered `true` on the
    // operator console — which logs "[scanner] not started" every boot — while
    // the scanning service had no FLAME creds and traded paper only. Read
    // `live_orders_allowed` together with `scanner_process`: false here means
    // the answer describes a process that cannot trade.
    scanner_process: process.env.SCANNER_ENABLED === 'true',
    live_gate: describeLiveGate(bot),
    placed: false,
  }

  if (!place) return NextResponse.json(payload)

  try {
    const res = await placeIcOrderAllAccounts(
      ticker, expiration,
      putShort, putLong, callShort, callLong,
      1, credit ?? 0.10,
      `preview-${Date.now()}`, bot,
      { sandboxOnly: true },   // production is unreachable from this route
    )
    payload.placed = true
    payload.result = res
    payload.accounts_hit = Object.keys(res)
  } catch (e) {
    payload.placed = false
    payload.place_error = e instanceof Error ? e.message : String(e)
  }
  return NextResponse.json(payload)
}
