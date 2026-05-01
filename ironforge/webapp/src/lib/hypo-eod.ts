/**
 * Hypothetical "exited at 2:59 PM CT" P&L helper for SPARK only.
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
  vix_at_entry?: number | null  // VIX %, used as IV proxy for the BS fallback
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
 * Compute the 2:59 PM CT hypothetical P&L for a single SPARK position.
 * Returns the result without writing to the DB — the caller persists.
 */
export async function computeHypoEodFor(pos: PositionMeta): Promise<HypoEodResult> {
  if (!isConfigured()) {
    return { position_id: pos.position_id, hypothetical_eod_pnl: null, hypothetical_eod_spot: null, computed: false, reason: 'tradier_not_configured' }
  }

  const occPs = buildOccSymbol(pos.ticker, pos.expiration, pos.put_short_strike, 'P')
  const occPl = buildOccSymbol(pos.ticker, pos.expiration, pos.put_long_strike, 'P')
  const occCs = buildOccSymbol(pos.ticker, pos.expiration, pos.call_short_strike, 'C')
  const occCl = buildOccSymbol(pos.ticker, pos.expiration, pos.call_long_strike, 'C')

  // Pull a generous window so we definitely cover the 14:59 bar even on
  // edge timezone days. session='all' here in case Tradier classifies the
  // late-session bar inconsistently — we filter by CT clock anyway.
  const [psBars, plBars, csBars, clBars, spyBars] = await Promise.all([
    getTimesales(occPs, 390, 'all', '1min').catch(() => []),
    getTimesales(occPl, 390, 'all', '1min').catch(() => []),
    getTimesales(occCs, 390, 'all', '1min').catch(() => []),
    getTimesales(occCl, 390, 'all', '1min').catch(() => []),
    getTimesales(pos.ticker, 390, 'all', '1min').catch(() => []),
  ])

  const psPx = findBarAt259CT(psBars, pos.close_date)
  const plPx = findBarAt259CT(plBars, pos.close_date)
  const csPx = findBarAt259CT(csBars, pos.close_date)
  const clPx = findBarAt259CT(clBars, pos.close_date)
  const spotPx = findBarAt259CT(spyBars, pos.close_date)

  if (psPx == null || plPx == null || csPx == null || clPx == null) {
    // Fallback path 1 — same-day-expiry: when close_date == expiration
    // (INFERNO 0DTE always; SPARK 1DTE only when closed on expiration day),
    // 2:59 PM CT is ~1 minute before settlement so remaining time value is
    // effectively zero. Use the IC's intrinsic value off the underlying
    // spot as the hypothetical exit price.
    if (spotPx != null && pos.close_date === pos.expiration) {
      const intrinsic = icIntrinsicAtExpiration(
        spotPx,
        pos.put_long_strike,
        pos.put_short_strike,
        pos.call_short_strike,
        pos.call_long_strike,
      )
      const pnlPerShare = pos.total_credit - intrinsic
      const pnl = Math.round(pnlPerShare * 100 * Math.max(1, pos.contracts) * 100) / 100
      return {
        position_id: pos.position_id,
        hypothetical_eod_pnl: pnl,
        hypothetical_eod_spot: Math.round(spotPx * 10000) / 10000,
        computed: true,
        reason: 'spot_intrinsic_fallback_same_day_expiry',
      }
    }

    // Fallback path 2 — Black-Scholes with VIX as IV proxy: when the close
    // happens BEFORE expiration (SPARK 1DTE typically closes day T-1 of a
    // T-expiration trade), per-leg quotes are missing from Tradier's
    // patchy intraday archive, but we have spot + the position's
    // vix_at_entry. Price each of the 4 legs with BS and combine into an
    // IC mid. This is an approximation — VIX is 30-day annualized SPX vol,
    // not SPY ATM vol on close day — but it gets us within ~$0.05-0.15 per
    // share on each leg, far better than leaving the row NULL.
    if (
      spotPx != null
      && pos.vix_at_entry != null
      && pos.vix_at_entry > 0
      && pos.close_date < pos.expiration
    ) {
      const T = yearsBetween259CtAnd3pmCt(pos.close_date, pos.expiration)
      if (T > 0) {
        const sigma = pos.vix_at_entry / 100
        const r = 0.05 // 1Y T-bill ballpark; option price is insensitive to r at small T
        const psPxBs = blackScholesPut(spotPx, pos.put_short_strike, T, r, sigma)
        const plPxBs = blackScholesPut(spotPx, pos.put_long_strike,  T, r, sigma)
        const csPxBs = blackScholesCall(spotPx, pos.call_short_strike, T, r, sigma)
        const clPxBs = blackScholesCall(spotPx, pos.call_long_strike,  T, r, sigma)
        const costToCloseBs = (psPxBs + csPxBs) - (plPxBs + clPxBs)
        const pnlPerShareBs = pos.total_credit - costToCloseBs
        const pnlBs = Math.round(pnlPerShareBs * 100 * Math.max(1, pos.contracts) * 100) / 100
        return {
          position_id: pos.position_id,
          hypothetical_eod_pnl: pnlBs,
          hypothetical_eod_spot: Math.round(spotPx * 10000) / 10000,
          computed: true,
          reason: 'black_scholes_vix_iv_approximation',
        }
      }
    }

    return {
      position_id: pos.position_id,
      hypothetical_eod_pnl: null,
      hypothetical_eod_spot: spotPx,
      computed: false,
      reason: 'leg_quotes_missing_at_2_59',
    }
  }

  // Cost to close = buy back the shorts, sell back the longs.
  // costToClose (per share) = (psPx + csPx) − (plPx + clPx)
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

/**
 * Fetch the underlying ticker's last RTH close price on a given CT calendar
 * date. Used by recover-phantom-trade to compute correct intrinsic P&L when
 * Tradier has no broker close-order history for an expired Iron Condor —
 * "no close fills" is NOT a safe proxy for "expired worthless" if the
 * underlying actually settled past one of the short strikes.
 *
 * Tradier's intraday timesales window is ~3 calendar days. For older
 * expirations this returns null and the caller must refuse to auto-recover.
 */
export async function getSpotCloseOnDate(
  ticker: string,
  dateCt: string,
): Promise<number | null> {
  // 3 sessions × 390 RTH minutes = 1170 bars. Pass a generous slice so the
  // target date's bars survive Tradier's "last N" trim across multi-session
  // windows.
  const bars = await getTimesales(ticker, 1170, 'open', '1min').catch(() => [])
  let lastClose: number | null = null
  let lastTime = 0
  for (const b of bars) {
    if (!b.time) continue
    const d = new Date(b.time)
    if (Number.isNaN(d.getTime())) continue
    if (ctDateString(d) !== dateCt) continue
    const t = d.getTime()
    if (t > lastTime) {
      lastTime = t
      lastClose = b.close
    }
  }
  return lastClose
}

/**
 * Per-share intrinsic value of an Iron Condor at expiration given the
 * underlying close price. Only one wing can be ITM at expiration; both
 * legs of the breached vertical contribute, capped at the spread width.
 *
 *   put_long < put_short < call_short < call_long  (bull put + bear call wings)
 *
 * Return value is the "cost to close" per share (always ≥ 0). Trader's
 * realized P&L per share = entry_credit − intrinsic.
 */
export function icIntrinsicAtExpiration(
  spot: number,
  putLong: number,
  putShort: number,
  callShort: number,
  callLong: number,
): number {
  const putItm = Math.max(0, Math.max(0, putShort - spot) - Math.max(0, putLong - spot))
  const callItm = Math.max(0, Math.max(0, spot - callShort) - Math.max(0, spot - callLong))
  return putItm + callItm
}

/**
 * Standard normal CDF via Abramowitz & Stegun 7.1.26 (max abs error 7.5e-8).
 * Avoids pulling in a stats dependency just for one function.
 */
function cumulativeNormal(x: number): number {
  const a1 =  0.254829592
  const a2 = -0.284496736
  const a3 =  1.421413741
  const a4 = -1.453152027
  const a5 =  1.061405429
  const p  =  0.3275911
  const sign = x < 0 ? -1 : 1
  const ax = Math.abs(x) / Math.SQRT2
  const t = 1 / (1 + p * ax)
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax)
  return 0.5 * (1 + sign * y)
}

