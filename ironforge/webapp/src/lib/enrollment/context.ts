import { customerQuery } from '@/lib/customers-db'
import { previewHash, type ActivationSnapshot } from './preview'
import { staleDocumentCodes, isAutomatePlan } from './legal'
import { acceptedVersionsFor } from './service'
import type { MembershipState } from './states'
import { getProductionPauseState } from '@/lib/tradier'
import { hasUsablePaymentMethod } from '@/lib/billing/stripe'
import type { ActivationInput } from './activation'
import { isUuid } from './ids'

/**
 * Gather every input the activation predicate judges (spec §4).
 *
 * Preview and activate MUST read the same state through the same code. If they diverged,
 * the preview hash would describe one reading of the world and the activation check
 * another, and the customer's consent would attach to something that was never checked —
 * which is exactly the failure the hash exists to prevent.
 *
 * So this is deliberately the ONLY place these reads happen. It performs no writes and
 * makes no decision; it returns the raw picture and lets `evaluateActivation` judge it.
 */

export interface ConfigRow {
  id: string
  agent_code: string
  rule_version: string
  status: string
  broker_account_id: string | null
  config_json: Record<string, unknown> | null
}

export interface ActivationContext {
  config: ConfigRow
  account?: { id: string; eligibility: string; ineligible_reason: string | null; display_mask: string }
  stripeCustomerId: string | null
  snapshot: ActivationSnapshot
  hash: string
  /** Everything except the two acknowledgments and the client's preview hash, which are per-request. */
  inputs: Omit<ActivationInput, 'riskAcknowledged' | 'authorizationAcknowledged' | 'previewCurrent'>
}

/** Returns null when the config does not exist or is not this customer's (§8). */
export async function loadActivationContext(
  userId: string,
  configId: string,
): Promise<ActivationContext | null> {
  // A malformed id raises on the UUID cast instead of returning no rows. Same answer
  // as an id that is not the caller's — which also avoids leaking whether one exists.
  if (!isUuid(configId) || !isUuid(userId)) return null

  const config = (await customerQuery<ConfigRow>(
    `SELECT id, agent_code, rule_version, status, broker_account_id, config_json
       FROM agent_configs WHERE id = $1 AND user_id = $2 LIMIT 1`,
    [configId, userId],
  ))[0]
  if (!config) return null

  // Ownership goes through the connection join — an account id is never authority by itself.
  const account = config.broker_account_id
    ? (await customerQuery<{
        id: string; eligibility: string; ineligible_reason: string | null; display_mask: string
      }>(
        `SELECT ba.id, ba.eligibility, ba.ineligible_reason, ba.display_mask
           FROM broker_accounts ba
           JOIN brokerage_connections bc ON bc.id = ba.connection_id
          WHERE ba.id = $1 AND bc.user_id = $2 LIMIT 1`,
        [config.broker_account_id, userId],
      ))[0]
    : undefined

  const conn = (await customerQuery<{ status: string }>(
    `SELECT status FROM brokerage_connections WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 1`,
    [userId],
  ))[0]

  const sub = (await customerQuery<{ status: string }>(
    `SELECT status FROM customer_bot_subscriptions WHERE user_id = $1 AND bot = $2 LIMIT 1`,
    [userId, config.agent_code],
  ))[0]

  // v2 order: card at $0, subscription created BY activation — so before activation
  // there is legitimately NO subscription row. That is 'setup_ready' ONLY when the open
  // enrollment proves the customer finished billing (setup_required, automate family);
  // any other absence stays 'pending' and blocks, fail-closed as before.
  let membership: MembershipState = (sub?.status as MembershipState) ?? 'pending'
  if (!sub) {
    const enrollment = (await customerQuery<{ selected_plan: string | null; status: string }>(
      `SELECT selected_plan, status FROM enrollments
        WHERE user_id = $1 AND status NOT IN ('complete', 'abandoned')
        ORDER BY created_at DESC LIMIT 1`,
      [userId],
    ))[0]
    if (enrollment?.status === 'setup_required' && isAutomatePlan(enrollment.selected_plan)) {
      membership = 'setup_ready'
    }
  }

  const user = (await customerQuery<{ stripe_customer_id: string | null }>(
    `SELECT stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
    [userId],
  ))[0]

  // Kill-switch read FAILS CLOSED: an unreadable pause state counts as engaged. The same
  // rule as the live page — an error must never read as permission to trade.
  const pause = await getProductionPauseState(config.agent_code).catch(() => ({ paused: true }))
  const accepted = await acceptedVersionsFor(userId)
  const paymentMethodValid = user?.stripe_customer_id
    ? await hasUsablePaymentMethod(user.stripe_customer_id)
    : false

  const snapshot: ActivationSnapshot = {
    userId,
    brokerAccountId: account?.id ?? '',
    accountMask: account?.display_mask ?? '',
    agentCode: config.agent_code,
    ruleVersion: config.rule_version,
    maxDeploymentCents: Number(config.config_json?.max_deployment_cents ?? 0),
    buyingPowerCents: Number(config.config_json?.buying_power_cents ?? 0),
    legalVersions: accepted.map((a) => `${a.code}@${a.version}`),
  }

  return {
    config,
    account,
    stripeCustomerId: user?.stripe_customer_id ?? null,
    snapshot,
    hash: previewHash(snapshot),
    inputs: {
      membership,
      paymentMethodValid,
      staleLegalDocuments: staleDocumentCodes(config.agent_code, accepted),
      brokerage: conn?.status === 'active' ? 'connected' : 'not_connected',
      accountEligible: account?.eligibility === 'eligible',
      accountIneligibleReason: account?.ineligible_reason ?? undefined,
      agentConfig: config.status as never,
      killSwitchEngaged: pause.paused === true,
    },
  }
}
