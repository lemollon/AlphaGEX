/**
 * Versioned legal documents (Enrollment spec §3 LEGAL-01, §5, §11).
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
 * Current active versions.
 *
 * `core` applies to EVERY member (Community and Automate alike). `automate` adds the
 * two the spec names as mandatory for automated trading: "Trading Authorization and
 * Electronic Consent are mandatory for Automate" (§3 LEGAL-01).
 *
 * TERMS + RISK map onto the three checkboxes the existing /onboarding/legal step
 * already collects (termsAccepted, riskDisclosure, automatedExecution) — AUTOMATED_
 * EXECUTION becomes TRADING_AUTH, which is where it belongs: it is an authorization,
 * not a disclosure, and it is Automate-only.
 */
export const LEGAL_DOCUMENTS: readonly LegalDocumentSpec[] = [
  { code: 'TERMS', scope: 'core', version: '1.0', title: 'Terms of Service', contentUri: '/terms' },
  { code: 'RISK', scope: 'core', version: '1.0', title: 'Options & Automated Trading Risk Disclosure', contentUri: '/legal/risk' },
  { code: 'ELECTRONIC_CONSENT', scope: 'automate', version: '1.0', title: 'Electronic Communications Consent', contentUri: '/legal/electronic-consent' },
  { code: 'TRADING_AUTH', scope: 'automate', version: '1.0', title: 'Automated Trading Authorization', contentUri: '/legal/trading-authorization' },
]

/** Plans that authorize automated trading. Community is education/chat only. */
const AUTOMATE_PLANS = new Set(['spark', 'flame', 'both'])

/**
 * Which documents this plan requires. "Render only documents required by selected
 * plan" (§3) — showing a Community member a trading authorization would be both
 * confusing and, since they cannot trade, untrue.
 */
export function requiredDocumentsFor(plan: string | null | undefined): LegalDocumentSpec[] {
  const core = LEGAL_DOCUMENTS.filter((d) => d.scope === 'core')
  if (!plan) return core
  return AUTOMATE_PLANS.has(plan)
    ? [...core, ...LEGAL_DOCUMENTS.filter((d) => d.scope === 'automate')]
    : core
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
