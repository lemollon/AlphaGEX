/**
 * Sparky's knowledge base — the curated, IronForge-specific facts Sparky answers from.
 *
 * This is the SOURCE OF TRUTH for support answers. Sparky is instructed to answer from
 * this content (and say "I don't know" + escalate when a question isn't covered) rather
 * than free-associating, which is what keeps answers accurate and on-policy. Edit here to
 * change what Sparky knows — no model retraining, just a redeploy.
 *
 * Keep entries short and factual. Prices/policy live in one place per topic so they can't
 * drift; where a real route exists, name it so Sparky can link the user straight to it.
 */

import { MARKETING_TIERS } from '@/lib/billing/plans'

export interface KbEntry {
  topic: string
  q: string
  a: string
}

export const SUPPORT_KB: KbEntry[] = [
  // ── Plans & pricing ────────────────────────────────────────────────────────
  {
    topic: 'plans',
    q: 'What plans and prices does IronForge offer?',
    // Prices and names interpolated from MARKETING_TIERS. This answer hardcoded
    // "Community ($15/mo)" — the price was $10, the same discrepancy caught in Stripe —
    // and "Forge Starter", and pointed at /pricing, which has 308'd to /#memberships
    // since that page was retired. A support bot quoting a price we do not charge is
    // the worst place for this to be wrong.
    a: `Three tiers: ${MARKETING_TIERS.community.name} ($${MARKETING_TIERS.community.priceMonthly}/mo — chat + education, no trading bot), ${MARKETING_TIERS.starter.name} ($${MARKETING_TIERS.starter.priceMonthly}/mo — one automated strategy), and ${MARKETING_TIERS.pro.name} ($${MARKETING_TIERS.pro.priceMonthly}/mo — both strategies). Every bot plan includes Community. See the memberships section on the homepage.`,
  },
  {
    topic: 'plans',
    q: 'How much is a second strategy / the bundle?',
    a: 'Adding a second strategy is +$25/mo, not another full $50 — it lifts a single-strategy subscription to the $75 Pro bundle covering both Spark and Flame. You can add it from your Live menu (the strategy you don\'t own yet) or from /account/billing.',
  },
  {
    topic: 'plans',
    q: 'Is there a free trial?',
    a: 'Yes — bot plans start with a 5-day free trial, so you are not charged today. Community ($15/mo) is billed immediately (no trial) since it is low-cost access.',
  },
  // ── Billing ─────────────────────────────────────────────────────────────────
  {
    topic: 'billing',
    q: 'How do I change my card, cancel, or get receipts?',
    a: 'Go to Manage Membership at /account/billing and click "Manage billing" — that opens the secure Stripe customer portal where you can update your card, change plan, download receipts, or cancel. You can cancel anytime.',
  },
  {
    topic: 'billing',
    q: 'How do I cancel my subscription?',
    a: 'Open /account/billing → "Manage billing" → cancel in the Stripe portal. Access continues until the end of the current billing period.',
  },
  {
    topic: 'billing',
    q: 'Where is my payment processed?',
    a: 'All card details are entered and stored on Stripe — never on IronForge. We never see or store your card number.',
  },
  // ── Onboarding ──────────────────────────────────────────────────────────────
  {
    topic: 'onboarding',
    q: 'How do I get started / what are the steps?',
    a: 'Sign up, accept the terms, take the short risk quiz (it recommends a strategy that fits you), optionally connect your brokerage, then open your account. The final step starts your free trial and takes you to your dashboard.',
  },
  {
    topic: 'onboarding',
    q: 'Do I have to connect a brokerage right away?',
    a: 'No — connecting a brokerage is optional during onboarding and can be done later from Brokerage Settings. You can explore the app first.',
  },
  // ── Brokerage ───────────────────────────────────────────────────────────────
  {
    topic: 'brokerage',
    q: 'Which brokers are supported?',
    a: 'IronForge connects to options-capable US brokers via SnapTrade — including tastytrade, E*TRADE, Webull, Public, and (where enabled) Robinhood, Schwab, Fidelity, TradeStation, and Interactive Brokers. You connect it in Brokerage Settings.',
  },
  {
    topic: 'brokerage',
    q: 'Is connecting my broker safe?',
    a: 'Yes — the broker connection is handled through SnapTrade\'s secure flow. IronForge never sees your brokerage password.',
  },
  // ── Strategies / product ────────────────────────────────────────────────────
  {
    topic: 'strategies',
    q: 'What do Spark and Flame do?',
    a: 'They are automated SPY options strategies. Spark trades shorter-dated (1DTE) setups for faster theta decay; Flame trades slightly longer-dated (2DTE) setups. Both are iron-condor / credit-spread style. Sparky can explain how they work but does not give personalized trade advice.',
  },
  {
    topic: 'strategies',
    q: 'What is the difference between paper and live?',
    a: 'A "Paper" badge means simulated results — no real orders are placed and no real money is at risk. A live strategy trades in your connected brokerage account. The Live and Performance pages label which is which.',
  },
  {
    topic: 'pages',
    q: 'What do the Performance and Live pages show?',
    a: 'Performance shows your account\'s results and KPIs over time. Live shows each strategy\'s current status and lets you switch between the ones you own. The Bot Ledger (/bot-ledger) is the public, closed-trade proof view.',
  },
  {
    topic: 'faq',
    q: 'What is PDT / the pattern day trader rule?',
    a: 'PDT is a FINRA rule about day trades in margin accounts under $25k. IronForge tracks day trades to help stay within the limit. Note a 2026 rule change is easing the old $25k minimum; your broker\'s specific rules still apply.',
  },
  // ── Community ───────────────────────────────────────────────────────────────
  {
    topic: 'community',
    q: 'What is the Forge Community and how do I join?',
    a: 'Forge Community is the in-app chat + education space. It is included with any bot plan, or available on its own for $15/mo. You can read the feed as a preview; posting requires an active membership. Join from /community or /account/billing.',
  },
  // ── Account / security ──────────────────────────────────────────────────────
  {
    topic: 'account',
    q: 'How do I change my password?',
    a: 'Use Change Password at /change-password while signed in. If you are locked out, use "Forgot password" on the login page.',
  },
  {
    topic: 'security',
    q: 'Is my money / are my trades safe?',
    a: 'Your funds always stay in your own brokerage account — IronForge places trades through your connected broker but never holds your money. Card billing is handled by Stripe.',
  },
]

/** Compact, model-ready context block built from the KB (grouped by topic, in array order). */
export function knowledgeContext(): string {
  const lines: string[] = []
  let current = ''
  for (const e of SUPPORT_KB) {
    if (e.topic !== current) {
      current = e.topic
      lines.push('', `## ${e.topic.toUpperCase()}`)
    }
    lines.push(`Q: ${e.q}\nA: ${e.a}`)
  }
  return lines.join('\n').trim()
}

/** Empty-state quick prompts shown before the first message. */
export const SUGGESTED_PROMPTS: string[] = [
  'How do I connect my brokerage?',
  "What's included in each plan?",
  'How do I cancel or change my card?',
  'What is the difference between paper and live?',
]
