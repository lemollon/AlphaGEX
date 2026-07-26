import SupportClient from './SupportClient'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: 'Support · IronForge',
  description: 'Chat with Sparky, the IronForge support assistant.',
}

export default function SupportPage() {
  return <SupportClient />
}
