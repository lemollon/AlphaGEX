import type { Metadata } from 'next'
import TrackRecordClient from './TrackRecordClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Track record — IronForge',
  description:
    'Every trade the IronForge bots have closed: realised profit and loss on live '
    + 'market data, with each strategy labelled real-money or simulated.',
}

export default function TrackRecordPage() {
  return <TrackRecordClient />
}
