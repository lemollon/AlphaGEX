/**
 * SPARK "Market Pulse" risk signals (Commit S1).
 *
 * Four beginner-friendly, profitability-focused indicators that help an
 * IC seller answer: "Is today a good day to sell premium, or am I about
 * to get run over?" Informational only — never affects trading logic.
 *
 *   1. PREMIUM QUALITY (IV Rank)
 *      Where today's VIX sits in its 12-month range. High rank = juicy
 *      credit, more cushion. Low rank = thin credit, worse risk/reward.
 *      Data: Tradier quote on VIX (uses week_52_high / week_52_low).
 *
 *   2. VOLATILITY PULSE (VIX rate of change)
 *      Live VIX minus VIX from 15m / 1h / 4h ago. Spikes are the fastest
 *      way for an open IC to go underwater. Data: vix_snapshots table
 *      (scanner writes once per cycle).
 *
 *   3. STRIKE DISTANCE (in standard deviations)
 *      How far SPY is from each short strike, measured in the same units
 *      the market uses to price options. <1σ = danger zone. Data: open
 *      SPARK position + live SPY + VIX.
 *
 *   4. REALIZED vs EXPECTED (today's move ratio)
 *      Today's actual SPY range / today's option-priced expected range.
 *      <0.5 = IC is winning. >1.5 = IC is losing.  Data: SPY intraday
 *      high/low via Tradier timesales + expected move from VIX.
 *
 * No scanner trading changes. No new env vars.
 */
import { dbQuery, botTable, dteMode } from './db'
import { getRawQuotes, getTimesales, isConfigured } from './tradier'

// ── Types ──────────────────────────────────────────────────────────────

/** Color tier for each signal. Green = favorable. Amber = caution.
 *  Red = hostile.  Grey = insufficient data (don't alarm the user). */
export type SignalColor = 'green' | 'amber' | 'red' | 'grey'

export interface SignalTile {
  key: 'premium_quality' | 'vol_pulse' | 'strike_distance' | 'move_ratio'
  title: string
  color: SignalColor
  /** One- or two-line summary shown in the tile header. */
  headline: string
  /** Compact numeric context (e.g. "19.3 / 15.0–28.0"). May be empty. */
  numbers: string
  /** Beginner explanation (1-3 sentences). Ties directly to profitability. */
  beginner: string
  /** Structured numeric values the UI/prompt can reuse. */
  values: Record<string, number | string | null>
}

export interface RiskSignalsResponse {
  generated_at: string
  spy_price: number | null
  vix: number | null
  /** Does SPARK have a live IC open right now? */
  has_open_position: boolean
  tiles: SignalTile[]
}

// ── Signal computations ────────────────────────────────────────────────

interface Quote52Week {
  last: number | null
  week_52_high: number | null
  week_52_low: number | null
  /** Change from prior close, in raw points (not %). */
  change: number | null
}

function extractQuote(quotes: Record<string, Record<string, unknown>>, sym: string): Quote52Week {
  const q = quotes[sym]
  if (!q) return { last: null, week_52_high: null, week_52_low: null, change: null }
  const numField = (k: string): number | null => {
    const v = q[k]
    if (v == null || v === '') return null
    const n = typeof v === 'number' ? v : parseFloat(String(v))
    return Number.isFinite(n) ? n : null
  }
  return {
    last: numField('last'),
    week_52_high: numField('week_52_high'),
    week_52_low: numField('week_52_low'),
    change: numField('change'),
  }
}

