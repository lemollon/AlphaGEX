/**
 * Risk-assessment scoring (onboarding suitability → recommended bot).
 *
 * Pure + dependency-free so it is unit-testable and shared by the questionnaire UI and
 * the submit route. Answers are stored by question `key` → option `id` (never display
 * text), so copy can change without breaking scoring or stored data.
 */

export interface RiskOption {
  id: string
  label: string
  points: number
}

export interface RiskQuestion {
  key: string
  label: string
  options: RiskOption[]
}

export const RISK_QUESTIONS: RiskQuestion[] = [
  {
    key: 'experience',
    label: 'Your experience trading options',
    options: [
      { id: 'none', label: 'None', points: 0 },
      { id: 'some', label: 'Some — under 2 years', points: 2 },
      { id: 'experienced', label: 'Experienced — 2+ years', points: 4 },
    ],
  },
  {
    key: 'goal',
    label: 'Your primary goal',
    options: [
      { id: 'preserve', label: 'Preserve capital', points: 0 },
      { id: 'steady', label: 'Steady growth', points: 2 },
      { id: 'aggressive', label: 'Aggressive growth', points: 4 },
    ],
  },
  {
    key: 'tolerance',
    label: 'Your risk tolerance',
    options: [
      { id: 'avoid', label: 'Avoid losses', points: 0 },
      { id: 'moderate', label: 'Accept moderate swings', points: 2 },
      { id: 'large', label: 'Comfortable with large swings for higher return', points: 4 },
    ],
  },
  {
    key: 'drawdown',
    label: 'If your account dropped 20% in a week, you would',
    options: [
      { id: 'sell', label: 'Sell to stop losses', points: 0 },
      { id: 'hold', label: 'Hold', points: 2 },
      { id: 'add', label: 'Add more', points: 4 },
    ],
  },
  {
    key: 'capacity',
    label: 'This money represents',
    options: [
      { id: 'critical', label: 'A large or critical portion of my savings', points: 0 },
      { id: 'moderate', label: 'A moderate portion', points: 2 },
      { id: 'small', label: 'A small slice I can afford to lose', points: 4 },
    ],
  },
  {
    key: 'horizon',
    label: 'Your style and availability to monitor',
    options: [
      { id: 'longterm', label: 'Long-term, hands-off', points: 0 },
      { id: 'weekly', label: 'Active weekly', points: 2 },
      { id: 'daily', label: 'Daily, fast-paced', points: 4 },
    ],
  },
]

export type RiskAnswers = Record<string, string> // question key → option id
export type RiskTier = 'Conservative' | 'Moderate' | 'Aggressive'
/**
 * Only bots a customer can actually subscribe to (BOT_PLANS: spark, flame).
 *
 * INFERNO was in this union and was what the Aggressive tier recommended, but it is
 * an INTERNAL 0DTE bot and has never been a customer product. So the risk step told
 * an Aggressive customer to run a bot no page will sell them, and /onboarding/complete
 * — which only highlights SPARK/FLAME — then showed them no recommendation at all.
 * Keep this union limited to purchasable strategies; a recommendation that cannot be
 * bought is worse than none.
 */
export type RecommendedBot = 'FLAME' | 'SPARK'

export interface RiskProfile {
  score: number
  tier: RiskTier
  recommendedBot: RecommendedBot
  caution: boolean
}

/**
 * Why the quiz recommends this bot. Renders on /onboarding/risk and
 * /onboarding/complete, so it is customer-facing copy about a real product.
 *
 * It said "2-day-to-expiration iron condors" (FLAME) and "1-day" (SPARK) until
 * 2026-08-27. Both were false from the 2026-08-16 EBB cutover: neither bot has
 * traded an iron condor or a multi-day expiry since. They run ONE strategy —
 * a same-day (0DTE) SPY put credit spread, short spot−$1.00, $2 wing, one
 * contract, held to settlement at the close — at two different clocks.
 *
 * The only honest difference is the entry session, and it IS a risk gradient:
 * on the deployed structure (1 lot, 2022-11 → 2026-08) the 13:05 CT tranche
 * draws $490 max and the 10:05 CT tranche draws $1,207 — so Conservative→FLAME
 * / Aggressive→SPARK still sorts correctly, just for a different reason than
 * the old copy claimed. `risk-scoring.test.ts` pins both strings to dteMode().
 */
export const BOT_RATIONALE: Record<RecommendedBot, string> = {
  FLAME: 'Same-day (0DTE) SPY put credit spreads entered at 1:05 PM CT — the afternoon session, with less of the trading day left to move against the position.',
  // Worded to read correctly for BOTH Moderate and Aggressive, which now share it.
  SPARK: 'Same-day (0DTE) SPY put credit spreads entered at 10:05 AM CT — the morning session, carrying the position through the whole trading day.',
}

/** The capacity answer that forces a caution regardless of total score. */
const CRITICAL_CAPACITY_OPTION = 'critical'

/** True only when every question has a valid option id selected. */
export function validateRiskAnswers(answers: unknown): answers is RiskAnswers {
  if (!answers || typeof answers !== 'object') return false
  const a = answers as Record<string, unknown>
  return RISK_QUESTIONS.every((q) => {
    const v = a[q.key]
    return typeof v === 'string' && q.options.some((o) => o.id === v)
  })
}

/** Sum points → tier → recommended bot. Caution at the low end or low capacity. */
export function scoreToProfile(answers: RiskAnswers): RiskProfile {
  let score = 0
  for (const q of RISK_QUESTIONS) {
    const opt = q.options.find((o) => o.id === answers[q.key])
    score += opt ? opt.points : 0
  }

  let tier: RiskTier
  let recommendedBot: RecommendedBot
  if (score <= 8) {
    tier = 'Conservative'
    recommendedBot = 'FLAME'
  } else if (score <= 16) {
    tier = 'Moderate'
    recommendedBot = 'SPARK'
  } else {
    tier = 'Aggressive'
    // SPARK is the shortest-duration strategy on offer. The tier is still reported
    // honestly as Aggressive; only the recommendation is clamped to what exists.
    recommendedBot = 'SPARK'
  }

  const caution = tier === 'Conservative' || answers.capacity === CRITICAL_CAPACITY_OPTION
  return { score, tier, recommendedBot, caution }
}
