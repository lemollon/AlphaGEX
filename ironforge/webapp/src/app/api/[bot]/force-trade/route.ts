import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, validateBot } from '@/lib/db'
import {
  getQuote,
  getOptionExpirations,
  getIcEntryCredit,
  isConfigured,
  placeIcOrderAllAccounts,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/* ------------------------------------------------------------------ */
/*  Lightweight advisor — mirrors Python advisor.py rules              */
/* ------------------------------------------------------------------ */

function evaluateAdvisor(vix: number, spot: number, expectedMove: number, dteMode: string) {
  const BASE_WP = 0.65
  let winProb = BASE_WP
  const factors: [string, number][] = []

  // VIX scoring
  if (vix >= 15 && vix <= 22) { const a = 0.10; winProb += a; factors.push(['VIX_IDEAL', a]) }
  else if (vix < 15) { const a = -0.05; winProb += a; factors.push(['VIX_LOW_PREMIUMS', a]) }
  else if (vix <= 28) { const a = -0.05; winProb += a; factors.push(['VIX_ELEVATED', a]) }
  else { const a = -0.15; winProb += a; factors.push(['VIX_HIGH_RISK', a]) }

  // Day of week (0=Sun, 6=Sat in JS)
  const dow = new Date().getDay()
  if (dow >= 2 && dow <= 4) { const a = 0.08; winProb += a; factors.push(['DAY_OPTIMAL', a]) }
  else if (dow === 1) { const a = 0.03; winProb += a; factors.push(['DAY_MONDAY', a]) }
  else if (dow === 5) { const a = -0.10; winProb += a; factors.push(['DAY_FRIDAY_RISK', a]) }
  else { const a = -0.20; winProb += a; factors.push(['DAY_WEEKEND', a]) }

  // Expected move ratio
  const emRatio = spot > 0 ? (expectedMove / spot * 100) : 1.0
  if (emRatio < 1.0) { const a = 0.08; winProb += a; factors.push(['EM_TIGHT', a]) }
  else if (emRatio <= 2.0) { factors.push(['EM_NORMAL', 0]) }
  else { const a = -0.08; winProb += a; factors.push(['EM_WIDE', a]) }

  // DTE factor
  if (dteMode === '2DTE') { const a = 0.03; winProb += a; factors.push(['DTE_2DAY_DECAY', a]) }
  else { const a = -0.02; winProb += a; factors.push(['DTE_1DAY_TIGHT', a]) }

  winProb = Math.max(0.10, Math.min(0.95, winProb))

  const pos = factors.filter(([, a]) => a > 0).length
  const neg = factors.filter(([, a]) => a < 0).length
  let confidence = pos === factors.length ? 0.85
    : neg === factors.length ? 0.25
    : pos > neg ? 0.60 + (pos / factors.length) * 0.20
    : 0.40
  confidence = Math.max(0.10, Math.min(0.95, confidence))

  const advice = winProb >= 0.60 && confidence >= 0.50 ? 'TRADE_FULL'
    : winProb >= 0.42 && confidence >= 0.35 ? 'TRADE_REDUCED'
    : 'SKIP'

  return {
    advice,
    winProbability: Math.round(winProb * 10000) / 10000,
    confidence: Math.round(confidence * 10000) / 10000,
    topFactors: factors,
    reasoning: `Advisor: ${advice} WP=${winProb.toFixed(2)} conf=${confidence.toFixed(2)}`,
  }
}

/* ------------------------------------------------------------------ */
/*  Strike calculation — mirrors Python signals.py exactly             */
/* ------------------------------------------------------------------ */

function calculateStrikes(spot: number, expectedMove: number) {
  const SD = 1.2 // sd_multiplier
  const WIDTH = 5 // spread_width

  const minEM = spot * 0.005
  const em = Math.max(expectedMove, minEM)

  let putShort = Math.floor(spot - SD * em)
  let callShort = Math.ceil(spot + SD * em)
  let putLong = putShort - WIDTH
  let callLong = callShort + WIDTH

  // Sanity guard
  if (callShort <= putShort) {
    putShort = Math.floor(spot - spot * 0.02)
    callShort = Math.ceil(spot + spot * 0.02)
    putLong = putShort - WIDTH
    callLong = callShort + WIDTH
  }

  return { putShort, putLong, callShort, callLong }
}

/** Find target expiration N trading days out. */
function getTargetExpiration(minDte: number): string {
  const now = new Date()
  let target = new Date(now)
  let counted = 0
  while (counted < minDte) {
    target.setDate(target.getDate() + 1)
    const dow = target.getDay()
    if (dow !== 0 && dow !== 6) counted++
  }
  return target.toISOString().slice(0, 10)
}

/* ------------------------------------------------------------------ */
/*  POST /api/[bot]/force-trade                                        */
/* ------------------------------------------------------------------ */

export async function POST(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  if (!isConfigured()) {
    return NextResponse.json(
      { error: 'TRADIER_API_KEY not configured' },
      { status: 500 },
    )
  }

  const dte = bot === 'flame' ? '2DTE' : '1DTE'
  const minDte = bot === 'flame' ? 2 : 1
  const botName = bot.toUpperCase()

  try {
    // 1. Check for existing open position
    const openRows = await query(
      `SELECT position_id FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = $1 LIMIT 1`,
      [dte],
    )
    if (openRows.length > 0) {
      return NextResponse.json(
        { error: `${botName} already has an open position: ${openRows[0].position_id}` },
        { status: 409 },
      )
    }

    // 2. Get market data
    const [spyQuote, vixQuote] = await Promise.all([
      getQuote('SPY'),
      getQuote('VIX'),
    ])

    if (!spyQuote) {
      return NextResponse.json(
        { error: 'Could not get SPY quote from Tradier' },
        { status: 502 },
      )
    }

    const spot = spyQuote.last
    const vix = vixQuote?.last ?? 20
    const expectedMove = (vix / 100 / Math.sqrt(252)) * spot

    // 3. VIX filter (skip if VIX > 32)
    if (vix > 32) {
      return NextResponse.json(
        { error: `VIX ${vix.toFixed(1)} too high (>32), skipping` },
        { status: 422 },
      )
    }

    // 4. Get target expiration
    const targetExp = getTargetExpiration(minDte)
    const expirations = await getOptionExpirations('SPY')

    let expiration = targetExp
    if (expirations.length > 0 && !expirations.includes(targetExp)) {
      // Find nearest valid expiration
      const targetDate = new Date(targetExp + 'T12:00:00').getTime()
      let nearest = expirations[0]
      let minDiff = Infinity
      for (const exp of expirations) {
        const diff = Math.abs(new Date(exp + 'T12:00:00').getTime() - targetDate)
        if (diff < minDiff) {
          minDiff = diff
          nearest = exp
        }
      }
      expiration = nearest
    }

    // 5. Calculate strikes
    const strikes = calculateStrikes(spot, expectedMove)

    // 6. Get real option credits from Tradier
    const credits = await getIcEntryCredit(
      'SPY',
      expiration,
      strikes.putShort,
      strikes.putLong,
      strikes.callShort,
      strikes.callLong,
    )

    if (!credits || credits.totalCredit < 0.05) {
      return NextResponse.json(
        {
          error: `Credit too low: $${credits?.totalCredit?.toFixed(4) ?? '0'} (min $0.05)`,
          strikes,
          expiration,
        },
        { status: 422 },
      )
    }

    // 7. Get paper account and calculate sizing
    const accountRows = await query(
      `SELECT id, current_balance, buying_power FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE AND dte_mode = $1 ORDER BY id DESC LIMIT 1`,
      [dte],
    )
    if (accountRows.length === 0) {
      return NextResponse.json(
        { error: 'No paper account found' },
        { status: 500 },
      )
    }

    const acct = accountRows[0]
    const buyingPower = num(acct.buying_power)
    const spreadWidth = strikes.putShort - strikes.putLong
    const collateralPer = Math.max(0, (spreadWidth - credits.totalCredit) * 100)
    const usableBP = buyingPower * 0.85
    const maxContracts = Math.min(10, Math.max(1, Math.floor(usableBP / collateralPer)))

    if (buyingPower < 200 || collateralPer <= 0) {
      return NextResponse.json(
        { error: `Insufficient buying power: $${buyingPower.toFixed(2)}` },
        { status: 422 },
      )
    }

    const totalCollateral = collateralPer * maxContracts
    const maxProfit = credits.totalCredit * 100 * maxContracts
    const maxLoss = totalCollateral

    // 8. Run advisor for oracle fields
    const adv = evaluateAdvisor(vix, spot, expectedMove, dte)

    // 9. Generate position ID
    const now = new Date()
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '')
    const hex = Math.random().toString(16).slice(2, 8).toUpperCase()
    const positionId = `${botName}-${dateStr}-${hex}`

    // 10. Insert position
    await query(
      `INSERT INTO ${botTable(bot, 'positions')} (
        position_id, ticker, expiration,
        put_short_strike, put_long_strike, put_credit,
        call_short_strike, call_long_strike, call_credit,
        contracts, spread_width, total_credit, max_loss, max_profit,
        collateral_required,
        underlying_at_entry, vix_at_entry, expected_move,
        call_wall, put_wall, gex_regime,
        flip_point, net_gex,
        oracle_confidence, oracle_win_probability, oracle_advice,
        oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
        wings_adjusted, original_put_width, original_call_width,
        put_order_id, call_order_id,
        status, open_time, open_date, dte_mode
      ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
        $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
        $31, $32, $33, $34, $35, NOW(), CURRENT_DATE, $36
      )`,
      [
        positionId, 'SPY', expiration,
        strikes.putShort, strikes.putLong, credits.putCredit,
        strikes.callShort, strikes.callLong, credits.callCredit,
        maxContracts, spreadWidth, credits.totalCredit, maxLoss, maxProfit,
        totalCollateral,
        spot, vix, expectedMove,
        0, 0, 'UNKNOWN',
        0, 0,
        adv.confidence, adv.winProbability, adv.advice,
        adv.reasoning, JSON.stringify(adv.topFactors), false,
        false, spreadWidth, spreadWidth,
        'PAPER', 'PAPER',
        'open', dte,
      ],
    )

    // 10b. Mirror to all 3 Tradier sandbox accounts (both FLAME and SPARK)
    let sandboxOrderIds: Record<string, number> = {}
    try {
      sandboxOrderIds = await placeIcOrderAllAccounts(
        'SPY', expiration,
        strikes.putShort, strikes.putLong,
        strikes.callShort, strikes.callLong,
        maxContracts, credits.totalCredit,
        positionId,
      )
      if (Object.keys(sandboxOrderIds).length > 0) {
        await query(
          `UPDATE ${botTable(bot, 'positions')}
           SET sandbox_order_id = $1, updated_at = NOW()
           WHERE position_id = $2`,
          [JSON.stringify(sandboxOrderIds), positionId],
        )
      }
    } catch (sbErr: any) {
      // Sandbox mirror is non-fatal — paper trade still succeeds
      console.warn(`Sandbox mirror failed for ${positionId}: ${sbErr.message}`)
    }

    // 11. Update paper account (deduct collateral)
    await query(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET collateral_in_use = collateral_in_use + $1,
           buying_power = buying_power - $1,
           updated_at = NOW()
       WHERE id = $2`,
      [totalCollateral, acct.id],
    )

    // 12. Log the signal
    await query(
      `INSERT INTO ${botTable(bot, 'signals')} (
        spot_price, vix, expected_move, call_wall, put_wall,
        gex_regime, put_short, put_long, call_short, call_long,
        total_credit, confidence, was_executed, reasoning,
        wings_adjusted, dte_mode
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)`,
      [
        spot, vix, expectedMove, 0, 0,
        'UNKNOWN', strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
        credits.totalCredit, adv.confidence, true, `Force trade via API | ${adv.reasoning}`,
        false, dte,
      ],
    )

    // 13. Log
    await query(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'TRADE_OPEN',
        `FORCE TRADE: ${positionId} ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C x${maxContracts} @ $${credits.totalCredit.toFixed(4)}`,
        JSON.stringify({
          position_id: positionId,
          contracts: maxContracts,
          credit: credits.totalCredit,
          collateral: totalCollateral,
          source: 'force_trade_api',
          sandbox_order_ids: sandboxOrderIds,
        }),
        dte,
      ],
    )

    // 13b. Log PDT entry (so force-trades count toward PDT limits)
    await query(
      `INSERT INTO ${botTable(bot, 'pdt_log')} (
        trade_date, symbol, position_id, opened_at,
        contracts, entry_credit, dte_mode
      ) VALUES (CURRENT_DATE, $1, $2, NOW(), $3, $4, $5)`,
      ['SPY', positionId, maxContracts, credits.totalCredit, dte],
    )

    // 14. Save equity snapshot
    const updatedAcct = await query(
      `SELECT current_balance, cumulative_pnl FROM ${botTable(bot, 'paper_account')}
       WHERE id = $1`,
      [acct.id],
    )
    const bal = num(updatedAcct[0]?.current_balance)
    await query(
      `INSERT INTO ${botTable(bot, 'equity_snapshots')}
       (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
       VALUES ($1, $2, 0, 1, $3, $4)`,
      [bal, num(updatedAcct[0]?.cumulative_pnl), `force_trade:${positionId}`, dte],
    )

    // 15. Update daily_perf
    await query(
      `INSERT INTO ${botTable(bot, 'daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl)
       VALUES (CURRENT_DATE, 1, 0, 0)
       ON CONFLICT (trade_date) DO UPDATE SET
         trades_executed = ${botTable(bot, 'daily_perf')}.trades_executed + 1`,
    )

    // 16. Update heartbeat
    await query(
      `INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
       VALUES ($1, NOW(), 'active', 1, $2)
       ON CONFLICT (bot_name) DO UPDATE SET
         last_heartbeat = NOW(), status = 'active',
         scan_count = bot_heartbeats.scan_count + 1,
         details = EXCLUDED.details`,
      [botName, JSON.stringify({ last_action: 'force_trade' })],
    )

    return NextResponse.json({
      success: true,
      position_id: positionId,
      expiration,
      strikes: {
        put_long: strikes.putLong,
        put_short: strikes.putShort,
        call_short: strikes.callShort,
        call_long: strikes.callLong,
      },
      contracts: maxContracts,
      credit: credits.totalCredit,
      collateral: totalCollateral,
      max_profit: Math.round(maxProfit * 100) / 100,
      max_loss: Math.round(maxLoss * 100) / 100,
      spot_price: spot,
      vix,
      source: credits.source,
      sandbox_order_ids: sandboxOrderIds,
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
