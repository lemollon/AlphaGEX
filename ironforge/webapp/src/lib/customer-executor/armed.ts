/**
 * The customer-executor arm switch, on its own so anything may ask.
 *
 * WHY IT IS NOT IN executor.ts. The answer to "can a customer's own brokerage
 * account be traded right now?" is needed by read paths — the Live summary, the
 * disclosure a customer is shown — and `executor.ts` pulls in SnapTrade, the
 * customers DB, secret decryption and the Tradier client. A page that only wants
 * to know whether to promise "no real money is at risk" should not import an
 * order placer to find out.
 *
 * It is a LEAF: no imports, ever. Keep it that way.
 *
 * There is exactly one definition of this check on purpose. Copying the
 * `process.env` read to the call site is how the bot taglines came to state
 * three different things about the same product (see lib/billing/plans.ts), and
 * this one guards a sentence about whether someone's money is at risk.
 */
export function isExecutorArmed(): boolean {
  return process.env.CUSTOMER_EXECUTOR_ENABLED === 'true'
}
