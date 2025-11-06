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
      <body className="bg-background-deep text-text-primary font-sans">
        {children}
      </body>
    </html>
  )
}
