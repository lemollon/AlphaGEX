import type { Metadata } from 'next'
import './globals.css'
import Shell from '@/components/Shell'

export const metadata: Metadata = {
  title: 'IronForge',
  description:
    'Autonomous, defined-risk options bots for SPY that run in your own Tradier account — every position has a capped max loss, sized and exited by rule. Join the IronForge early-access waitlist.',
  icons: { icon: '/ironforge-mark.png' },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans antialiased min-h-screen">
        <Shell>{children}</Shell>
      </body>
    </html>
  )
}
