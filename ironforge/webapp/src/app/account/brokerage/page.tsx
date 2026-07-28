import type { Metadata } from 'next'
import BrokerageSettingsClient from './BrokerageSettingsClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Brokerage — IronForge',
  description: 'The brokerage accounts linked to your IronForge strategies.',
}

/**
 * /account/brokerage — the SETTINGS view of a customer's brokerage links.
 *
 * The sidebar's "Brokerage Settings" pointed at /onboarding/brokerage, which is a funnel
 * step, not a settings page: no app chrome, "Connect your brokerage" regardless of what
 * you already had, no view of existing links, a "Skip for now" that makes no sense
 * outside signup, and an exit to /onboarding/complete. One page was doing two jobs and
 * doing the second one badly.
 *
 * Connecting still hands back to the funnel step — that flow owns the OAuth handshake,
 * and duplicating it is how the two would drift apart.
 */
export default function BrokerageSettingsPage() {
  return <BrokerageSettingsClient />
}