/** 1. Premium Quality — IV Rank via VIX 52wk range. */
function computePremiumQuality(vix: Quote52Week): SignalTile {
  const last = vix.last
  const hi = vix.week_52_high
  const lo = vix.week_52_low
  const change = vix.change
  let rank: number | null = null
  if (last != null && hi != null && lo != null && hi > lo) {
    rank = Math.round(((last - lo) / (hi - lo)) * 100)
  }
  let color: SignalColor = 'grey'
  let headline = ''
  let beginner = ''
  if (rank == null) {
    headline = 'Insufficient VIX data'
    beginner = 'We need a valid VIX quote with 52-week high/low to rank today\'s premium level. Check Tradier connectivity.'
  } else if (rank >= 50) {
    color = 'green'
    headline = `Juicy premium — IV Rank ${rank}%`
    beginner =
      `Good day to sell premium: VIX (${last!.toFixed(2)}) sits in the upper half of its 12-month range. ` +
      `Buyers are scared → paying up for protection → SPARK collects a fatter credit for the same structure. ` +
      `High-IV-Rank entries historically have the best risk/reward for short ICs because vol tends to mean-revert.`
  } else if (rank >= 25) {
    color = 'amber'
    headline = `Moderate premium — IV Rank ${rank}%`
    beginner =
      `VIX at ${last!.toFixed(2)} is in the middle of its 12-month range. Credits are average; not juicy, not ` +
      `terrible. Your max profit on the IC will be roughly in line with SPARK's historical avg. ` +
      `Nothing special about today — trade only if other signals align.`
  } else {
    color = 'red'
    headline = `Thin premium — IV Rank ${rank}%`
    beginner =
      `Bad day to sell premium: VIX (${last!.toFixed(2)}) is near its 12-month low. ` +
      `You're selling options for cheap — same max loss, smaller max profit. Also, when vol is this compressed ` +
      `it tends to expand, which hurts open short ICs fast. Historical edge is thin; consider sitting out.`
  }
  return {
    key: 'premium_quality',
    title: 'Premium Quality',
    color,
    headline,
    numbers: last != null && hi != null && lo != null
      ? `${last.toFixed(2)} in range ${lo.toFixed(1)}–${hi.toFixed(1)}`
      : '',
    beginner,
    values: {
      vix: last,
      vix_week_52_high: hi,
      vix_week_52_low: lo,
      iv_rank_pct: rank,
      vix_change_today: change,
    },
  }
}

interface VixSnapshot { ts: Date; vix: number | null }

/**
 * 2. Volatility Pulse — ΔVIX over 15m / 1h / 4h windows, signal off the
 * most alarming timeframe.
 */
