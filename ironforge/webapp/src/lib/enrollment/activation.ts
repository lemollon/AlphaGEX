import type { BrokerageState, AgentConfigState, MembershipState } from './states'

/**
 * The activation predicate (Enrollment spec §4).
 *
 * Trading may activate ONLY when every one of these holds:
 *   membership ∈ {active, setup_required-equivalent} AND payment method valid AND all
 *   required legal versions accepted AND brokerage connected AND selected account
 *   eligible AND agent config valid AND kill switch clear AND acknowledgments current.
 *
 * FAILS CLOSED. Every input defaults to the unsafe-to-trade reading, so a caller that
 * forgets to pass something gets a refusal, never an activation. The one thing this
 * function must never do is return ok on incomplete information.
 *
 * Returns EVERY blocker, not the first. The spec requires the UI to explain "the exact
 * remediable reason" (§12, Ineligible account), and a customer who fixes one problem
 * only to be shown the next one has been made to do the work twice.
 *
 * Pure: no I/O, no clock. The caller gathers state; this only judges it.
 */

export type ActivationBlockerCode =
  | 'MEMBERSHIP_NOT_ACTIVE'
  | 'PAYMENT_METHOD_INVALID'
  | 'LEGAL_ACCEPTANCE_STALE'
  | 'BROKERAGE_NOT_CONNECTED'
  | 'BROKER_ACCOUNT_INELIGIBLE'
  | 'AGENT_CONFIG_NOT_VALID'
  | 'KILL_SWITCH_ENGAGED'
  | 'ACKNOWLEDGMENTS_MISSING'
  | 'PREVIEW_STALE'

export interface ActivationBlocker {
  code: ActivationBlockerCode
  /** User-safe. Never leaks broker/Stripe internals (§6). */
  message: string
  field?: string
  /** False when the customer cannot fix it themselves (e.g. a platform kill switch). */
  remediable: boolean
}

export interface ActivationInput {
  membership: MembershipState
  paymentMethodValid: boolean
  /** Required document codes whose ACCEPTED version !== the current active version. */
  staleLegalDocuments: string[]
  brokerage: BrokerageState
  /** Result of re-checking the account immediately before activation (§4). */
  accountEligible: boolean
  accountIneligibleReason?: string
  agentConfig: AgentConfigState
  /** Any of global / broker / strategy / account kill switch engaged. */
  killSwitchEngaged: boolean
  killSwitchScope?: string
  riskAcknowledged: boolean
  authorizationAcknowledged: boolean
  /**
   * False when the immutable preview the customer consented to no longer matches
   * current state — buying power moved, account or agent changed (§4, §12 Stale review).
   */
  previewCurrent: boolean
}

/**
 * Membership states that may hold an activation. `past_due` may NOT open new trading.
 * `setup_ready` is the v2 pre-subscription state: card captured at $0, enrollment in
 * setup_required, subscription created BY this activation — so it must be allowed
 * through here or v2 activation can never succeed. Card validity is still enforced
 * separately by PAYMENT_METHOD_INVALID.
 */
const MEMBERSHIP_OK: MembershipState[] = ['active', 'setup_ready']

export interface ActivationDecision {
  ok: boolean
  blockers: ActivationBlocker[]
}

export function evaluateActivation(input: Partial<ActivationInput>): ActivationDecision {
  const blockers: ActivationBlocker[] = []
  const add = (b: ActivationBlocker) => blockers.push(b)

  // Every check reads the UNSAFE default when its input is absent.
  if (!input.membership || !MEMBERSHIP_OK.includes(input.membership)) {
    add({
      code: 'MEMBERSHIP_NOT_ACTIVE',
      message: 'Your membership is not active yet.',
      remediable: true,
    })
  }
  if (input.paymentMethodValid !== true) {
    add({
      code: 'PAYMENT_METHOD_INVALID',
      message: 'A valid payment method is required before trading can be activated.',
      field: 'payment_method',
      remediable: true,
    })
  }
  // Missing array => unknown => treated as stale.
  if (!Array.isArray(input.staleLegalDocuments) || input.staleLegalDocuments.length > 0) {
    add({
      code: 'LEGAL_ACCEPTANCE_STALE',
      message: 'Please review and accept the latest agreements.',
      field: 'legal',
      remediable: true,
    })
  }
  if (input.brokerage !== 'connected') {
    add({
      code: 'BROKERAGE_NOT_CONNECTED',
      message:
        input.brokerage === 'reauth_required' || input.brokerage === 'revoked'
          ? 'Reconnect your brokerage to continue.'
          : 'Connect your brokerage to continue.',
      field: 'brokerage',
      remediable: true,
    })
  }
  if (input.accountEligible !== true) {
    add({
      code: 'BROKER_ACCOUNT_INELIGIBLE',
      // The reason is the remediable detail the spec insists on surfacing.
      message: input.accountIneligibleReason || 'This account is not eligible for automated options trading.',
      field: 'broker_account_id',
      remediable: true,
    })
  }
  if (input.agentConfig !== 'valid') {
    add({
      code: 'AGENT_CONFIG_NOT_VALID',
      message:
        input.agentConfig === 'stale'
          ? 'Your settings changed and need to be re-checked.'
          : 'Finish configuring your strategy.',
      field: 'agent_config',
      remediable: true,
    })
  }
  if (input.killSwitchEngaged !== false) {
    add({
      code: 'KILL_SWITCH_ENGAGED',
      message: 'Trading is temporarily disabled platform-wide. No action is needed from you.',
      // The customer cannot clear this, and telling them to try again would be a lie.
      remediable: false,
    })
  }
  if (input.riskAcknowledged !== true || input.authorizationAcknowledged !== true) {
    add({
      code: 'ACKNOWLEDGMENTS_MISSING',
      message: 'Both acknowledgments are required to authorize trading.',
      field: 'acknowledgments',
      remediable: true,
    })
  }
  if (input.previewCurrent !== true) {
    add({
      code: 'PREVIEW_STALE',
      message: 'Something changed while you were reviewing. Please review the updated summary.',
      remediable: true,
    })
  }

  return { ok: blockers.length === 0, blockers }
}
