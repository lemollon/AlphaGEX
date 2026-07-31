import { permanentRedirect } from 'next/navigation'

/**
 * RETIRED (UAT-003, 2026-07-31) — the Bot Ledger page and its access points were
 * removed from the product. A 308 rather than a 404: the URL was linked from the
 * homepage hero, nav, footer, and external shares. The shared ledger data layer
 * (lib/bot-ledger) stays — the homepage hero still renders from it. The route file
 * stays so the surface classification in surface.ts describes a real route.
 */
export const dynamic = 'force-dynamic'

export default function BotLedgerPage() {
  permanentRedirect('/')
}
