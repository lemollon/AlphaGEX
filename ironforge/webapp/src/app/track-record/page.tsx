import { permanentRedirect } from 'next/navigation'

/**
 * RETIRED — superseded by /bot-ledger (2026-07-27).
 *
 * Both pages published a public Spark record, but from different row sets:
 * this one deliberately included every `account_type` (see the header comment
 * on the now-deleted TrackRecordClient), while the Bot Ledger reproduces the
 * operator console's filter. Two public proof surfaces disagreeing about the
 * same bot is a credibility problem, so there is now one.
 *
 * A 308 rather than a delete: the URL is linked externally and from other
 * pages, and a permanent redirect carries its SEO value across instead of
 * 404ing it away. The route file stays so the surface classification in
 * surface.ts continues to describe a real route.
 */
export const dynamic = 'force-dynamic'

export default function TrackRecordPage() {
  permanentRedirect('/bot-ledger')
}
