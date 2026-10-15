/**
 * EMBER — the single free agent for small accounts, like Spark/Flame on display but
 * free (§4/§5 10.4 design spec). Corrected 2026-10-04 (Leron, binding): there is NO
 * sub-agent picker. Customers see and enroll in ONE agent, EMBER — not a family with
 * REFLEX exposed anywhere in enrollment or dashboard copy.
 *
 * REFLEX is EMBER's internal execution engine (dev/meltup/ember/run_reflex.py) — never
 * named in customer-facing UI. It is a separate, ALREADY-ARMED live-equities sleeve on a
 * Robinhood "Agentic" account (570892331), executing a reactive-momentum squeeze signal
 * computed server-side by AlphaGEX/spreadworks (squeeze_reactive_alerts.py) and polled
 * read-only from https://spreadworks-backend.onrender.com/api/spreadworks/squeeze-reactive/state.
 * It is NOT wired to any ironforge/webapp API today — see the /agents/ember workspace
 * page for the honest empty state and the missing-endpoint note.
 *
 * Not Stripe-backed (no lookupKey/priceMonthly billing flow) — BOT_PLANS in
 * lib/billing/plans.ts stays spark/flame only. This file is display + enrollment-limits
 * config only.
 */

export const EMBER_AGENT = {
  id: 'ember' as const,
  name: 'Ember',
  /** Design spec §3: "Built for smaller accounts" / "Steady growth". */
  sub: 'Built for smaller accounts',
  blurb: 'Made for low-capital accounts and people new to investing. Aims for steady growth you can build on.',
  tags: ['$500–$2K accounts', 'One per person'] as const,
  /** --ember token (light/dark), from forge-tokens.css. */
  accent: '#b52fe0',
  accentDark: '#dd63ff',
  priceMonthly: 0,
  trialTradingDays: null, // "Always free" — no trial clock, per spec §3/§4
  limits: {
    accountsPerPerson: 1,
    minCapitalCents: 50_000, // $500
    maxCapitalCents: 200_000, // $2,000
  },
  /** Design spec §5 step-4 copy, verbatim. */
  balanceOutOfRangeCopy:
    "Ember needs a balance between $500 and $2,000. Adjust your balance or choose Spark or Flame.",
  balanceInRangeCopy: "Balance fits Ember's $500–$2,000 range.",
  liveHref: '/agents/ember',
}

export function isEmberCapitalInRange(buyingPowerCents: number | null | undefined): boolean {
  if (buyingPowerCents == null) return false
  return (
    buyingPowerCents >= EMBER_AGENT.limits.minCapitalCents &&
    buyingPowerCents <= EMBER_AGENT.limits.maxCapitalCents
  )
}

/**
 * Default per-account equity unlock threshold for EMBER auto-eligibility —
 * $500 (product decision, 2026-10-15: subscribed + equity >= this unlocks a
 * customer account), for consistency with SPARK ($5,000) and FLAME ($2,000)'s
 * own thresholds in tradier.ts.
 *
 * STANDALONE — NOT WIRED to any live path. EMBER has no customer-executor
 * mirror in this repo: CUSTOMER_AGENTS in executor.ts is
 * `Set(['spark', 'flame'])` only, and EMBER's actual execution engine (REFLEX,
 * dev/meltup/ember/run_reflex.py on a Robinhood "Agentic" account) is an
 * already-armed, separate sleeve outside ironforge/webapp — see this file's
 * header comment. EMBER is also currently paused by operator decision (failed
 * its own backtest validation at the $500 floor, 0 of 7 configurations
 * passed). This function exists only so EMBER's eligibility shape matches
 * SPARK/FLAME's; calling it has no effect on any order, arm switch, or pause
 * state. Do not wire this into REFLEX or any other execution path without an
 * explicit operator decision to un-pause EMBER first.
 */
export const EMBER_MIN_EQUITY_DEFAULT = 500

/**
 * EMBER_MIN_EQUITY — the per-account unlock threshold, in dollars. Default $500.
 * Env-overridable so a future decision can move it without a code change;
 * unparsable or non-positive falls back to the default rather than silently
 * unlocking at $0 — same convention as getSparkMinEquity()/getFlameMinEquity()
 * in tradier.ts.
 */
export function getEmberMinEquity(): number {
  const raw = Number(process.env.EMBER_MIN_EQUITY)
  if (!Number.isFinite(raw) || raw <= 0) return EMBER_MIN_EQUITY_DEFAULT
  return raw
}

/**
 * Per-customer-account EMBER eligibility: this account's own EMBER subscription
 * must be active AND its own current equity must clear EMBER_MIN_EQUITY. Mirrors
 * isSparkCustomerEligible()/isFlameCustomerEligible()'s shape exactly — fails
 * CLOSED on every input: `subscribed` must be exactly `true`, and `equity`
 * unreadable/non-finite never unlocks. See the STANDALONE note above — this is
 * not wired into EMBER's (REFLEX's) actual execution path.
 */
export function isEmberCustomerEligible(
  equity: number | null,
  subscribed: boolean,
  minEquity: number = getEmberMinEquity(),
): boolean {
  if (subscribed !== true) return false
  return equity != null && Number.isFinite(equity) && equity >= minEquity
}
