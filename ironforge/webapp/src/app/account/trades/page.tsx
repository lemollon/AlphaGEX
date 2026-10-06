import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

/**
 * /account/trades is superseded by the /dashboard History tab (dev-handoff
 * §6: a single tabbed page). TradeHistoryBody (the extracted table) now
 * renders inline there; redirecting rather than deleting keeps every
 * existing link and bookmark to /account/trades working.
 *
 * The brokerage trade-APPROVAL queue (TradeApprovalsClient) is now mounted at
 * its own dedicated route, /account/approvals — see that folder. The
 * `/api/brokerage/trades` approveUrl and trade-approval email point there, not
 * here (gap audit "Account/Trade Approvals: dead code — never mounted").
 */
export default function TradeHistoryPage() {
  redirect('/dashboard?tab=history')
}
