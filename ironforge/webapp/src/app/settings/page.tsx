import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

/**
 * /settings is superseded by the /dashboard Settings tab (dev-handoff §6: a
 * single tabbed page). SettingsBody (automation toggles, alerts, and the
 * billing/brokerage/security links) now renders inline there; redirecting
 * rather than deleting keeps every existing link and bookmark to /settings
 * working.
 */
export default function SettingsPage() {
  redirect('/dashboard?tab=settings')
}