function blackScholesCall(S: number, K: number, T: number, r: number, sigma: number): number {
  if (T <= 0 || sigma <= 0) return Math.max(0, S - K)
  const sqrtT = Math.sqrt(T)
  const d1 = (Math.log(S / K) + (r + (sigma * sigma) / 2) * T) / (sigma * sqrtT)
  const d2 = d1 - sigma * sqrtT
  return S * cumulativeNormal(d1) - K * Math.exp(-r * T) * cumulativeNormal(d2)
}

function blackScholesPut(S: number, K: number, T: number, r: number, sigma: number): number {
  if (T <= 0 || sigma <= 0) return Math.max(0, K - S)
  const sqrtT = Math.sqrt(T)
  const d1 = (Math.log(S / K) + (r + (sigma * sigma) / 2) * T) / (sigma * sqrtT)
  const d2 = d1 - sigma * sqrtT
  return K * Math.exp(-r * T) * cumulativeNormal(-d2) - S * cumulativeNormal(-d1)
}

/**
 * Years between 2:59 PM CT on `closeDateCt` and 3:00 PM CT on
 * `expirationDateCt`, using calendar time (weekend nights count). For SPY
 * ETF options, settlement is at market close = 3:00 PM CT. Returns 0 if
 * close >= expiration.
 *
 * Calendar-time is the right convention for BS pricing because options
 * decay through weekends too, even though the market doesn't trade.
 */
function yearsBetween259CtAnd3pmCt(closeDateCt: string, expirationDateCt: string): number {
  // Parse YYYY-MM-DD as midnight UTC, then offset by CT clock at 14:59 / 15:00.
  // Any consistent offset works since we only use the difference.
  const closeUtc  = Date.parse(`${closeDateCt}T19:59:00Z`)       // 14:59 CT (DST) ≈ 19:59 UTC
  const expiryUtc = Date.parse(`${expirationDateCt}T20:00:00Z`)  // 15:00 CT (DST) ≈ 20:00 UTC
  if (!Number.isFinite(closeUtc) || !Number.isFinite(expiryUtc)) return 0
  const diffMs = expiryUtc - closeUtc
  if (diffMs <= 0) return 0
  return diffMs / (365 * 24 * 3600 * 1000)
}