async function computeVolPulse(currentVix: number | null): Promise<SignalTile> {
  // Fetch last 4h of snapshots (≤240 rows at 1-min cadence). Small.
  let snaps: VixSnapshot[] = []
  try {
    const rows = await dbQuery(
      `SELECT ts, vix FROM vix_snapshots
       WHERE ts >= NOW() - INTERVAL '4 hours' AND vix IS NOT NULL
       ORDER BY ts DESC`,
    )
    snaps = rows.map((r) => ({
      ts: r.ts instanceof Date ? r.ts : new Date(r.ts),
      vix: r.vix != null ? Number(r.vix) : null,
    }))
  } catch { /* table may not exist on brand-new deploys */ }

  const findBackAt = (minsAgo: number): number | null => {
    const target = Date.now() - minsAgo * 60_000
    // snaps is newest-first. Find the first snap whose ts ≤ target.
    for (const s of snaps) {
      if (s.ts.getTime() <= target && s.vix != null) return s.vix
    }
    return null
  }
  const vix15 = findBackAt(15)
  const vix60 = findBackAt(60)
  const vix240 = findBackAt(240)
  const d15 = currentVix != null && vix15 != null ? Math.round((currentVix - vix15) * 100) / 100 : null
  const d60 = currentVix != null && vix60 != null ? Math.round((currentVix - vix60) * 100) / 100 : null
  const d240 = currentVix != null && vix240 != null ? Math.round((currentVix - vix240) * 100) / 100 : null

  // Signal off the biggest single-timeframe jump.
  const maxJump = Math.max(Math.abs(d15 ?? 0), Math.abs(d60 ?? 0), Math.abs(d240 ?? 0))
  let color: SignalColor = 'grey'
  let headline = ''
  let beginner = ''
  if (snaps.length < 3 || currentVix == null) {
    headline = 'Building VIX history…'
    beginner = 'Need ~15 minutes of VIX snapshots for the rate-of-change math. Come back after the scanner has run a few cycles today.'
  } else if (maxJump >= 2.0 && (d15 ?? 0) > 0) {
    color = 'red'
    headline = `Vol spiking — ΔVIX ${d15! >= 0 ? '+' : ''}${d15!.toFixed(2)} in 15m`
    beginner =
      `Fear is accelerating fast. Every option in your short IC just got more expensive to buy back, which ` +
      `means your unrealized P&L is dropping even if SPY hasn't moved much. This is the scenario that turns ` +
      `winning ICs into losers quickly. Watch your position carefully; the sliding PT won't help when cost-to-close ` +
      `is racing away from the threshold.`
  } else if (maxJump >= 1.0 && (d60 ?? 0) > 0) {
    color = 'amber'
    headline = `Vol rising — ΔVIX +${(d60 ?? 0).toFixed(2)} in 1h`
    beginner =
      `Vol is trending up but not panicking. Your IC is bleeding a little per hour as options reprice higher, ` +
      `but theta (time decay) is still working in your favor. Nothing to do yet; just watch if it accelerates above +2 ` +
      `points in 15 minutes.`
  } else {
    color = 'green'
    headline = `Vol stable — ΔVIX ${(d60 ?? 0) >= 0 ? '+' : ''}${(d60 ?? 0).toFixed(2)} / hr`
    beginner =
      `Vol is calm. Your short options are quietly losing value (good — that's the entire point of an IC) and ` +
      `SPARK's PT target is getting closer with every passing minute. Keep an eye on sudden jumps but right now ` +
      `time is on your side.`
  }
  return {
    key: 'vol_pulse',
    title: 'Volatility Pulse',
    color,
    headline,
    numbers: [
      d15 != null ? `15m: ${d15 >= 0 ? '+' : ''}${d15.toFixed(2)}` : '',
      d60 != null ? `1h: ${d60 >= 0 ? '+' : ''}${d60.toFixed(2)}` : '',
      d240 != null ? `4h: ${d240 >= 0 ? '+' : ''}${d240.toFixed(2)}` : '',
    ].filter(Boolean).join('  '),
    beginner,
    values: {
      current_vix: currentVix,
      vix_15m_ago: vix15,
      vix_60m_ago: vix60,
      vix_240m_ago: vix240,
      delta_15m: d15,
      delta_60m: d60,
      delta_240m: d240,
      snapshot_count: snaps.length,
    },
  }
}

interface OpenPosition {
  put_short: number
  call_short: number
  expiration: string
}

