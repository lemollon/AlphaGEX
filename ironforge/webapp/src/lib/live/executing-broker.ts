import { dbQuery } from '@/lib/db'
import { getProductionAccountsForBot } from '@/lib/tradier'
import { isLiveBot, resolveAccountMode } from './viewer'

/**
 * WRONG BROKER LABEL (customer audit). GET /api/brokerage/connections showed
 * whatever enrollment-time SnapTrade `brokerage_connections` row a customer
 * happened to have (e.g. "Tastytrade") even when CUSTOMER_EXECUTOR_ENABLED is
 * off — which it is in production (see customer-executor/executor.ts's
 * isExecutorArmed, "unset in production"). With the executor disarmed, no
 * customer order is actually mirrored into their own SnapTrade-linked
 * brokerage at all: every mapped bot trades the house's own Tradier account —
 * FLAME off TRADIER_FLAME_* env creds, SPARK off its `ironforge_accounts` row
 * (see live/viewer.ts's resolveAccountMode / canReadProductionBalance). The
 * customer was being shown a brokerage connection that is not what their
 * money is actually trading through.
 *
 * This resolves the TRUTH for a given customer: which bot (if any) they are
 * mapped to that is both a live bot and currently executing on an internal
 * Tradier production account, and that account's own last-4 — never a full
 * account number, never a credential.
 */
export interface ExecutingBrokerInfo {
  bot: string
  broker: 'Tradier'
  last4: string
}

export async function resolveExecutingBroker(
  customerId: string | null | undefined,
): Promise<ExecutingBrokerInfo | null> {
  if (!customerId) return null
  try {
    const rows = await dbQuery<{ bot: string }>(
      `SELECT bot FROM ironforge_customer_bots WHERE customer_id = $1`,
      [customerId],
    )
    for (const r of rows) {
      if (!isLiveBot(r.bot)) continue
      if (resolveAccountMode(r.bot) !== 'production') continue
      const accounts = await getProductionAccountsForBot(r.bot, { forRead: true })
      const acct = accounts.find((a) => a.accountId)
      if (acct?.accountId) {
        return { bot: r.bot, broker: 'Tradier', last4: acct.accountId.slice(-4) }
      }
    }
    return null
  } catch {
    // Fail closed to the existing brokerage_connections behavior — an
    // unreadable mapping must never crash the Brokerage Connections screen.
    return null
  }
}
