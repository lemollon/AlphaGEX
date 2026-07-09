import type { Metadata } from 'next'
import CommunityClient from './CommunityClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Forge Community — IronForge',
  description: 'A place for disciplined traders to learn, share ideas, and grow together.',
}

export default function CommunityPage() {
  return <CommunityClient />
}
