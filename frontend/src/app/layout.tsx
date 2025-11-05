import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AlphaGEX - Professional Options Intelligence',
  description: 'Advanced GEX analysis and autonomous trading platform',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans bg-background-deep text-text-primary">
        {children}
      </body>
    </html>
  )
}
