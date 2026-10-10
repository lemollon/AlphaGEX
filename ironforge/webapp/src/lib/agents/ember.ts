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
