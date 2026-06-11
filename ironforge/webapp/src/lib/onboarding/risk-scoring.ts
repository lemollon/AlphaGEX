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
export type RecommendedBot = 'FLAME' | 'SPARK' | 'INFERNO'

export interface RiskProfile {
  score: number
  tier: RiskTier
  recommendedBot: RecommendedBot
  caution: boolean
}

export const BOT_RATIONALE: Record<RecommendedBot, string> = {
  FLAME: '2-day-to-expiration iron condors — the most conservative, slowest-paced bot.',
  SPARK: '1-day-to-expiration iron condors — a balanced middle ground.',
  INFERNO: '0-day-to-expiration, aggressive and fast-paced — the highest risk and activity.',
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
    recommendedBot = 'INFERNO'
  }

  const caution = tier === 'Conservative' || answers.capacity === CRITICAL_CAPACITY_OPTION
  return { score, tier, recommendedBot, caution }
}
