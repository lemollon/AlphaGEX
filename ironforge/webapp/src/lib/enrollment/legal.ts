/**
 * Versioned legal documents (Enrollment spec §3 LEGAL-01, §5, §11; July 29 handoff
 * LEGAL-AUTO-01 / §17).
 *
 * The registry is CODE, not data, so a version bump is a reviewable diff rather than a
 * row someone edited in a console. The database holds the immutable versions and the
 * append-only acceptances; this file is the source of truth for what CURRENTLY applies.
 *
 * The rule that makes versioning necessary: "Any changed required document invalidates
 * only the affected prior acceptance" (§3). You cannot express that with a boolean
 * `accepted_terms` column — you need to know WHICH version of WHICH document a person
 * agreed to, so bumping one document does not silently re-open the others.
 *
 * ⚠️ Content and exact wording are NOT settled here. The doc's definition of done
 * requires "Legal approves exact agreements, disclosure copy, trial mechanics and
 * cancellation/refund presentation" — these codes and scopes are the mechanism; the
 * text behind content_uri still needs signoff.
 */

export type LegalPlanScope = 'core' | 'automate'

export interface LegalDocumentSpec {
  code: string
  scope: LegalPlanScope
  version: string
  title: string
  contentUri: string
}

/**
 * Current active versions, in the LEGAL-AUTO-01 display order (Terms, Risk, Privacy,
 * Advice Disclaimer, Electronic Consent, Trading Authorization, Refund) — the UI renders
 * requiredDocumentsFor() in registry order, so this array IS the on-screen order.
 *
 * `core` applies to EVERY member. Community has no standalone legal screen (the July 29
 * handoff shows none), so its core set — Terms, Privacy, Refund — is accepted via the
 * clickwrap block on the Community billing submit. `automate` adds the documents that
 * only make sense when automated execution is being authorized: the risk disclosure,
 * the advice disclaimer, electronic consent, and the trading authorization itself.
 */
export const LEGAL_DOCUMENTS: readonly LegalDocumentSpec[] = [
  { code: 'TERMS', scope: 'core', version: '1.0', title: 'Terms of Service', contentUri: '/terms' },
  { code: 'RISK', scope: 'automate', version: '1.0', title: 'Options & Automated Trading Risk Disclosure', contentUri: '/legal/risk' },
  { code: 'PRIVACY', scope: 'core', version: '1.0', title: 'Privacy Policy', contentUri: '/privacy' },
  { code: 'ADVICE_DISCLAIMER', scope: 'automate', version: '1.0', title: 'Investment Advice Disclaimer', contentUri: '/legal/investment-advice-disclaimer' },
  { code: 'ELECTRONIC_CONSENT', scope: 'automate', version: '1.0', title: 'Electronic Communications Consent', contentUri: '/legal/electronic-consent' },
  { code: 'TRADING_AUTH', scope: 'automate', version: '1.0', title: 'Automated Trading Authorization', contentUri: '/legal/trading-authorization' },
  { code: 'REFUND', scope: 'core', version: '1.0', title: 'Refund Policy', contentUri: '/legal/refund-policy' },
]

/**
 * Plans that authorize automated trading. Community is education/chat only.
 * 'automate' is the family value PLAN-01 persists before an agent is chosen — the
 * agent choice lives on agent_configs.agent_code, never as a second plan write.
 */
const AUTOMATE_PLANS = new Set(['spark', 'flame', 'both', 'automate'])

/** True when this plan (or plan family) authorizes automated trading. */
export function isAutomatePlan(plan: string | null | undefined): boolean {
  return plan != null && AUTOMATE_PLANS.has(plan)
}

/**
 * Which documents this plan requires. "Render only documents required by selected
 * plan" (§3) — showing a Community member a trading authorization would be both
 * confusing and, since they cannot trade, untrue. Registry order is preserved so the
 * legal screen lists documents in the approved order.
 */
export function requiredDocumentsFor(plan: string | null | undefined): LegalDocumentSpec[] {
  const automate = isAutomatePlan(plan)
  return LEGAL_DOCUMENTS.filter((d) => d.scope === 'core' || (automate && d.scope === 'automate'))
}

export interface AcceptedVersion {
  code: string
  version: string
}

/**
 * Which required documents are NOT satisfied by what this user has accepted.
 *
 * Matches on code AND version, which is the whole point: an acceptance of TERMS 1.0
 * does not satisfy TERMS 1.1. Returns only the affected codes, so a bump to one
 * document never invalidates the others (§11 "Return to affected document only;
 * preserve other acceptances").
 */
export function staleDocumentCodes(
  plan: string | null | undefined,
  accepted: readonly AcceptedVersion[],
): string[] {
  const have = new Set(accepted.map((a) => `${a.code}@${a.version}`))
  return requiredDocumentsFor(plan)
    .filter((d) => !have.has(`${d.code}@${d.version}`))
    .map((d) => d.code)
}
