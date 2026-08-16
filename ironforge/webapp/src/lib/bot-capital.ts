/**
 * PER-BOT PAPER SEED — the single source of truth for starting capital.
 *
 * This number lived in THREE places that could disagree: `DEFAULT_CONFIG` in
 * scanner.ts (what the bot actually sizes off), `DEFAULTS` in the config route
 * (what the API and config UI publish), and `DEFAULT_STARTING_CAPITAL` in
 * account-basis.ts (a flat 10000 used whenever no ledger row matches the scope).
 *
 * That third one is why every dashboard read $10,000 for FLAME and SPARK right
 * after the EBB cutover: moving to dte_mode 0DTE started a clean ledger, no
 * paper_account row matched yet, and the fallback published a number that
 * belonged to no bot. Divergence between the first two is the same failure that
 * orphaned the old config — see the note in db.ts's dteMode().
 *
 * All three now import from here. Change a seed HERE and nowhere else.
 *
 * 🚨 This is the PAPER SEED, not a live balance. syncSandboxCapital() writes it
 * back to {bot}_paper_account every scan cycle, so editing that row by hand does
 * nothing — the scanner syncs it straight back.
 */
export const BOT_STARTING_CAPITAL: Record<string, number> = {
  // EBB PM tranche. $2,000 is the real tier and it is the NARROW WING that makes
  // it viable: PM 13:05 / short spot-$1 / $2 wing on $2,000 measured maxDD $490
  // = 24% of the account, ret/DD 4.86, 5 of 5 years, max loss $169/day = 8%.
  // The $3,000 "registered minimum" it replaced was computed on the $5 wing,
  // where a single max-loss day is ~$484 and $2,000 genuinely does not clear.
  flame: 2000,
  // EBB AM tranche.
  spark: 5000,
  inferno: 10000,
  kindle: 490,
  forge: 5000,
  spark2: 10000,
}

/** Fallback for a bot with no entry above (should not happen for live bots). */
export const DEFAULT_STARTING_CAPITAL = 10000

export function startingCapitalFor(bot: string): number {
  return BOT_STARTING_CAPITAL[bot] ?? DEFAULT_STARTING_CAPITAL
}
