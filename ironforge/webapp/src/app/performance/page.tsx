import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

/**
 * /performance is superseded by the /dashboard Overview tab (dev-handoff §6:
 * a single tabbed page, not five separate routes) — the Overview tab now
 * carries everything this page used to (plus the 5/21-trading-day KPIs, P&L
 * range chart, daily-results bars and agent lead tiles the gap audit flagged
 * missing here). Redirecting rather than deleting keeps every existing link
 * and bookmark to /performance working.
 */
export default function PerformancePage() {
  redirect('/dashboard?tab=overview')
}
