import { permanentRedirect } from 'next/navigation'

/**
 * RETIRED — pointed at /bot-ledger until UAT-003 removed that page too
 * (2026-07-31); both retired URLs now 308 home. The redirect (not a 404)
 * preserves external links; the route file stays so the surface
 * classification in surface.ts continues to describe a real route.
 */
export const dynamic = 'force-dynamic'

export default function TrackRecordPage() {
  permanentRedirect('/')
}
