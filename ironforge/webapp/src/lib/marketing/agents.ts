/**
 * IronForge 10.4 marketing design — agent catalogue.
 *
 * Single source for the 3 agent cards (home, /agents) and the `.agent-name`
 * color variable they key off (`--spark` / `--flame` / `--ember` in
 * `forge-tokens.css`). Mirrors the shared `AGENTS` config described in the
 * 10.4 design spec section 3.
 *
 * Ember is ONE agent, same shape as Spark and Flame — not a parent with
 * sub-agents. (An earlier version of this file modeled Ember as a family with
 * a REFLEX sub-agent; Leron corrected that on 2026-10-04: customers see a
 * single Ember agent, REFLEX is an internal strategy detail, never shown.)
 */

import { BOT_PLANS } from '@/lib/billing/plans'

export type AgentSlug = 'spark' | 'flame' | 'ember'

/** Read from billing/plans.ts, never hardcoded here — so a price change there needs no edit here. */
function formatMonthly(amount: number): string {
  return `$${amount}`
}

export interface AgentRow {
  label: string
  value: string
  /** Risk meter fill, 1-3 bars. Omit for rows with no meter. */
  riskLevel?: number
}

export interface MarketingAgent {
  slug: AgentSlug
  name: string
  /** CSS custom property (defined in forge-tokens.css) driving this agent's color. */
  colorVar: '--spark' | '--flame' | '--ember'
  mascot: string
  /** Short line under the name, e.g. "Morning session". */
  tagline: string
  /** Filter chip tags on the home page agent grid. */
  tags: Array<'morning' | 'afternoon' | 'small' | 'new' | 'calm'>
  desc: string
  rows: AgentRow[]
  price: string
  per: string
  note: string
  isFree: boolean
  /** `?plan=` query value for Create account / Start trial CTAs. */
  planParam: AgentSlug
}

export const AGENTS: MarketingAgent[] = [
  {
    slug: 'spark',
    name: 'Spark',
    colorVar: '--spark',
    mascot: '/marketing/spark-mascot.webp',
    tagline: 'Morning session',
    tags: ['morning'],
    desc: 'Trades the opening hours, when the market moves the most. More opportunity, slightly more risk.',
    rows: [
      { label: 'Session', value: 'Morning' },
      { label: 'Approach', value: 'Put spreads' },
      { label: 'Risk', value: 'Slightly higher', riskLevel: 3 },
    ],
    price: formatMonthly(BOT_PLANS.spark.priceMonthly),
    per: 'per month',
    note: '5 trading days free',
    isFree: false,
    planParam: 'spark',
  },
  {
    slug: 'flame',
    name: 'Flame',
    colorVar: '--flame',
    mascot: '/marketing/flame-mascot.webp',
    tagline: 'Afternoon session',
    tags: ['afternoon', 'calm'],
    desc: 'Waits for the morning rush to settle and trades the calmer afternoon. Less volatility, smoother ride.',
    rows: [
      { label: 'Session', value: 'Afternoon' },
      { label: 'Approach', value: 'Put spreads' },
      { label: 'Risk', value: 'Lower volatility', riskLevel: 2 },
    ],
    price: formatMonthly(BOT_PLANS.flame.priceMonthly),
    per: 'per month',
    note: '5 trading days free',
    isFree: false,
    planParam: 'flame',
  },
  {
    slug: 'ember',
    name: 'Ember',
    colorVar: '--ember',
    mascot: '/marketing/ember-mascot.webp',
    tagline: 'Built for smaller accounts',
    tags: ['small', 'new', 'calm'],
    desc: 'Made for low-capital accounts and people new to investing. Aims for steady growth you can build on.',
    rows: [
      { label: 'Built for', value: 'Smaller accounts' },
      { label: 'Approach', value: 'Steady growth' },
      { label: 'Best for', value: 'First-time investors' },
    ],
    price: 'Free',
    per: 'no monthly fee',
    note: '$500–$2K accounts. One per person.',
    isFree: true,
    planParam: 'ember',
  },
]

export function getAgent(slug: AgentSlug): MarketingAgent {
  const agent = AGENTS.find((a) => a.slug === slug)
  if (!agent) throw new Error(`Unknown agent: ${slug}`)
  return agent
}

/** Side-by-side compare table rows (Agents page), verbatim from the design. */
export const AGENT_COMPARE_ROWS: Array<{ label: string; spark: string; flame: string; ember: string }> = [
  { label: 'When it trades', spark: 'Morning session', flame: 'Afternoon session', ember: 'To be announced' },
  { label: 'Approach', spark: 'Put spreads', flame: 'Put spreads', ember: 'Steady growth' },
  {
    label: 'Market conditions',
    spark: 'Bigger morning moves',
    flame: 'Calmer afternoon trading',
    ember: 'Paced for small balances',
  },
  { label: 'Risk', spark: 'Slightly higher', flame: 'Lower volatility', ember: 'Measured' },
  { label: 'Best for', spark: 'Comfort with some swing', flame: 'A steadier pace', ember: 'First-time investors' },
  { label: 'Position sizing', spark: 'The Ladder', flame: 'The Ladder', ember: 'The Ladder' },
  {
    label: 'Price',
    spark: `${formatMonthly(BOT_PLANS.spark.priceMonthly)} / month`,
    flame: `${formatMonthly(BOT_PLANS.flame.priceMonthly)} / month`,
    ember: 'Free',
  },
  { label: 'Free trial', spark: '5 trading days', flame: '5 trading days', ember: 'Always free' },
  {
    label: 'Limits',
    spark: 'None',
    flame: 'None',
    ember: '1 account per person, $500–$2,000 trading capital',
  },
]
