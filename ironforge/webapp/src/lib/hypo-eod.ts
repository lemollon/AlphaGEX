/**
 * Hypothetical "exited at 2:59 PM CT" P&L helper. Used by SPARK (1DTE IC),
 * INFERNO (0DTE IC), and FLAME (2DTE put-credit spread). PCS positions have
 * call_short_strike = call_long_strike = 0 and use 2-leg math.
 *
 * Why this exists:
 *   SPARK is a 1DTE same-day-exit bot. It opens a position on day T and
 *   closes by 2:50 PM CT on day T via sliding PT tiers (30%/20%/15% of
 *   credit) or EOD force-close. The early-tier exits leave money on the
 *   table when price stays in the profit zone. To measure how much the
 *   PT discipline costs us, we compute a counterfactual: "what would the
 *   P&L have been if we'd held until 2:59 PM CT (1 minute before market
 *   close)?" Stored alongside the actual realized P&L for every closed
 *   SPARK trade so historical analysis can A/B "did our early exit beat
 *   or trail the late-day hold?"
 *
 * How:
 *   1. Look up SPARK position metadata (4 strikes, contracts, credit, close date)
 *   2. Build OCC symbols for all 4 legs at the original expiration
 *   3. For each leg, fetch Tradier 1-min timesales on the close date and
 *      pull the bar at 14:59 CT (= 19:59 UTC during DST, 20:59 UTC standard)
 *   4. Use that bar's `close` price as the leg's mid (cheap proxy — the bar
 *      represents the last traded prints in that minute)
 *   5. Cost to close (per share) = (short_put + short_call) − (long_put + long_call)
 *   6. Hypothetical P&L = (entry_credit − cost_to_close) × 100 × contracts
 *
 *   Also fetches SPY's 14:59 bar for `hypothetical_eod_spot` (reference column,
 *   useful when eyeballing why a particular trade's hypothetical was high or low).
 *
 * Tradier limit: option timesales is available for ~40 days back. Rows with
 * close_time older than that get `hypothetical_eod_computed_at = NOW()` and
 * `hypothetical_eod_pnl = NULL` so we don't keep retrying them on every cron.
 */
import { buildOccSymbol, getTimesales, isConfigured } from './tradier'

interface PositionMeta {
  position_id: string
  ticker: string
  expiration: string         // 'YYYY-MM-DD'
  put_short_strike: number
  put_long_strike: number
  call_short_strike: number
  call_long_strike: number
  contracts: number
  total_credit: number       // per-contract dollars (e.g. 0.41)
  close_date: string         // 'YYYY-MM-DD' (CT calendar date of close_time)
}

export interface HypoEodResult {
  position_id: string
  hypothetical_eod_pnl: number | null
  hypothetical_eod_spot: number | null
  computed: boolean
  reason?: string
}

/** "YYYY-MM-DD" in CT for a given Date. */
export function ctDateString(d: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(d)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '00'
  return `${get('year')}-${get('month')}-${get('day')}`
}

/**
 * Find the bar in `series` whose timestamp matches 14:59 CT on `closeDate`.
 * Tradier timestamps are unambiguous UTC ISO (post-Commit I), so we compare
 * against the UTC instant equivalent of 14:59 CT.
 *
 * Returns the bar's close price, or null if no bar within ±2 minutes was found.
 */
function findBarAt259CT(
  series: Array<{ time: string; open: number; high: number; low: number; close: number }>,
  closeDate: string,
): number | null {
  // 14:59 CT = 19:59 UTC during DST (Mar–Nov) or 20:59 UTC standard time.
  // Easiest check: build the target instant via toLocaleString and look up
  // the bar whose CT-formatted time matches "14:59" on closeDate.
  for (const b of series) {
    if (!b.time) continue
    const d = new Date(b.time)
    if (Number.isNaN(d.getTime())) continue
    const dateCt = ctDateString(d)
    if (dateCt !== closeDate) continue
    const hhmm = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(d)
    if (hhmm === '14:59') return b.close
  }
  // Fallback: closest bar within the closeDate window (last bar of session)
  let lastClose: number | null = null
  for (const b of series) {
    if (!b.time) continue
    const d = new Date(b.time)
    if (Number.isNaN(d.getTime())) continue
    if (ctDateString(d) === closeDate) lastClose = b.close
  }
  return lastClose
}

