#!/usr/bin/env node
/**
 * IronForge Force Trade (Render Shell)
 * ======================================
 * Forces FLAME or SPARK to execute a paper trade NOW.
 * Uses Node.js + pg (already installed in webapp's node_modules).
 * No Python, no venv, no pip install.
 *
 * Usage (from Render shell):
 *   cd ~/project/src/ironforge/webapp
 *   node scripts/force.js                     # FLAME (default)
 *   node scripts/force.js spark               # SPARK
 *   node scripts/force.js flame --close-first # Close existing, then open
 *   node scripts/force.js flame --close-only  # Just close, don't open new
 */

const { Pool } = require('pg')

const DATABASE_URL = process.env.DATABASE_URL
if (!DATABASE_URL) {
  console.error('ERROR: DATABASE_URL not set')
  process.exit(1)
}

const TRADIER_API_KEY = process.env.TRADIER_API_KEY || ''
const TRADIER_BASE_URL = process.env.TRADIER_BASE_URL || 'https://sandbox.tradier.com/v1'

if (!TRADIER_API_KEY) {
  console.error('ERROR: TRADIER_API_KEY not set — cannot get quotes')
  process.exit(1)
}

const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  max: 3,
})

// Parse args
const args = process.argv.slice(2)
const botArg = (args.find(a => !a.startsWith('--')) || 'flame').toLowerCase()
const closeFirst = args.includes('--close-first')
const closeOnly = args.includes('--close-only')

if (botArg !== 'flame' && botArg !== 'spark') {
  console.error(`ERROR: Invalid bot '${botArg}'. Use 'flame' or 'spark'.`)
  process.exit(1)
}

const BOT = botArg
const BOT_NAME = BOT.toUpperCase()
const DTE = BOT === 'flame' ? '2DTE' : '1DTE'
const MIN_DTE = BOT === 'flame' ? 2 : 1

// ── Tradier helpers ──────────────────────────────────────────────

async function tradierGet(endpoint, params) {
  const url = new URL(`${TRADIER_BASE_URL}${endpoint}`)
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))

  const resp = await fetch(url.toString(), {
    headers: {
      'Authorization': `Bearer ${TRADIER_API_KEY}`,
      'Accept': 'application/json',
    },
  })
  if (!resp.ok) return null
  return resp.json()
}

function buildOcc(ticker, exp, strike, type) {
  const d = new Date(exp + 'T12:00:00')
  const yy = String(d.getFullYear()).slice(2)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const s = String(Math.round(strike * 1000)).padStart(8, '0')
  return `${ticker}${yy}${mm}${dd}${type}${s}`
}

async function getQuote(symbol) {
  const data = await tradierGet('/markets/quotes', { symbols: symbol })
  if (!data) return null
  let q = data.quotes?.quote
  if (Array.isArray(q)) q = q[0]
  if (!q?.last) return null
  return { last: parseFloat(q.last), bid: parseFloat(q.bid || '0'), ask: parseFloat(q.ask || '0') }
}

async function getOptionQuote(occ) {
  const data = await tradierGet('/markets/quotes', { symbols: occ })
  if (!data) return null
  let q = data.quotes?.quote
  if (Array.isArray(q)) q = q[0]
  if (!q || q.bid == null) return null
  if (data.quotes?.unmatched_symbols) return null
  return { bid: parseFloat(q.bid || '0'), ask: parseFloat(q.ask || '0'), last: parseFloat(q.last || '0') }
}

async function getExpirations() {
  const data = await tradierGet('/markets/options/expirations', { symbol: 'SPY', includeAllRoots: 'true' })
  if (!data) return []
  const dates = data.expirations?.date
  if (!dates) return []
  return Array.isArray(dates) ? dates : [dates]
}

// ── Strike & credit logic (mirrors Python signals.py) ────────────

