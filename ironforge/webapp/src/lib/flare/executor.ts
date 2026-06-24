/**
 * FLARE — paper executor. Builds OCC symbols + fetches Tradier quotes for the
 * 2-leg debit vertical, computes debit + size, and inserts into flare_positions.
 *
 * KEY DIFFERENCE from BLAZE: expiration is the SAME trading day (0DTE),
 * not the next trading day.
 */
import { buildOccSymbol, getOptionQuote } from '../tradier'
import { insertFlarePosition, getPaperBalance } from './db'
import { FlareConfig, GexSnapshot, SetupAction } from './types'

export interface OpenResult {
  position_id: number
  debit: number
  contracts: number
  long_symbol: string
  short_symbol: string
}

/** Same trading day (0DTE) as `from`, in CT, YYYY-MM-DD. */
export function todayTradingDay(from: Date): string {
  const ct = new Date(from.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const yyyy = ct.getFullYear()
  const mm = String(ct.getMonth() + 1).padStart(2, '0')
  const dd = String(ct.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

/** Next trading day (1DTE) after `from`, in CT, YYYY-MM-DD. Skips weekends.
 * (Holidays not modelled — a holiday makes the position effectively 2DTE, rare
 * and harmless for the hold-to-expiry momentum strategy.) FLARE trades 1DTE:
 * the validated neg-GEX momentum edge holds the next-day expiry to settlement. */
export function nextTradingDay(from: Date): string {
  const ct = new Date(from.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  ct.setDate(ct.getDate() + 1)
  while (ct.getDay() === 0 || ct.getDay() === 6) ct.setDate(ct.getDate() + 1)
  const yyyy = ct.getFullYear()
  const mm = String(ct.getMonth() + 1).padStart(2, '0')
  const dd = String(ct.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

export async function openVertical(
  action: SetupAction,
  snap: GexSnapshot,
  config: FlareConfig,
): Promise<OpenResult | null> {
  // 1DTE: expiration is the NEXT trading day, held to settlement.
  const expiration = nextTradingDay(snap.snapshot_at)
  const optType: 'C' | 'P' = action.direction === 'call' ? 'C' : 'P'
  const longSym = buildOccSymbol(config.ticker, expiration, action.long_strike, optType)
  const shortSym = buildOccSymbol(config.ticker, expiration, action.short_strike, optType)

  const [longQ, shortQ] = await Promise.all([
    getOptionQuote(longSym),
    getOptionQuote(shortSym),
  ])
  if (!longQ || !shortQ) return null

  // Debit vertical: pay long ask, receive short bid, net = long.ask - short.bid (worst case)
  const debit = longQ.ask - shortQ.bid
  if (debit <= 0 || debit >= config.spread_width) return null

  // Sizing: risk fraction of balance is the max loss (= debit deployed), since this
  // is a debit spread held to expiry. PER-LEG SIZING: the conviction directional
  // leg (gex_momentum) is the FRAGILE one (41% win, losses cluster), so it sizes
  // DOWN to risk_per_trade_pct * conviction_size_mult (~3.3%), while the durable
  // put-credit leg uses the full base. This stops the fragile leg from capping the
  // book's size (2026-06-24 sizing study). Legacy wall setups (inert) keep the base.
  const balance = await getPaperBalance()
  const riskPct = action.setup === 'gex_momentum'
    ? config.risk_per_trade_pct * config.conviction_size_mult
    : config.risk_per_trade_pct
  const capitalAtRisk = balance * riskPct
  const costPerContract = debit * 100
  const contracts = Math.max(1, Math.floor(capitalAtRisk / costPerContract))

  const position_id = await insertFlarePosition({
    setup_type: action.setup,
    direction: action.direction,
    long_strike: action.long_strike,
    short_strike: action.short_strike,
    long_symbol: longSym,
    short_symbol: shortSym,
    debit,
    contracts,
    expiration,
    spot_at_entry: snap.spot,
    // Stamp GEX context at entry so every trade is regime-gateable later
    // (previously NULL — the gate work was blind to regime/walls).
    gex_regime: snap.regime,
    net_gex: snap.net_gex,
    call_wall: snap.call_wall,
    put_wall: snap.put_wall,
    flip_point: snap.flip_point,
    vix: snap.vix,
  })

  if (!position_id) return null

  return {
    position_id,
    debit,
    contracts,
    long_symbol: longSym,
    short_symbol: shortSym,
  }
}

/** OTM offset (points) of the short put for the pin-day put-credit leg. */
const PUTCREDIT_SHORT_OFFSET = 3

/**
 * FLARE pin-day PREMIUM leg (positive-GEX regime): a BULLISH PUT CREDIT spread,
 * 1DTE, held to expiry. Sell a put ~$3 OTM (round(spot) - 3), buy the wing
 * config.spread_width lower. Profits if SPY rises OR holds (the grind-up thesis);
 * loses only on a real drop, with defined risk. `debit` is stored NEGATIVE
 * (= credit received) so the monitor's (mark - debit) P&L works unchanged, and
 * the position is held to expiry exactly like the directional leg (no intraday
 * management — pay the spread once at entry, which is why 1DTE survives where the
 * old 0DTE fly did not). Tagged setup_type 'gex_putcredit'.
 *
 * Validated (gauntlet_pc.py, consistent raw pricing, $5-wide): +$13.9/trade,
 * 88% win, 6/7 yrs green, broad (not concentrated), non-decaying. NOTE: this leg
 * was validated on the warehouse spy_gex_daily GEX series; the live bot gates on
 * its own γ×OI net_gex, so paper trading is itself the A/B test of that gate.
 */
export async function openPutCredit(
  snap: GexSnapshot,
  config: FlareConfig,
): Promise<OpenResult | null> {
  const expiration = nextTradingDay(snap.snapshot_at)  // 1DTE, held to expiry
  const shortK = Math.round(snap.spot) - PUTCREDIT_SHORT_OFFSET
  const longK = shortK - config.spread_width
  const longSym = buildOccSymbol(config.ticker, expiration, longK, 'P')
  const shortSym = buildOccSymbol(config.ticker, expiration, shortK, 'P')

  const [longQ, shortQ] = await Promise.all([getOptionQuote(longSym), getOptionQuote(shortSym)])
  if (!longQ || !shortQ) return null

  // Credit vertical: sell the short put (receive bid), buy the long wing (pay ask).
  // debit = long.ask - short.bid is NEGATIVE here (= credit received). Reject if it
  // isn't actually a credit.
  const debit = longQ.ask - shortQ.bid
  if (debit >= 0) return null
  const maxLoss = config.spread_width + debit   // = width - credit (debit is negative)
  if (maxLoss <= 0) return null

  // Size by capital-at-risk: each contract risks maxLoss × 100. Floor at 1 contract.
  const balance = await getPaperBalance()
  const capitalAtRisk = balance * config.risk_per_trade_pct
  const contracts = Math.max(1, Math.floor(capitalAtRisk / (maxLoss * 100)))

  const position_id = await insertFlarePosition({
    setup_type: 'gex_putcredit',
    direction: 'put',
    long_strike: longK,
    short_strike: shortK,
    long_symbol: longSym,
    short_symbol: shortSym,
    debit,
    contracts,
    expiration,
    spot_at_entry: snap.spot,
    gex_regime: snap.regime,
    net_gex: snap.net_gex,
    call_wall: snap.call_wall,
    put_wall: snap.put_wall,
    flip_point: snap.flip_point,
    vix: snap.vix,
  })
  if (!position_id) return null
  return { position_id, debit, contracts, long_symbol: longSym, short_symbol: shortSym }
}

/**
 * QUICK-ITM morning sleeve (ADDITIVE — runs alongside the two-regime legs, replaces
 * nothing). A single 0DTE ITM long CALL bought in the morning on positive-GEX days
 * to capture the intraday grind-up; the monitor sells it SAME-DAY at the configured
 * exit time (no overnight). Modeled as a single-leg position: short_symbol is empty
 * and short_strike == long_strike (spread_width 0) so the monitor knows it's a lone
 * call. `debit` = the call ask (premium paid = max loss). Sized at a fixed small
 * quick_itm_contracts (naked long, 54-day sample -> not risk-%-scaled). Tagged
 * setup_type 'gex_quick_itm'. Caller gates on net_gex>=0 + the morning entry window.
 */
export async function openQuickItmCall(
  snap: GexSnapshot,
  config: FlareConfig,
): Promise<OpenResult | null> {
  const expiration = todayTradingDay(snap.snapshot_at)        // 0DTE same-day
  const K = Math.round(snap.spot) - config.quick_itm_strike_itm
  const longSym = buildOccSymbol(config.ticker, expiration, K, 'C')
  const longQ = await getOptionQuote(longSym)
  if (!longQ || longQ.ask <= 0) return null
  const debit = longQ.ask                                     // pay the ask to buy the call
  const contracts = Math.max(1, Math.floor(config.quick_itm_contracts))

  const position_id = await insertFlarePosition({
    setup_type: 'gex_quick_itm',
    direction: 'call',
    long_strike: K,
    short_strike: K,            // single leg -> spread_width 0
    long_symbol: longSym,
    short_symbol: '',           // no short leg; monitor treats '' as single-leg
    debit,
    contracts,
    expiration,
    spot_at_entry: snap.spot,
    gex_regime: snap.regime,
    net_gex: snap.net_gex,
    call_wall: snap.call_wall,
    put_wall: snap.put_wall,
    flip_point: snap.flip_point,
    vix: snap.vix,
  })
  if (!position_id) return null
  return { position_id, debit, contracts, long_symbol: longSym, short_symbol: '' }
}

/** Max contracts a single hedge top-up order may place — bounds blast radius
 *  while the per-tick shortfall logic converges the protective side to target. */
export const HEDGE_MAX_CONTRACTS_PER_ORDER =
  Number(process.env.FLARE_HEDGE_MAX_CONTRACTS) || 50

/**
 * Open (or top up) the net-imbalance HEDGE: an OPPOSING 0DTE debit spread that
 * profits on the move that hurts the heavy side. Width spans ~the 1σ move so it
 * reaches near-max on an adverse day. Contracts are sized by CAPITAL-AT-RISK so
 * the hedge's max loss (debit × 100 × contracts) ≈ targetRisk — this RISK-balances
 * the protective side against the heavy side (so the call/put-balance card moves
 * toward even), rather than only matching max-payoff. Tagged 'imbalance_hedge' so
 * computeImbalance ignores it. Closes via the normal PT/SL/14:45 exit path.
 */
export async function openImbalanceHedge(
  args: { hedgeSide: 'call' | 'put'; targetRisk: number; spot: number; sigMove: number },
  config: FlareConfig,
): Promise<OpenResult | null> {
  const expiration = todayTradingDay(new Date())
  const optType: 'C' | 'P' = args.hedgeSide === 'call' ? 'C' : 'P'
  const width = Math.max(2, Math.min(10, Math.round(args.sigMove))) // span ~the adverse move
  const atm = Math.round(args.spot)
  // call hedge: long ATM / short higher (bullish). put hedge: long ATM / short lower (bearish).
  const longStrike = atm
  const shortStrike = args.hedgeSide === 'call' ? atm + width : atm - width
  const longSym = buildOccSymbol(config.ticker, expiration, longStrike, optType)
  const shortSym = buildOccSymbol(config.ticker, expiration, shortStrike, optType)

  const [longQ, shortQ] = await Promise.all([getOptionQuote(longSym), getOptionQuote(shortSym)])
  if (!longQ || !shortQ) return null
  const debit = longQ.ask - shortQ.bid
  if (debit <= 0 || debit >= width) return null

  // Size by capital-at-risk: each contract risks debit × 100. Clamp to a per-order
  // ceiling so one tick can't place a pathological order if targetRisk is large.
  const riskPerContract = debit * 100
  const contracts = Math.min(
    HEDGE_MAX_CONTRACTS_PER_ORDER,
    Math.max(1, Math.round(args.targetRisk / riskPerContract)),
  )

  const position_id = await insertFlarePosition({
    setup_type: 'imbalance_hedge',
    direction: args.hedgeSide,
    long_strike: longStrike,
    short_strike: shortStrike,
    long_symbol: longSym,
    short_symbol: shortSym,
    debit,
    contracts,
    expiration,
    spot_at_entry: args.spot,
  })
  if (!position_id) return null
  return { position_id, debit, contracts, long_symbol: longSym, short_symbol: shortSym }
}
