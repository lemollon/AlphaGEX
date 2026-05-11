/**
 * BLAZE — paper executor. Builds OCC symbols + fetches Tradier quotes for the
 * 2-leg debit vertical, computes debit + size, and inserts into blaze_positions.
 */
import { buildOccSymbol, getOptionQuote } from '../tradier'
import { insertBlazePosition, getPaperBalance } from './db'
import { BlazeConfig, GexSnapshot, SetupAction } from './types'

export interface OpenResult {
  position_id: number
  debit: number
  contracts: number
  long_symbol: string
  short_symbol: string
}

/** Next trading day (Mon–Fri) after `from` in CT. */
export function nextTradingDay(from: Date): string {
  const ct = new Date(from.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  let d = new Date(ct.getFullYear(), ct.getMonth(), ct.getDate() + 1)
  while (d.getDay() === 0 || d.getDay() === 6) {
    d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)
  }
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

export async function openVertical(
  action: SetupAction,
  snap: GexSnapshot,
  config: BlazeConfig,
): Promise<OpenResult | null> {
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

  // Kelly cap × BP usage on current balance
  const balance = await getPaperBalance()
  const capitalAtRisk = balance * config.risk_per_trade_pct * config.buying_power_usage_pct
  const costPerContract = debit * 100
  const contracts = Math.max(1, Math.floor(capitalAtRisk / costPerContract))

  const position_id = await insertBlazePosition({
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
