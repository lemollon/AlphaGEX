import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

/**
 * /community is superseded by the /dashboard Community tab (dev-handoff §6:
 * a single tabbed page). CommunityBody (the extracted feed component) now
 * renders inline there; redirecting rather than deleting keeps every
 * existing link and bookmark to /community working.
 */
export default function CommunityPage() {
  redirect('/dashboard?tab=community')
}
