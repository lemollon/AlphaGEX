/**
 * FLAME put-credit-spread preview (read-only — validates strategy math
 * before PR 2 flips FLAME's scanner to actually trade this way).
 *
 * GET /api/flame/preview-put-spread
 *
 * Shows exactly what FLAME would trade RIGHT NOW under the new tasty-adapted
 * put-credit-spread rules:
 *   - Short put at ~1.0 SD OTM (16-delta proxy), $5 wing → put credit spread
 *   - VIX > 18 gate (IV rank proxy)
 *   - Min credit $1.50 (30% of $5 width)
 *   - Size for 10% of Tradier User sandbox balance at risk
 *   - 50% profit target, 200% stop loss
 *
 * Read-only. Zero writes. Zero scanner changes. Call this anytime to
 * validate the math before we wire it into the scanner in PR 2.
 *
 * Scoped to FLAME — SPARK/INFERNO return 403.
 */
import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import {
  getQuote,
  getBatchOptionQuotes,
  buildOccSymbol,
  getOptionExpirations,
  getLoadedSandboxAccountsAsync,
  getAccountIdForKey,
  getTradierBalanceDetail,
  isConfigured,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const SUPPORTED_BOTS = new Set(['flame'])

// Strategy parameters — kept in one place so we can tune without touching
// wiring. These match the rules approved in the chat spec.
const SD_MULT = 1.0           // 16-delta proxy (short put 1.0 SD OTM)
const SPREAD_WIDTH = 5
const MIN_CREDIT = 1.50       // 30% of $5 wing — tasty's R:R floor
const VIX_GATE = 18           // IV rank proxy — no trade when VIX <= this
const RISK_PCT = 0.10         // 10% of account at risk per trade
const PROFIT_TARGET_PCT = 0.50  // close at 50% of credit
const STOP_LOSS_MULT = 2.0    // close at 2x credit
const MIN_DTE = 2             // FLAME = 2DTE

interface Gate {
  required: string
  actual: number | string
  pass: boolean
}

/**
 * Compute the 2DTE-forward target expiration in YYYY-MM-DD, skipping weekends.
 * Inlined here so this endpoint has no dependency on scanner.ts internals.
 */
function getTargetExpiration(minDte: number): string {
  const ctNow = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const target = new Date(ctNow)
  let counted = 0
  while (counted < minDte) {
    target.setDate(target.getDate() + 1)
    const dow = target.getDay()
    if (dow !== 0 && dow !== 6) counted++
  }
  const y = target.getFullYear()
  const m = String(target.getMonth() + 1).padStart(2, '0')
  const d = String(target.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (!SUPPORTED_BOTS.has(bot)) {
    return NextResponse.json(
      { error: `preview-put-spread is only enabled for: ${Array.from(SUPPORTED_BOTS).join(', ')}` },
      { status: 403 },
    )
  }

  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured — cannot preview' }, { status: 503 })
  }

  try {
    // 1. Account balance (Tradier User sandbox — same source the status API uses)
    let accountBalance: number | null = null
    let accountSource: 'tradier' | 'unavailable' = 'unavailable'
    let accountError: string | null = null
    try {
      const accts = await getLoadedSandboxAccountsAsync()
      const userAcct = accts.find((a) => a.name === 'User' && a.type === 'sandbox')
      if (userAcct) {
        const accountId = await getAccountIdForKey(userAcct.apiKey, userAcct.baseUrl)
        if (accountId) {
          const bal = await getTradierBalanceDetail(userAcct.apiKey, accountId, userAcct.baseUrl)
          if (bal?.total_equity != null) {
            accountBalance = bal.total_equity
            accountSource = 'tradier'
          } else {
            accountError = 'no_total_equity'
          }
        } else {
          accountError = 'no_account_id'
        }
      } else {
        accountError = 'no_user_sandbox_account'
      }
    } catch (err: unknown) {
      accountError = err instanceof Error ? err.message : String(err)
    }

    // 2. Market quotes
    const [spyQuote, vixQuote, expirations] = await Promise.all([
      getQuote('SPY'),
      getQuote('VIX'),
      getOptionExpirations('SPY').catch(() => [] as string[]),
    ])

    const spot = spyQuote?.last ?? null
    const vix = vixQuote?.last ?? null

    if (spot == null || vix == null) {
      return NextResponse.json({
        error: 'SPY or VIX quote unavailable — cannot preview',
        spy: spot,
        vix,
      }, { status: 503 })
    }

    // 3. Expected move = spot * VIX% / sqrt(trading_days_per_year)
    const expectedMove = (vix / 100 / Math.sqrt(252)) * spot

    // 4. Target expiration — nearest weekday 2 business days out
    const desiredExp = getTargetExpiration(MIN_DTE)
    const expiration = expirations.includes(desiredExp)
      ? desiredExp
      : (expirations.find((e) => e >= desiredExp) || desiredExp)

    // 5. Strikes: 1.0 SD OTM short put, $5 wing below
    const minEM = spot * 0.005
    const em = Math.max(expectedMove, minEM)
    const putShort = Math.floor(spot - SD_MULT * em)
    const putLong = putShort - SPREAD_WIDTH

    // 6. Put credit — fetch just the 2 put legs (not IC's 4 legs).
    //    Conservative paper fill: sell put_short at bid, buy put_long at ask.
    //    Mid-price fallback if bid/ask gives a non-positive credit (wide quotes,
    //    premarket, etc.).
    const occPs = buildOccSymbol('SPY', expiration, putShort, 'P')
    const occPl = buildOccSymbol('SPY', expiration, putLong, 'P')
    const legQuotes = await getBatchOptionQuotes([occPs, occPl])
    const psQ = legQuotes[occPs]
    const plQ = legQuotes[occPl]

    let putCredit = 0
    let creditSource: 'TRADIER_BIDASK' | 'TRADIER_MID' | 'unavailable' = 'unavailable'
    if (psQ && plQ) {
      const bidAsk = psQ.bid - plQ.ask
      if (bidAsk > 0) {
        putCredit = bidAsk
        creditSource = 'TRADIER_BIDASK'
      } else {
        const psMid = (psQ.bid + psQ.ask) / 2
        const plMid = (plQ.bid + plQ.ask) / 2
        const mid = psMid - plMid
        if (mid > 0) {
          putCredit = mid
          creditSource = 'TRADIER_MID'
        }
      }
    }

    // 7. Sizing at 10% of account
    const maxLossPerContract = Math.round((SPREAD_WIDTH - putCredit) * 100 * 100) / 100
    const contracts = accountBalance != null && maxLossPerContract > 0
      ? Math.floor((accountBalance * RISK_PCT) / maxLossPerContract)
      : 0
    const totalRisk = Math.round(contracts * maxLossPerContract * 100) / 100
    const maxProfitTotal = Math.round(contracts * putCredit * 100 * 100) / 100

    // 8. Exit targets
    const ptCostToClose = Math.round(putCredit * (1 - PROFIT_TARGET_PCT) * 10000) / 10000
    const ptPnlDollar = Math.round(contracts * (putCredit - ptCostToClose) * 100 * 100) / 100
    const slCostToClose = Math.round(putCredit * STOP_LOSS_MULT * 10000) / 10000
    const slPnlDollar = Math.round(contracts * (putCredit - slCostToClose) * 100 * 100) / 100  // negative

    // 9. Gates
    const vixGate: Gate = {
      required: `>${VIX_GATE}`,
      actual: Math.round(vix * 100) / 100,
      pass: vix > VIX_GATE,
    }
    const creditGate: Gate = {
      required: `>=$${MIN_CREDIT.toFixed(2)}`,
      actual: Math.round(putCredit * 10000) / 10000,
      pass: putCredit >= MIN_CREDIT,
    }
    const accountGate: Gate = {
      required: 'Tradier User sandbox balance available',
      actual: accountSource,
      pass: accountBalance != null && contracts > 0,
    }

    const gates = { vix: vixGate, credit: creditGate, account: accountGate }
    const allPass = vixGate.pass && creditGate.pass && accountGate.pass
    const goNoGo = allPass ? 'READY' : 'BLOCKED'
    const reasonsBlocked: string[] = []
    if (!vixGate.pass) reasonsBlocked.push(`VIX ${vixGate.actual} <= ${VIX_GATE} (IV too low)`)
    if (!creditGate.pass) reasonsBlocked.push(`Put credit $${creditGate.actual} < $${MIN_CREDIT} (premium too thin)`)
    if (!accountGate.pass) reasonsBlocked.push(
      accountBalance == null
        ? `Cannot read Tradier balance (${accountError ?? 'unknown'})`
        : `Sizing produced 0 contracts (balance $${accountBalance}, max-loss/contract $${maxLossPerContract})`,
    )

    return NextResponse.json({
      preview_time: new Date().toISOString(),
      bot: 'flame',
      strategy: 'put_credit_spread_2dte',
      account: {
        balance: accountBalance,
        source: accountSource,
        error: accountError,
      },
      market: {
        spy: Math.round(spot * 100) / 100,
        vix: Math.round(vix * 100) / 100,
        expected_move: Math.round(expectedMove * 100) / 100,
        expected_move_pct: Math.round((expectedMove / spot) * 10000) / 100,
      },
      expiration,
      strikes: {
        put_long: putLong,
        put_short: putShort,
        short_distance_dollars: Math.round((spot - putShort) * 100) / 100,
        short_distance_sd: Math.round(((spot - putShort) / em) * 100) / 100,
      },
      credit: {
        per_contract: Math.round(putCredit * 10000) / 10000,
        source: creditSource,
        raw_legs: {
          put_short: psQ ? { bid: psQ.bid, ask: psQ.ask } : null,
          put_long: plQ ? { bid: plQ.bid, ask: plQ.ask } : null,
        },
      },
      sizing: {
        risk_pct: RISK_PCT,
        max_loss_per_contract: maxLossPerContract,
        contracts,
        total_risk_dollar: totalRisk,
        max_profit_total_dollar: maxProfitTotal,
      },
      exits: {
        profit_target: {
          pct_of_credit: PROFIT_TARGET_PCT,
          cost_to_close: ptCostToClose,
          pnl_dollar: ptPnlDollar,
        },
        stop_loss: {
          multiplier_of_credit: STOP_LOSS_MULT,
          cost_to_close: slCostToClose,
          pnl_dollar: slPnlDollar,
        },
      },
      gates,
      go_no_go: goNoGo,
      reasons_blocked: reasonsBlocked,
      note: 'Read-only preview. No scanner changes. No writes. Validates ' +
            'the put-credit-spread strategy math against live Tradier data. ' +
            'Flip FLAME to actually trade this way in a follow-up PR.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
