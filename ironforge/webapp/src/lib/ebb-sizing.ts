/**
 * EBB contract-count ladder — SPARK (AM 10:05) and FLAME (PM 13:05).
 *
 * THE RULE (Leron, 2026-09-04): the ladder is CONTRACT COUNT, never wing width.
 * Each bot's structure is fixed in botStructure() (SPARK spot-$2/$5, FLAME
 * spot-$1/$2). Account size changes ONLY how many lots run.
 *
 * WHY THESE RUNGS — measured, 2026-08-27 (`2026-08-27-flame-spark-spec-and-sizing.md`,
 * scripts scratchpad/ladder_survivors.py + deposit_ladder.py; 1 lot, net $0.70,
 * 2022-11-02 -> 2026-08-26, SPY expiry NBBO):
 *
 *   - Every EQUITY-keyed rule failed a 35%-of-account drawdown ceiling in at
 *     least one of three windows (full / 2025+ / 2026 YTD): either it breached
 *     once the account had grown, or on a fresh account it never left 1 lot.
 *   - The survivor keys on FUNDED CAPITAL (the ledger's starting_capital) and
 *     never re-reads equity. It is one ratio per bot, so every rung carries
 *     the same drawdown:
 *         FLAME  1 lot per $1,500 funded  -> 14.1 / 19.5 / 20.4 % DD, worst day -12.3%
 *         SPARK  1 lot per $5,000 funded  -> 11.8 / 23.2 / 23.1 % DD, worst day  -8.3%
 *     SPARK 2 lots at $5,000 breaches (40.3% in 2025+). FLAME tolerates ~17%
 *     max-loss exposure, SPARK only ~9% (ret/DD 1.87 vs 4.90).
 *
 * ROUNDING (Leron 2026-09-04): per-lot risk is not a round number, so the
 * count is ALWAYS floor()ed to whole contracts, never rounded up. $8,000 SPARK
 * is 1 lot, not 2. Below one rung the bot gets ZERO lots for that account —
 * the caller must skip, never fall back to 1.
 *
 * WHAT THE LADDER KEYS ON (ADR 0013, 2026-09-04): the HIGH-WATER equity of the
 * ledger, max(starting_capital, high_water_balance). It ratchets UP as the
 * account grows and NEVER down — sizing down in a drawdown was measured on
 * 2026-08-27 at $258/yr with a 54% drawdown (the de-lever rule). Never size
 * from current_balance alone. `ebbLadderCapital()` is the one place that
 * combines the two fields; both money paths go through it.
 *
 * THE CAP IS A LIQUIDITY GUARD, NOT A RISK KNOB (ADR 0013, backtest
 * `2026-09-04-uncapped-ladder-backtest.md`, high-water ladder at these rungs,
 * cap 5 / 10 / 20 / none, 2022-11 -> 2026-09, fresh account in each of three
 * windows): NO cap ever breached the 35% drawdown ceiling — worst FLAME 32.5%,
 * SPARK 29.3%, uncapped. Drawdown is bounded by the RUNG, not the cap. Leron
 * 2026-09-04: "the app is live, the time for 5 max is over" and "we are
 * expecting to get 100k accounts maybe more" ($100k = 20 SPARK lots / 66 FLAME
 * lots). So:
 *   - EBB_LADDER_CAP is 100: a static safety ceiling only, never the
 *     working limit.
 *   - The working limit is the LIQUIDITY check at entry: lots <= 25% of the
 *     displayed bid size of the put being SOLD (the live quote at the short
 *     strike). Fills above ~10 lots were never measured in the backtest (it
 *     fills every lot at NBBO with zero impact), so the book depth at entry is
 *     what makes size honest. `liquidityCappedLots()` does that; when the
 *     size is unavailable or 0 the count falls back to the ladder under the
 *     static cap and the caller logs liquidity=UNKNOWN.
 *
 * Changing any number here is a real-money risk change. `ebb-sizing.test.ts`
 * pins the rungs, the cap, the ratchet, the liquidity share and the rounding.
 */

export const FLAME_RUNG_USD = 1500
export const SPARK_RUNG_USD = 5000
/** Static safety ceiling per bot per account. NOT the working limit — see header. */
export const EBB_LADDER_CAP = 100
/** Share of the displayed bid size at the short strike a single entry may take. */
export const EBB_LIQUIDITY_SHARE = 0.25

export type EbbBot = 'spark' | 'flame'

export function isEbbLadderBot(name: string | undefined | null): name is EbbBot {
  return name === 'spark' || name === 'flame'
}

export function ebbRungUsd(bot: EbbBot): number {
  return bot === 'spark' ? SPARK_RUNG_USD : FLAME_RUNG_USD
}

