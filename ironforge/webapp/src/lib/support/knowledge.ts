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
import { SUPPORTED_BROKERS } from '@/lib/brokerage/catalog'

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
    // and "Forge Starter". A support bot quoting a price we do not charge is the worst
    // place for this to be wrong.
    a: `Three tiers: ${MARKETING_TIERS.community.name} ($${MARKETING_TIERS.community.priceMonthly}/mo — chat + education, no trading bot), ${MARKETING_TIERS.starter.name} ($${MARKETING_TIERS.starter.priceMonthly}/mo — one automated strategy), and ${MARKETING_TIERS.pro.name} ($${MARKETING_TIERS.pro.priceMonthly}/mo — both strategies). Every bot plan includes Community. See ironforge.trade/pricing.`,
  },
  {
    topic: 'plans',
    q: 'How much is a second strategy / the bundle?',
    a: 'From Community only, activating your FIRST strategy upgrades your membership to $50/mo total (Community stays included — it is not $10 + $50). Adding a SECOND strategy is +$25/mo, lifting a single-strategy subscription to the $75 bundle covering both Spark and Flame. You can add either from /account/billing.',
  },
  {
    topic: 'plans',
    q: 'Is there a free trial?',
    a: `Yes — strategy plans start with a 5-trading-day free trial (trading days, not calendar days), so you are not charged today. Community ($${MARKETING_TIERS.community.priceMonthly}/mo) is billed immediately (no trial) since it is low-cost access.`,
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
    a: 'Sign up, verify your email, choose your membership (Community or Forge Automate), review and sign the agreements, save a payment method, connect your brokerage, pick your agent (Spark or Flame), then review and activate. Your free trial starts at activation and you land on your agent dashboard.',
  },
  {
    topic: 'onboarding',
    q: 'Do I have to connect a brokerage right away?',
    a: 'For Forge Automate, yes — connecting an eligible brokerage account is a required enrollment step before activation, because the agent trades in your own account. Community membership needs no brokerage at all.',
  },
  // ── Brokerage ───────────────────────────────────────────────────────────────
  // Derived from the ordered broker catalog (lib/brokerage/catalog.ts) so ordering
  // and capability claims can never drift from the product (UAT-015): Tradier is
  // always listed first as the partner brokerage, and only factual integration
  // benefits are stated — never "best for you" (Sparky gives no personalized advice).
  {
    topic: 'brokerage',
    q: 'Which brokers are supported / which should I consider?',
    a: `In order of integration depth: ${SUPPORTED_BROKERS.map((b) => `${b.displayName}${b.partner ? ' (IronForge partner — direct integration that verifies options approval level)' : b.trading === 'multi_leg' ? ' (multi-leg options via SnapTrade)' : ' (view-only via SnapTrade — automated trading is not available there)'}`).join('; ')}. You connect a broker in Brokerage Settings. Sparky states integration facts only — it does not make personalized brokerage recommendations.`,
  },
  {
    topic: 'brokerage',
    q: 'Is connecting my broker safe?',
    a: 'Yes — Tradier connects through its official OAuth flow and other brokers connect through SnapTrade\'s secure flow. Either way IronForge never sees your brokerage password, and your funds stay in your own account in your name.',
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
    a: 'Performance shows your account\'s results and KPIs over time. Live shows each strategy\'s current status and lets you switch between the ones you own.',
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
    a: `Forge Community is the in-app chat + education space. It is included with any strategy plan, or available on its own for $${MARKETING_TIERS.community.priceMonthly}/mo. You can read the feed as a preview; posting requires an active membership. Join from /community or /account/billing.`,
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