/**
 * Compute the 2:59 PM CT hypothetical P&L for a single position. Handles both
 * 4-leg Iron Condors (SPARK / INFERNO) and 2-leg put-credit spreads (FLAME,
 * which stores call_short_strike = call_long_strike = 0). Returns the result
 * without writing to the DB — the caller persists.
 */
export async function computeHypoEodFor(pos: PositionMeta): Promise<HypoEodResult> {
  if (!isConfigured()) {
    return { position_id: pos.position_id, hypothetical_eod_pnl: null, hypothetical_eod_spot: null, computed: false, reason: 'tradier_not_configured' }
  }

  const isPutSpread = pos.call_short_strike === 0 && pos.call_long_strike === 0
  const occPs = buildOccSymbol(pos.ticker, pos.expiration, pos.put_short_strike, 'P')
  const occPl = buildOccSymbol(pos.ticker, pos.expiration, pos.put_long_strike, 'P')

  // Pull a generous window so we definitely cover the 14:59 bar even on
  // edge timezone days. session='all' here in case Tradier classifies the
  // late-session bar inconsistently — we filter by CT clock anyway.
  const baseFetches: Array<Promise<Array<{ time: string; open: number; high: number; low: number; close: number }>>> = [
    getTimesales(occPs, 390, 'all', '1min').catch(() => []),
    getTimesales(occPl, 390, 'all', '1min').catch(() => []),
    getTimesales(pos.ticker, 390, 'all', '1min').catch(() => []),
  ]
  const callFetches: Array<Promise<Array<{ time: string; open: number; high: number; low: number; close: number }>>> = isPutSpread
    ? []
    : [
        getTimesales(buildOccSymbol(pos.ticker, pos.expiration, pos.call_short_strike, 'C'), 390, 'all', '1min').catch(() => []),
        getTimesales(buildOccSymbol(pos.ticker, pos.expiration, pos.call_long_strike, 'C'), 390, 'all', '1min').catch(() => []),
      ]
  const allBars = await Promise.all([...baseFetches, ...callFetches])
  const [psBars, plBars, spyBars, csBars, clBars] = allBars

  const psPx = findBarAt259CT(psBars, pos.close_date)
  const plPx = findBarAt259CT(plBars, pos.close_date)
  const spotPx = findBarAt259CT(spyBars, pos.close_date)
  const csPx = isPutSpread ? 0 : (csBars ? findBarAt259CT(csBars, pos.close_date) : null)
  const clPx = isPutSpread ? 0 : (clBars ? findBarAt259CT(clBars, pos.close_date) : null)

  if (psPx == null || plPx == null || csPx == null || clPx == null) {
    return {
      position_id: pos.position_id,
      hypothetical_eod_pnl: null,
      hypothetical_eod_spot: spotPx,
      computed: false,
      reason: 'leg_quotes_missing_at_2_59',
    }
  }

  // Cost to close = buy back the shorts, sell back the longs.
  // 4-leg IC: costToClose (per share) = (psPx + csPx) − (plPx + clPx)
  // 2-leg PCS: csPx = clPx = 0, so costToClose = psPx − plPx
  // P&L (per share) = entry_credit − costToClose
  const costToClose = (psPx + csPx) - (plPx + clPx)
  const pnlPerShare = pos.total_credit - costToClose
  const pnl = Math.round(pnlPerShare * 100 * Math.max(1, pos.contracts) * 100) / 100

  return {
    position_id: pos.position_id,
    hypothetical_eod_pnl: pnl,
    hypothetical_eod_spot: spotPx != null ? Math.round(spotPx * 10000) / 10000 : null,
    computed: true,
  }
}