/** 3. Strike Distance — SDs to each short strike. */
async function computeStrikeDistance(bot: string, spy: number | null, vix: number | null): Promise<SignalTile> {
  let pos: OpenPosition | null = null
  try {
    const dte = dteMode(bot)
    const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''
    const rows = await dbQuery(
      `SELECT put_short_strike, call_short_strike, expiration
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}
       ORDER BY open_time DESC NULLS LAST
       LIMIT 1`,
    )
    if (rows.length > 0) {
      const r = rows[0]
      const exp = r.expiration instanceof Date
        ? r.expiration.toISOString().slice(0, 10)
        : String(r.expiration).slice(0, 10)
      pos = {
        put_short: Number(r.put_short_strike),
        call_short: Number(r.call_short_strike),
        expiration: exp,
      }
    }
  } catch { /* table may not exist yet */ }

  if (!pos) {
    return {
      key: 'strike_distance',
      title: 'Strike Distance',
      color: 'grey',
      headline: `No open ${bot.toUpperCase()} position`,
      numbers: '',
      beginner:
        `${bot.toUpperCase()} doesn\'t have a live position right now, so there are no strikes to measure distance to. ` +
        `When a trade is open this tile will show how many standard deviations SPY is from each short strike. ` +
        `Under 1 SD is the danger zone.`,
      values: { put_short: null, call_short: null, sd_put: null, sd_call: null },
    }
  }
  if (spy == null || vix == null) {
    return {
      key: 'strike_distance',
      title: 'Strike Distance',
      color: 'grey',
      headline: 'Waiting for SPY/VIX quote',
      numbers: '',
      beginner: 'Strike distance needs a live SPY and VIX quote to compute the standard-deviation range.',
      values: { put_short: pos.put_short, call_short: pos.call_short, sd_put: null, sd_call: null },
    }
  }

  // Days to expiration
  const nowUtc = Date.now()
  const expUtc = Date.parse(`${pos.expiration}T20:00:00Z`) // SPY options expire ~4PM ET ≈ 20:00 UTC
  const daysToExp = Math.max(0.04, (expUtc - nowUtc) / (86_400_000))
  // Expected move (dollars) = SPY × (VIX/100) × sqrt(DTE/252)
  const expMove = spy * (vix / 100) * Math.sqrt(daysToExp / 252)
  const sdPut = expMove > 0 ? Math.round(((spy - pos.put_short) / expMove) * 100) / 100 : null
  // FLAME (2-leg put credit spread) stores call strikes as 0 — treat that
  // as "no call leg" and only show the put-side distance.
  const hasCallLeg = pos.call_short > 0
  const sdCall = (expMove > 0 && hasCallLeg)
    ? Math.round(((pos.call_short - spy) / expMove) * 100) / 100
    : null
  const minSd = sdPut != null && (hasCallLeg ? sdCall != null : true)
    ? hasCallLeg
      ? Math.min(Math.abs(sdPut), Math.abs(sdCall!))
      : Math.abs(sdPut)
    : null

  let color: SignalColor = 'green'
  let beginner = ''
  if (minSd == null) {
    color = 'grey'
    beginner = 'Could not compute SD distance — likely missing SPY/VIX data.'
  } else if (minSd < 1.0) {
    color = 'red'
    beginner =
      `SPY is less than 1 standard deviation from one of your short strikes. In market terms, the OPTIONS ` +
      `themselves say there is a meaningful (>30%) chance of a breach today. This is the danger zone — ` +
      `cost-to-close will explode if SPY moves further in that direction. SPARK's sliding PT will NOT save you ` +
      `here; the position has to be managed by its stop-loss or EOD cutoff.`
  } else if (minSd < 1.5) {
    color = 'amber'
    beginner =
      `One of your short strikes is 1.0-1.5 SDs away. Not imminent, but one typical daily move in the wrong ` +
      `direction closes the gap. If the Volatility Pulse tile also goes amber/red while this is happening, ` +
      `you\'re stacking risk.`
  } else {
    color = 'green'
    beginner =
      `Both short strikes are more than 1.5 SDs away. The options market is pricing roughly a 13% combined chance ` +
      `of breach — your statistical edge is healthy. Let theta (time decay) do its work; the IC is in its ` +
      `happy place.`
  }
  return {
    key: 'strike_distance',
    title: 'Strike Distance',
    color,
    headline:
      sdPut != null && sdCall != null
        ? `Put ${sdPut.toFixed(1)}σ · Call ${sdCall.toFixed(1)}σ`
        : sdPut != null
          ? `Put ${sdPut.toFixed(1)}σ`
          : 'Distances unavailable',
    numbers: spy != null && expMove > 0 ? `SPY $${spy.toFixed(2)} · ±$${expMove.toFixed(2)} exp move` : '',
    beginner,
    values: {
      spy,
      put_short: pos.put_short,
      call_short: pos.call_short,
      expected_move_dollars: Math.round(expMove * 100) / 100,
      sd_put: sdPut,
      sd_call: sdCall,
      min_sd: minSd,
      days_to_expiration: Math.round(daysToExp * 10000) / 10000,
    },
  }
}

