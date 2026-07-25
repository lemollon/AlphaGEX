import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

/**
 * The Home dashboard was merged into Performance (operator, 2026-07-27): its
 * weekly/monthly income KPIs already live on /performance, so a standalone Home
 * page was redundant. This route now redirects there, so old links, bookmarks
 * and `?next=/home` impersonation targets keep working.
 */
export default function HomePage() {
  redirect('/performance')
}