function calculateStrikes(spot, expectedMove) {
  const SD = 1.2
  const WIDTH = 5
  const minEM = spot * 0.005
  const em = Math.max(expectedMove, minEM)

  let putShort = Math.floor(spot - SD * em)
  let callShort = Math.ceil(spot + SD * em)
  let putLong = putShort - WIDTH
  let callLong = callShort + WIDTH

  if (callShort <= putShort) {
    putShort = Math.floor(spot - spot * 0.02)
    callShort = Math.ceil(spot + spot * 0.02)
    putLong = putShort - WIDTH
    callLong = callShort + WIDTH
  }

  return { putShort, putLong, callShort, callLong }
}

function getTargetExpiration(minDte) {
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

async function getIcEntryCredit(exp, strikes) {
  const [psQ, plQ, csQ, clQ] = await Promise.all([
    getOptionQuote(buildOcc('SPY', exp, strikes.putShort, 'P')),
    getOptionQuote(buildOcc('SPY', exp, strikes.putLong, 'P')),
    getOptionQuote(buildOcc('SPY', exp, strikes.callShort, 'C')),
    getOptionQuote(buildOcc('SPY', exp, strikes.callLong, 'C')),
  ])

  if (!psQ || !plQ || !csQ || !clQ) return null

  let putCredit = psQ.bid - plQ.ask
  let callCredit = csQ.bid - clQ.ask

  if (putCredit <= 0 || callCredit <= 0) {
    putCredit = Math.max(0, (psQ.bid + psQ.ask) / 2 - (plQ.bid + plQ.ask) / 2)
    callCredit = Math.max(0, (csQ.bid + csQ.ask) / 2 - (clQ.bid + clQ.ask) / 2)
  }

  return {
    putCredit: round4(putCredit),
    callCredit: round4(callCredit),
    totalCredit: round4(putCredit + callCredit),
  }
}

async function getIcMtm(exp, pos) {
  const [psQ, plQ, csQ, clQ] = await Promise.all([
    getOptionQuote(buildOcc('SPY', exp, pos.put_short_strike, 'P')),
    getOptionQuote(buildOcc('SPY', exp, pos.put_long_strike, 'P')),
    getOptionQuote(buildOcc('SPY', exp, pos.call_short_strike, 'C')),
    getOptionQuote(buildOcc('SPY', exp, pos.call_long_strike, 'C')),
  ])
  if (!psQ || !plQ || !csQ || !clQ) return null
  return Math.max(0, round4(psQ.ask + csQ.ask - plQ.bid - clQ.bid))
}

// ── Advisor (mirrors Python advisor.py) ──────────────────────────

function evaluate(vix, spot, expectedMove) {
  let winProb = 0.65
  const factors = []

  if (vix >= 15 && vix <= 22) { winProb += 0.10; factors.push(['VIX_IDEAL', 0.10]) }
  else if (vix < 15) { winProb -= 0.05; factors.push(['VIX_LOW', -0.05]) }
  else if (vix <= 28) { winProb -= 0.05; factors.push(['VIX_ELEVATED', -0.05]) }
  else { winProb -= 0.15; factors.push(['VIX_HIGH', -0.15]) }

  const dow = new Date().getDay()
  if (dow >= 2 && dow <= 4) { winProb += 0.08; factors.push(['DAY_OPTIMAL', 0.08]) }
  else if (dow === 1) { winProb += 0.03; factors.push(['DAY_MON', 0.03]) }
  else if (dow === 5) { winProb -= 0.10; factors.push(['DAY_FRI', -0.10]) }
  else { winProb -= 0.20; factors.push(['DAY_WKND', -0.20]) }

  const emRatio = spot > 0 ? (expectedMove / spot * 100) : 1.0
  if (emRatio < 1.0) { winProb += 0.08; factors.push(['EM_TIGHT', 0.08]) }
  else if (emRatio <= 2.0) { factors.push(['EM_NORMAL', 0]) }
  else { winProb -= 0.08; factors.push(['EM_WIDE', -0.08]) }

  if (DTE === '2DTE') { winProb += 0.03; factors.push(['DTE_2', 0.03]) }
  else { winProb -= 0.02; factors.push(['DTE_1', -0.02]) }

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

  return { advice, winProb: round4(winProb), confidence: round4(confidence), factors }
}

// ── Main ─────────────────────────────────────────────────────────

async function run() {
  console.log('============================================================')
  console.log(`  IRONFORGE FORCE TRADE: ${BOT_NAME} (${DTE})`)
  console.log(`  ${new Date().toISOString()}`)
  if (closeFirst) console.log('  Mode: --close-first (close existing, then open new)')
  if (closeOnly) console.log('  Mode: --close-only (close existing, do not open new)')
  console.log('============================================================')

  // ── Check open positions ──────────────────────────────────────
  const openRes = await pool.query(
    `SELECT position_id, ticker, expiration,
            put_short_strike, put_long_strike,
            call_short_strike, call_long_strike,
            total_credit, contracts, collateral_required
     FROM ${BOT}_positions
     WHERE status = 'open' AND dte_mode = $1
     ORDER BY open_time DESC`,
    [DTE]
  )

  if (openRes.rows.length > 0) {
    console.log(`\n  OPEN POSITIONS: ${openRes.rows.length}`)
    for (const p of openRes.rows) {
      console.log(`    ${p.position_id}: ` +
        `${p.put_long_strike}/${p.put_short_strike}P-` +
        `${p.call_short_strike}/${p.call_long_strike}C ` +
        `x${p.contracts} @ $${pf(p.total_credit)} exp=${str(p.expiration).slice(0,10)}`)
    }

    if (closeFirst || closeOnly) {
      console.log(`\n  FORCE-CLOSING ${openRes.rows.length} position(s)...`)
      for (const p of openRes.rows) {
        const exp = str(p.expiration).slice(0, 10)
        const mtm = await getIcMtm(exp, p)
        const closePrice = mtm != null ? mtm : parseFloat(p.total_credit)
        const totalCredit = parseFloat(p.total_credit)
        const contracts = parseInt(p.contracts)
        const collateral = parseFloat(p.collateral_required || 0)
        const pnl = round2((totalCredit - closePrice) * 100 * contracts)

        // Close position
        await pool.query(
          `UPDATE ${BOT}_positions
           SET status = 'closed', close_time = NOW(),
               close_price = $1, realized_pnl = $2,
               close_reason = 'manual_close', updated_at = NOW()
           WHERE position_id = $3 AND status = 'open' AND dte_mode = $4`,
          [closePrice, pnl, p.position_id, DTE]
        )

        // Update account
        await pool.query(
          `UPDATE ${BOT}_paper_account
           SET current_balance = current_balance + $1,
               cumulative_pnl = cumulative_pnl + $1,
               total_trades = total_trades + 1,
               collateral_in_use = GREATEST(0, collateral_in_use - $2),
               buying_power = buying_power + $2 + $1,
               high_water_mark = GREATEST(high_water_mark, current_balance + $1),
               updated_at = NOW()
           WHERE is_active IS NOT NULL AND dte_mode = $3`,
          [pnl, collateral, DTE]
        )

        // Log
        await pool.query(
          `INSERT INTO ${BOT}_logs (level, message, details, dte_mode)
           VALUES ($1, $2, $3, $4)`,
          ['TRADE_CLOSE', `FORCE CLOSE: ${p.position_id} @ $${closePrice.toFixed(4)} P&L=$${pnl.toFixed(2)}`,
           JSON.stringify({ position_id: p.position_id, close_price: closePrice, realized_pnl: pnl }), DTE]
        )

        console.log(`    ${p.position_id}: CLOSED (close@$${closePrice.toFixed(4)}, P&L=$${pnl.toFixed(2)})`)
      }

      // Verify
      const remaining = await pool.query(
        `SELECT COUNT(*) as cnt FROM ${BOT}_positions WHERE status = 'open' AND dte_mode = $1`,
        [DTE]
      )
      console.log(`  Remaining open: ${remaining.rows[0].cnt}`)
    } else {
      console.log(`\n  Cannot open new trade with position(s) open.`)
      console.log(`  Re-run with --close-first or --close-only:`)
      console.log(`    node scripts/force.js ${BOT} --close-first`)
      await pool.end()
      process.exit(1)
    }
  }

  if (closeOnly) {
    console.log('\n  --close-only mode: done.')
    await pool.end()
    return
  }

  // ── Paper account ──────────────────────────────────────────────
  console.log(`\n${'='.repeat(56)}`)
  console.log('  STEP 1: PAPER ACCOUNT')
  console.log('='.repeat(56))

  const acctRes = await pool.query(
    `SELECT id, current_balance, buying_power, cumulative_pnl, total_trades, is_active
     FROM ${BOT}_paper_account
     WHERE dte_mode = $1 ORDER BY id DESC LIMIT 1`,
    [DTE]
  )
  if (acctRes.rows.length === 0) {
    console.error('  ERROR: No paper account found')
    await pool.end()
    process.exit(1)
  }
  const acct = acctRes.rows[0]
  const buyingPower = parseFloat(acct.buying_power)
  console.log(`  Balance: $${pf(acct.current_balance)}`)
  console.log(`  Buying Power: $${pf(acct.buying_power)}`)
  console.log(`  Cumulative P&L: $${pf(acct.cumulative_pnl)}`)
  console.log(`  Trades: ${acct.total_trades}`)

  if (buyingPower < 200) {
    console.error(`\n  ERROR: Buying power $${pf(acct.buying_power)} < $200 minimum`)
    await pool.end()
    process.exit(1)
  }

  // ── Market data ────────────────────────────────────────────────
  console.log(`\n${'='.repeat(56)}`)
  console.log('  STEP 2: MARKET DATA & SIGNAL')
  console.log('='.repeat(56))

  const [spyQ, vixQ] = await Promise.all([getQuote('SPY'), getQuote('VIX')])
  if (!spyQ) {
    console.error('  ERROR: Could not get SPY quote from Tradier')
    await pool.end()
    process.exit(1)
  }

  const spot = spyQ.last
  const vix = vixQ?.last ?? 20
  const expectedMove = (vix / 100 / Math.sqrt(252)) * spot

  console.log(`  SPY: $${spot.toFixed(2)}`)
  console.log(`  VIX: ${vix.toFixed(1)}`)
  console.log(`  Expected Move: $${expectedMove.toFixed(2)}`)

  if (vix > 32) {
    console.error(`  ERROR: VIX ${vix.toFixed(1)} too high (>32)`)
    await pool.end()
    process.exit(1)
  }

  // ── Expiration ─────────────────────────────────────────────────
  const targetExp = getTargetExpiration(MIN_DTE)
  const expirations = await getExpirations()
  let expiration = targetExp
  if (expirations.length > 0 && !expirations.includes(targetExp)) {
    const targetMs = new Date(targetExp + 'T12:00:00').getTime()
    let nearest = expirations[0]
    let minDiff = Infinity
    for (const exp of expirations) {
      const diff = Math.abs(new Date(exp + 'T12:00:00').getTime() - targetMs)
      if (diff < minDiff) { minDiff = diff; nearest = exp }
    }
    expiration = nearest
  }
  console.log(`  Expiration: ${expiration} (target was ${targetExp})`)

  // ── Strikes ────────────────────────────────────────────────────
  const strikes = calculateStrikes(spot, expectedMove)
  console.log(`  Strikes: ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C`)

  // ── Credits ────────────────────────────────────────────────────
  const credits = await getIcEntryCredit(expiration, strikes)
  if (!credits || credits.totalCredit < 0.05) {
    console.error(`  ERROR: Credit too low: $${credits?.totalCredit?.toFixed(4) ?? '0'} (min $0.05)`)
    await pool.end()
    process.exit(1)
  }
  console.log(`  Credit: $${credits.totalCredit.toFixed(4)} (put=$${credits.putCredit.toFixed(4)} call=$${credits.callCredit.toFixed(4)})`)

  // ── Advisor ────────────────────────────────────────────────────
  const adv = evaluate(vix, spot, expectedMove)
  console.log(`  Advisor: ${adv.advice} WP=${adv.winProb} conf=${adv.confidence}`)

  // ── Sizing ─────────────────────────────────────────────────────
  console.log(`\n${'='.repeat(56)}`)
  console.log('  STEP 3: SIZING')
  console.log('='.repeat(56))

  const spreadWidth = strikes.putShort - strikes.putLong
  const collateralPer = Math.max(0, (spreadWidth - credits.totalCredit) * 100)
  const usableBP = buyingPower * 0.85
  const maxContracts = Math.min(10, Math.max(1, Math.floor(usableBP / collateralPer)))
  const totalCollateral = collateralPer * maxContracts

  console.log(`  Spread width: $${spreadWidth}`)
  console.log(`  Collateral/contract: $${collateralPer.toFixed(2)}`)
  console.log(`  Usable BP (85%): $${usableBP.toFixed(2)}`)
  console.log(`  Contracts: ${maxContracts} (cap=10)`)
  console.log(`  Total collateral: $${totalCollateral.toFixed(2)}`)
  console.log(`  Max profit: $${(credits.totalCredit * 100 * maxContracts).toFixed(2)}`)
  console.log(`  Max loss: $${totalCollateral.toFixed(2)}`)

  if (maxContracts < 1 || collateralPer <= 0) {
    console.error('  ERROR: Cannot afford any contracts')
    await pool.end()
    process.exit(1)
  }

  // ── Execute ────────────────────────────────────────────────────
  console.log(`\n${'='.repeat(56)}`)
  console.log('  STEP 4: EXECUTING PAPER TRADE')
  console.log('='.repeat(56))

  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const hex = Math.random().toString(16).slice(2, 8).toUpperCase()
  const positionId = `${BOT_NAME}-${dateStr}-${hex}`

  // Insert position
  await pool.query(
    `INSERT INTO ${BOT}_positions (
      position_id, ticker, expiration,
      put_short_strike, put_long_strike, put_credit,
      call_short_strike, call_long_strike, call_credit,
      contracts, spread_width, total_credit, max_loss, max_profit,
      collateral_required,
      underlying_at_entry, vix_at_entry, expected_move,
      call_wall, put_wall, gex_regime, flip_point, net_gex,
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
      maxContracts, spreadWidth, credits.totalCredit, totalCollateral,
      round2(credits.totalCredit * 100 * maxContracts),
      totalCollateral,
      spot, vix, expectedMove,
      0, 0, 'UNKNOWN', 0, 0,
      adv.confidence, adv.winProb, adv.advice,
      `Force trade: ${adv.advice} WP=${adv.winProb} conf=${adv.confidence}`,
      JSON.stringify(adv.factors), false,
      false, spreadWidth, spreadWidth,
      'PAPER', 'PAPER',
      DTE,
    ]
  )

  // Update paper account (deduct collateral)
  await pool.query(
    `UPDATE ${BOT}_paper_account
     SET collateral_in_use = collateral_in_use + $1,
         buying_power = buying_power - $1,
         updated_at = NOW()
     WHERE id = $2`,
    [totalCollateral, acct.id]
  )

  // Log signal
  await pool.query(
    `INSERT INTO ${BOT}_signals (
      spot_price, vix, expected_move, call_wall, put_wall,
      gex_regime, put_short, put_long, call_short, call_long,
      total_credit, confidence, was_executed, reasoning,
      wings_adjusted, dte_mode
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)`,
    [
      spot, vix, expectedMove, 0, 0,
      'UNKNOWN', strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
      credits.totalCredit, adv.confidence, true,
      `FORCE TRADE (node): ${adv.advice}`, false, DTE,
    ]
  )

  // Activity log
  await pool.query(
    `INSERT INTO ${BOT}_logs (level, message, details, dte_mode)
     VALUES ($1, $2, $3, $4)`,
    [
      'TRADE_OPEN',
      `FORCE TRADE: ${positionId} ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C x${maxContracts} @ $${credits.totalCredit.toFixed(4)}`,
      JSON.stringify({ position_id: positionId, contracts: maxContracts, credit: credits.totalCredit, collateral: totalCollateral }),
      DTE,
    ]
  )

  // Equity snapshot
  const updAcct = await pool.query(
    `SELECT current_balance, cumulative_pnl FROM ${BOT}_paper_account WHERE id = $1`,
    [acct.id]
  )
  await pool.query(
    `INSERT INTO ${BOT}_equity_snapshots (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
     VALUES ($1, $2, 0, 1, $3, $4)`,
    [parseFloat(updAcct.rows[0].current_balance), parseFloat(updAcct.rows[0].cumulative_pnl),
     `force_trade:${positionId}`, DTE]
  )

  // Daily perf
  await pool.query(
    `INSERT INTO ${BOT}_daily_perf (trade_date, trades_executed, positions_closed, realized_pnl)
     VALUES (CURRENT_DATE, 1, 0, 0)
     ON CONFLICT (trade_date) DO UPDATE SET
       trades_executed = ${BOT}_daily_perf.trades_executed + 1`
  )

  // Heartbeat
  await pool.query(
    `INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
     VALUES ($1, NOW(), 'active', 1, $2)
     ON CONFLICT (bot_name) DO UPDATE SET
       last_heartbeat = NOW(), status = 'active',
       scan_count = bot_heartbeats.scan_count + 1,
       details = EXCLUDED.details`,
    [BOT_NAME, JSON.stringify({ last_action: 'force_trade_node' })]
  )

  // Verify
  const verify = await pool.query(
    `SELECT position_id FROM ${BOT}_positions WHERE position_id = $1 AND status = 'open'`,
    [positionId]
  )
  const verified = verify.rows.length > 0

  const finalAcct = await pool.query(
    `SELECT current_balance, buying_power FROM ${BOT}_paper_account WHERE id = $1`,
    [acct.id]
  )

  console.log(`\n  ${'='.repeat(52)}`)
  console.log('  SUCCESS!')
  console.log(`  ${'='.repeat(52)}`)
  console.log(`  Position ID: ${positionId}`)
  console.log(`  Strikes: ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C`)
  console.log(`  Expiration: ${expiration}`)
  console.log(`  Contracts: ${maxContracts}`)
  console.log(`  Credit: $${credits.totalCredit.toFixed(4)}`)
  console.log(`  Collateral: $${totalCollateral.toFixed(2)}`)
  console.log(`  DB verified: ${verified ? 'YES' : 'NO — CHECK DB!'}`)
  console.log(`  New balance: $${pf(finalAcct.rows[0]?.current_balance)}`)
  console.log(`  New BP: $${pf(finalAcct.rows[0]?.buying_power)}`)
  console.log(`  ${'='.repeat(52)}`)
  console.log(`\n  Position will be managed by the scheduler.`)
  console.log(`  To force-close: node scripts/force.js ${BOT} --close-first`)

  await pool.end()
}

// Helpers
function pf(val) { return val == null ? '0.00' : parseFloat(val).toFixed(2) }
function str(val) { return val == null ? '?' : val instanceof Date ? val.toISOString() : String(val) }
function round2(n) { return Math.round(n * 100) / 100 }
function round4(n) { return Math.round(n * 10000) / 10000 }

run().catch(err => {
  console.error('FATAL:', err)
  pool.end()
  process.exit(1)
})
