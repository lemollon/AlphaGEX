/**
 * FLARE — paper executor. Builds OCC symbols + fetches Tradier quotes for the
 * 2-leg debit vertical, computes debit + size, and inserts into flare_positions.
 *
 * KEY DIFFERENCE from BLAZE: expiration is the SAME trading day (0DTE),
 * not the next trading day.
 */
import { buildOccSymbol, getOptionQuote } from '../tradier'
import { insertFlarePosition, getPaperBalance, getDirectionForceCloseCount } from './db'
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

export async function openVertical(
  action: SetupAction,
  snap: GexSnapshot,
  config: FlareConfig,
): Promise<OpenResult | null> {
  // 0DTE: expiration is today, not tomorrow
  const expiration = todayTradingDay(snap.snapshot_at)
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

  // Risk-% × BP usage on current balance, then SIZE-DOWN by 0.33^(force-closes
  // today on this side): a repeatedly-stopped side keeps trading all day but at
  // rapidly shrinking size so a one-way trend can't run away. Resets each AM.
  const balance = await getPaperBalance()
  const fcCount = await getDirectionForceCloseCount(action.direction)
  const sizeMult = Math.pow(config.perdir_size_mult_after_fc, fcCount)
  const capitalAtRisk = balance * config.risk_per_trade_pct * config.buying_power_usage_pct * sizeMult
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
