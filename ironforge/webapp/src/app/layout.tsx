import type { Metadata } from 'next'
import './globals.css'
import Shell from '@/components/Shell'

export const metadata: Metadata = {
  title: 'IronForge',
  description: 'FLAME vs SPARK Iron Condor Paper Trading on Render',
  icons: { icon: '/favicon.svg' },
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
