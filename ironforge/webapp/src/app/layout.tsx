import type { Metadata } from 'next'
import './globals.css'
import ClientNav from '@/components/ClientNav'

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
        <ClientNav />
        <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  )
}