/** 4. Realized vs Expected — today's actual range vs option-priced range. */
async function computeMoveRatio(spy: number | null, vix: number | null): Promise<SignalTile> {
  if (spy == null || vix == null) {
    return {
      key: 'move_ratio',
      title: "Today's Move vs Expected",
      color: 'grey',
      headline: 'Waiting for SPY/VIX quote',
      numbers: '',
      beginner: `Need a live SPY + VIX quote to compute today\'s realized vs expected move.`,
      values: { spy, vix, expected_today: null, realized_today: null, ratio: null },
    }
  }

  // Today's expected 1-day move (1 trading day = 1/252 of a year)
  const expectedToday = spy * (vix / 100) * Math.sqrt(1 / 252)

  // Today's realized range from SPY RTH timesales
  let realizedToday: number | null = null
  try {
    const candles = await getTimesales('SPY', 390, 'open', '5min')
    if (candles.length > 0) {
      const high = Math.max(...candles.map((c) => c.high))
      const low = Math.min(...candles.map((c) => c.low))
      realizedToday = Math.round((high - low) * 10000) / 10000
    }
  } catch { /* Tradier transient — leave null */ }

  const ratio = realizedToday != null && expectedToday > 0
    ? Math.round((realizedToday / expectedToday) * 100) / 100
    : null

  let color: SignalColor = 'green'
  let beginner = ''
  if (ratio == null) {
    color = 'grey'
    beginner = 'Not enough intraday data yet to compute the realized-vs-expected ratio. Usually valid by ~9 AM CT.'
  } else if (ratio >= 1.5) {
    color = 'red'
    beginner =
      `SPY has already moved ${ratio.toFixed(1)}x more than option prices predicted for today. Vol is ` +
      `under-priced — and SPARK sells over-priced vol for a living, so this is the wrong-way trade. Every ` +
      `candle that extends the range makes the IC bleed. Expect cost-to-close to stay elevated.`
  } else if (ratio >= 1.0) {
    color = 'amber'
    beginner =
      `SPY has moved about what option prices predicted (${ratio.toFixed(1)}x). IC is roughly break-even on ` +
      `the "vol realization" dimension — your PnL depends on where price settles rather than expansion/contraction ` +
      `of vol itself.`
  } else if (ratio >= 0.5) {
    color = 'green'
    beginner =
      `SPY has moved less than option prices predicted (${ratio.toFixed(1)}x). Options were too expensive — ` +
      `this is the tailwind SPARK wants. Keep an eye on the close; this tends to hold through EOD most days.`
  } else {
    color = 'green'
    beginner =
      `Unusually quiet day: SPY has moved only ${ratio.toFixed(1)}x the expected range. Options were vastly ` +
      `over-priced. Your short IC is collecting decay at full speed; this is the best kind of session for ` +
      `premium sellers.`
  }
  return {
    key: 'move_ratio',
    title: "Today's Move vs Expected",
    color,
    headline:
      ratio != null
        ? `Realized ${ratio.toFixed(1)}× expected`
        : 'Computing…',
    numbers:
      expectedToday > 0 && realizedToday != null
        ? `$${realizedToday.toFixed(2)} actual · ±$${expectedToday.toFixed(2)} expected`
        : '',
    beginner,
    values: {
      spy,
      vix,
      expected_today_dollars: Math.round(expectedToday * 100) / 100,
      realized_today_dollars: realizedToday,
      ratio,
    },
  }
}

// ── Public orchestrator ────────────────────────────────────────────────

export async function getRiskSignals(bot: string = 'spark'): Promise<RiskSignalsResponse> {
  if (!isConfigured()) {
    return {
      generated_at: new Date().toISOString(),
      spy_price: null,
      vix: null,
      has_open_position: false,
      tiles: [],
    }
  }
  const quotes = await getRawQuotes(['SPY', 'VIX', 'VVIX']).catch(() => ({}))
  const spyQuote = extractQuote(quotes, 'SPY')
  const vixQuote = extractQuote(quotes, 'VIX')

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''
  const hasOpenPos = await dbQuery(
    `SELECT COUNT(*) AS n FROM ${botTable(bot, 'positions')} WHERE status = 'open' ${dteFilter}`,
  ).then((rows) => Number(rows[0]?.n ?? 0) > 0).catch(() => false)

  const [premium, volPulse, strikeDist, moveRatio] = await Promise.all([
    Promise.resolve(computePremiumQuality(vixQuote)),
    computeVolPulse(vixQuote.last),
    computeStrikeDistance(bot, spyQuote.last, vixQuote.last),
    computeMoveRatio(spyQuote.last, vixQuote.last),
  ])

  return {
    generated_at: new Date().toISOString(),
    spy_price: spyQuote.last,
    vix: vixQuote.last,
    has_open_position: hasOpenPos,
    tiles: [premium, volPulse, strikeDist, moveRatio],
  }
}
