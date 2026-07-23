import TradeHistoryClient from './TradeHistoryClient'

export const dynamic = 'force-dynamic'

/**
 * /account/trades — customer Trade History (redesigned 2026-07-23).
 *
 * Every customer-facing link ("Trade History" in the sidebar, the account menu,
 * "View All" on the Home recent-trades card) points here and expects a HISTORY
 * table, so this route now renders it. Data comes from /api/live/trades, scoped
 * to the signed-in customer.
 *
 * The older brokerage trade-APPROVAL queue (TradeApprovalsClient, fed by
 * /api/brokerage/trades) is retained in this folder but no longer mounted here.
 * NOTE for when live approvals ship: /api/brokerage/trades still emails an
 * approveUrl of /account/trades — that destination must move to a dedicated
 * approvals route before the approval flow goes live.
 */
export default function TradeHistoryPage() {
  return <TradeHistoryClient />
}
