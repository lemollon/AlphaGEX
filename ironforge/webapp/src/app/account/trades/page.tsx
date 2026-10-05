import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

/**
 * /account/trades is superseded by the /dashboard History tab (dev-handoff
 * §6: a single tabbed page). TradeHistoryBody (the extracted table) now
 * renders inline there; redirecting rather than deleting keeps every
 * existing link and bookmark to /account/trades working — including the
 * `/api/brokerage/trades` approveUrl noted below.
 *
 * The older brokerage trade-APPROVAL queue (TradeApprovalsClient, fed by
 * /api/brokerage/trades) is retained in this folder but was never mounted
 * here. NOTE for when live approvals ship: /api/brokerage/trades still
 * emails an approveUrl of /account/trades — that destination must move to a
 * dedicated approvals route before the approval flow goes live.
 */
export default function TradeHistoryPage() {
  redirect('/dashboard?tab=history')
}