function positiveOrNull(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) && n > 0 ? n : null
}

/**
 * The capital the ladder keys on: max(starting_capital, high_water_balance).
 *
 * - starting_capital is the funded seed (real broker equity at enrolment).
 * - high_water_balance is the ledger's peak current_balance, maintained with
 *   GREATEST() at every balance write, so it can only ratchet up.
 * - A missing / invalid high-water (pre-migration row, NULL, 0) means
 *   starting_capital alone; a missing starting_capital with a valid high-water
 *   keys on the high-water. Neither valid -> null, and the caller must SKIP.
 *
 * Never pass current_balance here. It is deliberately not an input.
 */
export function ebbLadderCapital(
  startingCapital: number | null | undefined,
  highWaterBalance: number | null | undefined,
): number | null {
  const s = positiveOrNull(startingCapital)
  const h = positiveOrNull(highWaterBalance)
  if (s === null && h === null) return null
  return Math.max(s ?? 0, h ?? 0)
}

/**
 * Contracts per trade for `bot` on an account whose ladder capital (see
 * ebbLadderCapital) is `ladderCapital`.
 * Returns 0 (not 1) when the account is below one rung or the input is
 * missing/invalid — a 0 means "do not trade this account", never "guess".
 */
export function ebbLadderContracts(bot: EbbBot, ladderCapital: number | null | undefined): number {
  if (typeof ladderCapital !== 'number' || !Number.isFinite(ladderCapital) || ladderCapital <= 0) return 0
  const lots = Math.floor(ladderCapital / ebbRungUsd(bot))
  return Math.max(0, Math.min(EBB_LADDER_CAP, lots))
}

export type EbbLiquidityStatus = 'ok' | 'capped' | 'unknown'

export interface EbbLiquidityResult {
  /** Lots to trade after the liquidity check. */
  lots: number
  /** 'ok' = ladder fit inside the share; 'capped' = the book was thinner than the ladder; 'unknown' = no size. */
  liquidity: EbbLiquidityStatus
  /** floor(share * displayedSize), or null when the size was unknown. */
  maxLots: number | null
  /** The displayed size the decision used (null when unknown). */
  displayedSize: number | null
}

/**
 * Liquidity check at entry (ADR 0013): lots = min(ladderLots, floor(share × displayedSize)).
 *
 * `displayedSize` is the bid size of the put being SOLD, from the live quote at
 * the moment of entry. Unavailable (null/undefined/NaN/negative) or ZERO size
 * is UNKNOWN — a quote with no size tells us nothing about the book, so the
 * count falls back to the ladder lots under EBB_LADDER_CAP and the caller must
 * log liquidity=UNKNOWN. It does NOT zero the trade.
 *
 * A real but tiny size (1-3 contracts at 25%) floors to 0 lots: the book
 * cannot absorb even one lot inside the share, so the caller skips. That is
 * the rule binding, not a fallback.
 *
 * Ladder lots <= 0 stay 0 regardless of the book.
 */
export function liquidityCappedLots(
  ladderLots: number,
  displayedSize: number | null | undefined,
  share: number = EBB_LIQUIDITY_SHARE,
): EbbLiquidityResult {
  const ladder = Number.isFinite(ladderLots) && ladderLots > 0
    ? Math.min(EBB_LADDER_CAP, Math.floor(ladderLots))
    : 0
  const size = positiveOrNull(displayedSize)
  if (size === null || !(share > 0)) {
    return { lots: ladder, liquidity: 'unknown', maxLots: null, displayedSize: null }
  }
  const maxLots = Math.floor(share * size)
  const lots = Math.max(0, Math.min(ladder, maxLots))
  return {
    lots,
    liquidity: lots < ladder ? 'capped' : 'ok',
    maxLots,
    displayedSize: size,
  }
}

/** One-line audit of a sizing decision — both money paths print this. */
export function formatEbbSizingLine(args: {
  funded: number | null
  highWater: number | null
  rung: number
  ladderLots: number
  liq: EbbLiquidityResult
  finalLots: number
}): string {
  const usd = (v: number | null) => (v === null ? 'NONE' : '$' + v.toFixed(0))
  return (
    `funded=${usd(args.funded)} high_water=${usd(args.highWater)} ` +
    `ladder_capital=${usd(ebbLadderCapital(args.funded, args.highWater))} rung=$${args.rung} ` +
    `ladder_lots=${args.ladderLots} displayed_size=${args.liq.displayedSize ?? 'UNKNOWN'} ` +
    `liquidity=${args.liq.liquidity.toUpperCase()} liquidity_capped_lots=${args.liq.lots} ` +
    `final_lots=${args.finalLots}`
  )
}
