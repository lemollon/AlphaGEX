import type { Metadata } from 'next'
import HomeNav from '../_home/HomeNav'
import HomeFooter from '../_home/HomeFooter'
import TrackRecordClient from './TrackRecordClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Track record — IronForge',
  description:
    'Every trade the IronForge bots have closed: realised profit and loss on live '
    + 'market data, with each strategy labelled real-money or simulated.',
}

export default function TrackRecordPage() {
  // Own chrome, like every other marketing screen (Shell.tsx treats this route as
  // standalone so the OPERATOR nav never renders on a page built for prospects).
  return (
    <div className="min-h-screen bg-forge-bg">
      <HomeNav active="track-record" />
      <TrackRecordClient />
      <HomeFooter />
    </div>
  )
}
