import type { Metadata } from 'next'
import { Inter, Oswald } from 'next/font/google'
import './globals.css'
import Shell from '@/components/Shell'

// Single source of truth for site typography.
// Inter = body/UI sans (--font-sans, also Tailwind's font-sans).
// Oswald = condensed industrial display face for headings (--font-display / font-display).
const inter = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-sans' })
const oswald = Oswald({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-display',
})

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
    <html lang="en" className={`dark ${inter.variable} ${oswald.variable}`}>
      <body className="font-sans antialiased min-h-screen">
        <Shell>{children}</Shell>
      </body>
    </html>
  )
}
