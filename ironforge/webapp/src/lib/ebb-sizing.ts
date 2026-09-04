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
 * Cap 5 lots per bot per account: the study only scored up to 5 and the
 * 8/3 loss (25 contracts, -$10,500) came from an uncapped path.
 *
 * Changing any number here is a real-money risk change. `ebb-sizing.test.ts`
 * pins the rungs and the rounding.
 */

export const FLAME_RUNG_USD = 1500
export const SPARK_RUNG_USD = 5000
export const EBB_LADDER_CAP = 5

export type EbbBot = 'spark' | 'flame'

export function isEbbLadderBot(name: string | undefined | null): name is EbbBot {
  return name === 'spark' || name === 'flame'
}

export function ebbRungUsd(bot: EbbBot): number {
  return bot === 'spark' ? SPARK_RUNG_USD : FLAME_RUNG_USD
}

/**
 * Contracts per trade for `bot` on an account funded with `fundedCapital`.
 * Returns 0 (not 1) when the account is below one rung or the input is
 * missing/invalid — a 0 means "do not trade this account", never "guess".
 */
export function ebbLadderContracts(bot: EbbBot, fundedCapital: number | null | undefined): number {
  if (typeof fundedCapital !== 'number' || !Number.isFinite(fundedCapital) || fundedCapital <= 0) return 0
  const lots = Math.floor(fundedCapital / ebbRungUsd(bot))
  return Math.max(0, Math.min(EBB_LADDER_CAP, lots))
}
